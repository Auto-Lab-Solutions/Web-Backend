import json
import os
import sys
import boto3
from botocore.exceptions import ClientError

# Add common_lib to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'common_lib'))

import response_utils as resp

def lambda_handler(event, context):
    """
    API Gateway Lambda for Backup/Restore Operations
    
    Endpoints:
    POST /backup - Trigger manual backup
    POST /restore - Trigger restore operation
    GET /backups - List available backups
    """
    try:
        # Parse the request
        http_method = event.get('httpMethod', '')
        path = event.get('path', '')
        body = event.get('body', '{}')
        
        # Parse request body
        try:
            request_data = json.loads(body) if body and body != '{}' else {}
        except json.JSONDecodeError:
            return resp.error_response("Invalid JSON in request body", 400)
        
        # Route requests
        if http_method == 'POST' and path.endswith('/backup'):
            return handle_backup_request(request_data, event, context)
        elif http_method == 'POST' and path.endswith('/restore'):
            return handle_restore_request(request_data, event, context)
        elif http_method == 'GET' and path.endswith('/backups'):
            return handle_list_backups_request(event, context)
        else:
            return resp.error_response(f"Unsupported method {http_method} for path {path}", 404)
            
    except Exception as e:
        print(f"Error in lambda_handler: {str(e)}")
        return resp.error_response(f"Internal server error: {str(e)}", 500)

def handle_backup_request(request_data, event, context):
    """Handle manual backup request"""
    try:
        # Get backup function name from environment
        backup_function_name = os.environ.get('BACKUP_FUNCTION_NAME')
        if not backup_function_name:
            return resp.error_response("BACKUP_FUNCTION_NAME environment variable not set", 500)
        
        # Extract user info from event if available
        user_info = get_user_from_event(event)
        
        # Prepare backup event
        backup_event = {
            'operation': 'backup',
            'manual_trigger': True,
            'triggered_by': user_info.get('username', 'api'),
            'reason': request_data.get('reason', 'Manual backup via API'),
            'tables': request_data.get('tables', []),  # Empty means all tables
        }
        
        # Invoke backup function
        lambda_client = boto3.client('lambda')
        response = lambda_client.invoke(
            FunctionName=backup_function_name,
            InvocationType='Event',  # Asynchronous invocation
            Payload=json.dumps(backup_event)
        )
        
        return resp.success_response({
            'message': 'Backup initiated successfully',
            'backup_function': backup_function_name,
            'request_id': context.aws_request_id,
            'triggered_by': backup_event['triggered_by']
        })
        
    except Exception as e:
        print(f"Error handling backup request: {str(e)}")
        return resp.error_response(f"Failed to initiate backup: {str(e)}", 500)

def handle_restore_request(request_data, event, context):
    """Handle restore request"""
    try:
        # Validate required parameters
        backup_timestamp = request_data.get('backup_timestamp')
        if not backup_timestamp:
            return resp.error_response("backup_timestamp is required for restore operation", 400)
        
        # Get backup function name from environment
        backup_function_name = os.environ.get('BACKUP_FUNCTION_NAME')
        if not backup_function_name:
            return resp.error_response("BACKUP_FUNCTION_NAME environment variable not set", 500)
        
        # Extract user info from event if available
        user_info = get_user_from_event(event)
        
        # Prepare restore event
        restore_event = {
            'operation': 'restore',
            'backup_timestamp': backup_timestamp,
            'tables': request_data.get('tables', []),  # Empty means all tables
            'clear_tables': request_data.get('clear_tables', True),
            'create_backup': request_data.get('create_backup', True),
            'manual_trigger': True,
            'triggered_by': user_info.get('username', 'api'),
            'reason': request_data.get('reason', 'Manual restore via API')
        }
        
        # Invoke backup function for restore
        lambda_client = boto3.client('lambda')
        response = lambda_client.invoke(
            FunctionName=backup_function_name,
            InvocationType='RequestResponse',  # Synchronous for restore
            Payload=json.dumps(restore_event)
        )
        
        # Parse response
        response_payload = json.loads(response['Payload'].read().decode('utf-8'))
        
        if response_payload.get('statusCode') == 200:
            return resp.success_response({
                'message': 'Restore completed successfully',
                'restore_result': json.loads(response_payload.get('body', '{}')),
                'request_id': context.aws_request_id,
                'triggered_by': restore_event['triggered_by']
            })
        else:
            return resp.error_response(
                f"Restore failed: {response_payload.get('body', 'Unknown error')}", 
                response_payload.get('statusCode', 500)
            )
        
    except Exception as e:
        print(f"Error handling restore request: {str(e)}")
        return resp.error_response(f"Failed to initiate restore: {str(e)}", 500)

def handle_list_backups_request(event, context):
    """Handle list backups request"""
    try:
        # Get backup function name from environment
        backup_function_name = os.environ.get('BACKUP_FUNCTION_NAME')
        if not backup_function_name:
            return resp.error_response("BACKUP_FUNCTION_NAME environment variable not set", 500)
        
        # Prepare list backups event
        list_event = {
            'operation': 'list_backups'
        }
        
        # Invoke backup function for listing
        lambda_client = boto3.client('lambda')
        response = lambda_client.invoke(
            FunctionName=backup_function_name,
            InvocationType='RequestResponse',  # Synchronous for listing
            Payload=json.dumps(list_event)
        )
        
        # Parse response
        response_payload = json.loads(response['Payload'].read().decode('utf-8'))
        
        if response_payload.get('statusCode') == 200:
            return response_payload
        else:
            return resp.error_response(
                f"Failed to list backups: {response_payload.get('body', 'Unknown error')}", 
                response_payload.get('statusCode', 500)
            )
        
    except Exception as e:
        print(f"Error handling list backups request: {str(e)}")
        return resp.error_response(f"Failed to list backups: {str(e)}", 500)

def get_user_from_event(event):
    """Extract user information from API Gateway event"""
    try:
        # Try to get user from JWT claims or request context
        request_context = event.get('requestContext', {})
        authorizer = request_context.get('authorizer', {})
        
        if 'claims' in authorizer:
            # JWT claims
            claims = authorizer['claims']
            return {
                'username': claims.get('email', claims.get('sub', 'unknown')),
                'user_id': claims.get('sub', 'unknown')
            }
        elif 'principalId' in authorizer:
            # Custom authorizer
            return {
                'username': authorizer.get('principalId', 'unknown'),
                'user_id': authorizer.get('principalId', 'unknown')
            }
        else:
            # No auth info available
            return {
                'username': 'api-user',
                'user_id': 'unknown'
            }
    except Exception as e:
        print(f"Error extracting user info: {e}")
        return {
            'username': 'unknown',
            'user_id': 'unknown'
        }
