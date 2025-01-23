import datetime
from decimal import Decimal
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.validators import RegexValidator

# class Department(models.Model):
#     name = models.CharField(max_length=100, unique=True)
#     description = models.TextField(blank=True)
    
#     def __str__(self):
#         return self.name

class Employee(models.Model):
    # Link to Django's built-in User model for authentication
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    
    # Employee Details
    employee_id = models.CharField(
        max_length=20, 
        unique=True,
        validators=[
            RegexValidator(
                regex='^EMP\d{4}$',
                message='Employee ID must be in format EMP1234'
            )
        ]
    )
    # department = models.ForeignKey(Department, on_delete=models.PROTECT)
    designation = models.CharField(max_length=100)
    date_joined = models.DateField()
    base_salary = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        default=0.00,
        help_text="Monthly base salary amount"
    )
    # Contact Information
    phone_number = models.CharField(max_length=15)
    emergency_contact = models.CharField(max_length=15)
    address = models.TextField()
    
    # Biometric Data
    fingerprint_data = models.BinaryField(null=True, blank=True)
    fingerprint_template_id = models.IntegerField(null=True, blank=True)
    
    # Status
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['employee_id']
    
    def __str__(self):
        return f"{self.employee_id} - {self.user.get_full_name()}"
    
    def get_full_name(self):
        return self.user.get_full_name()


# models.py

class SalaryConfiguration(models.Model):
    """Global salary configuration settings"""
    standard_work_start = models.TimeField(default='09:00')
    standard_work_end = models.TimeField(default='17:00')
    working_hours_per_day = models.DecimalField(max_digits=4, decimal_places=2, default=8.00)
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, help_text="Base hourly rate for calculations")
    late_deduction_rate = models.DecimalField(max_digits=6, decimal_places=2, help_text="Deduction rate per hour of lateness")
    early_leave_deduction_rate = models.DecimalField(max_digits=6, decimal_places=2, help_text="Deduction rate per hour of early leaving")
    overtime_fixed_rate = models.DecimalField(max_digits=6, decimal_places=2, help_text="Fixed rate per overtime hour")
    
    class Meta:
        verbose_name = "Salary Configuration"
        verbose_name_plural = "Salary Configurations"

def calculate_monthly_salary(employee, month_date):
    """
    Calculate monthly salary with deductions for missed hours and overtime compensation
    
    Args:
        employee (Employee): Employee instance
        month_date (date): Month for salary calculation
    
    Returns:
        EmployeeSalary: Calculated salary record
    """
    # Get salary configuration
    config = SalaryConfiguration.objects.first()
    if not config:
        raise ValueError("Salary configuration not found")
    
    # Get or create salary record for the month
    salary_record, created = EmployeeSalary.objects.get_or_create(
        employee=employee,
        month=month_date.replace(day=1),
        defaults={'base_salary': employee.base_salary}
    )
    
    # Get attendance records for the month
    attendance_records = Attendance.objects.filter(
        employee=employee,
        date__year=month_date.year,
        date__month=month_date.month
    )
    
    # Initialize totals
    total_late_hours = Decimal('0.00')
    total_early_leave_hours = Decimal('0.00')
    total_overtime_hours = Decimal('0.00')
    
    # Calculate totals from attendance records
    for record in attendance_records:
        if record.check_in and record.check_out:
            # Calculate late hours
            check_in_time = record.check_in.time()
            if check_in_time > config.standard_work_start:
                time_diff = datetime.datetime.combine(record.date, check_in_time) - \
                           datetime.datetime.combine(record.date, config.standard_work_start)
                total_late_hours += Decimal(time_diff.total_seconds() / 3600).quantize(Decimal('0.01'))
            
            # Calculate early leave hours
            check_out_time = record.check_out.time()
            if check_out_time < config.standard_work_end:
                time_diff = datetime.datetime.combine(record.date, config.standard_work_end) - \
                           datetime.datetime.combine(record.date, check_out_time)
                total_early_leave_hours += Decimal(time_diff.total_seconds() / 3600).quantize(Decimal('0.01'))
            
            # Calculate overtime hours
            if check_out_time > config.standard_work_end:
                time_diff = datetime.datetime.combine(record.date, check_out_time) - \
                           datetime.datetime.combine(record.date, config.standard_work_end)
                total_overtime_hours += Decimal(time_diff.total_seconds() / 3600).quantize(Decimal('0.01'))
    
    # Update salary record with totals
    salary_record.total_late_hours = total_late_hours
    salary_record.total_early_leave_hours = total_early_leave_hours
    salary_record.total_overtime_hours = total_overtime_hours
    
    # Calculate deductions
    late_deductions = total_late_hours * config.late_deduction_rate
    early_leave_deductions = total_early_leave_hours * config.early_leave_deduction_rate
    
    # Calculate overtime compensation (fixed rate per hour)
    overtime_compensation = total_overtime_hours * config.overtime_fixed_rate
    
    # Calculate final salary
    salary_record.late_deductions = late_deductions
    salary_record.early_leave_deductions = early_leave_deductions
    salary_record.overtime_additions = overtime_compensation
    salary_record.final_salary = (
        salary_record.base_salary - 
        late_deductions - 
        early_leave_deductions + 
        overtime_compensation
    )
    
    salary_record.save()
    return salary_record

