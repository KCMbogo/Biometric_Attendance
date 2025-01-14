from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Employee

class Command(BaseCommand):
    help = 'Set default base salaries for employees that have none'

    def add_arguments(self, parser):
        parser.add_argument('--default-salary', type=float, default=0.00,
                          help='Default base salary to set for employees')

    def handle(self, *args, **options):
        default_salary = options['default_salary']
        
        with transaction.atomic():
            updated_count = Employee.objects.filter(base_salary=0).update(
                base_salary=default_salary
            )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully updated {updated_count} employees with default salary of ${default_salary}'
                )
            )