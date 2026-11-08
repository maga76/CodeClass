from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.shortcuts import redirect, render
from django.urls import reverse_lazy

from .forms import RegisterForm
from .models import User


def register(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    role = request.GET.get('role')
    initial = {'role': role if role in User.Role.values else User.Role.STUDENT}
    form = RegisterForm(request.POST or None, initial=initial)
    if form.is_valid():
        user = form.save()
        login(request, user)
        return redirect('dashboard')
    return render(request, 'accounts/register.html', {'form': form})


class LoginView(auth_views.LoginView):
    template_name = 'accounts/login.html'
    redirect_authenticated_user = True

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields['username'].label = 'Логин'
        return form

    def get_context_data(self, **kwargs):
        from classroom.demo import DEMO_ACCOUNTS
        demo_usernames = set(User.objects.filter(is_demo=True).values_list('username', flat=True))
        kwargs['demo_accounts'] = [a for a in DEMO_ACCOUNTS if a[1] in demo_usernames]
        return super().get_context_data(**kwargs)


class PasswordChangeView(auth_views.PasswordChangeView):
    template_name = 'accounts/password_change.html'
    success_url = reverse_lazy('dashboard')

    def form_valid(self, form):
        messages.success(self.request, 'Пароль изменён')
        return super().form_valid(form)
