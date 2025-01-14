# attendance/fingerprint_utils.py
from datetime import date, timezone
from pyexpat.errors import messages
from django.shortcuts import redirect
from pyfingerprint.pyfingerprint import PyFingerprint
import tempfile
import os
import hashlib
import logging
from typing import Optional, Tuple, List
import base64
from django.conf import settings

from core.models import Attendance, Employee

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FingerprintError(Exception):
    """Custom exception for fingerprint-related errors"""
    pass

class FingerprintScanner:
    def __init__(self, port: str = '/dev/ttyUSB0', baudrate: int = 57600):
        """
        Initialize the fingerprint scanner.
        
        Args:
            port (str): Serial port for the scanner
            baudrate (int): Communication speed
            
        Raises:
            FingerprintError: If scanner initialization fails
        """
        try:
            self.scanner = PyFingerprint(
                port=port,
                baudrate=baudrate,
                password=0x00000000,
                address=0xFFFFFFFF
            )
            
            if not self.scanner.verifyPassword():
                raise FingerprintError("Password verification failed!")
            
            logger.info("Fingerprint scanner initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize fingerprint scanner: {str(e)}")
            raise FingerprintError(f"Scanner initialization failed: {str(e)}")
    
    def wait_for_finger(self) -> bool:
        """
        Wait for a finger to be placed on the scanner.
        
        Returns:
            bool: True if finger is detected
            
        Raises:
            FingerprintError: If reading fails
        """
        try:
            logger.info("Waiting for finger...")
            while not self.scanner.readImage():
                pass
            return True
            
        except Exception as e:
            logger.error(f"Error reading fingerprint: {str(e)}")
            raise FingerprintError(f"Failed to read fingerprint: {str(e)}")
    
    def convert_and_store(self, buffer: int = 0x01) -> None:
        """
        Convert the current fingerprint image and store it in the specified buffer.
        
        Args:
            buffer (int): Buffer location (0x01 or 0x02)
            
        Raises:
            FingerprintError: If conversion fails
        """
        try:
            self.scanner.convertImage(buffer)
            
        except Exception as e:
            logger.error(f"Error converting fingerprint: {str(e)}")
            raise FingerprintError(f"Failed to convert fingerprint: {str(e)}")
    
    def create_template(self) -> bytes:
        """
        Create a fingerprint template from the stored characteristics.
        
        Returns:
            bytes: Encoded fingerprint template
            
        Raises:
            FingerprintError: If template creation fails
        """
        try:
            self.scanner.createTemplate()
            characteristics = self.scanner.downloadCharacteristics()
            
            # Convert to bytes and encode
            template = bytes(characteristics)
            encoded_template = base64.b64encode(template)
            
            return encoded_template
            
        except Exception as e:
            logger.error(f"Error creating template: {str(e)}")
            raise FingerprintError(f"Failed to create template: {str(e)}")
    
    def enroll_fingerprint(self) -> Tuple[bytes, str]:
        """
        Enroll a new fingerprint by taking two samples and creating a template.
        
        Returns:
            Tuple[bytes, str]: Encoded template and template hash
            
        Raises:
            FingerprintError: If enrollment fails
        """
        try:
            # First reading
            logger.info("Place finger for first reading...")
            self.wait_for_finger()
            self.convert_and_store(0x01)
            
            # Wait for finger removal
            logger.info("Remove finger...")
            while self.scanner.readImage():
                pass
            
            # Second reading
            logger.info("Place same finger for second reading...")
            self.wait_for_finger()
            self.convert_and_store(0x02)
            
            # Check if prints match
            if self.scanner.compareCharacteristics() == 0:
                raise FingerprintError("Fingerprints do not match! Please try again.")
            
            # Create and store template
            template = self.create_template()
            template_hash = hashlib.sha256(template).hexdigest()
            
            logger.info("Fingerprint enrolled successfully")
            return template, template_hash
            
        except Exception as e:
            logger.error(f"Enrollment failed: {str(e)}")
            raise FingerprintError(f"Enrollment failed: {str(e)}")
    
    def verify_fingerprint(self, stored_template: bytes) -> bool:
        """
        Verify a fingerprint against a stored template.
        
        Args:
            stored_template (bytes): Previously stored template
            
        Returns:
            bool: True if fingerprint matches
            
        Raises:
            FingerprintError: If verification fails
        """
        try:
            # Read current fingerprint
            self.wait_for_finger()
            self.convert_and_store(0x01)
            
            # Load stored template
            decoded_template = base64.b64decode(stored_template)
            self.scanner.uploadCharacteristics(0x02, list(decoded_template))
            
            # Compare fingerprints
            result = self.scanner.compareCharacteristics()
            
            # Use a threshold for matching (adjust as needed)
            threshold = 50
            return result >= threshold
            
        except Exception as e:
            logger.error(f"Verification failed: {str(e)}")
            raise FingerprintError(f"Verification failed: {str(e)}")
    
    def get_scanner_status(self) -> dict:
        """
        Get current status of the fingerprint scanner.
        
        Returns:
            dict: Scanner status information
        """
        try:
            return {
                'scanner_connected': True,
                'template_count': self.scanner.getTemplateCount(),
                'storage_capacity': self.scanner.getStorageCapacity(),
                'security_level': self.scanner.getSecurityLevel()
            }
        except Exception as e:
            logger.error(f"Failed to get scanner status: {str(e)}")
            return {
                'scanner_connected': False,
                'error': str(e)
            }
    
    def clean_scanner(self) -> None:
        """
        Clean up scanner resources and temporary files.
        """
        try:
            # Add any cleanup code here if needed
            logger.info("Scanner cleaned up successfully")
        except Exception as e:
            logger.error(f"Cleanup failed: {str(e)}")

