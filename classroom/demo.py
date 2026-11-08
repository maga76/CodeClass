"""Готовые задания-примеры и демо-данные.

create_sample_classroom — класс с заданиями для учителя (кнопка «Создать пример класса»).
load_demo_data — демо-аккаунты учителя и учеников с решениями (python manage.py load_demo).
"""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from accounts.models import User

from .judge import judge
from .models import Classroom, Submission, Task, TestCase

# (название, язык, условие, [(ввод, вывод, скрытый)], дней до дедлайна или None)
SAMPLE_TASKS = [
    ('Привет, мир!', 'python',
     'Напишите программу, которая выводит фразу «Привет, мир!».\n\n'
     'Выходные данные: строка «Привет, мир!» (без кавычек).',
     [('', 'Привет, мир!', False)], None),

    ('Сумма двух чисел', 'python',
     'Даны два целых числа a и b. Выведите их сумму.\n\n'
     'Входные данные: два целых числа, каждое на отдельной строке.\n'
     'Выходные данные: одно число — сумма a + b.',
     [('2\n3', '5', False), ('-10\n4', '-6', False), ('1000000\n1', '1000001', True)], 7),

    ('Чётное или нечётное', 'python',
     'Дано целое число n. Выведите «Чётное», если оно чётное, и «Нечётное» — если нечётное.\n\n'
     'Входные данные: одно целое число.\nВыходные данные: слово «Чётное» или «Нечётное».',
     [('4', 'Чётное', False), ('7', 'Нечётное', False), ('0', 'Чётное', True), ('-3', 'Нечётное', True)], 7),

    ('Максимум из трёх', 'python',
     'Даны три целых числа. Выведите наибольшее из них.\n\n'
     'Входные данные: три целых числа, каждое на отдельной строке.\nВыходные данные: наибольшее число.',
     [('1\n5\n3', '5', False), ('-1\n-7\n-3', '-1', False), ('4\n4\n2', '4', True)], None),

    ('Таблица умножения', 'python',
     'Дано число n. Выведите таблицу умножения размером n × n: в строке номер i — числа i·1, i·2, …, i·n '
     'через пробел.\n\nВходные данные: одно натуральное число n (1 ≤ n ≤ 9).\nВыходные данные: n строк.',
     [('3', '1 2 3\n2 4 6\n3 6 9', False), ('1', '1', False), ('4', '1 2 3 4\n2 4 6 8\n3 6 9 12\n4 8 12 16', True)],
     14),

    ('Факториал', 'python',
     'Дано число n. Выведите n! = 1 · 2 · … · n. Считается, что 0! = 1.\n\n'
     'Входные данные: одно целое число n (0 ≤ n ≤ 20).\nВыходные данные: значение n!.',
     [('5', '120', False), ('0', '1', False), ('10', '3628800', True)], None),

    ('Палиндром', 'python',
     'Дана строка. Выведите «Да», если она читается одинаково слева направо и справа налево, иначе «Нет».\n\n'
     'Входные данные: одна строка из строчных букв.\nВыходные данные: «Да» или «Нет».',
     [('шалаш', 'Да', False), ('привет', 'Нет', False), ('а', 'Да', True), ('ab', 'Нет', True)], None),

    ('Сумма цифр', 'python',
     'Дано натуральное число. Выведите сумму его цифр.\n\n'
     'Входные данные: одно натуральное число.\nВыходные данные: сумма цифр.',
     [('12345', '15', False), ('7', '7', False), ('1000', '1', True)], None),

    ('C++: сумма двух чисел', 'cpp',
     'Даны два целых числа на одной строке через пробел. Выведите их сумму.\n\n'
     'Подсказка: #include <iostream>, std::cin >> a >> b; std::cout << a + b;',
     [('2 3', '5', False), ('-5 10', '5', False), ('100 200', '300', True)], None),

    ('C++: квадрат числа', 'cpp',
     'Дано целое число n. Выведите n².\n\nВходные данные: одно целое число.\nВыходные данные: n * n.',
     [('4', '16', False), ('-3', '9', False), ('0', '0', True)], None),

    ('HTML: моя визитка', 'html',
     'Сделайте страницу о себе:\n'
     '• заголовок <h1> с вашим именем;\n'
     '• список увлечений <ul> с пунктами <li>;\n'
     '• ссылку <a href="..."> на любимый сайт;\n'
     '• картинку <img> с описанием в атрибуте alt.',
     [('h1', '', False), ('ul li', '', False), ('a[href]', '', False), ('img[alt]', '', True)], 10),

    ('HTML: форма регистрации', 'html',
     'Сделайте форму регистрации <form>: поле для email (<input type="email">), поле для пароля '
     '(<input type="password">) и кнопку с текстом «Зарегистрироваться».',
     [('form input[type=email]', '', False), ('form input[type=password]', '', False),
      ('button', 'Зарегистрироваться', False)], None),
]

