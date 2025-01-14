# attendance/views.py
import csv
import datetime
import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.db import transaction
from .models import Employee, Attendance, EmployeeSalary, SalaryConfiguration, calculate_monthly_salary
from .forms import EmployeeForm, SalaryConfigurationForm
from .fingerprint_utils import FingerprintScanner, FingerprintError, record_attendance
import logging

logger = logging.getLogger(__name__)

# @login_required
def dashboard(request):
    """Main dashboard view showing attendance overview"""
    today = timezone.now().date()
    present_employees = Attendance.objects.filter(
        date=today,
        check_in__isnull=False,
        check_out__isnull=True
    ).select_related('employee')
    
    context = {
        'present_count': present_employees.count(),
        'present_employees': present_employees,
        'total_employees': Employee.objects.filter(is_active=True).count(),
    }
    return render(request, 'core/dashboard.html', context)

# @login_required
def employee_list(request):
    """Display list of all employees"""
    employees = Employee.objects.select_related('user').all()
    
    context = {
        'employees': employees,
    }
    return render(request, 'core/employee_list.html', context)

# @login_required
def employee_detail(request, pk):
    """Show detailed employee information"""
    employee = get_object_or_404(Employee.objects.select_related('user'), pk=pk)
    today = timezone.now().date()
    attendance = Attendance.objects.filter(
        employee=employee,
        date=today
    ).first()
    
    context = {
        'employee': employee,
        'attendance': attendance,
    }
    return render(request, 'core/employee_detail.html', context)

# @login_required
def enroll_fingerprint(request, employee_id):
    """Handle fingerprint enrollment for an employee"""
    employee = get_object_or_404(Employee, id=employee_id)
    
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            action = data.get('action')
            scanner = FingerprintScanner()
            
            if action == 'start':
                # Initialize enrollment session
                return JsonResponse({'status': 'success', 'message': 'Enrollment started'})
                
            elif action == 'complete':
                # Complete the enrollment process
                template, template_hash = scanner.enroll_fingerprint()
                
                with transaction.atomic():
                    employee.fingerprint_data = template
                    employee.fingerprint_hash = template_hash
                    employee.save()
                
                return JsonResponse({'status': 'success', 'message': 'Enrollment completed'})
            
        except FingerprintError as e:
            return JsonResponse({'status': 'error', 'message': str(e)})
            
        except Exception as e:
            logger.error(f"Unexpected error during enrollment: {str(e)}")
            return JsonResponse({'status': 'error', 'message': 'An unexpected error occurred'})
        
        finally:
            if 'scanner' in locals():
                scanner.clean_scanner()
    
    return render(request, 'core/enroll_fingerprint.html', {'employee': employee})

# @login_required
def scanner_status(request):
    """Check current scanner status during enrollment"""
    try:
        scanner = FingerprintScanner()
        if scanner.scanner.readImage():
            return JsonResponse({'status': 'fingerprint_detected'})
        return JsonResponse({'status': 'waiting'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})
    finally:
        if 'scanner' in locals():
            scanner.clean_scanner()
    """Handle fingerprint enrollment for an employee"""
    employee = get_object_or_404(Employee, id=employee_id)
    
    if request.method == 'POST':
        try:
            scanner = FingerprintScanner()
            
            # Get fingerprint template and hash
            template, template_hash = scanner.enroll_fingerprint()
            
            # Store fingerprint data
            with transaction.atomic():
                employee.fingerprint_data = template
                employee.fingerprint_hash = template_hash
                employee.save()
            
            messages.success(request, 'Fingerprint enrolled successfully!')
            logger.info(f"Fingerprint enrolled for employee {employee.employee_id}")
            
            return JsonResponse({
                'status': 'success',
                'message': 'Fingerprint enrolled successfully'
            })
            
        except FingerprintError as e:
            logger.error(f"Fingerprint enrollment failed for {employee.employee_id}: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': str(e)
            })
            
        except Exception as e:
            logger.error(f"Unexpected error during enrollment: {str(e)}")
            return JsonResponse({
                'status': 'error',
                'message': 'An unexpected error occurred'
            })
        
        finally:
            if 'scanner' in locals():
                scanner.clean_scanner()
    
    return render(request, 'core/enroll_fingerprint.html', {
        'employee': employee
    })

