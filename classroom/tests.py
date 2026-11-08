import os
import shutil
from unittest import skipUnless

from django.conf import settings
from django.test import TestCase as DjangoTestCase
from django.urls import reverse

from accounts.models import User

from .judge import calculate_score, find_cpp_compiler, judge, run_once
from .models import Classroom, Submission, Task, TestCase


def cpp_runs():
    """Есть ли g++ и разрешает ли Windows запускать скомпилированные программы (Smart App Control)."""
    if not hasattr(cpp_runs, 'result'):
        if find_cpp_compiler() is None:
            cpp_runs.result = False
        else:
            task = Task(language=Task.Language.CPP)
            code = '#include <iostream>\nint main() { std::cout << 1; }'
            cpp_runs.result = run_once(task, code, '').get('verdict') == 'Выполнено'
    return cpp_runs.result


def skip_if_blocked_by_windows(testcase, result):
    """Smart App Control блокирует скомпилированные программы непредсказуемо — это не ошибка CodeClass."""
    if any('Smart App Control' in r.get('error', '') for r in result['results']):
        testcase.skipTest('Windows (Smart App Control) заблокировал запуск скомпилированной программы')


class ScoreTests(DjangoTestCase):
    def test_score_range(self):
        self.assertEqual(calculate_score(0, 4), 1)
        self.assertEqual(calculate_score(2, 4), 5)
        self.assertEqual(calculate_score(4, 4), 10)
        self.assertEqual(calculate_score(0, 0), 0)


class JudgeTests(DjangoTestCase):
    def setUp(self):
        teacher = User.objects.create_user('t', password='x', role=User.Role.TEACHER)
        classroom = Classroom.objects.create(name='9А', teacher=teacher)
        self.task = Task.objects.create(classroom=classroom, title='Сумма', description='a+b')
        TestCase.objects.create(task=self.task, input_data='2\n3', expected_output='5')
        TestCase.objects.create(task=self.task, input_data='10\n-4', expected_output='6', is_hidden=True)

    def test_correct_solution(self):
        result = judge(self.task, 'print(int(input()) + int(input()))')
        self.assertEqual(result['status'], Submission.Status.ACCEPTED)
        self.assertEqual(result['score'], 10)

    def test_partial_solution(self):
        result = judge(self.task, 'print(5)')
        self.assertEqual((result['passed'], result['score']), (1, 5))
        self.assertNotIn('input', result['results'][1])

    def test_runtime_error_and_timeout(self):
        self.assertEqual(judge(self.task, 'raise ValueError')['results'][0]['verdict'], 'Ошибка выполнения')
        self.assertEqual(judge(self.task, 'while True: pass')['results'][0]['verdict'], 'Превышено время')


@skipUnless(cpp_runs(), 'C++ недоступен: нет g++ или запуск запрещён Windows')
class CppJudgeTests(DjangoTestCase):
    def setUp(self):
        teacher = User.objects.create_user('t', password='x', role=User.Role.TEACHER)
        classroom = Classroom.objects.create(name='9А', teacher=teacher)
        self.task = Task.objects.create(classroom=classroom, title='Сумма', description='a+b',
                                        language=Task.Language.CPP)
        TestCase.objects.create(task=self.task, input_data='2 3', expected_output='5')

    def test_correct_solution(self):
        code = '#include <iostream>\nint main() { int a, b; std::cin >> a >> b; std::cout << a + b; }'
        result = judge(self.task, code)
        skip_if_blocked_by_windows(self, result)
        self.assertEqual(result['score'], 10)

    def test_compile_error(self):
        result = judge(self.task, 'int main() { return x; }')
        self.assertEqual(result['status'], Submission.Status.ERROR)
        self.assertEqual(result['results'][0]['verdict'], 'Ошибка компиляции')


