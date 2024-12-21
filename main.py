import os
import re
import subprocess
from flask import Flask, request, jsonify, render_template, session

# Папки для загрузки файлов и хранения результатов
UPLOAD_FOLDER = './uploads'
COMPILE_FOLDER = './compiled'
RESULTS_FILE = './results.txt'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(COMPILE_FOLDER, exist_ok=True)

app = Flask(__name__)


# Главная страница
@app.route('/')
def index():
    return render_template('index.html')


# Функция для получения среза данных
def get_test_input_slice(file_path, test_number):
    """
    Считывает входные данные из файла и возвращает срез.

    :param file_path: Путь к файлу с входными данными.
    :param test_number: Номер текущего теста.
    :return: Срез входных данных (строка).
    """
    try:
        with open(file_path, "r") as file:
            # Считываем все строки и убираем лишние пробелы
            test_data = file.read().strip()

            # Определяем размер среза: по умолчанию 4 строки, но для третьего запуска — 9 строк
            if test_number == 2:  # Третий запуск
                slice_size = 12
            elif test_number == 3:
                slice_size = 7
            else:
                slice_size = 4

            # Вычисляем начальный и конечный индексы среза
            start_index = sum(4 if i not in [2, 3] else (12 if i == 2 else 7) for i in range(test_number))
            end_index = start_index + slice_size
            # Берём только нужный срез
            sliced_data = "\n".join(test_data[start_index:end_index])
            return sliced_data
    except FileNotFoundError:
        raise FileNotFoundError(f"Файл {file_path} не найден")


# Функция для сохранения результата в файл
def save_result_to_file(result, file_path):
    """
    Сохраняет результат выполнения программы в файл.

    :param result: Результат выполнения программы (строка).
    :param file_path: Путь к файлу для сохранения.
    """
    with open(file_path, "a") as file:
        file.write(result + "\n")

score = 0

@app.before_request
def reset_score():
    global score
    score = 0

# Функция для выполнения всех тестов
def run_tests(file_path):
    # Проверяем наличие g++
    if subprocess.run("g++ --version", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode != 0:
        raise EnvironmentError("Компилятор g++ не установлен или недоступен в PATH.")

    # Компиляция файла
    executable_path = os.path.join(COMPILE_FOLDER, "program.out")
    compile_command = f"g++ {file_path} -o {executable_path}"
    try:
        subprocess.run(compile_command, shell=True, check=True, stderr=subprocess.PIPE)
    except subprocess.CalledProcessError as e:
        return {"status": "Ошибка", "error": "Ошибка компиляции", "details": e.stderr.decode('utf-8', errors='replace')}

    # Выполняем тесты
    results = []
    global score
    for test_number in range(4):  # Четыре запуска: c = 0, 1, 2, 3
        try:
            # Читаем данные для текущего теста
            test_input = get_test_input_slice("test_input.txt", test_number)

            # Выполнение программы с входными данными
            result = subprocess.run(
                executable_path,
                input=test_input.encode(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5
            )
            # Обработка вывода программы
            try:
                actual_output = result.stdout.decode('utf-8', errors='replace').strip()

                # Регулярное выражение: извлекаем число в конце строки (если есть)
                match = re.search(r'\d+$', actual_output)  # Ищем любое число в конце строки
                if match:
                    extracted_output = match.group()
                else:
                    extracted_output = "Ответ не найден"
            except UnicodeDecodeError as e:
                return jsonify({"status": "ФАЙЛ", "error": f"Ошибка декодирования вывода: {str(e)}"}), 400

            # Сохраняем результат выполнения программы
            save_result_to_file(extracted_output, RESULTS_FILE)

            # Сравниваем с ожидаемым результатом
            with open("test_output.txt", "r") as expected_file:
                expected_outputs = expected_file.read().strip().splitlines()
            
            if test_number < len(expected_outputs):
                expected_output = expected_outputs[test_number]
                if extracted_output == expected_output:
                    score += 1
                    results.append({
                        "test_number": test_number + 1,
                        "status": "УСПЕХ",
                        "extracted_output": extracted_output,
                        "expected_output": expected_output
                    })
                else:
                    score += 0
                    results.append({
                        "test_number": test_number + 1,
                        "status": "НЕУДАЧА",
                        "extracted_output": extracted_output,
                        "expected_output": expected_output
                    })
                         
        except FileNotFoundError as e:
            results.append({"test_number": test_number + 1, "status": "Ошибка", "error": str(e)})
        except subprocess.TimeoutExpired:
            results.append({"test_number": test_number + 1, "status": "Ошибка", "error": "Тест превысил время выполнения"})
        except Exception as e:
            results.append({"test_number": test_number + 1, "status": "Ошибка", "error": str(e)})

    return results


# Маршрут для загрузки файлов
@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({"status": "Ошибка", "error": "Файл не загружен"}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "Ошибка", "error": "Файл не выбран"}), 400
    if not file.filename.endswith(".cpp"):
        return jsonify({"status": "Ошибка", "error": "Файл должен быть .cpp"}), 400

    # Сохраняем файл
    file_path = os.path.join(UPLOAD_FOLDER, file.filename)
    file.save(file_path)
    
    # Запуск тестов
    try:
        test_results = run_tests(file_path)
        return jsonify({"status": "УСПЕХ", "results": test_results,"score": score}), 200
    except Exception as e:
        return jsonify({"status": "Ошибка", "error": str(e)}), 500

# Запуск приложения
if __name__ == '__main__':
    app.run(debug=True)

