import json
import os
import sys

# Add common_lib to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'common_lib'))

from permission_utils import PermissionManager
from email_suppression_manager import EmailSuppressionManager
from validation_utils import ValidationManager
import response_utils as resp
import request_utils as req

def lambda_handler(event, context):
    """
    Manage email suppression list - API for checking, adding, removing suppressed emails
    """
    print(f"Email suppression manager invoked: {json.dumps(event, default=str)}")
    
    try:
        # Initialize managers
        permission_manager = PermissionManager()
        suppression_manager = EmailSuppressionManager()
        validation_manager = ValidationManager()
        
        # Validate staff authentication and permissions
        try:
            if 'httpMethod' in event:  # API Gateway request
                staff_email = req.get_staff_user_email(event)
                has_permission = permission_manager.check_staff_permission(staff_email, 'email_management')
                if not has_permission:
                    return resp.error_response(403, "Insufficient permissions for email management")
        except Exception as e:
            return resp.error_response(401, f"Authentication failed: {str(e)}")
        
        # Parse the request
        http_method = event.get('httpMethod', 'GET')
        path = event.get('path', '')
        query_params = event.get('queryStringParameters') or {}
        body = event.get('body')
        
        if body:
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                body = {}
        
        # Route to appropriate handler based on HTTP method and path
        if http_method == 'GET' and '/check' in path:
            return check_suppression_status(suppression_manager, query_params)
        elif http_method == 'GET' and '/list' in path:
            return list_suppressed_emails(suppression_manager, query_params)
        elif http_method == 'POST' and '/add' in path:
            return add_to_suppression(suppression_manager, body)
        elif http_method == 'DELETE' and '/remove' in path:
            return remove_from_suppression(suppression_manager, query_params)
        elif http_method == 'GET' and '/analytics' in path:
            return get_email_analytics(suppression_manager, query_params)
        elif http_method == 'POST' and '/cleanup' in path:
            return cleanup_expired_suppressions(suppression_manager)
        else:
            return resp.error_response(404, 'Endpoint not found')
            
    except Exception as e:
        print(f"Error in email suppression manager: {str(e)}")
        return resp.error_response(500, f"Internal server error: {str(e)}")


def check_suppression_status(suppression_manager, query_params):
    """Check if an email address is suppressed"""
    try:
        email = query_params.get('email')
        if not email:
            return resp.error_response(400, 'Email parameter required')
        
        result = suppression_manager.check_suppression_status(email)
        return resp.success_response(result)
        
    except Exception as e:
        print(f"Error checking suppression status: {str(e)}")
        return resp.error_response(500, str(e))


def list_suppressed_emails(suppression_manager, query_params):
    """List suppressed email addresses with pagination"""
    try:
        limit = int(query_params.get('limit', 50))
        suppression_type = query_params.get('type')
        last_evaluated_key = query_params.get('lastKey')
        
        result = suppression_manager.list_suppressed_emails(
            limit=limit,
            suppression_type=suppression_type,
            last_evaluated_key=last_evaluated_key
        )
        
        return resp.success_response(result)
        
    except Exception as e:
        print(f"Error listing suppressed emails: {str(e)}")
        return resp.error_response(500, str(e))


def add_to_suppression(suppression_manager, body):
    """Manually add an email to suppression list"""
    try:
        email = body.get('email')
        reason = body.get('reason', 'manual')
        notes = body.get('notes', '')
        
        if not email:
            return resp.error_response(400, 'Email is required')
        
        result = suppression_manager.add_to_suppression(email, reason, notes)
        
        if result['success']:
            return resp.success_response({
                'message': f'Added {email} to suppression list',
                'email': email,
                'reason': reason,
                'added_at': result['added_at']
            })
        else:
            return resp.error_response(500, result['error'])
        
    except Exception as e:
        print(f"Error adding to suppression: {str(e)}")
        return resp.error_response(500, str(e))


def remove_from_suppression(suppression_manager, query_params):
    """Remove an email from suppression list"""
    try:
        email = query_params.get('email')
        suppression_type = query_params.get('type')
        
        if not email:
            return resp.error_response(400, 'Email parameter required')
        
        result = suppression_manager.remove_from_suppression(email, suppression_type)
        
        if result['success']:
            return resp.success_response({
                'message': f'Removed {email} from suppression list',
                'email': email,
                'removed_count': result['removed_count']
            })
        else:
            return resp.error_response(500, result['error'])
        
    except Exception as e:
        print(f"Error removing from suppression: {str(e)}")
        return resp.error_response(500, str(e))


def get_email_analytics(suppression_manager, query_params):
    """Get email analytics and suppression statistics"""
    try:
        start_date = query_params.get('start_date')
        end_date = query_params.get('end_date')
        
        result = suppression_manager.get_email_analytics(start_date, end_date)
        return resp.success_response(result)
        
    except Exception as e:
        print(f"Error getting email analytics: {str(e)}")
        return resp.error_response(500, str(e))


def cleanup_expired_suppressions(suppression_manager):
    """Cleanup expired suppressions"""
    try:
        result = suppression_manager.cleanup_expired_suppressions()
        
        return resp.success_response({
            'message': 'Cleanup completed',
            'cleaned_count': result['cleaned_count'],
            'errors': result['errors']
        })
        
    except Exception as e:
        print(f"Error cleaning up suppressions: {str(e)}")
        return resp.error_response(500, str(e))