class HtmlJudgeTests(DjangoTestCase):
    def setUp(self):
        teacher = User.objects.create_user('t', password='x', role=User.Role.TEACHER)
        classroom = Classroom.objects.create(name='9А', teacher=teacher)
        self.task = Task.objects.create(classroom=classroom, title='Визитка', description='...',
                                        language=Task.Language.HTML)
        TestCase.objects.create(task=self.task, input_data='h1', expected_output='Привет')
        TestCase.objects.create(task=self.task, input_data='ul li')
        TestCase.objects.create(task=self.task, input_data='form input[type=email]', is_hidden=True)

    def test_all_rules(self):
        code = ('<h1>Привет, мир</h1><ul><li>Python</li></ul>'
                '<form><input type="email"></form>')
        self.assertEqual(judge(self.task, code)['score'], 10)

    def test_wrong_text_and_missing_element(self):
        result = judge(self.task, '<h1>Пока</h1><ul><li>1</li></ul>')
        verdicts = [r['verdict'] for r in result['results']]
        self.assertEqual(verdicts, ['Неверный текст', 'OK', 'Элемент не найден'])
        self.assertEqual(result['score'], 3)

    def test_teacher_cannot_save_bad_selector(self):
        self.client.force_login(self.task.classroom.teacher)
        response = self.client.post(reverse('task_create', args=[self.task.classroom_id]), {
            'title': 'Ещё', 'description': '...', 'language': 'html', 'deadline': '',
            'tests-TOTAL_FORMS': '1', 'tests-INITIAL_FORMS': '0',
            'tests-MIN_NUM_FORMS': '0', 'tests-MAX_NUM_FORMS': '1000',
            'tests-0-input_data': 'div[[', 'tests-0-expected_output': '',
        })
        self.assertContains(response, 'Некорректный CSS-селектор')
        self.assertEqual(Task.objects.count(), 1)


class AccessTests(DjangoTestCase):
    def setUp(self):
        self.teacher = User.objects.create_user('t', password='x', role=User.Role.TEACHER)
        self.student = User.objects.create_user('s', password='x')
        self.classroom = Classroom.objects.create(name='9А', teacher=self.teacher)
        self.task = Task.objects.create(classroom=self.classroom, title='Привет', description='...')
        TestCase.objects.create(task=self.task, expected_output='Привет')

    def test_student_joins_and_submits(self):
        self.client.force_login(self.student)
        self.client.post(reverse('dashboard'), {'join_code': self.classroom.join_code.lower()})
        self.assertTrue(self.classroom.students.filter(pk=self.student.pk).exists())

        self.client.post(reverse('task_detail', args=[self.task.pk]), {'code': 'print("Привет")'})
        self.assertEqual(self.task.final_score(self.student), 10)

        response = self.client.get(reverse('gradebook', args=[self.classroom.pk]))
        self.assertEqual(response.status_code, 403)

    def test_outsider_cannot_open_task(self):
        self.client.force_login(self.student)
        response = self.client.get(reverse('task_detail', args=[self.task.pk]))
        self.assertEqual(response.status_code, 404)

    def test_teacher_gradebook(self):
        self.classroom.students.add(self.student)
        Submission.objects.create(task=self.task, student=self.student, code='', status='accepted', score=10)
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('gradebook', args=[self.classroom.pk]))
        self.assertContains(response, '>10<')


