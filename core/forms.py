from django import forms
from django.contrib.auth.models import User
from .models import Employee
from .models import SalaryConfiguration

class SalaryConfigurationForm(forms.ModelForm):
    class Meta:
        model = SalaryConfiguration
        fields = [
            'standard_work_start', 
            'standard_work_end', 
            'working_hours_per_day',
            'hourly_rate',
            'late_deduction_rate',
            'early_leave_deduction_rate',
            'overtime_fixed_rate',
        ]

class EmployeeForm(forms.ModelForm):
    first_name = forms.CharField(max_length=30)
    last_name = forms.CharField(max_length=30)
    email = forms.EmailField()
    
    class Meta:
        model = Employee
        fields = [
            'employee_id', 'designation', 'date_joined',
            'phone_number', 'emergency_contact', 'address', 'base_salary'
        ]
        widgets = {
            'date_joined': forms.DateInput(attrs={'type': 'date'}),
            'base_salary': forms.NumberInput(attrs={'step': '0.01', 'min': '0'}),
        }
    
    def save(self, commit=True):
        # Get or create User instance
        user_data = {
            'first_name': self.cleaned_data['first_name'],
            'last_name': self.cleaned_data['last_name'],
            'email': self.cleaned_data['email'],
            'username': self.cleaned_data['email']  # Using email as username
        }
        
        if self.instance.pk:
            # Update existing user
            User.objects.filter(employee=self.instance).update(**user_data)
        else:
            # Create new user
            user = User.objects.create(**user_data)
            self.instance.user = user
        
        return super().save(commit)
    
    def clean_base_salary(self):
        base_salary = self.cleaned_data['base_salary']
        if base_salary < 0:
            raise forms.ValidationError("Base salary cannot be negative")
        return base_salary