# Example usage in views.py
def enroll_employee_fingerprint(request, employee_id):
    try:
        employee = Employee.objects.get(id=employee_id)
        scanner = FingerprintScanner()
        
        template, template_hash = scanner.enroll_fingerprint()
        
        # Store template in employee record
        employee.fingerprint_data = template
        employee.fingerprint_hash = template_hash
        employee.save()
        
        messages.success(request, "Fingerprint enrolled successfully!")
        return redirect('employee_detail', pk=employee_id)
        
    except FingerprintError as e:
        messages.error(request, str(e))
        return redirect('employee_detail', pk=employee_id)
        
    except Exception as e:
        messages.error(request, f"An unexpected error occurred: {str(e)}")
        return redirect('employee_detail', pk=employee_id)
    
    finally:
        if 'scanner' in locals():
            scanner.clean_scanner()

def record_attendance(employee: Employee) -> Tuple[Attendance, str]:
    """
    Record attendance for an employee with current timestamp.
    
    Args:
        employee (Employee): Employee instance
        
    Returns:
        Tuple[Attendance, str]: Created/updated attendance record and status message
        
    Raises:
        Exception: If attendance recording fails
    """
    try:
        current_time = timezone.now()
        current_date = current_time.date()
        
        # Try to get existing attendance record for today
        attendance = Attendance.objects.filter(
            employee=employee,
            date=current_date
        ).first()
        
        if not attendance:
            # First scan of the day - Create check-in record
            attendance = Attendance.objects.create(
                employee=employee,
                check_in=current_time,
                date=current_date
            )
            return attendance, "check_in"
            
        elif not attendance.check_out:
            # Second scan - Record check-out
            attendance.check_out = current_time
            attendance.save()
            return attendance, "check_out"
            
        else:
            # Already checked out
            raise Exception("Employee has already checked out for today")
            
    except Exception as e:
        logger.error(f"Failed to record attendance: {str(e)}")
        raise Exception(f"Attendance recording failed: {str(e)}")

def verify_attendance(request):
    try:
        scanner = FingerprintScanner()
        
        # Get current fingerprint
        scanner.wait_for_finger()
        
        # Try to match with all employees
        for employee in Employee.objects.filter(fingerprint_data__isnull=False):
            if scanner.verify_fingerprint(employee.fingerprint_data):
                # Record attendance
                attendance, status = record_attendance(employee)
                
                if status == "check_in":
                    messages.success(
                        request, 
                        f"Check-in recorded for {employee.get_full_name()} at {attendance.check_in.strftime('%H:%M:%S')}"
                    )
                else:
                    duration = attendance.get_duration()
                    messages.success(
                        request, 
                        f"Check-out recorded for {employee.get_full_name()} at {attendance.check_out.strftime('%H:%M:%S')}. "
                        f"Duration: {duration}"
                    )
                return redirect('dashboard')
        
        messages.error(request, "No matching fingerprint found")
        return redirect('dashboard')
        
    except Exception as e:
        messages.error(request, str(e))
        return redirect('dashboard')
        
    finally:
        if 'scanner' in locals():
            scanner.clean_scanner()

# Add utility methods for attendance reporting
def get_employee_attendance_summary(employee: Employee, start_date: date, end_date: date) -> dict:
    """
    Get attendance summary for an employee within a date range.
    
    Args:
        employee (Employee): Employee instance
        start_date (date): Start date for report
        end_date (date): End date for report
        
    Returns:
        dict: Attendance summary statistics
    """
    attendance_records = Attendance.objects.filter(
        employee=employee,
        date__range=[start_date, end_date]
    )
    
    total_days = (end_date - start_date).days + 1
    present_days = attendance_records.count()
    
    # Calculate total working hours
    total_hours = timezone.timedelta()
    for record in attendance_records:
        if record.check_in and record.check_out:
            total_hours += record.get_duration()
    
    return {
        'total_days': total_days,
        'present_days': present_days,
        'absent_days': total_days - present_days,
        'total_hours': total_hours,
        'attendance_percentage': (present_days / total_days) * 100 if total_days > 0 else 0
    }

def get_late_check_ins(employee: Employee, month: Optional[date] = None) -> List[Attendance]:
    """
    Get list of late check-ins for an employee.
    
    Args:
        employee (Employee): Employee instance
        month (date, optional): Specific month to check
        
    Returns:
        List[Attendance]: List of late check-in records
    """
    if not month:
        month = timezone.now().date()
    
    # Define work start time (e.g., 9:00 AM)
    work_start_time = timezone.datetime.strptime('09:00', '%H:%M').time()
    
    late_records = Attendance.objects.filter(
        employee=employee,
        date__month=month.month,
        date__year=month.year,
        check_in__time__gt=work_start_time
    )
    
    return late_records
    try:
        scanner = FingerprintScanner()
        
        # Get current fingerprint
        scanner.wait_for_finger()
        
        # Try to match with all employees (in production, use indexing for better performance)
        for employee in Employee.objects.filter(fingerprint_data__isnull=False):
            if scanner.verify_fingerprint(employee.fingerprint_data):
                # Record attendance
                record_attendance(employee)
                messages.success(request, f"Attendance recorded for {employee.get_full_name()}")
                return redirect('dashboard')
        
        messages.error(request, "No matching fingerprint found")
        return redirect('dashboard')
        
    except FingerprintError as e:
        messages.error(request, str(e))
        return redirect('dashboard')
        
    finally:
        if 'scanner' in locals():
            scanner.clean_scanner()