class TeacherToolsTests(DjangoTestCase):
    def setUp(self):
        self.teacher = User.objects.create_user('t', password='x', role=User.Role.TEACHER)
        self.student = User.objects.create_user('s', password='x', first_name='Пётр')
        self.classroom = Classroom.objects.create(name='9А', teacher=self.teacher)
        self.classroom.students.add(self.student)
        self.task = Task.objects.create(classroom=self.classroom, title='Сумма', description='a+b')
        TestCase.objects.create(task=self.task, input_data='2\n3', expected_output='5')
        Submission.objects.create(task=self.task, student=self.student, code='', status='failed', score=1)

    def test_manual_grade_overrides_auto_score(self):
        self.client.force_login(self.teacher)
        url = reverse('set_grade', args=[self.task.pk, self.student.pk])
        self.client.post(url, {'score': 8, 'comment': 'Молодец'})
        self.assertEqual(self.task.final_score(self.student), 8)
        self.client.post(url, {'score': 11})
        self.assertEqual(self.task.final_score(self.student), 8)
        self.client.post(url, {'reset': '1'})
        self.assertEqual(self.task.final_score(self.student), 1)

    def test_set_grade_ignores_foreign_redirect(self):
        self.client.force_login(self.teacher)
        response = self.client.post(reverse('set_grade', args=[self.task.pk, self.student.pk]),
                                    {'score': 5, 'next': 'https://evil.example.com/'})
        self.assertEqual(response['Location'], reverse('gradebook', args=[self.classroom.pk]))

    def test_student_cannot_grade(self):
        self.client.force_login(self.student)
        response = self.client.post(reverse('set_grade', args=[self.task.pk, self.student.pk]), {'score': 10})
        self.assertEqual(response.status_code, 403)

    def test_excel_export(self):
        from io import BytesIO
        from openpyxl import load_workbook
        self.client.force_login(self.teacher)
        response = self.client.get(reverse('gradebook_export', args=[self.classroom.pk]))
        sheet = load_workbook(BytesIO(response.content)).active
        self.assertEqual([c.value for c in sheet[1]], ['Ученик', 'Сумма', 'Средний'])
        self.assertEqual([c.value for c in sheet[2]], ['Пётр', 1, 1])

    def test_delete_task(self):
        self.client.force_login(self.teacher)
        self.client.post(reverse('task_delete', args=[self.task.pk]))
        self.assertFalse(Task.objects.exists())

    def test_run_button(self):
        self.client.force_login(self.student)
        response = self.client.post(reverse('task_run', args=[self.task.pk]),
                                    {'code': 'print(input()[::-1])', 'input': 'привет'})
        self.assertEqual(response.json()['verdict'], 'Выполнено')
        self.assertEqual(response.json()['output'].strip(), 'тевирп')
        self.assertEqual(Submission.objects.count(), 1)  # запуск не сохраняется

    def test_huge_output_is_truncated(self):
        result = judge(self.task, 'print("x" * 10_000_000)')
        self.assertEqual(result['results'][0]['verdict'], 'Неверный ответ')
        self.assertLessEqual(len(result['results'][0]['output']), 2000)


class ClassManagementTests(DjangoTestCase):
    def setUp(self):
        self.teacher = User.objects.create_user('t', password='x', role=User.Role.TEACHER)
        self.other_teacher = User.objects.create_user('t2', password='x', role=User.Role.TEACHER)
        self.student = User.objects.create_user('s', password='old-password-1')
        self.classroom = Classroom.objects.create(name='9А', teacher=self.teacher)
        self.classroom.students.add(self.student)

    def test_reset_password(self):
        self.client.force_login(self.teacher)
        response = self.client.post(reverse('student_reset_password', args=[self.classroom.pk, self.student.pk]),
                                    follow=True)
        text = [str(m) for m in response.context['messages']][0]
        new_password = text.rsplit(': ', 1)[1]
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password(new_password))
        self.assertFalse(self.student.check_password('old-password-1'))

    def test_other_teacher_cannot_reset_password(self):
        self.client.force_login(self.other_teacher)
        response = self.client.post(reverse('student_reset_password', args=[self.classroom.pk, self.student.pk]))
        self.assertEqual(response.status_code, 404)

    def test_remove_student_rename_and_delete_class(self):
        self.client.force_login(self.teacher)
        self.client.post(reverse('student_remove', args=[self.classroom.pk, self.student.pk]))
        self.assertFalse(self.classroom.students.exists())
        self.client.post(reverse('classroom_rename', args=[self.classroom.pk]), {'name': '10Б'})
        self.classroom.refresh_from_db()
        self.assertEqual(self.classroom.name, '10Б')
        self.client.post(reverse('classroom_delete', args=[self.classroom.pk]))
        self.assertFalse(Classroom.objects.exists())

    def test_password_change(self):
        self.client.force_login(self.student)
        self.client.post(reverse('password_change'), {
            'old_password': 'old-password-1', 'new_password1': 'Nov1y-parol!', 'new_password2': 'Nov1y-parol!'})
        self.student.refresh_from_db()
        self.assertTrue(self.student.check_password('Nov1y-parol!'))

    def test_home_page(self):
        self.assertContains(self.client.get(reverse('home')), 'настоящие задачи')
        self.client.force_login(self.student)
        self.assertRedirects(self.client.get(reverse('home')), reverse('dashboard'))


