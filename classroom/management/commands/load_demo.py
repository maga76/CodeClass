"""python manage.py load_demo — демо-аккаунты и класс с заданиями, чтобы сразу попробовать CodeClass.
python manage.py load_demo --remove — удалить их перед настоящими уроками."""
from django.core.management.base import BaseCommand

from accounts.models import User
from classroom.demo import DEMO_ACCOUNTS, DEMO_CLASS_CODE, load_demo_data
from classroom.models import Classroom


class Command(BaseCommand):
    help = 'Создаёт (или удаляет с --remove) демо-учителя, учеников и класс с заданиями'

    def add_arguments(self, parser):
        parser.add_argument('--remove', action='store_true', help='удалить демо-аккаунты и демо-класс')

    def handle(self, *args, remove=False, **options):
        if remove:
            Classroom.objects.filter(join_code=DEMO_CLASS_CODE).delete()
            count, _ = User.objects.filter(is_demo=True).delete()
            self.stdout.write(self.style.SUCCESS(f'Демо-данные удалены ({count} записей)'))
            return
        teacher, classroom = load_demo_data()
        self.stdout.write(self.style.SUCCESS(
            f'Готово: класс «{classroom.name}» ({classroom.tasks.count()} заданий), код {DEMO_CLASS_CODE}'))
        for role, username, password in DEMO_ACCOUNTS:
            self.stdout.write(f'  {role}: логин {username}, пароль {password}')
