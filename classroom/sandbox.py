"""Запуск чужого кода с ограничениями.

На Linux процесс получает лимиты памяти, процессорного времени и размера файлов.
Если JUDGE_SANDBOX = 'bwrap' (нужен пакет bubblewrap), процесс дополнительно запускается
в изолированном окружении: без сети, без доступа к файлам сайта и базе данных —
видны только системные программы (/usr) и папка с решением (/box).

На Windows (разработка) работает только ограничение по времени.
"""
import os
import signal
import subprocess
import tempfile

from django.conf import settings

IS_POSIX = os.name == 'posix'
MAX_OUTPUT_BYTES = 64 * 1024
MAX_FILE_BYTES = 16 * 1024 * 1024


def box_path(workdir):
    """Путь к папке решения так, как его видит запущенная программа."""
    return '/box' if settings.JUDGE_SANDBOX == 'bwrap' else str(workdir)


def _bwrap_prefix(workdir):
    return [
        'bwrap', '--unshare-all', '--die-with-parent', '--new-session',
        '--ro-bind', '/usr', '/usr',
        '--symlink', 'usr/bin', '/bin', '--symlink', 'usr/lib', '/lib', '--symlink', 'usr/lib64', '/lib64',
        '--ro-bind-try', '/etc/alternatives', '/etc/alternatives',
        '--ro-bind-try', '/etc/ld.so.cache', '/etc/ld.so.cache',
        '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp',
        '--bind', str(workdir), '/box', '--chdir', '/box', '--',
    ]


def _environment():
    if IS_POSIX:
        return {'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C.UTF-8', 'HOME': '/tmp'}
    # На Windows без системных переменных не запускаются ни Python, ни g++; секреты сайта убираем
    return {k: v for k, v in os.environ.items() if not k.startswith('DJANGO_')}


def _limits(memory_mb, cpu_seconds):
    def apply():
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (memory_mb * 2 ** 20,) * 2)
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
        resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_FILE_BYTES,) * 2)
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    return apply


def _read(file):
    file.seek(0)
    return file.read(MAX_OUTPUT_BYTES).decode('utf-8', errors='replace')


def run(command, workdir, input_data='', timeout=None, memory_mb=None):
    """Запускает команду и возвращает CompletedProcess. При превышении времени — TimeoutExpired."""
    timeout = timeout or settings.JUDGE_TIMEOUT_SECONDS
    memory_mb = memory_mb or settings.JUDGE_MEMORY_MB
    # На Windows без этого флага каждый запуск решения открывал бы окно консоли
    extra = {} if IS_POSIX else {'creationflags': subprocess.CREATE_NO_WINDOW}
    if IS_POSIX:
        if settings.JUDGE_SANDBOX == 'bwrap':
            command = _bwrap_prefix(workdir) + command
        # Своя группа процессов, чтобы при таймауте убить и всех потомков
        extra = {'preexec_fn': _limits(memory_mb, timeout + 1), 'process_group': 0}

    # Вывод пишется во временные файлы, а не в память: RLIMIT_FSIZE не даст забить диск,
    # а бесконечный print() не съест память сервера
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        proc = subprocess.Popen(command, cwd=workdir, env=_environment(), stdin=subprocess.PIPE,
                                stdout=stdout, stderr=stderr, **extra)
        try:
            proc.communicate(input_data.encode('utf-8'), timeout=timeout)
        except subprocess.TimeoutExpired:
            if IS_POSIX:
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
            proc.wait()
            raise
        except BrokenPipeError:
            # Программа завершилась, не прочитав весь ввод — это не ошибка проверки
            proc.wait()
        return subprocess.CompletedProcess(command, proc.returncode, _read(stdout), _read(stderr))
