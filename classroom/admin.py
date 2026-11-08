from django.contrib import admin

from .models import Classroom, ManualGrade, Submission, Task, TestCase


@admin.register(Classroom)
class ClassroomAdmin(admin.ModelAdmin):
    list_display = ('name', 'teacher', 'join_code', 'created_at')
    filter_horizontal = ('students',)


class TestCaseInline(admin.TabularInline):
    model = TestCase
    extra = 1


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'classroom', 'language', 'deadline')
    list_filter = ('language', 'classroom')
    inlines = [TestCaseInline]


@admin.register(ManualGrade)
class ManualGradeAdmin(admin.ModelAdmin):
    list_display = ('task', 'student', 'score', 'updated_at')


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ('task', 'student', 'status', 'score', 'created_at')
    list_filter = ('status', 'task__classroom')