# @login_required
def process_attendance(request):
    """Enhanced attendance processing with hour calculations"""
    try:
        scanner = FingerprintScanner()
        
        # Verify fingerprint and get employee
        employee = scanner.verify_fingerprint(scanner)
        if not employee:
            return JsonResponse({'status': 'error', 'message': 'No matching fingerprint found'})
        
        # Record attendance
        attendance = record_attendance(employee)
        
        # Calculate hours if it's a check-out
        if attendance.check_out:
            attendance.calculate_hours()
        
        # Prepare response message
        if attendance.check_out:
            message = f"Check-out recorded. "
            if attendance.early_leave_hours > 0:
                message += f"Left {attendance.early_leave_hours} hours early. "
            if attendance.overtime_hours > 0:
                message += f"Overtime: {attendance.overtime_hours} hours."
        else:
            message = "Check-in recorded. "
            if attendance.late_hours > 0:
                message += f"Late by {attendance.late_hours} hours."
        
        return JsonResponse({
            'status': 'success',
            'message': message
        })
        
    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        })

def salary_report(request, employee_id=None):
    """Generate salary report for an employee or all employees"""
    month = request.GET.get('month')
    if month:
        month_date = datetime.strptime(month, '%Y-%m').date()
    else:
        month_date = timezone.now().date()
    
    if employee_id:
        employee = get_object_or_404(Employee, id=employee_id)
        salary_records = [calculate_monthly_salary(employee, month_date)]
    else:
        salary_records = []
        for employee in Employee.objects.filter(is_active=True):
            salary_records.append(calculate_monthly_salary(employee, month_date))
    
    context = {
        'salary_records': salary_records,
        'month': month_date,
        'config': SalaryConfiguration.objects.first()
    }
    return render(request, 'attendance/salary_report.html', context)
    """Handle check-in/check-out via fingerprint"""
    try:
        scanner = FingerprintScanner()
        today = timezone.now().date()
        
        # Wait for finger placement
        if not scanner.wait_for_finger():
            return JsonResponse({
                'status': 'error',
                'message': 'No finger detected'
            })
        
        # Try to match with registered employees
        matched_employee = None
        for employee in Employee.objects.filter(fingerprint_data__isnull=False):
            if scanner.verify_fingerprint(employee.fingerprint_data):
                matched_employee = employee
                break
        
        if not matched_employee:
            return JsonResponse({
                'status': 'error',
                'message': 'No matching fingerprint found'
            })
        
        # Handle attendance record
        with transaction.atomic():
            attendance = Attendance.objects.filter(
                employee=matched_employee,
                date=today
            ).first()
            
            if not attendance:
                # Check-in
                attendance = Attendance.objects.create(
                    employee=matched_employee,
                    date=today,
                    check_in=timezone.now()
                )
                action = 'check-in'
            elif not attendance.check_out:
                # Check-out
                attendance.check_out = timezone.now()
                attendance.save()
                action = 'check-out'
            else:
                return JsonResponse({
                    'status': 'error',
                    'message': 'Already checked out for today'
                })
        
        logger.info(f"{action.title()} recorded for employee {matched_employee.employee_id}")
        
        return JsonResponse({
            'status': 'success',
            'message': f'{action.title()} successful',
            'employee_name': matched_employee.get_full_name(),
            'time': timezone.now().strftime('%I:%M %p')
        })
        
    except FingerprintError as e:
        logger.error(f"Fingerprint verification failed: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': str(e)
        })
        
    except Exception as e:
        logger.error(f"Unexpected error during attendance: {str(e)}")
        return JsonResponse({
            'status': 'error',
            'message': 'An unexpected error occurred'
        })
        
    finally:
        if 'scanner' in locals():
            scanner.clean_scanner()