class EmployeeSalary(models.Model):
    """Employee base salary and monthly calculations"""
    employee = models.ForeignKey('Employee', on_delete=models.CASCADE)
    base_salary = models.DecimalField(max_digits=10, decimal_places=2)
    month = models.DateField()  # Store first day of the month
    total_late_hours = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    total_early_leave_hours = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    total_overtime_hours = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    late_deductions = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    early_leave_deductions = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    overtime_additions = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    final_salary = models.DecimalField(max_digits=10, decimal_places=2, default=100000)
    
    class Meta:
        unique_together = ['employee', 'month']
        ordering = ['-month']
        verbose_name_plural = 'Employee salaries'

    def calculate_final_salary(self):
        """Calculate final salary after deductions and additions"""
        config = SalaryConfiguration.objects.first()
        
        # Calculate deductions
        self.late_deductions = self.total_late_hours * config.late_deduction_rate
        self.early_leave_deductions = self.total_early_leave_hours * config.early_leave_deduction_rate
        
        # Calculate overtime additions
        self.overtime_additions = self.total_overtime_hours * config.overtime_fixed_rate
        
        # Calculate final salary
        self.final_salary = (
            self.base_salary - 
            self.late_deductions - 
            self.early_leave_deductions + 
            self.overtime_additions
        )
        self.save()

# Update Attendance model to include work hour calculations
class Attendance(models.Model):
    """Enhanced attendance model with work hour calculations"""
    employee = models.ForeignKey('Employee', on_delete=models.CASCADE)
    date = models.DateField()
    check_in = models.DateTimeField(null=True)
    check_out = models.DateTimeField(null=True)
    late_hours = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    early_leave_hours = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    overtime_hours = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    
    def calculate_hours(self):
        """Calculate late, early leave, and overtime hours"""
        if not (self.check_in and self.check_out):
            return
            
        config = SalaryConfiguration.objects.first()
        
        # Convert times to datetime.time for comparison
        check_in_time = self.check_in.time()
        check_out_time = self.check_out.time()
        
        # Calculate late hours
        if check_in_time > config.standard_work_start:
            time_diff = datetime.combine(self.date, check_in_time) - datetime.combine(self.date, config.standard_work_start)
            self.late_hours = Decimal(time_diff.total_seconds() / 3600).quantize(Decimal('0.01'))
        
        # Calculate early leave hours
        if check_out_time < config.standard_work_end:
            time_diff = datetime.combine(self.date, config.standard_work_end) - datetime.combine(self.date, check_out_time)
            self.early_leave_hours = Decimal(time_diff.total_seconds() / 3600).quantize(Decimal('0.01'))
        
        # Calculate overtime hours
        if check_out_time > config.standard_work_end:
            time_diff = datetime.combine(self.date, check_out_time) - datetime.combine(self.date, config.standard_work_end)
            self.overtime_hours = Decimal(time_diff.total_seconds() / 3600).quantize(Decimal('0.01'))
        
        self.save()

def calculate_monthly_salary(employee, month_date):
    """Calculate monthly salary based on attendance"""
    # Get or create salary record for the month
    salary_record, created = EmployeeSalary.objects.get_or_create(
        employee=employee,
        month=month_date.replace(day=1),
        defaults={'base_salary': employee.base_salary}
    )
    
    # Get all attendance records for the month
    attendance_records = Attendance.objects.filter(
        employee=employee,
        date__year=month_date.year,
        date__month=month_date.month
    )
    
    # Calculate totals
    salary_record.total_late_hours = sum(record.late_hours for record in attendance_records)
    salary_record.total_early_leave_hours = sum(record.early_leave_hours for record in attendance_records)
    salary_record.total_overtime_hours = sum(record.overtime_hours for record in attendance_records)
    
    # Calculate final salary
    salary_record.calculate_final_salary()
    
    return salary_record
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE)
    date = models.DateField(auto_now_add=True)
    check_in = models.DateTimeField(null=True)
    check_out = models.DateTimeField(null=True)
    
    def get_duration(self):
        if self.check_in and self.check_out:
            return self.check_out - self.check_in
        return None