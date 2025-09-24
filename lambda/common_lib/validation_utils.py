"""
Validation utilities for common input validation patterns
Centralizes validation logic across Lambda functions
"""

import re
from datetime import datetime
from zoneinfo import ZoneInfo
from decimal import Decimal, InvalidOperation


class ValidationError(Exception):
    """Custom exception for validation errors"""
    def __init__(self, message, field=None):
        self.message = message
        self.field = field
        super().__init__(self.message)


class DataValidator:
    """Common data validation patterns"""
    
    @staticmethod
    def validate_required_fields(data, required_fields):
        """
        Validate that all required fields are present and not empty
        
        Args:
            data (dict): Data to validate
            required_fields (list): List of required field names
            
        Raises:
            ValidationError: If any required field is missing or empty
        """
        if not isinstance(data, dict):
            raise ValidationError("Data must be a dictionary")
        
        for field in required_fields:
            if field not in data or data[field] is None or data[field] == '':
                raise ValidationError(f"Field '{field}' is required", field)
    
    @staticmethod
    def validate_email(email, field_name="email"):
        """
        Validate email format using regex
        
        Args:
            email (str): Email to validate
            field_name (str): Field name for error messages
            
        Returns:
            bool: True if valid
            
        Raises:
            ValidationError: If email is invalid
        """
        if not email or not isinstance(email, str):
            raise ValidationError(f"{field_name} must be a valid string", field_name)
        
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, email):
            raise ValidationError(f"{field_name} must be a valid email address", field_name)
        
        return True
    
    @staticmethod
    def validate_phone_number(phone, field_name="phone"):
        """
        Validate phone number format
        
        Args:
            phone (str): Phone number to validate
            field_name (str): Field name for error messages
            
        Returns:
            bool: True if valid
            
        Raises:
            ValidationError: If phone number is invalid
        """
        if not phone or not isinstance(phone, str):
            raise ValidationError(f"{field_name} must be a valid string", field_name)
        
        # Remove spaces, dashes, and parentheses for validation
        clean_phone = re.sub(r'[\s\-\(\)]', '', phone)
        
        # Allow international format starting with + or domestic format
        phone_pattern = r'^(\+\d{1,3})?\d{7,15}$'
        if not re.match(phone_pattern, clean_phone):
            raise ValidationError(f"{field_name} must be a valid phone number", field_name)
        
        return True
    
    @staticmethod
    def validate_year(year, field_name="year"):
        """
        Validate year value
        
        Args:
            year: Year to validate
            field_name (str): Field name for error messages
            
        Returns:
            bool: True if valid
            
        Raises:
            ValidationError: If year is invalid
        """
        try:
            year_int = int(year)
            current_year = datetime.now(ZoneInfo('Australia/Perth')).year
            if year_int < 1900 or year_int > current_year + 1:
                raise ValidationError(f"{field_name} must be between 1900 and {current_year + 1}", field_name)
            return True
        except (ValueError, TypeError):
            raise ValidationError(f"{field_name} must be a valid integer", field_name)
    
    @staticmethod
    def validate_positive_number(value, field_name="value"):
        """
        Validate positive number
        
        Args:
            value: Value to validate
            field_name (str): Field name for error messages
            
        Returns:
            bool: True if valid
            
        Raises:
            ValidationError: If value is not a positive number
        """
        try:
            num_value = float(value)
            if num_value <= 0:
                raise ValidationError(f"{field_name} must be a positive number", field_name)
            return True
        except (ValueError, TypeError):
            raise ValidationError(f"{field_name} must be a valid number", field_name)
    
    @staticmethod
    def validate_string_length(value, min_length=None, max_length=None, field_name="value"):
        """
        Validate string length
        
        Args:
            value (str): String to validate
            min_length (int): Minimum length (optional)
            max_length (int): Maximum length (optional)
            field_name (str): Field name for error messages
            
        Returns:
            bool: True if valid
            
        Raises:
            ValidationError: If length is invalid
        """
        if not isinstance(value, str):
            raise ValidationError(f"{field_name} must be a string", field_name)
        
        length = len(value)
        
        if min_length is not None and length < min_length:
            raise ValidationError(f"{field_name} must be at least {min_length} characters", field_name)
        
        if max_length is not None and length > max_length:
            raise ValidationError(f"{field_name} must be no more than {max_length} characters", field_name)
        
        return True
    
    @staticmethod
    def validate_list_not_empty(value, field_name="value"):
        """
        Validate that a list is not empty
        
        Args:
            value (list): List to validate
            field_name (str): Field name for error messages
            
        Returns:
            bool: True if valid
            
        Raises:
            ValidationError: If list is empty or not a list
        """
        if not isinstance(value, list):
            raise ValidationError(f"{field_name} must be a list", field_name)
        
        if len(value) == 0:
            raise ValidationError(f"{field_name} cannot be empty", field_name)
        
        return True

    @staticmethod
    def validate_and_convert_date_to_analytics_format(date_value, field_name="date"):
        """
        Validate and convert various date formats to analytics format (DD/MM/YYYY)
        
        This function handles multiple input formats and converts them to the standardized
        DD/MM/YYYY format required by the analytics system.
        
        Supported input formats:
        - DD/MM/YYYY (analytics format - returned as-is)
        - YYYY-MM-DD (ISO format)
        - DD Month YYYY (e.g., "20 September 2025")
        - DD-MM-YYYY
        - MM/DD/YYYY (US format)
        - YYYY/MM/DD
        - DD Mon YYYY (e.g., "20 Sep 2025")
        
        Args:
            date_value (str): Date string to validate and convert
            field_name (str): Field name for error messages
            
        Returns:
            str: Date in DD/MM/YYYY format (e.g., "20/09/2025")
            
        Raises:
            ValidationError: If date format is invalid or date cannot be parsed
        """
        if not date_value or not isinstance(date_value, str):
            raise ValidationError(f"{field_name} must be a non-empty string", field_name)
        
        date_value = date_value.strip()
        
        # If already in DD/MM/YYYY format, validate and return as-is
        try:
            parsed_date = datetime.strptime(date_value, '%d/%m/%Y')
            return date_value  # Already in correct format
        except ValueError:
            pass
        
        # List of other date formats to try
        date_formats = [
            '%Y-%m-%d',      # ISO format
            '%d %B %Y',      # DD Month YYYY (e.g., "20 September 2025")
            '%d-%m-%Y',      # DD-MM-YYYY
            '%m/%d/%Y',      # MM/DD/YYYY (US format)
            '%Y/%m/%d',      # YYYY/MM/DD
            '%d %b %Y',      # DD Mon YYYY (e.g., "20 Sep 2025")
        ]
        
        parsed_date = None
        
        for date_format in date_formats:
            try:
                parsed_date = datetime.strptime(date_value, date_format)
                break
            except ValueError:
                continue
        
        if parsed_date is None:
            raise ValidationError(
                f"Invalid date format for {field_name}: '{date_value}'. "
                f"Supported formats: DD/MM/YYYY, YYYY-MM-DD, DD Month YYYY, etc.",
                field_name
            )
        
        # Return in analytics format (DD/MM/YYYY)
        return parsed_date.strftime('%d/%m/%Y')


