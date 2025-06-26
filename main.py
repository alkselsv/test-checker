import os
import subprocess
import json
import git
import logging
from typing import List, Dict
from datetime import datetime
import argparse
import re
import shutil

# Настройка глобального логгера
if not os.path.exists('logs'):
    os.makedirs('logs')
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/global.log", mode='a', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("GlobalLogger")

def main():
    parser = argparse.ArgumentParser(description='Test Runner for JavaScript repositories')
    parser.add_argument('repos_file', help='File containing repository URLs')
    parser.add_argument(
        '--log-level',
        default='DEBUG',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help='Set the logging level'
    )
    args = parser.parse_args()
    
    runner = TestRunner(args.repos_file, log_level=args.log_level)
    runner.run_all()

class TestRunner:
    def __init__(self, repos_file: str, log_level: str = 'INFO'):
        """
        Инициализация с файлом репозиториев и уровнем логирования
        """
        self.log_level = getattr(logging, log_level.upper())
        self._setup_logging()
        self.logger.info("Initializing TestRunner")
        self.repos = self._read_repos(repos_file)
        self.results = {}

    def _setup_logging(self):
        """
        Настройка логирования с указанным уровнем
        """
        if not os.path.exists('logs'):
            os.makedirs('logs')

        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        self.logger = logging.getLogger('TestRunner')
        self.logger.setLevel(self.log_level)

        log_file = f'logs/test_runner_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log'
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        file_handler.setLevel(self.log_level)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(self.log_level)

        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

    def _read_repos(self, file_path: str) -> List[str]:
        """
        Чтение списка репозиториев из файла
        """
        self.logger.info(f"Reading repositories from {file_path}")
        try:
            with open(file_path, 'r') as f:
                repos = [line.strip() for line in f if line.strip()]
            self.logger.info(f"Found {len(repos)} repositories")
            return repos
        except Exception as e:
            self.logger.error(f"Error reading repos file: {str(e)}")
            raise

    def clone_repo(self, repo_url: str, temp_dir: str) -> str:
        """
        Клонирование репозитория с уникальным именем директории
        """
        self.logger.info(f"Cloning repository: {repo_url}")
        
        # Извлекаем имя пользователя и репозитория из URL
        parts = repo_url.split('/')
        user_name = parts[-2]
        repo_name = parts[-1].replace('.git', '')
        
        # Создаем уникальное имя директории
        unique_repo_path = os.path.join(temp_dir, f"{user_name}_{repo_name}")
        
        try:
            if not os.path.exists(unique_repo_path):
                self.logger.debug(f"Cloning to {unique_repo_path}")
                git.Repo.clone_from(repo_url, unique_repo_path)
                self.logger.info(f"Successfully cloned {repo_url}")
            else:
                self.logger.info(f"Repository already exists at {unique_repo_path}")
            return unique_repo_path
        except Exception as e:
            self.logger.error(f"Error cloning repository {repo_url}: {str(e)}")
            raise

    def _parse_test_output(self, output: str) -> int:
        """
        Парсинг вывода тестов в формате 'Test Suites: X passed, Y total'
        или в формате '1 passed'
        """
        self.logger.debug("Parsing test output")
        self.logger.debug(f"Raw output: {output}")
        
        try:
            # Паттерн для удаления ANSI escape-последовательностей
            ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            
            for line in output.split('\n'):
                # Проверяем формат Test Suites
                if 'Test Suites:' in line:
                    self.logger.debug(f"Found line with test results: {line}")
                    # Очищаем строку от ANSI escape-последовательностей
                    clean_line = ansi_escape.sub('', line)
                    self.logger.debug(f"Clean line: {clean_line}")
                    # Берем часть строки после "Test Suites:"
                    parts = clean_line.split('Test Suites:')[1]
                    # Извлекаем первое число из строки
                    passed_tests = int(parts.split('passed')[0].strip())
                    self.logger.debug(f"Found {passed_tests} passed test suites")
                    return passed_tests
                
                # Проверяем альтернативный формат "X passed"
                if 'passed' in line:
                    clean_line = ansi_escape.sub('', line)
                    self.logger.debug(f"Found alternative passed line: {clean_line}")
                    # Ищем число перед словом "passed"
                    match = re.search(r'(\d+)\s+passed', clean_line)
                    if match:
                        passed_tests = int(match.group(1))
                        self.logger.debug(f"Found {passed_tests} passed tests")
                        return passed_tests
                    
        except Exception as e:
            self.logger.error(f"Error parsing test output: {str(e)}")
            self.logger.error(f"Exception details:", exc_info=True)
        return 0

    def run_all(self, temp_dir: str = 'temp_repos'):
        """
        Запуск проверки всех репозиториев
        """
        self.logger.info("Starting test run for all repositories")
        
        if not os.path.exists(temp_dir):
            self.logger.debug(f"Creating temporary directory: {temp_dir}")
            os.makedirs(temp_dir)

        # Проверяем, пуст ли файл repos_file
        if not self.repos:
            self.logger.info("No repositories found in repos_file, checking temp_repos directory.")
            # Получаем список всех репозиториев в temp_repos
            self.repos = [os.path.join(temp_dir, d) for d in os.listdir(temp_dir) 
                          if os.path.isdir(os.path.join(temp_dir, d))]

        for repo_url in self.repos:
            try:
                # Если это путь к локальному репозиторию, просто запускаем тесты
                if os.path.isdir(repo_url):
                    self.results[repo_url] = self.run_tests(repo_url)
                else:
                    repo_path = self.clone_repo(repo_url, temp_dir)
                    self.results[repo_url] = self.run_tests(repo_path)
            except Exception as e:
                error_msg = f"Error: {str(e)}"
                self.logger.error(f"Failed to process repository {repo_url}: {error_msg}")
                self.results[repo_url] = error_msg

        self.save_results()
        self.logger.info("Completed test run for all repositories")

    def save_results(self, output_file: str = 'test_results.json'):
        """
        Сохранение результатов в JSON файл с добавлением статистики
        """
        self.logger.info(f"Saving results to {output_file}")
        try:
            formatted_results = {}
            for repo_url, test_results in self.results.items():
                if isinstance(test_results, dict):  # Если это словарь с результатами тестов
                    total_tests = len(test_results)
                    passed_tests = sum(1 for result in test_results.values() 
                                     if isinstance(result, int) and result > 0)
                    
                    formatted_results[repo_url] = {
                        'details': test_results,
                        'statistics': {
                            'total_directories': total_tests,
                            'successful_tests': passed_tests
                        }
                    }
                else:  # Если произошла ошибка при обработке репозитория
                    formatted_results[repo_url] = {
                        'details': str(test_results),
                        'statistics': {
                            'total_directories': 0,
                            'successful_tests': 0
                        }
                    }
            
            with open(output_file, 'w') as f:
                json.dump(formatted_results, f, indent=2)
            self.logger.info("Results saved successfully")
        except Exception as e:
            self.logger.error(f"Error saving results: {str(e)}")
            raise

