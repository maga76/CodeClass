# Сборка: powershell -ExecutionPolicy Bypass -File desktop\build_exe.ps1
# Программа включает весь сайт (Django), встроенный сервер (waitress) и окно (pywebview).
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent

# Модули стандартной библиотеки, которые могут понадобиться в решениях учеников:
# программа сама служит для них интерпретатором Python (CodeClass.exe --run-python)
STUDENT_MODULES = [
    'math', 'cmath', 'random', 'statistics', 'decimal', 'fractions', 'numbers',
    'collections', 'collections.abc', 'itertools', 'functools', 'operator', 'heapq', 'bisect', 'array',
    'string', 're', 'textwrap', 'unicodedata', 'difflib',
    'datetime', 'time', 'calendar', 'json', 'csv', 'copy', 'pprint', 'dataclasses', 'enum', 'typing',
    'sys', 'os', 'io', 'struct', 'hashlib', 'base64', 'secrets', 'uuid', 'turtle',
]


def project_modules(package):
    """Модули проекта по файлам: collect_submodules запускается в отдельном процессе,
    который не видит папку проекта, и молча возвращает пустой список."""
    modules = []
    for path in (ROOT / package).rglob('*.py'):
        parts = path.relative_to(ROOT).with_suffix('').parts
        if parts[-1] == '__init__':
            parts = parts[:-1]
        if 'tests' not in parts:
            modules.append('.'.join(parts))
    return modules


hiddenimports = (
    STUDENT_MODULES
    + project_modules('config') + project_modules('accounts') + project_modules('classroom')
    + collect_submodules('django', filter=lambda name: not name.startswith(
        ('django.contrib.gis', 'django.contrib.postgres', 'django.db.backends.mysql',
         'django.db.backends.oracle', 'django.db.backends.postgresql')))
    + collect_submodules('whitenoise') + collect_submodules('waitress')
    + collect_submodules('openpyxl') + collect_submodules('bs4') + collect_submodules('soupsieve')
)

datas = [
    (str(ROOT / 'templates'), 'templates'),
    (str(ROOT / 'static'), 'static'),
    *collect_data_files('django'),
]

a = Analysis(
    [str(ROOT / 'desktop' / 'app.py')],
    pathex=[str(ROOT)],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=['PIL', 'PyInstaller'],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='CodeClass',
    icon=str(ROOT / 'desktop' / 'icon.ico'),
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name='CodeClass')