class AppointmentDataValidator:
    """Specialized validator for appointment data"""
    
    @staticmethod
    def validate_appointment_data(appointment_data, staff_user=False):
        """
        Validate appointment data structure and content
        
        Args:
            appointment_data (dict): Appointment data to validate
            staff_user (bool): Whether this is a staff user (affects validation)
            
        Returns:
            tuple: (is_valid, error_message)
        """
        try:
            if not appointment_data:
                raise ValidationError("Appointment data is required")
            
            if not isinstance(appointment_data, dict):
                raise ValidationError("Appointment data must be a dictionary")
            
            # Define required and optional fields
            required_fields = ['serviceId', 'planId', 'isBuyer', 'carData']
            
            if not staff_user:
                required_fields.append('selectedSlots')
            
            # Validate required fields
            DataValidator.validate_required_fields(appointment_data, required_fields)
            
            # Validate specific field types
            if not isinstance(appointment_data.get('serviceId'), int):
                raise ValidationError("serviceId must be an integer", 'serviceId')
            
            if not isinstance(appointment_data.get('planId'), int):
                raise ValidationError("planId must be an integer", 'planId')
            
            # Determine which data field is required based on isBuyer value
            is_buyer_value = appointment_data.get('isBuyer')
            if is_buyer_value is True:
                DataValidator.validate_required_fields(appointment_data, ['buyerData'])
                AppointmentDataValidator._validate_person_data(appointment_data['buyerData'], 'buyerData')
            elif is_buyer_value is False:
                DataValidator.validate_required_fields(appointment_data, ['sellerData'])
                AppointmentDataValidator._validate_person_data(appointment_data['sellerData'], 'sellerData')
            else:
                raise ValidationError("isBuyer must be true or false", 'isBuyer')
            
            # Validate car data
            AppointmentDataValidator._validate_car_data(appointment_data['carData'])
            
            # Validate selected slots if provided
            if 'selectedSlots' in appointment_data:
                AppointmentDataValidator._validate_selected_slots(appointment_data['selectedSlots'], required=not staff_user)
            
            return True, ""
            
        except ValidationError as e:
            return False, e.message
        except Exception as e:
            return False, f"Unexpected validation error: {str(e)}"
    
    @staticmethod
    def _validate_person_data(person_data, data_type):
        """Validate buyer/seller data"""
        # Handle both phoneNumber (legacy) and contactNumber (new) field names
        required_fields = ['name', 'email']
        if 'phoneNumber' in person_data:
            required_fields.append('phoneNumber')
            phone_field = 'phoneNumber'
        elif 'contactNumber' in person_data:
            required_fields.append('contactNumber')
            phone_field = 'contactNumber'
        else:
            raise ValidationError(f"{data_type} must contain either phoneNumber or contactNumber")
        
        DataValidator.validate_required_fields(person_data, required_fields)
        
        DataValidator.validate_email(person_data['email'], f"{data_type}.email")
        DataValidator.validate_phone_number(person_data[phone_field], f"{data_type}.{phone_field}")
        DataValidator.validate_string_length(person_data['name'], min_length=1, max_length=100, field_name=f"{data_type}.name")
    
    @staticmethod
    def _validate_car_data(car_data):
        """Validate car data"""
        required_fields = ['make', 'model', 'year']
        DataValidator.validate_required_fields(car_data, required_fields)
        
        DataValidator.validate_year(car_data['year'], 'carData.year')
        DataValidator.validate_string_length(car_data['make'], min_length=1, max_length=50, field_name='carData.make')
        DataValidator.validate_string_length(car_data['model'], min_length=1, max_length=50, field_name='carData.model')
        
        # registrationNumber is optional in the original code
        if 'registrationNumber' in car_data:
            DataValidator.validate_string_length(car_data['registrationNumber'], min_length=1, max_length=20, field_name='carData.registrationNumber')
    
    @staticmethod
    def _validate_selected_slots(selected_slots, required=True):
        """Validate selected time slots"""
        if not isinstance(selected_slots, list):
            raise ValidationError("selectedSlots must be an array", 'selectedSlots')
        
        if required and len(selected_slots) == 0:
            raise ValidationError("At least one selected time slot is required", 'selectedSlots')
        
        for i, slot in enumerate(selected_slots):
            if not isinstance(slot, dict):
                raise ValidationError(f"selectedSlots[{i}] must be an object", 'selectedSlots')
            
            required_slot_fields = ['date', 'start', 'end', 'priority']
            for field in required_slot_fields:
                if field not in slot:
                    raise ValidationError(f"selectedSlots[{i}] must contain {field}", 'selectedSlots')
            
            # Validate field types
            if not isinstance(slot['date'], str):
                raise ValidationError(f"selectedSlots[{i}].date must be a string", 'selectedSlots')
            if not isinstance(slot['start'], str):
                raise ValidationError(f"selectedSlots[{i}].start must be a string", 'selectedSlots')
            if not isinstance(slot['end'], str):
                raise ValidationError(f"selectedSlots[{i}].end must be a string", 'selectedSlots')
            if not isinstance(slot['priority'], int):
                raise ValidationError(f"selectedSlots[{i}].priority must be an integer", 'selectedSlots')


