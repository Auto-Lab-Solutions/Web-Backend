import json
import os
import sys

# Add common_lib to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'common_lib'))

import response_utils as resp
import request_utils as req
import permission_utils as perm
import business_logic_utils as biz
import backup_restore_utils as backup_utils

@perm.handle_permission_error
@biz.handle_business_logic_error
def lambda_handler(event, context):
    """
    API Gateway Lambda for Backup/Restore Operations
    
    Endpoints:
    POST /backup - Trigger manual backup (with optional cleanup)
    POST /restore - Trigger restore operation
    POST /cleanup - Trigger cleanup-only operation
    GET /backups - List available backups
    
    Requires ADMIN role for all operations.
    """
    try:
        # Validate staff permissions - only ADMIN can perform backup operations
        staff_user_email = req.get_staff_user_email(event)
        staff_context = perm.PermissionValidator.validate_staff_access(
            staff_user_email,
            required_roles=['ADMIN']
        )
        
        # Parse the request
        http_method = event.get('httpMethod', '')
        path = event.get('path', '')
        body = event.get('body', '{}')
        
        # Parse request body
        try:
            request_data = json.loads(body) if body and body != '{}' else {}
        except json.JSONDecodeError:
            raise biz.BusinessLogicError("Invalid JSON in request body", 400)
        
        # Route requests based on method and path
        if http_method == 'POST' and path.endswith('/backup'):
            return handle_backup_request(request_data, event, context, staff_context)
        elif http_method == 'POST' and path.endswith('/restore'):
            return handle_restore_request(request_data, event, context, staff_context)
        elif http_method == 'POST' and path.endswith('/cleanup'):
            return handle_cleanup_request(request_data, event, context, staff_context)
        elif http_method == 'GET' and path.endswith('/backups'):
            return handle_list_backups_request(event, context, staff_context)
        else:
            raise biz.BusinessLogicError(f"Unsupported method {http_method} for path {path}", 404)
            
    except Exception as e:
        print(f"Error in api-backup-restore lambda_handler: {str(e)}")
        return resp.error_response(f"Internal server error: {str(e)}", 500)

def handle_backup_request(request_data, event, context, staff_context):
    """Handle manual backup request with enhanced options"""
    try:
        # Get backup restore manager
        backup_manager = backup_utils.get_backup_restore_manager()
        
        # Build backup event using shared utility
        backup_event = backup_manager.build_backup_event(request_data, staff_context, context.aws_request_id)
        
        print(f"Initiating backup with parameters: {json.dumps(backup_event, default=str)}")
        
        # Invoke backup function asynchronously for better performance
        backup_manager.invoke_backup_function_async(backup_event)
        
        # Build response data
        parameters = {
            'tables': request_data.get('tables', []) if request_data.get('tables') else 'all',
            'skip_cleanup': request_data.get('skip_cleanup', False),
            'reason': request_data.get('reason', 'Manual backup via API')
        }
        
        response_data = backup_manager.build_api_response_data(
            'backup', staff_context, context.aws_request_id, None, parameters
        )
        
        return resp.success_response(response_data)
        
    except Exception as e:
        print(f"Error handling backup request: {str(e)}")
        raise biz.BusinessLogicError(f"Failed to initiate backup: {str(e)}", 500)

def handle_restore_request(request_data, event, context, staff_context):
    """Handle restore request with comprehensive validation"""
    try:
        # Get backup restore manager
        backup_manager = backup_utils.get_backup_restore_manager()
        
        # Build restore event using shared utility (includes validation)
        restore_event = backup_manager.build_restore_event(request_data, staff_context, context.aws_request_id)
        
        print(f"Initiating restore with parameters: {json.dumps(restore_event, default=str)}")
        
        # Invoke backup function for restore synchronously to get immediate result
        response_payload = backup_manager.invoke_backup_function_sync(restore_event)
        
        # Validate and parse response
        restore_result = backup_manager.validate_sync_response(response_payload, 'restore')
        
        # Build response data
        parameters = {
            'tables': request_data.get('tables', []) if request_data.get('tables') else 'all',
            'clear_tables': request_data.get('clear_tables', True),
            'create_backup': request_data.get('create_backup', True),
            'restore_s3_objects': request_data.get('restore_s3_objects', True),
            'reason': request_data.get('reason', 'Manual restore via API')
        }
        
        response_data = backup_manager.build_api_response_data(
            'restore', staff_context, context.aws_request_id, restore_result, parameters
        )
        response_data['backup_timestamp'] = request_data.get('backup_timestamp')
        
        return resp.success_response(response_data)
        
    except Exception as e:
        print(f"Error handling restore request: {str(e)}")
        raise biz.BusinessLogicError(f"Failed to initiate restore: {str(e)}", 500)

def handle_cleanup_request(request_data, event, context, staff_context):
    """Handle cleanup-only request"""
    try:
        # Get backup restore manager
        backup_manager = backup_utils.get_backup_restore_manager()
        
        # Build cleanup event using shared utility
        cleanup_event = backup_manager.build_cleanup_event(request_data, staff_context, context.aws_request_id)
        
        print(f"Initiating cleanup with parameters: {json.dumps(cleanup_event, default=str)}")
        
        # Invoke backup function for cleanup synchronously to get immediate result
        response_payload = backup_manager.invoke_backup_function_sync(cleanup_event)
        
        # Validate and parse response
        cleanup_result = backup_manager.validate_sync_response(response_payload, 'cleanup')
        
        # Build response data
        parameters = {
            'tables': request_data.get('tables', []) if request_data.get('tables') else 'all',
            'reason': request_data.get('reason', 'Manual cleanup via API')
        }
        
        response_data = backup_manager.build_api_response_data(
            'cleanup', staff_context, context.aws_request_id, cleanup_result, parameters
        )
        
        return resp.success_response(response_data)
        
    except Exception as e:
        print(f"Error handling cleanup request: {str(e)}")
        raise biz.BusinessLogicError(f"Failed to initiate cleanup: {str(e)}", 500)

def handle_list_backups_request(event, context, staff_context):
    """Handle list backups request with enhanced information"""
    try:
        # Get backup restore manager
        backup_manager = backup_utils.get_backup_restore_manager()
        
        # Build list backups event using shared utility
        list_event = backup_manager.build_list_backups_event(staff_context, context.aws_request_id)
        
        staff_user_email = staff_context.get('staff_user_email', 'unknown')
        print(f"Listing backups for user: {staff_user_email}")
        
        # Invoke backup function for listing synchronously
        response_payload = backup_manager.invoke_backup_function_sync(list_event)
        
        # For list_backups, return the response as-is from backup function if successful
        if response_payload.get('statusCode') == 200:
            return response_payload
        else:
            error_body = response_payload.get('body', 'Unknown error')
            status_code = response_payload.get('statusCode', 500)
            raise biz.BusinessLogicError(f"Failed to list backups: {error_body}", status_code)
        
    except Exception as e:
        print(f"Error handling list backups request: {str(e)}")
        raise biz.BusinessLogicError(f"Failed to list backups: {str(e)}", 500)

