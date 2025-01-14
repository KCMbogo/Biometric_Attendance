from django.contrib import admin
from .models import *

admin.site.register(Employee)
admin.site.register(SalaryConfiguration)
admin.site.register(EmployeeSalary)
admin.site.register(Attendance)