import secrets
import string
from collections import Counter
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from openpyxl import Workbook
from openpyxl.styles import Font

from accounts.models import User

from .forms import (ClassroomForm, JoinClassroomForm, ManualGradeForm, SubmissionForm, TaskForm,
                    TestCaseFormSet)
from .demo import create_sample_classroom
from .judge import judge, run_once
from .models import Classroom, ManualGrade, Submission, Task, final_scores

MAX_CODE_LENGTH = 100_000


def generate_temporary_password():
    """Пароль, который удобно продиктовать: «kqz-4821»."""
    letters = ''.join(secrets.choice('abcdefghjkmnpqrstuvwxyz') for _ in range(3))
    digits = ''.join(secrets.choice(string.digits) for _ in range(4))
    return f'{letters}-{digits}'


def teacher_required(view):
    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_teacher:
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return wrapper


def get_classroom_for(user, pk):
    """Учитель видит только свои классы, ученик — только те, в которые вступил."""
    if user.is_teacher:
        return get_object_or_404(Classroom, pk=pk, teacher=user)
    return get_object_or_404(Classroom, pk=pk, students=user)


def get_task_for(user, pk):
    task = get_object_or_404(Task.objects.select_related('classroom'), pk=pk)
    get_classroom_for(user, task.classroom_id)
    return task


def home(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'classroom/home.html')


@login_required
def dashboard(request):
    user = request.user
    if user.is_teacher:
        form = ClassroomForm(request.POST or None)
        if form.is_valid():
            classroom = form.save(commit=False)
            classroom.teacher = user
            classroom.save()
            messages.success(request, f'Класс создан. Код для учеников: {classroom.join_code}')
            return redirect('classroom_detail', pk=classroom.pk)
        classrooms = list(user.taught_classrooms.annotate(
            student_count=Count('students', distinct=True), task_count=Count('tasks', distinct=True)))
        stats = {
            'classes': len(classrooms),
            'students': User.objects.filter(classrooms__teacher=user).distinct().count(),
            'tasks': sum(c.task_count for c in classrooms),
            'submissions': Submission.objects.filter(task__classroom__teacher=user).count(),
        }
        public_urls = settings.PUBLIC_URLS
    else:
        form = JoinClassroomForm(request.POST or None)
        if form.is_valid():
            form.classroom.students.add(user)
            messages.success(request, f'Вы вступили в класс «{form.classroom}»')
            return redirect('classroom_detail', pk=form.classroom.pk)
        classrooms = list(user.classrooms.select_related('teacher').annotate(task_count=Count('tasks')))
        tasks = list(Task.objects.filter(classroom__in=classrooms))
        scores = final_scores(tasks, [user.pk])
        solved_by_class = Counter(task.classroom_id for task in tasks if (user.pk, task.pk) in scores)
        for classroom in classrooms:
            classroom.solved_count = solved_by_class[classroom.pk]
        stats = {
            'classes': len(classrooms),
            'solved': len(scores),
            'todo': len(tasks) - len(scores),
            'average': round(sum(scores.values()) / len(scores), 1) if scores else None,
        }
        public_urls = []
    return render(request, 'classroom/dashboard.html', {
        'form': form, 'classrooms': classrooms, 'stats': stats, 'public_urls': public_urls,
    })


@login_required
def classroom_detail(request, pk):
    classroom = get_classroom_for(request.user, pk)
    context = {'classroom': classroom}
    if request.user.is_teacher:
        students = list(classroom.students.order_by('last_name', 'first_name', 'username'))
        context.update(
            tasks=classroom.tasks.annotate(solved_count=Count('submissions__student', distinct=True)),
            students=students, student_count=len(students), rename_form=ClassroomForm(instance=classroom),
        )
    else:
        tasks = list(classroom.tasks.all())
        scores = final_scores(tasks, [request.user.pk])
        for task in tasks:
            task.my_score = scores.get((request.user.pk, task.pk))
            task.is_late = _is_late(task)
        context.update(tasks=tasks, solved_count=len(scores), task_count=len(tasks))
    return render(request, 'classroom/classroom_detail.html', context)


