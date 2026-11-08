from django import forms

from .judge import validate_html_rule
from .models import Classroom, ManualGrade, Task, TestCase


class ClassroomForm(forms.ModelForm):
    class Meta:
        model = Classroom
        fields = ('name',)


class JoinClassroomForm(forms.Form):
    join_code = forms.CharField(label='Код класса', max_length=6)

    def clean_join_code(self):
        code = self.cleaned_data['join_code'].strip().upper()
        try:
            self.classroom = Classroom.objects.get(join_code=code)
        except Classroom.DoesNotExist:
            raise forms.ValidationError('Класс с таким кодом не найден')
        return code


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ('title', 'description', 'language', 'deadline')
        widgets = {
            'description': forms.Textarea(attrs={'rows': 8}),
            'deadline': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
        }


class BaseTestCaseFormSet(forms.BaseInlineFormSet):
    language = None  # проставляется во view после проверки формы задания

    def clean(self):
        super().clean()
        if self.language != Task.Language.HTML:
            return
        for form in self.forms:
            if not form.has_changed() or self._should_delete_form(form) or 'input_data' not in form.cleaned_data:
                continue
            error = validate_html_rule(form.cleaned_data['input_data'])
            if error:
                form.add_error('input_data', error)


TestCaseFormSet = forms.inlineformset_factory(
    Task, TestCase, formset=BaseTestCaseFormSet,
    fields=('input_data', 'expected_output', 'is_hidden'),
    widgets={
        'input_data': forms.Textarea(attrs={'rows': 3, 'class': 'mono'}),
        'expected_output': forms.Textarea(attrs={'rows': 3, 'class': 'mono'}),
    },
    extra=2, can_delete=True,
)


class ManualGradeForm(forms.ModelForm):
    class Meta:
        model = ManualGrade
        fields = ('score', 'comment')
        widgets = {'score': forms.NumberInput(attrs={'min': 1, 'max': 10})}


class SubmissionForm(forms.Form):
    code = forms.CharField(label='', widget=forms.Textarea(attrs={
        'rows': 18, 'class': 'mono code-editor', 'spellcheck': 'false'}))