SAMPLE_SOLUTIONS = {
    'Привет, мир!': 'print("Привет, мир!")',
    'Сумма двух чисел': 'print(int(input()) + int(input()))',
    'Чётное или нечётное': 'print("Чётное" if int(input()) % 2 == 0 else "Нечётное")',
    'Максимум из трёх': 'print(max(int(input()) for _ in range(3)))',
    'Таблица умножения': 'n = int(input())\nfor i in range(1, n + 1):\n    print(*[i * j for j in range(1, n + 1)])',
    'Факториал': 'import math\nprint(math.factorial(int(input())))',
    'Палиндром': 's = input()\nprint("Да" if s == s[::-1] else "Нет")',
    'Сумма цифр': 'print(sum(map(int, input())))',
    'C++: сумма двух чисел': '#include <iostream>\nint main() { long long a, b; std::cin >> a >> b; std::cout << a + b; }',
    'C++: квадрат числа': '#include <iostream>\nint main() { long long n; std::cin >> n; std::cout << n * n; }',
    'HTML: моя визитка': '<h1>Я</h1><ul><li>Шахматы</li></ul><a href="https://example.com">сайт</a><img src="a.png" alt="фото">',
    'HTML: форма регистрации': '<form><input type="email"><input type="password"><button>Зарегистрироваться</button></form>',
}


class SampleTasksTests(DjangoTestCase):
    def setUp(self):
        self.teacher = User.objects.create_user('t', password='x', role=User.Role.TEACHER)

    def test_every_sample_task_is_solvable(self):
        from .demo import SAMPLE_TASKS, create_sample_classroom
        classroom = create_sample_classroom(self.teacher)
        self.assertEqual(classroom.tasks.count(), len(SAMPLE_TASKS))
        has_cpp = cpp_runs()
        for task in classroom.tasks.all():
            if task.language == 'cpp' and not has_cpp:
                continue
            with self.subTest(task=task.title):
                result = judge(task, SAMPLE_SOLUTIONS[task.title])
                skip_if_blocked_by_windows(self, result)
                self.assertEqual(result['score'], 10, result['results'])

    def test_sample_classroom_button(self):
        self.client.force_login(self.teacher)
        response = self.client.post(reverse('sample_classroom_create'))
        classroom = Classroom.objects.get(teacher=self.teacher)
        self.assertRedirects(response, reverse('classroom_detail', args=[classroom.pk]))
        self.assertEqual(classroom.tasks.count(), 12)

    def test_load_demo_is_idempotent_and_shown_on_login(self):
        from django.core.management import call_command
        call_command('load_demo', stdout=open(os.devnull, 'w'))
        call_command('load_demo', stdout=open(os.devnull, 'w'))
        self.assertEqual(Classroom.objects.filter(join_code='DEMO9A').count(), 1)
        self.assertTrue(self.client.login(username='student', password='student123'))
        self.client.logout()
        self.assertContains(self.client.get(reverse('login')), 'teacher123')
        call_command('load_demo', remove=True, stdout=open(os.devnull, 'w'))
        self.assertFalse(User.objects.filter(is_demo=True).exists())
        self.assertNotContains(self.client.get(reverse('login')), 'teacher123')


class CppLaunchBlockedTests(DjangoTestCase):
    def test_blocked_launch_gives_clear_message_instead_of_crash(self):
        from unittest import mock
        teacher = User.objects.create_user('t', password='x', role=User.Role.TEACHER)
        task = Task.objects.create(classroom=Classroom.objects.create(name='9А', teacher=teacher),
                                   title='x', description='x')
        TestCase.objects.create(task=task, expected_output='1')
        blocked = OSError('blocked')
        blocked.winerror = 4551
        with mock.patch('classroom.sandbox.run', side_effect=blocked):
            result = judge(task, 'print(1)')
        self.assertEqual(result['status'], Submission.Status.ERROR)
        self.assertIn('Smart App Control', result['results'][0]['error'])