def _teacher_classroom(request, pk):
    return get_object_or_404(Classroom, pk=pk, teacher=request.user)


@teacher_required
@require_POST
def sample_classroom_create(request):
    classroom = create_sample_classroom(request.user)
    messages.success(request, f'Создан класс-пример с {classroom.tasks.count()} заданиями. Код для учеников: '
                              f'{classroom.join_code}')
    return redirect('classroom_detail', pk=classroom.pk)


@teacher_required
@require_POST
def classroom_rename(request, pk):
    classroom = _teacher_classroom(request, pk)
    form = ClassroomForm(request.POST, instance=classroom)
    if form.is_valid():
        form.save()
        messages.success(request, 'Название класса изменено')
    return redirect('classroom_detail', pk=pk)


@teacher_required
@require_POST
def classroom_delete(request, pk):
    classroom = _teacher_classroom(request, pk)
    classroom.delete()
    messages.success(request, f'Класс «{classroom.name}» удалён')
    return redirect('dashboard')


@teacher_required
@require_POST
def student_remove(request, pk, student_pk):
    classroom = _teacher_classroom(request, pk)
    student = get_object_or_404(classroom.students, pk=student_pk)
    classroom.students.remove(student)
    messages.success(request, f'{student} исключён из класса. Его решения сохранены.')
    return redirect('classroom_detail', pk=pk)


@teacher_required
@require_POST
def student_reset_password(request, pk, student_pk):
    """Ученики часто забывают пароль — учитель выдаёт новый временный."""
    classroom = _teacher_classroom(request, pk)
    student = get_object_or_404(classroom.students.filter(role=User.Role.STUDENT), pk=student_pk)
    password = generate_temporary_password()
    student.set_password(password)
    student.save(update_fields=['password'])
    messages.success(request, f'Новый пароль для {student} (логин {student.username}): {password}',
                     extra_tags='sticky')
    return redirect('classroom_detail', pk=pk)


@teacher_required
def task_edit(request, classroom_pk, task_pk=None):
    classroom = get_object_or_404(Classroom, pk=classroom_pk, teacher=request.user)
    task = get_object_or_404(Task, pk=task_pk, classroom=classroom) if task_pk else Task(classroom=classroom)
    form = TaskForm(request.POST or None, instance=task)
    formset = TestCaseFormSet(request.POST or None, instance=task)
    if form.is_valid():
        formset.language = form.cleaned_data['language']
    if form.is_valid() and formset.is_valid():
        with transaction.atomic():
            task = form.save()
            formset.instance = task
            formset.save()
        messages.success(request, 'Задание сохранено')
        return redirect('task_detail', pk=task.pk)
    return render(request, 'classroom/task_edit.html',
                  {'classroom': classroom, 'task': task, 'form': form, 'formset': formset})


@teacher_required
@require_POST
def task_delete(request, pk):
    task = get_object_or_404(Task, pk=pk, classroom__teacher=request.user)
    task.delete()
    messages.success(request, f'Задание «{task.title}» удалено')
    return redirect('classroom_detail', pk=task.classroom_id)


def _is_late(task):
    return task.deadline is not None and timezone.now() > task.deadline


@login_required
def task_detail(request, pk):
    task = get_task_for(request.user, pk)
    if request.user.is_teacher:
        return render(request, 'classroom/task_detail.html', {'task': task, 'tests': task.tests.all()})

    is_late = _is_late(task)
    form = SubmissionForm(request.POST or None)
    if request.method == 'POST' and is_late:
        messages.error(request, 'Дедлайн прошёл, решения больше не принимаются')
    elif form.is_valid():
        code = form.cleaned_data['code'][:MAX_CODE_LENGTH]
        submission = Submission.objects.create(task=task, student=request.user, code=code,
                                               **judge(task, code))
        return redirect('submission_detail', pk=submission.pk)

    submissions = task.submissions.filter(student=request.user)
    if request.method == 'GET' and submissions:
        form = SubmissionForm(initial={'code': submissions[0].code})
    form.fields['code'].widget.attrs.update({'data-language': task.language, 'data-preview': 'html-preview'})
    return render(request, 'classroom/task_detail.html', {
        'task': task, 'form': form, 'is_late': is_late, 'submissions': submissions,
        'visible_tests': task.tests.filter(is_hidden=False),
        'final_score': task.final_score(request.user),
        'manual_grade': task.manual_grades.filter(student=request.user).first(),
    })


