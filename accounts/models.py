from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        TEACHER = 'teacher', 'Учитель'
        STUDENT = 'student', 'Ученик'

    role = models.CharField('роль', max_length=10, choices=Role.choices, default=Role.STUDENT)
    # Демо-аккаунты (python manage.py load_demo): их логины и пароли показываются на странице входа
    is_demo = models.BooleanField('демо-аккаунт', default=False)

    @property
    def is_teacher(self):
        return self.role == self.Role.TEACHER

    def __str__(self):
        return self.get_full_name() or self.username
