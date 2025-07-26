import json
import re
from datetime import datetime

def get_query_param(event, key, default=None):
    return (event.get('queryStringParameters') or {}).get(key, default)

def get_header(event, key, default=None):
    return (event.get('headers') or {}).get(key, default)

def get_path_param(event, key, default=None):
    return (event.get('pathParameters') or {}).get(key, default)

def get_body(event, default=None):
    body = event.get('body')
    if body:
        try:
            return json.loads(body)
        except (json.JSONDecodeError, TypeError):
            return default
    return default

def get_body_param(event, key, default=None):
    body = get_body(event, {})
    return body.get(key, default)

def get_authorizer_context(event):
    return event.get('requestContext', {}).get('authorizer', {})

def get_staff_user_email(event):
    context = get_authorizer_context(event)
    if context:
        return context.get('email', None)
    return None

def get_staff_user_roles(event):
    context = get_authorizer_context(event)
    if context:
        roles_text = context.get('staff_roles', None)
        if roles_text:
            return roles_text.split(',')
    return []


def validate_email(email):
    """Validate email format using regex"""
    if not email or not isinstance(email, str):
        return False
    
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(email_pattern, email) is not None

def validate_phone_number(phone):
    """Validate phone number format"""
    if not phone or not isinstance(phone, str):
        return False
    
    # Remove spaces, dashes, and parentheses for validation
    clean_phone = re.sub(r'[\s\-\(\)]', '', phone)
    
    # Allow international format starting with + or domestic format
    phone_pattern = r'^(\+\d{1,3})?\d{7,15}$'
    return re.match(phone_pattern, clean_phone) is not None

def validate_year(year, field_name="year"):
    """Validate year value"""
    try:
        year_int = int(year)
        current_year = datetime.now().year
        if year_int < 1900 or year_int > current_year + 1:
            return False, f"{field_name} must be between 1900 and {current_year + 1}"
        return True, ""
    except (ValueError, TypeError):
        return False, f"{field_name} must be a valid integer"


def validate_appointment_data(appointment_data, staff_user=False):
    if not appointment_data:
        return False, "Appointment data is required"
    
    if not isinstance(appointment_data, dict):
        return False, "Appointment data must be a dictionary"
    
    all_fields = ['serviceId', 'planId', 'isBuyer', 'buyerData', 'carData', 'sellerData', 'notes', 'selectedSlots']
    required_fields = ['serviceId', 'planId', 'isBuyer', 'carData']

    if not staff_user:
        required_fields.append('selectedSlots')
        if 'isBuyer' in appointment_data:
            if appointment_data['isBuyer']:
                required_fields.append('buyerData')
            else:
                required_fields.append('sellerData')
    
    optional_fields = [field for field in all_fields if field not in required_fields]

    # Validate required fields
    for field in required_fields:
        valid, msg = validate_field(field, appointment_data.get(field), required=True)
        if not valid:
            return False, msg

    # Validate optional fields if present
    for field in optional_fields:
        if field in appointment_data:
            valid, msg = validate_field(field, appointment_data.get(field), required=False)
            if not valid:
                return False, msg

    return True, ""