# @login_required
def attendance_report(request, employee_id=None):
    """Generate attendance report for an employee or all employees"""
    start_date = request.GET.get('start_date', timezone.now().date())
    end_date = request.GET.get('end_date', timezone.now().date())
    
    attendance_query = Attendance.objects.filter(
        date__range=[start_date, end_date]
    ).select_related('employee')
    
    if employee_id:
        attendance_query = attendance_query.filter(employee_id=employee_id)
    
    attendance_records = attendance_query.order_by('-date')
    
    context = {
        'attendance_records': attendance_records,
        'start_date': start_date,
        'end_date': end_date,
        'employee_id': employee_id
    }
    return render(request, 'core/attendance_report.html', context)

# @login_required
def create_employee(request):
    """Create new employee record"""
    if request.method == 'POST':
        form = EmployeeForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    employee = form.save()
                    messages.success(request, 'Employee created successfully')
                    return redirect('enroll_fingerprint', employee_id=employee.id)
            except Exception as e:
                messages.error(request, f'Error creating employee: {str(e)}')
    else:
        form = EmployeeForm()
    
    return render(request, 'core/employee_form.html', {'form': form})

# views.py

# @login_required
def salary_report(request):
    """View for displaying salary reports for all employees"""
    # Get the selected month from query params, default to current month
    selected_month = request.GET.get('month')
    if selected_month:
        month_date = datetime.datetime.strptime(selected_month, '%Y-%m').date()
    else:
        today = timezone.now()
        month_date = today.replace(day=1)

    # Get all active employees
    employees = Employee.objects.filter(is_active=True)
    
    # Calculate salary for each employee
    salary_records = []
    for employee in employees:
        try:
            salary_record = calculate_monthly_salary(employee, month_date)
            salary_records.append({
                'employee': employee,
                'salary': salary_record,
                'error': None
            })
        except Exception as e:
            salary_records.append({
                'employee': employee,
                'salary': None,
                'error': str(e)
            })

    # Get salary configuration for reference
    salary_config = SalaryConfiguration.objects.first()

    context = {
        'salary_records': salary_records,
        'selected_month': month_date,
        'salary_config': salary_config,
        # Add previous and next month for navigation
        'prev_month': (month_date - datetime.timedelta(days=1)).replace(day=1),
        'next_month': (month_date + datetime.timedelta(days=32)).replace(day=1)
    }
    
    return render(request, 'core/salary_report.html', context)

# @login_required
def download_salary_report(request):
    """Download salary report as CSV"""
    selected_month = request.GET.get('month')
    if selected_month:
        month_date = datetime.datetime.strptime(selected_month, '%Y-%m').date()
    else:
        month_date = timezone.now().replace(day=1)

    # Create response with CSV header
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="salary_report_{month_date.strftime("%Y_%m")}.csv"'
    
    writer = csv.writer(response)
    writer.writerow([
        'Employee ID',
        'Name',
        'Base Salary',
        'Late Hours',
        'Early Leave Hours',
        'Overtime Hours',
        'Late Deductions',
        'Early Leave Deductions',
        'Overtime Additions',
        'Final Salary'
    ])

    for employee in Employee.objects.filter(is_active=True):
        try:
            salary = calculate_monthly_salary(employee, month_date)
            writer.writerow([
                employee.employee_id,
                employee.get_full_name(),
                salary.base_salary,
                salary.total_late_hours,
                salary.total_early_leave_hours,
                salary.total_overtime_hours,
                salary.late_deductions,
                salary.early_leave_deductions,
                salary.overtime_additions,
                salary.final_salary
            ])
        except Exception as e:
            writer.writerow([
                employee.employee_id,
                employee.get_full_name(),
                'Error calculating salary',
                str(e)
            ])

    return response

# @login_required
def salary_configuration(request):
    """View and edit salary configuration."""
    config = SalaryConfiguration.objects.first()

    if request.method == 'POST':
        form = SalaryConfigurationForm(request.POST, instance=config)
        if form.is_valid():
            form.save()
            messages.success(request, "Salary configuration updated successfully!")
            return redirect('salary_configuration')
    else:
        form = SalaryConfigurationForm(instance=config)

    context = {
        'form': form,
        'config': config,
    }
    return render(request, 'core/salary_configuration.html', context)