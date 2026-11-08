"""Проверка решений учеников на тестах учителя.

Сам запуск кода с ограничениями — в sandbox.py.
"""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import soupsieve
from bs4 import BeautifulSoup
from django.conf import settings

from . import sandbox
from .models import Submission, Task

MAX_SHOWN_OUTPUT = 2000


class CompileError(Exception):
    pass


def calculate_score(passed, total):
    """Балл от 1 до 10: за любую отправку минимум 1, за все тесты — 10."""
    if total == 0:
        return 0
    return max(1, round(passed / total * 10))


def _normalize(text):
    # Пробелы в конце строк и пустые строки в конце не считаются ошибкой
    return '\n'.join(line.rstrip() for line in text.strip().splitlines())


def _prepare_python(code, workdir):
    (workdir / 'solution.py').write_text(code, encoding='utf-8')
    # -X utf8: иначе на Windows кириллица в print() уходит в cp1251
    return [*settings.JUDGE_PYTHON_COMMAND, f'{sandbox.box_path(workdir)}/solution.py']


def find_cpp_compiler():
    """g++ из PATH, а на Windows ещё и из установки через winget (PATH обновляется только после перезапуска)."""
    compiler = shutil.which(settings.CPP_COMPILER)
    if compiler is None and os.name == 'nt':
        packages = Path(os.environ.get('LOCALAPPDATA', '')) / 'Microsoft' / 'WinGet' / 'Packages'
        found = sorted(packages.glob('BrechtSanders.WinLibs*/mingw*/bin/g++.exe'))
        compiler = str(found[-1]) if found else None
    return compiler


def _prepare_cpp(code, workdir):
    compiler = find_cpp_compiler()
    if compiler is None:
        raise CompileError('Компилятор C++ не установлен на сервере. Сообщите учителю.')
    (workdir / 'main.cpp').write_text(code, encoding='utf-8')
    box = sandbox.box_path(workdir)
    command = [compiler, '-std=c++17', '-O2', '-o', f'{box}/main.exe', f'{box}/main.cpp']
    if os.name == 'nt':
        command.append('-static')  # иначе программе нужны DLL от MinGW
    try:
        proc = sandbox.run(command, workdir, timeout=settings.JUDGE_COMPILE_TIMEOUT_SECONDS,
                           memory_mb=settings.JUDGE_COMPILE_MEMORY_MB)
    except subprocess.TimeoutExpired:
        raise CompileError('Компиляция заняла слишком много времени')
    except OSError as error:
        raise CompileError(_launch_error_message(error))
    if proc.returncode != 0:
        raise CompileError(proc.stderr.replace(box, '')[-MAX_SHOWN_OUTPUT:])
    return [f'{box}/main.exe']


PREPARERS = {
    Task.Language.PYTHON: _prepare_python,
    Task.Language.CPP: _prepare_cpp,
}


def _execute(language, code, inputs):
    """Компилирует (если нужно) и запускает программу на каждом входе.

    Возвращает список: CompletedProcess или None, если программа не уложилась во время.
    """
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        command = PREPARERS[language](code, workdir)
        runs = []
        for input_data in inputs:
            try:
                runs.append(sandbox.run(command, workdir, input_data))
            except subprocess.TimeoutExpired:
                runs.append(None)
            except OSError as error:
                raise CompileError(_launch_error_message(error))
        return runs


def _launch_error_message(error):
    # 4551: Smart App Control в Windows 11 не даёт запускать неподписанные программы, в том числе
    # только что скомпилированные решения на C++
    if getattr(error, 'winerror', None) == 4551:
        return ('Windows не разрешил запустить скомпилированную программу (Smart App Control). '
                'На компьютере с сервером C++ работает только при выключенном Smart App Control. Сообщите учителю.')
    return f'Не удалось запустить программу: {error}'


def _describe_run(proc, expected=None):
    if proc is None:
        return {'verdict': 'Превышено время'}
    result = {'output': proc.stdout[:MAX_SHOWN_OUTPUT]}
    if proc.returncode != 0:
        result['verdict'] = 'Ошибка выполнения'
        result['error'] = proc.stderr[-MAX_SHOWN_OUTPUT:] or f'Код завершения {proc.returncode}'
    elif expected is None:
        result['verdict'] = 'Выполнено'
    elif _normalize(proc.stdout) == _normalize(expected):
        result['verdict'] = 'OK'
    else:
        result['verdict'] = 'Неверный ответ'
    return result


def _check_html(code, tests):
    """Каждый тест — правило: «есть элемент по CSS-селектору», и если задан текст — «он содержит этот текст»."""
    soup = BeautifulSoup(code, 'html.parser')
    results = []
    for test in tests:
        selector = test.input_data.strip()
        expected_text = test.expected_output.strip()
        try:
            elements = soup.select(selector)
        except soupsieve.SelectorSyntaxError:
            results.append({'verdict': 'Ошибка в правиле — сообщите учителю'})
            continue
        if not elements:
            verdict = 'Элемент не найден'
        elif expected_text and not any(expected_text in el.get_text(' ', strip=True) for el in elements):
            verdict = 'Неверный текст'
        else:
            verdict = 'OK'
        results.append({'verdict': verdict})
    return results


def judge(task, code):
    """Проверяет код на всех тестах задания и возвращает данные для Submission."""
    tests = list(task.tests.all())
    total = len(tests)
    try:
        if task.language == Task.Language.HTML:
            results = _check_html(code, tests)
        else:
            runs = _execute(task.language, code, [test.input_data for test in tests])
            results = [_describe_run(proc, test.expected_output) for proc, test in zip(runs, tests)]
    except CompileError as error:
        return {'status': Submission.Status.ERROR, 'passed': 0, 'total': total,
                'score': calculate_score(0, total),
                'results': [{'verdict': 'Ошибка компиляции', 'error': str(error)}]}

    for number, (test, result) in enumerate(zip(tests, results), start=1):
        result.update(number=number, hidden=test.is_hidden)
        if test.is_hidden:
            # Вывод и ошибки на скрытом тесте могут подсказать ответ
            result.pop('output', None)
            result.pop('error', None)
        else:
            result['input'] = test.input_data
            result['expected'] = test.expected_output

    passed = sum(result['verdict'] == 'OK' for result in results)
    if total and passed == total:
        status = Submission.Status.ACCEPTED
    elif passed:
        status = Submission.Status.PARTIAL
    else:
        status = Submission.Status.FAILED
    return {'status': status, 'passed': passed, 'total': total,
            'score': calculate_score(passed, total), 'results': results}


def run_once(task, code, input_data):
    """Кнопка «Запустить»: один запуск на вводе ученика, без оценки."""
    if task.language not in PREPARERS:
        return {'verdict': 'Для этого языка запуск не нужен — смотрите просмотр страницы'}
    try:
        [proc] = _execute(task.language, code, [input_data])
    except CompileError as error:
        return {'verdict': 'Ошибка компиляции', 'error': str(error)}
    return _describe_run(proc)


def validate_html_rule(selector):
    """Возвращает текст ошибки, если CSS-селектор учителя некорректен."""
    if not selector.strip():
        return 'Укажите CSS-селектор, например h1 или form input[type=email]'
    try:
        soupsieve.compile(selector.strip())
    except soupsieve.SelectorSyntaxError:
        return 'Некорректный CSS-селектор'
    return None
