"""python manage.py check_judge — проверяет, что запуск решений работает и защищён."""
from django.conf import settings
from django.core.management.base import BaseCommand

from classroom import sandbox
from classroom.judge import CompileError, _execute

# Программа-«взломщик»: пытается прочитать базу данных сайта и выйти в интернет
PROBE = '''
import socket
try:
    open({db!r}, 'rb').read(16)
    print('FILES-OPEN')
except OSError:
    print('FILES-CLOSED')
try:
    socket.create_connection(('1.1.1.1', 53), timeout=2)
    print('NET-OPEN')
except OSError:
    print('NET-CLOSED')
'''


class Command(BaseCommand):
    help = 'Проверяет запуск Python и C++ и изоляцию решений учеников'

    def handle(self, *args, **options):
        self.stdout.write(f'Режим песочницы: {settings.JUDGE_SANDBOX}, Python для решений: {settings.JUDGE_PYTHON}')
        ok = True

        runs = _execute('python', 'print(int(input()) * 2)', ['21'])
        ok &= self._report('Python запускается', runs[0] is not None and runs[0].stdout.strip() == '42')

        try:
            runs = _execute('cpp', '#include <iostream>\nint main(){int a;std::cin>>a;std::cout<<a*2;}', ['21'])
            ok &= self._report('C++ компилируется и запускается', runs[0] is not None and runs[0].stdout.strip() == '42')
        except CompileError as error:
            ok &= self._report(f'C++: {error}', False)

        runs = _execute('python', 'while True: pass', [''])
        ok &= self._report('Бесконечный цикл останавливается по времени', runs[0] is None)

        runs = _execute('python', 'x = bytearray(2 * 1024 ** 3)', [''])
        memory_limited = runs[0] is not None and runs[0].returncode != 0
        ok &= self._report('Лимит памяти работает', memory_limited, warn_only=not sandbox.IS_POSIX)

        db_path = str(settings.DATABASES['default']['NAME'])
        runs = _execute('python', PROBE.format(db=db_path), [''])
        output = runs[0].stdout if runs[0] else ''
        ok &= self._report('Решение не видит базу данных сайта', 'FILES-CLOSED' in output,
                           warn_only=settings.JUDGE_SANDBOX != 'bwrap')
        ok &= self._report('Решение не может выйти в интернет', 'NET-CLOSED' in output,
                           warn_only=settings.JUDGE_SANDBOX != 'bwrap')

        if settings.JUDGE_SANDBOX != 'bwrap':
            self.stdout.write(self.style.WARNING(
                'Изоляция выключена. На сервере установите bubblewrap и задайте JUDGE_SANDBOX=bwrap.'))
        if ok:
            self.stdout.write(self.style.SUCCESS('Всё в порядке'))
        else:
            self.stdout.write(self.style.ERROR('Есть проблемы — см. выше'))

    def _report(self, name, passed, warn_only=False):
        if passed:
            self.stdout.write(self.style.SUCCESS(f'  ✓ {name}'))
            return True
        style = self.style.WARNING if warn_only else self.style.ERROR
        self.stdout.write(style(f'  ✗ {name}'))
        return warn_only
