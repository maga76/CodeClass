from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import User


class RegisterForm(UserCreationForm):
    class Meta:
        model = User
        fields = ('role', 'first_name', 'last_name', 'username')
        labels = {'role': 'Кто вы', 'username': 'Логин', 'first_name': 'Имя', 'last_name': 'Фамилия'}
        widgets = {'role': forms.RadioSelect}
