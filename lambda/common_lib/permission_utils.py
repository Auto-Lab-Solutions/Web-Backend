"""
Permission and authorization utilities for Lambda functions
Centralizes common permission checking patterns across the application
"""

import db_utils as db
import response_utils as resp


class PermissionError(Exception):
    """Custom exception for permission-related errors"""
    def __init__(self, message, status_code=403):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)


class PermissionValidator:
    """Handles common permission validation patterns"""
    
    @staticmethod
    def validate_staff_access(staff_user_email, required_roles=None, optional=False):
        """
        Validate staff access with role checking
        
        Args:
            staff_user_email (str): Email from staff authorization context
            required_roles (list): List of required roles (any one is sufficient)
            optional (bool): If True, allows non-staff access
            
        Returns:
            dict: Contains staff_record, staff_roles, staff_user_id
            
        Raises:
            PermissionError: If access is denied
        """
        if not staff_user_email:
            if optional:
                return {'staff_record': None, 'staff_roles': [], 'staff_user_id': None}
            raise PermissionError("Unauthorized: Staff authentication required", 401)
        
        staff_record = db.get_staff_record(staff_user_email)
        if not staff_record:
            raise PermissionError(f"No staff record found for email: {staff_user_email}", 404)
        
        staff_roles = staff_record.get('roles', [])
        staff_user_id = staff_record.get('userId')
        
        if required_roles:
            if isinstance(required_roles, str):
                required_roles = [required_roles]
            
            if not any(role in staff_roles for role in required_roles):
                role_str = ', '.join(required_roles)
                raise PermissionError(f"Unauthorized: Requires one of roles: {role_str}", 403)
        
        return {
            'staff_record': staff_record,
            'staff_roles': staff_roles,
            'staff_user_id': staff_user_id
        }
    
    @staticmethod
    def validate_user_access(user_id, staff_context=None):
        """
        Validate user access and ownership
        
        Args:
            user_id (str): User ID to validate
            staff_context (dict): Staff context from validate_staff_access()
            
        Returns:
            dict: Contains user_record and effective_user_id
            
        Raises:
            PermissionError: If access is denied
        """
        if staff_context and staff_context['staff_record']:
            # Staff user - use their user_id unless overridden
            effective_user_id = staff_context['staff_user_id']
            if user_id:
                effective_user_id = user_id  # Staff can operate on behalf of others
            
            user_record = db.get_user_record(effective_user_id)
            if not user_record:
                raise PermissionError(f"No user record found for userId: {effective_user_id}", 404)
        else:
            # Regular user
            if not user_id:
                raise PermissionError("userId is required for non-staff users", 400)
            
            user_record = db.get_user_record(user_id)
            if not user_record:
                raise PermissionError(f"No user record found for userId: {user_id}", 404)
            
            effective_user_id = user_id
        
        return {
            'user_record': user_record,
            'effective_user_id': effective_user_id
        }
    
    @staticmethod
    def check_ownership(resource, user_id, staff_context=None, owner_field='createdUserId'):
        """
        Check if user owns a resource or if staff has override access
        
        Args:
            resource (dict): Resource to check ownership for
            user_id (str): User ID to check ownership against
            staff_context (dict): Staff context from validate_staff_access()
            owner_field (str): Field name that contains the owner ID
            
        Returns:
            bool: True if access is allowed
            
        Raises:
            PermissionError: If access is denied
        """
        if staff_context and staff_context['staff_record']:
            # Staff users typically have override access
            return True
        
        resource_owner = resource.get(owner_field)
        if resource_owner != user_id:
            raise PermissionError(f"Unauthorized: You can only access resources you created", 403)
        
        return True
    
    @staticmethod
    def validate_daily_limits(user_id, limit_type, limit_value, staff_override=False):
        """
        Validate daily limits for resource creation
        
        Args:
            user_id (str): User ID to check limits for
            limit_type (str): Type of limit ('appointments', 'orders', etc.)
            limit_value (int): Maximum allowed per day
            staff_override (bool): Whether to skip limits for staff
            
        Returns:
            bool: True if within limits
            
        Raises:
            PermissionError: If limit exceeded
        """
        if staff_override:
            return True
        
        from datetime import datetime
        today = datetime.now().date()
        
        if limit_type == 'appointments':
            count = db.get_daily_unpaid_appointments_count(user_id, today)
        elif limit_type == 'orders':
            count = db.get_daily_unpaid_orders_count(user_id, today)
        else:
            raise ValueError(f"Unknown limit type: {limit_type}")
        
        if count >= limit_value:
            raise PermissionError(f"{limit_type.title()} limit ({limit_value}) reached for today", 400)
        
        return True


class RoleBasedPermissions:
    """Role-based permission definitions"""
    
    # Define role permissions
    ROLE_PERMISSIONS = {
        'ADMIN': {
            'can_manage_staff': True,
            'can_manage_payments': True,
            'can_manage_schedules': True,
            'can_view_all_data': True,
            'can_update_any_resource': True
        },
        'CUSTOMER_SUPPORT': {
            'can_create_appointments': True,
            'can_create_orders': True,
            'can_view_customer_data': True,
            'can_send_messages': True,
            'can_take_users': True
        },
        'CLERK': {
            'can_view_appointments': True,
            'can_view_orders': True,
            'can_view_connections': True,
            'can_view_messages': True,
            'can_generate_reports': True
        },
        'MECHANIC': {
            'can_view_assigned_appointments': True,
            'can_update_appointment_status': True,
            'can_upload_reports': True,
            'can_update_work_progress': True
        }
    }
    
    @classmethod
    def check_permission(cls, staff_roles, permission):
        """
        Check if any of the staff roles has the specified permission
        
        Args:
            staff_roles (list): List of staff roles
            permission (str): Permission to check
            
        Returns:
            bool: True if permission granted
        """
        for role in staff_roles:
            role_perms = cls.ROLE_PERMISSIONS.get(role, {})
            if role_perms.get(permission, False):
                return True
        return False
    
    @classmethod
    def require_permission(cls, staff_roles, permission):
        """
        Require a specific permission, raise PermissionError if not granted
        
        Args:
            staff_roles (list): List of staff roles
            permission (str): Permission to check
            
        Raises:
            PermissionError: If permission not granted
        """
        if not cls.check_permission(staff_roles, permission):
            raise PermissionError(f"Unauthorized: Missing required permission: {permission}", 403)


def handle_permission_error(func):
    """
    Decorator to handle PermissionError exceptions and convert to proper responses
    """
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except PermissionError as e:
            return resp.error_response(e.message, e.status_code)
        except Exception as e:
            print(f"Unexpected error in {func.__name__}: {str(e)}")
            return resp.error_response("Internal server error", 500)
    
    return wrapper