DEMO_CLASS_CODE = 'DEMO9A'
DEMO_PASSWORD_TEACHER = 'teacher123'
DEMO_PASSWORD_STUDENT = 'student123'
DEMO_TEACHER = ('teacher', 'Анна', 'Каримова')
DEMO_STUDENTS = [('student', 'Алишер', 'Рахимов'), ('student2', 'Мадина', 'Саидова'),
                 ('student3', 'Тимур', 'Назаров')]

# Готовые решения для демо-учеников: (ученик, задание, код)
DEMO_SOLUTIONS = [
    ('student2', 'Привет, мир!', 'print("Привет, мир!")\n'),
    ('student2', 'Сумма двух чисел', 'a = int(input())\nb = int(input())\nprint(a + b)\n'),
    ('student2', 'Чётное или нечётное', 'n = int(input())\nprint("Чётное" if n % 2 == 0 else "Нечётное")\n'),
    ('student2', 'Факториал', 'n = int(input())\nf = 1\nfor i in range(2, n + 1):\n    f *= i\nprint(f)\n'),
    ('student2', 'HTML: моя визитка',
     '<h1>Мадина</h1>\n<ul>\n  <li>Рисование</li>\n  <li>Python</li>\n</ul>\n'
     '<a href="https://example.com">Мой сайт</a>\n<img src="cat.png" alt="Мой кот">\n'),
    ('student3', 'Привет, мир!', 'print("Привет мир")\n'),
    ('student3', 'Привет, мир!', 'print("Привет, мир!")\n'),
    ('student3', 'Сумма двух чисел', 'a = int(input())\nb = int(input())\nprint(a - b)\n'),
    ('student3', 'Чётное или нечётное', 'n = int(input())\nif n % 2 == 0:\n    print("Чётное")\n'),
    ('student3', 'Максимум из трёх', 'print(max(int(input()), int(input()), int(input())))\n'),
]


@transaction.atomic
def create_sample_classroom(teacher, name='Пример: основы программирования', join_code=None):
    classroom = Classroom.objects.create(name=name, teacher=teacher, **({'join_code': join_code} if join_code else {}))
    now = timezone.now()
    for title, language, description, tests, deadline_days in SAMPLE_TASKS:
        task = Task.objects.create(
            classroom=classroom, title=title, language=language, description=description,
            deadline=now + timedelta(days=deadline_days) if deadline_days else None,
        )
        TestCase.objects.bulk_create(
            TestCase(task=task, input_data=i, expected_output=o, is_hidden=h) for i, o, h in tests)
    return classroom


def _demo_user(username, first_name, last_name, role, password):
    user, created = User.objects.get_or_create(username=username, defaults={
        'first_name': first_name, 'last_name': last_name, 'role': role, 'is_demo': True})
    if created:
        user.set_password(password)
        user.save()
    return user


def load_demo_data():
    """Создаёт демо-учителя, учеников, класс с заданиями и несколько решений. Повторный запуск ничего не дублирует."""
    teacher = _demo_user(*DEMO_TEACHER, User.Role.TEACHER, DEMO_PASSWORD_TEACHER)
    students = {username: _demo_user(username, first, last, User.Role.STUDENT, DEMO_PASSWORD_STUDENT)
                for username, first, last in DEMO_STUDENTS}
    classroom = Classroom.objects.filter(join_code=DEMO_CLASS_CODE).first()
    if classroom is None:
        classroom = create_sample_classroom(teacher, name='Информатика — 9 «А»', join_code=DEMO_CLASS_CODE)
        classroom.students.add(*students.values())
        tasks = {task.title: task for task in classroom.tasks.all()}
        for username, title, code in DEMO_SOLUTIONS:
            task = tasks[title]
            Submission.objects.create(task=task, student=students[username], code=code, **judge(task, code))
    return teacher, classroom


DEMO_ACCOUNTS = [
    ('Учитель', DEMO_TEACHER[0], DEMO_PASSWORD_TEACHER),
    ('Ученик', DEMO_STUDENTS[0][0], DEMO_PASSWORD_STUDENT),
]
