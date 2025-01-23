# attendance/fingerprint_utils.py
from datetime import date, timezone
from pyexpat.errors import messages
from django.shortcuts import redirect
import serial
import time
import base64
import hashlib
import logging
from typing import Optional, Tuple, List
from django.conf import settings

from core.models import Attendance, Employee

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FingerprintError(Exception):
    """Custom exception for fingerprint-related errors"""
    pass

class FingerprintScanner:
    def __init__(self, port: str = '/dev/ttyACM0', baudrate: int = 9600, timeout: int = 1):
        """
        Initialize the Arduino fingerprint scanner connection.
        
        Args:
            port (str): Serial port for Arduino connection
            baudrate (int): Communication speed
            timeout (int): Serial timeout in seconds
            
        Raises:
            FingerprintError: If scanner initialization fails
        """
        try:
            self.serial = serial.Serial(
                port=port,
                baudrate=baudrate,
                timeout=timeout
            )
            time.sleep(2)  # Wait for Arduino to reset
            
            # Test connection
            self.serial.write(b'TEST\n')
            response = self._read_response()
            if response != 'OK':
                raise FingerprintError("Arduino not responding correctly")
            
            logger.info("Arduino fingerprint scanner initialized successfully")
            
        except serial.SerialException as e:
            logger.error(f"Failed to connect to Arduino: {str(e)}")
            raise FingerprintError(f"Arduino connection failed: {str(e)}")
        except Exception as e:
            logger.error(f"Failed to initialize scanner: {str(e)}")
            raise FingerprintError(f"Scanner initialization failed: {str(e)}")
    
    def _read_response(self, timeout: int = 10) -> str:
        """
        Read response from Arduino with timeout.
        
        Args:
            timeout (int): Maximum wait time in seconds
            
        Returns:
            str: Response from Arduino
            
        Raises:
            FingerprintError: If reading times out
        """
        start_time = time.time()
        response = ''
        
        while time.time() - start_time < timeout:
            if self.serial.in_waiting:
                char = self.serial.read().decode('utf-8')
                if char == '\n':
                    return response.strip()
                response += char
        
        raise FingerprintError("Timeout waiting for Arduino response")
    
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
            self.serial.write(b'SCAN\n')
            
            while True:
                response = self._read_response()
                if response == 'DETECTED':
                    return True
                elif response == 'ERROR':
                    raise FingerprintError("Error detecting finger")
                time.sleep(0.1)
                
        except Exception as e:
            logger.error(f"Error reading fingerprint: {str(e)}")
            raise FingerprintError(f"Failed to read fingerprint: {str(e)}")
    
    def enroll_fingerprint(self) -> Tuple[bytes, str]:
        """
        Enroll a new fingerprint by taking two samples and creating a template.
        
        Returns:
            Tuple[bytes, str]: Encoded template and template hash
            
        Raises:
            FingerprintError: If enrollment fails
        """
        try:
            # Start enrollment process
            logger.info("Starting enrollment...")
            self.serial.write(b'ENROLL\n')
            
            # Wait for first reading
            logger.info("Place finger for first reading...")
            while self._read_response() != 'PLACE_FIRST':
                pass
            
            # Wait for removal prompt
            while self._read_response() != 'REMOVE':
                pass
                
            logger.info("Remove finger...")
            time.sleep(2)
            
            # Wait for second reading
            logger.info("Place same finger for second reading...")
            while self._read_response() != 'PLACE_SECOND':
                pass
            
            # Get template
            response = self._read_response()
            if response.startswith('TEMPLATE:'):
                template_str = response[9:]  # Remove 'TEMPLATE:' prefix
                template = base64.b64decode(template_str.encode())
                template_hash = hashlib.sha256(template).hexdigest()
                
                logger.info("Fingerprint enrolled successfully")
                return template, template_hash
            else:
                raise FingerprintError("Failed to get template from Arduino")
            
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
            # Send stored template to Arduino
            template_str = base64.b64encode(stored_template).decode()
            self.serial.write(f'VERIFY:{template_str}\n'.encode())
            
            # Wait for finger placement
            logger.info("Place finger to verify...")
            while self._read_response() != 'PLACE_FINGER':
                pass
            
            # Get verification result
            response = self._read_response()
            if response == 'MATCH':
                return True
            elif response == 'NO_MATCH':
                return False
            else:
                raise FingerprintError("Invalid response from Arduino")
            
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
            self.serial.write(b'STATUS\n')
            response = self._read_response()
            
            if response.startswith('STATUS:'):
                status_data = response[7:].split(',')
                return {
                    'scanner_connected': True,
                    'sensor_status': status_data[0],
                    'image_quality': int(status_data[1]) if len(status_data) > 1 else None
                }
            else:
                return {
                    'scanner_connected': False,
                    'error': 'Invalid status response'
                }
                
        except Exception as e:
            logger.error(f"Failed to get scanner status: {str(e)}")
            return {
                'scanner_connected': False,
                'error': str(e)
            }
    
    def clean_scanner(self) -> None:
        """
        Clean up scanner resources and close serial connection.
        """
        try:
            if hasattr(self, 'serial') and self.serial.is_open:
                self.serial.close()
            logger.info("Scanner cleaned up successfully")
        except Exception as e:
            logger.error(f"Cleanup failed: {str(e)}")



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