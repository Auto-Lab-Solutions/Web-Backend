import json

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
    
    elif field_name in ['buyerData', 'carData', 'sellerData'] and not isinstance(field_value, dict):
        return False, f"{field_name} must be a dictionary"
        required_keys = [], optional_keys = []
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