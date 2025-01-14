from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('employees/', views.employee_list, name='employee_list'),
    path('employees/create/', views.create_employee, name='create_employee'),
    path('employees/<int:pk>/', views.employee_detail, name='employee_detail'),
    path('enroll-fingerprint/<int:employee_id>/', views.enroll_fingerprint, name='enroll_fingerprint'),
    path('process-attendance/', views.process_attendance, name='process_attendance'),
    path('attendance-report/', views.attendance_report, name='attendance_report'),
    path('attendance-report/<int:employee_id>/', views.attendance_report, name='employee_attendance_report'),
    path('scanner-status/', views.scanner_status, name='scanner_status'),
    path('salary-report/', views.salary_report, name='salary_report'),
    path('salary-report/download/', views.download_salary_report, name='download_salary_report'),
    path('salary-configuration/', views.salary_configuration, name='salary_configuration'),
]