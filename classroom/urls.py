from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('classes/sample/', views.sample_classroom_create, name='sample_classroom_create'),
    path('classes/<int:pk>/', views.classroom_detail, name='classroom_detail'),
    path('classes/<int:pk>/rename/', views.classroom_rename, name='classroom_rename'),
    path('classes/<int:pk>/delete/', views.classroom_delete, name='classroom_delete'),
    path('classes/<int:pk>/students/<int:student_pk>/remove/', views.student_remove, name='student_remove'),
    path('classes/<int:pk>/students/<int:student_pk>/reset-password/', views.student_reset_password,
         name='student_reset_password'),
    path('classes/<int:pk>/gradebook/', views.gradebook, name='gradebook'),
    path('classes/<int:pk>/gradebook/export/', views.gradebook_export, name='gradebook_export'),
    path('classes/<int:classroom_pk>/tasks/new/', views.task_edit, name='task_create'),
    path('classes/<int:classroom_pk>/tasks/<int:task_pk>/edit/', views.task_edit, name='task_edit'),
    path('tasks/<int:pk>/', views.task_detail, name='task_detail'),
    path('tasks/<int:pk>/run/', views.task_run, name='task_run'),
    path('tasks/<int:pk>/delete/', views.task_delete, name='task_delete'),
    path('tasks/<int:task_pk>/students/<int:student_pk>/', views.student_task_submissions,
         name='student_task_submissions'),
    path('tasks/<int:task_pk>/students/<int:student_pk>/grade/', views.set_grade, name='set_grade'),
    path('submissions/<int:pk>/', views.submission_detail, name='submission_detail'),
]