def parse_deadlines(deadlines_file: str) -> dict:
    """
    Читает файл дедлайнов и возвращает словарь:
    { 'solutions02.txt': {'soft': datetime, 'hard': datetime} }
    """
    deadlines = {}
    with open(deadlines_file, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 7:
                fname = parts[0]
                soft = ' '.join(parts[1:5])
                hard = ' '.join(parts[5:9])
                deadlines[fname] = {
                    'soft': datetime.strptime(soft, '%B %d, %Y %H:%M'),
                    'hard': datetime.strptime(hard, '%B %d, %Y %H:%M')
                }
    return deadlines


def get_last_commit_date(repo_path: str) -> datetime:
    """
    Возвращает дату последнего коммита в репозитории
    """
    repo = git.Repo(repo_path)
    commit = next(repo.iter_commits(), None)
    if commit:
        return datetime.fromtimestamp(commit.committed_date)
    return None


def check_deadline(commit_date: datetime, soft: datetime, hard: datetime) -> str:
    if commit_date <= soft:
        return 'до мягкого'
    elif commit_date <= hard:
        return 'до жёсткого'
    else:
        return 'дедлайн превышен'


def process_assignment(solutions_file: str, deadlines: dict, temp_dir: str = 'temp_repos', results_dir: str = 'results'):
    """
    Обрабатывает одно задание: запускает тесты, формирует resultsXX.tsv
    """
    # Очищаем временную директорию перед проверкой задания
    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
    os.makedirs(temp_dir)
    if not os.path.exists(results_dir):
        os.makedirs(results_dir)
    assignment = os.path.basename(solutions_file)
    match = re.search(r'\d+', assignment)
    num = match.group().zfill(2) if match else '00'
    result_file = os.path.join(results_dir, f"results{num}.tsv")
    deadline = deadlines.get(assignment)
    if not deadline:
        logger.warning(f"No deadline for {assignment}")
        print(f"No deadline for {assignment}")
        return
    results_lines = []
    with open(solutions_file, 'r') as f:
        for line in f:
            if not line.strip():
                continue
            name, repo_url = line.strip().split('\t')
            try:
                logger.info(f"Processing student: {name}")
                # Клонируем или обновляем репозиторий
                parts = repo_url.split('/')
                user_name = parts[-2]
                repo_name = parts[-1].replace('.git', '')
                unique_repo_path = os.path.join(temp_dir, f"{user_name}_{repo_name}")
                if not os.path.exists(unique_repo_path):
                    logger.info(f"Cloning repo {repo_url} to {unique_repo_path}")
                    git.Repo.clone_from(repo_url, unique_repo_path)
                else:
                    logger.info(f"Pulling latest changes for {repo_url}")
                    repo = git.Repo(unique_repo_path)
                    repo.remotes.origin.pull()
                # Запуск тестов
                test_results = run_tests(unique_repo_path)
                passed = sum(v[0] for v in test_results.values())
                total = sum(v[1] for v in test_results.values())
                failed = total - passed
                # Дата последнего коммита
                commit_date = get_last_commit_date(unique_repo_path)
                commit_date_str = commit_date.strftime('%Y-%m-%d %H:%M') if commit_date else '-'
                # Проверка дедлайна
                deadline_status = check_deadline(commit_date, deadline['soft'], deadline['hard']) if commit_date else '-'
                # Сохраняем строку в список
                results_lines.append((name, f"{name}\t{passed}\t{failed}\t{commit_date_str}\t{deadline_status}\n"))
                logger.info(f"Result for {name}: {passed} passed, {failed} failed, commit {commit_date_str}, deadline {deadline_status}")
            except Exception as e:
                logger.error(f"Error processing {name}: {str(e)}")
                results_lines.append((name, f"{name}\tERROR\tERROR\t-\t-\n"))
    # Сортируем по ФИО
    results_lines.sort(key=lambda x: x[0])
    # Записываем в файл
    with open(result_file, 'w') as out:
        for _, line in results_lines:
            out.write(line)

def parse_test_output(output: str) -> tuple:
    """
    Парсит вывод тестов и возвращает (passed, total) по строке 'Test Suites: X passed, Y total'.
    Если не найдено — возвращает (0, 0).
    """
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    try:
        for line in output.split('\n'):
            if 'Test Suites:' in line:
                clean_line = ansi_escape.sub('', line)
                # Пример: 'Test Suites: 7 passed, 7 total'
                match = re.search(r'Test Suites:\s*(\d+) passed, (\d+) total', clean_line)
                if match:
                    passed = int(match.group(1))
                    total = int(match.group(2))
                    logger.info(f"Test Suites parsed: {passed} passed, {total} total")
                    return passed, total
            if 'passed' in line:
                clean_line = ansi_escape.sub('', line)
                match = re.search(r'(\d+)\s+passed', clean_line)
                if match:
                    passed = int(match.group(1))
                    logger.info(f"Alternative passed line parsed: {passed} passed")
                    return passed, passed
    except Exception as e:
        logger.error(f"Error parsing test output: {str(e)}")
    return 0, 0

def run_tests(repo_path: str) -> dict:
    """
    Запуск тестов в каждой директории с поддержкой JS и Python проектов,
    либо из корня, если нет числовых директорий.
    """
    results = {}
    dirs = [d for d in os.listdir(repo_path)
            if os.path.isdir(os.path.join(repo_path, d)) and d.isdigit()]
    if dirs:
        logger.info(f"Found {len(dirs)} test directories in {repo_path}")
        for dir_name in sorted(dirs, key=int):
            dir_path = os.path.join(repo_path, dir_name)
            logger.info(f"Processing directory {dir_name}")
            try:
                is_js_project = os.path.exists(os.path.join(dir_path, 'package.json'))
                is_python_project = os.path.exists(os.path.join(dir_path, 'pyproject.toml'))
                if is_js_project:
                    install_cmd = ['npm', 'install']
                    test_cmd = ['npm', 'test']
                elif is_python_project:
                    install_cmd = ['poetry', 'install']
                    test_cmd = ['poetry', 'run', 'pytest']
                else:
                    logger.warning(f"Unknown project type in {dir_path}")
                    results[dir_name] = (0, 0)
                    continue
                logger.info(f"Running install command: {' '.join(install_cmd)}")
                subprocess.run(install_cmd, cwd=dir_path, check=True, capture_output=True, text=True)
                logger.info(f"Running test command: {' '.join(test_cmd)}")
                test_process = subprocess.run(test_cmd, cwd=dir_path, capture_output=True, text=True)
                if test_process.returncode != 0:
                    logger.error(f"Test failed in {dir_path}: {test_process.stderr}")
                    results[dir_name] = (0, 0)
                    continue
                full_output = test_process.stdout + test_process.stderr
                passed, total = parse_test_output(full_output)
                results[dir_name] = (passed, total)
                logger.info(f"Directory {dir_name}: {passed} passed, {total} total")
            except Exception as e:
                logger.error(f"Error in directory {dir_name}: {str(e)}")
                results[dir_name] = (0, 0)
    else:
        logger.info(f"No digit-named directories in {repo_path}, running tests from root.")
        try:
            is_js_project = os.path.exists(os.path.join(repo_path, 'package.json'))
            is_python_project = os.path.exists(os.path.join(repo_path, 'pyproject.toml'))
            if is_js_project:
                install_cmd = ['npm', 'install']
                test_cmd = ['npm', 'test']
            elif is_python_project:
                install_cmd = ['poetry', 'install']
                test_cmd = ['poetry', 'run', 'pytest']
            else:
                logger.warning(f"Unknown project type in {repo_path}")
                results['root'] = (0, 0)
                return results
            logger.info(f"Running install command: {' '.join(install_cmd)}")
            subprocess.run(install_cmd, cwd=repo_path, check=True, capture_output=True, text=True)
            logger.info(f"Running test command: {' '.join(test_cmd)}")
            test_process = subprocess.run(test_cmd, cwd=repo_path, capture_output=True, text=True)
            if test_process.returncode != 0:
                logger.error(f"Test failed in {repo_path}: {test_process.stderr}")
                results['root'] = (0, 0)
            else:
                full_output = test_process.stdout + test_process.stderr
                passed, total = parse_test_output(full_output)
                results['root'] = (passed, total)
                logger.info(f"Repo {repo_path}: {passed} passed, {total} total")
        except Exception as e:
            logger.error(f"Error in repo {repo_path}: {str(e)}")
            results['root'] = (0, 0)
    return results

if __name__ == '__main__':
    # Автоматически обработать все solutionsXX.txt строго в порядке из deadlines.txt
    deadlines = parse_deadlines('deadlines.txt')
    solutions_dir = 'solutions'
    results_dir = 'results'
    for fname in deadlines.keys():
        solutions_path = os.path.join(solutions_dir, fname)
        match = re.search(r'\d+', fname)
        num = match.group().zfill(2) if match else '00'
        result_file = os.path.join(results_dir, f"results{num}.tsv")
        if os.path.exists(result_file):
            logger.info(f"Results already exist for {fname}, skipping.")
            continue
        if os.path.exists(solutions_path):
            process_assignment(solutions_path, deadlines)