import json
import response_utils as resp
import request_utils as req
import validation_utils as val
import permission_utils as perm
import business_logic_utils as biz
import db_utils as db
from exceptions import BusinessLogicError, ValidationError, PermissionError

@perm.handle_permission_error
@val.handle_validation_error
@biz.handle_business_logic_error
def lambda_handler(event, context):
    """
    Update user information in the users table
    Requires admin or customer support role
    """
    # Validate staff authentication and get staff context
    staff_user_email = req.get_staff_user_email(event)
    staff_context = perm.PermissionValidator.validate_staff_access(
        staff_user_email,
        required_roles=['ADMIN', 'CUSTOMER_SUPPORT']
    )
    staff_roles = staff_context.get('staff_roles', [])
    staff_user_email = staff_context.get('staff_record', {}).get('userEmail', '')
    
    # Extract and validate request data
    request_body = req.get_body(event)
    if not request_body or not isinstance(request_body, dict):
        raise ValidationError("Request body must be a valid JSON object")
    
    # Get target user ID from request body
    target_user_id = request_body.get('userId')
    if not target_user_id:
        raise ValidationError("userId is required in request body")
    
    # Validate that the target user exists
    existing_user = db.get_user_record(target_user_id)
    if not existing_user:
        raise ValidationError("User not found")
    
    # Extract update fields from request body
    update_data = {}
    
    # Optional fields that can be updated
    if 'userEmail' in request_body:
        user_email = request_body.get('userEmail', '').strip()
        if user_email:
            val.DataValidator.validate_email(user_email, 'userEmail')
            update_data['userEmail'] = user_email
    
    if 'userName' in request_body:
        user_name = request_body.get('userName', '').strip()
        if user_name:
            val.DataValidator.validate_string_length(user_name, min_length=1, max_length=100, field_name='userName')
            update_data['userName'] = user_name
    
    if 'userDevice' in request_body:
        user_device = request_body.get('userDevice', '').strip()
        if user_device:
            val.DataValidator.validate_string_length(user_device, min_length=1, max_length=200, field_name='userDevice')
            update_data['userDevice'] = user_device
    
    if 'userLocation' in request_body:
        user_location = request_body.get('userLocation', '').strip()
        if user_location:
            val.DataValidator.validate_string_length(user_location, min_length=1, max_length=200, field_name='userLocation')
            update_data['userLocation'] = user_location
    
    if 'contactNumber' in request_body:
        contact_number = request_body.get('contactNumber', '').strip()
        if contact_number:
            val.DataValidator.validate_phone_number(contact_number, 'contactNumber')
            update_data['contactNumber'] = contact_number
    
    # Check if any valid update fields were provided
    if not update_data:
        raise ValidationError("At least one valid field must be provided for update (userEmail, userName, userDevice, userLocation, contactNumber)")
    
    # Update the user record
    success = db.update_user_record(target_user_id, update_data)
    
    if not success:
        raise BusinessLogicError("Failed to update user information", 500)
    
    # Get the updated user record to return
    updated_user = db.get_user_record(target_user_id)
    
    # Log the update action for audit purposes
    print(f"User information updated by staff: {staff_user_email} for user: {target_user_id}, fields: {list(update_data.keys())}")
    
    return resp.success_response({
        "message": "User information updated successfully",
        "userId": target_user_id,
        "updatedFields": list(update_data.keys()),
        "updatedUser": resp.convert_decimal(updated_user)
    })
