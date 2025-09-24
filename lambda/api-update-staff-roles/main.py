import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import response_utils as resp
import request_utils as req
import permission_utils as perm
import business_logic_utils as biz
import validation_utils as val
import db_utils as db

@perm.handle_permission_error
@biz.handle_business_logic_error
def lambda_handler(event, context):
    """
    Update Staff Roles API - Admin Only
    
    POST /users/staff - Update staff member roles
    
    Requires ADMIN role for role management operations.
    Only admins can update staff roles as this is a sensitive operation
    that affects access control and permissions.
    
    Request body:
    {
        "user_email": "staff@example.com",
        "roles": ["ADMIN", "STAFF", "MANAGER"]
    }
    """
    try:
        # Validate staff permissions - only ADMIN can update staff roles
        staff_user_email = req.get_staff_user_email(event)
        staff_context = perm.PermissionValidator.validate_staff_access(
            staff_user_email,
            required_roles=['ADMIN']
        )
        
        # Get target user email from request body
        target_user_email = req.get_body_param(event, 'user_email')
        if not target_user_email:
            raise biz.BusinessLogicError("user_email is required in request body", 400)
        
        # Validate email format using validation utils
        try:
            val.DataValidator.validate_email(target_user_email, "user_email")
        except val.ValidationError as e:
            raise biz.BusinessLogicError(e.message, 400)
        
        # Check if admin is trying to update their own roles
        if staff_user_email.lower() == target_user_email.lower():
            raise biz.BusinessLogicError("Self-update forbidden: Admins cannot update their own roles", 403)
        
        # Get new roles from request body
        new_roles = req.get_body_param(event, 'roles')
        if new_roles is None:
            raise biz.BusinessLogicError("roles field is required in request body", 400)
        
        # Validate roles format
        if not isinstance(new_roles, list):
            raise biz.BusinessLogicError("roles must be an array", 400)
        
        if not new_roles:
            raise biz.BusinessLogicError("At least one role must be specified", 400)
        
        # Validate each role
        valid_roles = ['ADMIN', 'MECHANIC', 'CLERK', 'CUSTOMER_SUPPORT']
        normalized_roles = []
        
        for role in new_roles:
            if not isinstance(role, str):
                raise biz.BusinessLogicError("Each role must be a string", 400)
            
            # Normalize role to uppercase
            normalized_role = role.upper()
            if normalized_role not in valid_roles:
                raise biz.BusinessLogicError(f"Role '{role}' is not valid. Valid roles: {', '.join(valid_roles)}", 400)
            
            normalized_roles.append(normalized_role)
        
        # Remove duplicates while preserving order
        normalized_roles = list(dict.fromkeys(normalized_roles))
        
        # Check if target user exists in staff table
        target_staff_record = db.get_staff_record(target_user_email)
        if not target_staff_record:
            raise biz.BusinessLogicError(f"Staff member with email '{target_user_email}' not found", 404)
        
        # Capture current roles for logging
        current_roles = target_staff_record.get('roles', [])
        
        # Update staff roles in database
        success = db.update_staff_roles(target_user_email, normalized_roles)
        
        if not success:
            raise biz.BusinessLogicError(f"Failed to update roles for '{target_user_email}'. Please try again.", 500)
        
        # Log the action for audit purposes
        staff_user_id = staff_context.get('staff_user_id', 'unknown')
        staff_user_name = staff_context.get('staff_record', {}).get('userName', 'Unknown Admin')
        target_staff_name = target_staff_record.get('userName', 'Unknown Staff')
        
        print(f"AUDIT: Staff roles updated by admin {staff_user_name} (ID: {staff_user_id}) - "
              f"Target: {target_staff_name} ({target_user_email}), "
              f"Previous Roles: {current_roles}, "
              f"New Roles: {normalized_roles}")
        
        # Prepare success response
        response_data = {
            "message": "Staff roles updated successfully",
            "updatedStaff": {
                "userEmail": target_user_email,
                "userName": target_staff_name,
                "previousRoles": current_roles,
                "newRoles": normalized_roles
            },
            "updatedBy": {
                "adminEmail": staff_user_email,
                "adminName": staff_user_name,
                "adminId": staff_user_id,
                "updatedAt": int(datetime.now(ZoneInfo('Australia/Perth')).timestamp())
            }
        }
        
        return resp.success_response(response_data)
        
    except Exception as e:
        print(f"Error in api-update-staff-roles lambda_handler: {str(e)}")
        # Re-raise known business logic errors
        if isinstance(e, (biz.BusinessLogicError, perm.PermissionError)):
            raise
        # Handle unexpected errors
        return resp.error_response(f"Internal server error: {str(e)}", 500)