class OrderDataValidator:
    """Specialized validator for order data"""
    
    @staticmethod
    def validate_order_data(order_data, staff_user=False):
        """
        Validate order data structure and content
        
        Args:
            order_data (dict): Order data to validate
            staff_user (bool): Whether this is a staff user (affects validation)
            
        Returns:
            tuple: (is_valid, error_message)
        """
        try:
            if not order_data:
                raise ValidationError("Order data is required")
            
            if not isinstance(order_data, dict):
                raise ValidationError("Order data must be a dictionary")
            
            # Define required fields
            required_fields = ['items', 'customerData', 'carData']
            DataValidator.validate_required_fields(order_data, required_fields)
            
            # Validate items
            OrderDataValidator._validate_items(order_data['items'])
            
            # Validate customer data
            OrderDataValidator._validate_customer_data(order_data['customerData'])
            
            # Validate car data
            AppointmentDataValidator._validate_car_data(order_data['carData'])
            
            return True, ""
            
        except ValidationError as e:
            return False, e.message
        except Exception as e:
            return False, f"Unexpected validation error: {str(e)}"
    
    @staticmethod
    def _validate_items(items):
        """Validate order items"""
        DataValidator.validate_list_not_empty(items, 'items')
        
        if len(items) > 10:  # Maximum items per order
            raise ValidationError("Maximum 10 items allowed per order", 'items')
        
        for i, item in enumerate(items):
            field_prefix = f"items[{i}]"
            
            if not isinstance(item, dict):
                raise ValidationError(f"{field_prefix} must be an object", 'items')
            
            required_fields = ['categoryId', 'itemId', 'quantity']
            DataValidator.validate_required_fields(item, required_fields)
            
            # Validate types and values
            try:
                category_id = int(item['categoryId'])
                item_id = int(item['itemId'])
                quantity = int(item['quantity'])
                
                if category_id <= 0:
                    raise ValidationError(f"{field_prefix}.categoryId must be a positive integer", 'items')
                if item_id <= 0:
                    raise ValidationError(f"{field_prefix}.itemId must be a positive integer", 'items')
                if quantity <= 0:
                    raise ValidationError(f"{field_prefix}.quantity must be a positive integer", 'items')
                if quantity > 30:  # Maximum quantity per item
                    raise ValidationError(f"{field_prefix}.quantity maximum is 30", 'items')
                    
            except (ValueError, TypeError):
                raise ValidationError(f"{field_prefix} categoryId, itemId, and quantity must be valid integers", 'items')
    
    @staticmethod
    def _validate_customer_data(customer_data):
        """Validate customer data"""
        # Handle both phoneNumber (legacy) and contactNumber (new) field names
        required_fields = ['name', 'email']
        if 'phoneNumber' in customer_data:
            required_fields.append('phoneNumber')
            phone_field = 'phoneNumber'
        elif 'contactNumber' in customer_data:
            required_fields.append('contactNumber')
            phone_field = 'contactNumber'
        else:
            raise ValidationError("customerData must contain either phoneNumber or contactNumber")
        
        DataValidator.validate_required_fields(customer_data, required_fields)
        
        DataValidator.validate_email(customer_data['email'], 'customerData.email')
        DataValidator.validate_phone_number(customer_data[phone_field], f'customerData.{phone_field}')
        DataValidator.validate_string_length(customer_data['name'], min_length=1, max_length=100, field_name='customerData.name')