def validate_field(field_name, field_value, required=True):
    if required and not field_value:
        return False, f"{field_name} is required"
    
    if field_name == 'serviceId' and not isinstance(field_value, int):
        return False, "serviceId must be an integer"
    
    elif field_name == 'planId' and not isinstance(field_value, int):
        return False, "planId must be an integer"

    elif field_name == 'isBuyer' and not isinstance(field_value, bool):
        return False, "isBuyer must be a boolean"
    
    elif field_name in ['buyerData', 'carData', 'sellerData']:
        if not isinstance(field_value, dict):
            return False, f"{field_name} must be a dictionary"
        required_keys = []
        optional_keys = []
        if field_name == 'buyerData' or field_name == 'sellerData':
            required_keys = ['name', 'email', 'phoneNumber']
        elif field_name == 'carData':
            required_keys = ['make', 'model', 'year']
            optional_keys = ['location']
        
        for key in required_keys:
            if key not in field_value:
                return False, f"{field_name} must contain {key}"
            if not field_value[key]:
                return False, f"{field_name}.{key} cannot be empty"
            
            # Enhanced validation for specific fields
            if key == 'email':
                if not validate_email(field_value[key]):
                    return False, f"{field_name}.{key} has invalid email format"
            elif key == 'phoneNumber':
                if not validate_phone_number(field_value[key]):
                    return False, f"{field_name}.{key} has invalid phone number format"
            elif key == 'year':
                valid_year, year_msg = validate_year(field_value[key], f"{field_name}.{key}")
                if not valid_year:
                    return False, year_msg
        
        for key in optional_keys:
            if key in field_value and not field_value[key]:
                return False, f"{field_name}.{key} cannot be empty"
    
    elif field_name == 'notes' and not isinstance(field_value, str):
        return False, "notes must be a string"
    
    elif field_name == 'selectedSlots':
        if not isinstance(field_value, list) or not all(isinstance(slot, dict) for slot in field_value):
            return False, "selectedSlots must be an array of objects"

        if required and len(field_value) == 0:
            return False, "At least one selected time slot is required"

        for slot in field_value:
            if not all(key in slot for key in ['date', 'start', 'end', 'priority']):
                return False, "Each slot must have date, start, end, and priority"
            if not isinstance(slot['date'], str) or not isinstance(slot['start'], str) or not isinstance(slot['end'], str):
                return False, "Slot date, start, and end must be strings"
            if not isinstance(slot['priority'], int):
                return False, "Slot priority must be an integer"
    
    return True, ""

def validate_order_data(order_data, staff_user=False):
    """Validate order data with enhanced validation"""
    if not order_data:
        return False, "Order data is required"
    
    if not isinstance(order_data, dict):
        return False, "Order data must be an object"
    
    # Required fields
    required_fields = ['items', 'customerData', 'carData']
    for field in required_fields:
        if field not in order_data:
            return False, f"{field} is required"
    
    # Validate items array
    items = order_data.get('items', [])
    if not isinstance(items, list) or len(items) == 0:
        return False, "items must be a non-empty array"
    
    if len(items) > 10:  # Maximum items per order
        return False, "Maximum 10 items allowed per order"
    
    # Validate each item
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            return False, f"Item {i+1} must be an object"
        
        # Required item fields
        required_item_fields = ['categoryId', 'itemId', 'quantity']
        for field in required_item_fields:
            if field not in item:
                return False, f"Item {i+1}: {field} is required"
        
        # Validate item values
        try:
            category_id = int(item['categoryId'])
            item_id = int(item['itemId'])
            quantity = int(item['quantity'])
            
            if category_id <= 0 or item_id <= 0 or quantity <= 0:
                return False, f"Item {i+1}: categoryId, itemId, and quantity must be positive integers"
                
            if quantity > 30:  # Maximum quantity per item
                return False, f"Item {i+1}: Maximum quantity per item is 30"

        except (ValueError, TypeError):
            return False, f"Item {i+1}: categoryId, itemId, and quantity must be valid integers"
    
    # Validate customer data
    customer_data = order_data.get('customerData', {})
    if not isinstance(customer_data, dict):
        return False, "customerData must be an object"
    
    required_customer_fields = ['name', 'email', 'phoneNumber']
    for field in required_customer_fields:
        if field not in customer_data or not customer_data[field]:
            return False, f"customerData.{field} is required"
    
    # Enhanced email validation
    email = customer_data.get('email', '')
    if not validate_email(email):
        return False, "Invalid email format"
    
    # Enhanced phone number validation
    phone = customer_data.get('phoneNumber', '')
    if not validate_phone_number(phone):
        return False, "Invalid phone number format"
    
    # Validate car data
    car_data = order_data.get('carData', {})
    if not isinstance(car_data, dict):
        return False, "carData must be an object"
    
    required_car_fields = ['make', 'model', 'year']
    for field in required_car_fields:
        if field not in car_data or not car_data[field]:
            return False, f"carData.{field} is required"
    
    # Enhanced year validation
    year = car_data.get('year')
    valid_year, year_msg = validate_year(year, "Car year")
    if not valid_year:
        return False, year_msg

    return True, "Valid"