@login_required
@require_POST
def task_run(request, pk):
    """Кнопка «Запустить»: выполнить код на своём вводе, без оценки и без сохранения."""
    task = get_task_for(request.user, pk)
    code = request.POST.get('code', '')[:MAX_CODE_LENGTH]
    return JsonResponse(run_once(task, code, request.POST.get('input', '')))


@login_required
def submission_detail(request, pk):
    submission = get_object_or_404(Submission.objects.select_related('task__classroom', 'student'), pk=pk)
    if request.user.is_teacher:
        if submission.task.classroom.teacher_id != request.user.pk:
            raise PermissionDenied
    elif submission.student_id != request.user.pk:
        raise PermissionDenied
    manual_grade = ManualGrade.objects.filter(task=submission.task, student=submission.student).first()
    context = {'submission': submission, 'manual_grade': manual_grade}
    if request.user.is_teacher:
        context['grade_form'] = ManualGradeForm(instance=manual_grade)
    return render(request, 'classroom/submission_detail.html', context)


@teacher_required
@require_POST
def set_grade(request, task_pk, student_pk):
    task = get_object_or_404(Task, pk=task_pk, classroom__teacher=request.user)
    student = get_object_or_404(task.classroom.students, pk=student_pk)
    grade = ManualGrade.objects.filter(task=task, student=student).first()
    if 'reset' in request.POST:
        if grade:
            grade.delete()
        messages.success(request, 'Оценка учителя убрана, снова действует автоматический балл')
    else:
        form = ManualGradeForm(request.POST, instance=grade or ManualGrade(task=task, student=student))
        if form.is_valid():
            form.save()
            messages.success(request, f'Оценка {form.instance.score}/10 сохранена')
        else:
            messages.error(request, 'Балл должен быть от 1 до 10')
    next_url = request.POST.get('next', '')
    if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect('gradebook', pk=task.classroom_id)


def _gradebook_rows(classroom):
    tasks = list(classroom.tasks.all())
    students = list(classroom.students.order_by('last_name', 'first_name', 'username'))
    scores = final_scores(tasks, [s.pk for s in students])
    rows = []
    for student in students:
        cells = [scores.get((student.pk, task.pk)) for task in tasks]
        solved = [s for s in cells if s is not None]
        rows.append({
            'student': student,
            'cells': [{'task': task, 'score': score} for task, score in zip(tasks, cells)],
            'average': round(sum(solved) / len(solved), 1) if solved else None,
        })
    return tasks, rows


@teacher_required
def gradebook(request, pk):
    classroom = get_object_or_404(Classroom, pk=pk, teacher=request.user)
    tasks, rows = _gradebook_rows(classroom)
    return render(request, 'classroom/gradebook.html', {'classroom': classroom, 'tasks': tasks, 'rows': rows})


@teacher_required
def gradebook_export(request, pk):
    classroom = get_object_or_404(Classroom, pk=pk, teacher=request.user)
    tasks, rows = _gradebook_rows(classroom)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Журнал'
    sheet.append(['Ученик', *[task.title for task in tasks], 'Средний'])
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in rows:
        sheet.append([str(row['student']), *[c['score'] for c in row['cells']], row['average']])
    sheet.column_dimensions['A'].width = 30
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="gradebook-{classroom.pk}.xlsx"'
    workbook.save(response)
    return response


@teacher_required
def student_task_submissions(request, task_pk, student_pk):
    task = get_object_or_404(Task, pk=task_pk, classroom__teacher=request.user)
    submissions = task.submissions.filter(student_id=student_pk)
    if not submissions:
        messages.info(request, 'Ученик ещё не отправлял решений')
        return redirect('gradebook', pk=task.classroom_id)
    best = max(submissions, key=lambda s: (s.score, s.created_at))
    return redirect('submission_detail', pk=best.pk)