class ValidationManager:
    """
    Legacy compatibility class for existing code that expects ValidationManager
    Wraps the new validator classes for backward compatibility
    """
    
    def __init__(self):
        self.data_validator = DataValidator()
        self.appointment_validator = AppointmentDataValidator()
        self.order_validator = OrderDataValidator()
    
    def validate_required_fields(self, data, required_fields):
        """Validate required fields using DataValidator"""
        return self.data_validator.validate_required_fields(data, required_fields)
    
    def validate_email(self, email, field_name="email"):
        """Validate email using DataValidator"""
        return self.data_validator.validate_email(email, field_name)
    
    def validate_phone_number(self, phone, field_name="phone"):
        """Validate phone number using DataValidator"""
        return self.data_validator.validate_phone_number(phone, field_name)
    
    def validate_appointment_data(self, appointment_data, staff_user=False):
        """Validate appointment data using AppointmentDataValidator"""
        return self.appointment_validator.validate_appointment_data(appointment_data, staff_user)
    
    def validate_order_data(self, order_data, staff_user=False):
        """Validate order data using OrderDataValidator"""
        return self.order_validator.validate_order_data(order_data, staff_user)
    
    def validate_positive_number(self, value, field_name="value"):
        """Validate positive number using DataValidator"""
        return self.data_validator.validate_positive_number(value, field_name)
    
    def validate_string_length(self, value, min_length=None, max_length=None, field_name="value"):
        """Validate string length using DataValidator"""
        return self.data_validator.validate_string_length(value, min_length, max_length, field_name)


def handle_validation_error(func):
    """
    Decorator to handle ValidationError exceptions and convert to proper responses
    """
    import response_utils as resp
    
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ValidationError as e:
            return resp.error_response(e.message, 400)
        except Exception as e:
            print(f"Unexpected error in {func.__name__}: {str(e)}")
            return resp.error_response("Internal server error", 500)
    
    return wrapper
