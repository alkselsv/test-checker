import os
import subprocess
import json
import git
import logging
from typing import List, Dict
from datetime import datetime
import argparse

def main():
    parser = argparse.ArgumentParser(description='Test Runner for JavaScript repositories')
    parser.add_argument('repos_file', help='File containing repository URLs')
    parser.add_argument(
        '--log-level',
        default='INFO',
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

    def run_tests(self, repo_path: str) -> Dict:
        """
        Запуск тестов в каждой директории
        """
        self.logger.info(f"Running tests in {repo_path}")
        results = {}
        
        dirs = [d for d in os.listdir(repo_path) 
                if os.path.isdir(os.path.join(repo_path, d)) and d.isdigit()]
        
        self.logger.info(f"Found {len(dirs)} test directories")
        
        for dir_name in sorted(dirs, key=int):
            dir_path = os.path.join(repo_path, dir_name)
            self.logger.info(f"Processing directory {dir_name}")
            
            try:
                self.logger.debug(f"Running npm install in {dir_path}")
                install_process = subprocess.run(
                    ['npm', 'install'], 
                    cwd=dir_path, 
                    check=True, 
                    capture_output=True,
                    text=True
                )
                
                self.logger.debug(f"Running npm test in {dir_path}")
                test_process = subprocess.run(
                    ['npm', 'test'], 
                    cwd=dir_path, 
                    capture_output=True,
                    text=True
                )
                
                # Проверяем наличие ошибок
                if test_process.returncode != 0:
                    error_msg = f"Test failed: {test_process.stderr}"
                    self.logger.error(error_msg)
                    results[dir_name] = 0  # Сохраняем 0 вместо сообщения об ошибке
                    continue
                    
                # Объединяем stdout и stderr для полного вывода
                full_output = test_process.stdout + test_process.stderr
                self.logger.debug(f"Test output: {full_output}")
                
                passed_tests = self._parse_test_output(full_output)
                results[dir_name] = passed_tests
                self.logger.info(f"Directory {dir_name}: {passed_tests} tests passed")
                
            except subprocess.CalledProcessError as e:
                error_msg = f"Error: {str(e)}"
                self.logger.error(f"Error in directory {dir_name}: {error_msg}")
                results[dir_name] = 0  # Сохраняем 0 вместо сообщения об ошибке
                
        return results

    def _parse_test_output(self, output: str) -> int:
        """
        Парсинг вывода тестов в формате 'Test Suites: X passed, Y total'
        """
        self.logger.debug("Parsing test output")
        self.logger.debug(f"Raw output: {output}")
        
        try:
            import re
            # Паттерн для удаления ANSI escape-последовательностей
            ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            
            for line in output.split('\n'):
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

        for repo_url in self.repos:
            try:
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

if __name__ == '__main__':
    main()