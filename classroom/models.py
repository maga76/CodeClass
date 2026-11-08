import secrets
import string

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Max


def generate_join_code():
    alphabet = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(6))


class Classroom(models.Model):
    name = models.CharField('название', max_length=100)
    teacher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name='taught_classrooms', verbose_name='учитель')
    students = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True,
                                      related_name='classrooms', verbose_name='ученики')
    join_code = models.CharField('код для входа', max_length=6, unique=True, default=generate_join_code)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'класс'
        verbose_name_plural = 'классы'
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class Task(models.Model):
    class Language(models.TextChoices):
        PYTHON = 'python', 'Python'
        CPP = 'cpp', 'C++'
        HTML = 'html', 'HTML'

    classroom = models.ForeignKey(Classroom, on_delete=models.CASCADE, related_name='tasks',
                                  verbose_name='класс')
    title = models.CharField('название', max_length=200)
    description = models.TextField('условие')
    language = models.CharField('язык', max_length=10, choices=Language.choices, default=Language.PYTHON)
    deadline = models.DateTimeField('дедлайн', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'задание'
        verbose_name_plural = 'задания'
        ordering = ['created_at']

    def __str__(self):
        return self.title

    def final_score(self, student):
        return final_scores([self], [student.pk]).get((student.pk, self.pk))


class TestCase(models.Model):
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='tests', verbose_name='задание')
    input_data = models.TextField('входные данные', blank=True)
    # Для HTML-заданий: input_data — CSS-селектор, expected_output — текст внутри элемента (необязательно)
    expected_output = models.TextField('ожидаемый вывод', blank=True)
    is_hidden = models.BooleanField('скрытый', default=False,
                                    help_text='Ученик не увидит входные данные и ответ этого теста')

    class Meta:
        verbose_name = 'тест'
        verbose_name_plural = 'тесты'
        ordering = ['id']


class Submission(models.Model):
    class Status(models.TextChoices):
        ACCEPTED = 'accepted', 'Все тесты пройдены'
        PARTIAL = 'partial', 'Частично'
        FAILED = 'failed', 'Не пройдено'
        ERROR = 'error', 'Ошибка'

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='submissions',
                             verbose_name='задание')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name='submissions', verbose_name='ученик')
    code = models.TextField('код')
    status = models.CharField('статус', max_length=10, choices=Status.choices)
    passed = models.PositiveIntegerField('пройдено тестов', default=0)
    total = models.PositiveIntegerField('всего тестов', default=0)
    score = models.PositiveSmallIntegerField('балл', default=0)
    results = models.JSONField('результаты по тестам', default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'решение'
        verbose_name_plural = 'решения'
        ordering = ['-created_at']


class ManualGrade(models.Model):
    """Оценка учителя вручную. Если она есть, она заменяет автоматический балл."""
    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name='manual_grades', verbose_name='задание')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name='manual_grades', verbose_name='ученик')
    score = models.PositiveSmallIntegerField('балл', validators=[MinValueValidator(1), MaxValueValidator(10)])
    comment = models.CharField('комментарий', max_length=500, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'оценка учителя'
        verbose_name_plural = 'оценки учителя'
        constraints = [models.UniqueConstraint(fields=['task', 'student'], name='one_manual_grade_per_task')]


def final_scores(tasks, student_ids):
    """Итоговые баллы {(id ученика, id задания): балл}: оценка учителя, иначе лучший автоматический балл."""
    scores = {
        (student, task): score for student, task, score in
        Submission.objects.filter(task__in=tasks, student__in=student_ids)
        .values('student', 'task').annotate(m=Max('score')).values_list('student', 'task', 'm')
    }
    scores.update({
        (grade.student_id, grade.task_id): grade.score
        for grade in ManualGrade.objects.filter(task__in=tasks, student__in=student_ids)
    })
    return scores
