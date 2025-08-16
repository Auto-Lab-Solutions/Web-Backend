import json
import os
import sys

# Add common_lib to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'common_lib'))

from permission_utils import PermissionManager
from email_manager import EmailManager
from validation_utils import ValidationManager
from data_retrieval_utils import DataRetrievalManager
import response_utils as resp
import request_utils as req

def lambda_handler(event, context):
    """API Gateway handler for retrieving emails"""
    try:
        print(f"Get emails request: {json.dumps(event)}")
        
        # Initialize managers
        permission_manager = PermissionManager()
        email_manager = EmailManager()
        validation_manager = ValidationManager()
        
        # Validate staff authentication and permissions
        try:
            staff_email = req.get_staff_user_email(event)
            has_permission = permission_manager.check_staff_permission(staff_email, 'email_management')
            if not has_permission:
                return resp.error_response(403, "Insufficient permissions for email management")
        except Exception as e:
            return resp.error_response(401, f"Authentication failed: {str(e)}")
        
        # Extract pagination parameters
        limit = req.get_query_param(event, 'limit', 50)
        offset = req.get_query_param(event, 'offset', 0)

        # Extract filter parameters
        to_email = req.get_query_param(event, 'to_email')
        from_email = req.get_query_param(event, 'from_email')
        start_date = req.get_query_param(event, 'start_date')
        end_date = req.get_query_param(event, 'end_date')
        is_read = req.get_query_param(event, 'is_read')
        has_attachments = req.get_query_param(event, 'has_attachments')

        # Check if this is a request for a specific email
        path_params = event.get('pathParameters', {})
        if path_params and path_params.get('id'):
            email_id = path_params['id']
            email_data = email_manager.get_email_by_id_full(email_id)
            
            if email_data:
                # Mark as read when retrieved
                email_manager.update_email_read_status(email_id, True)
                return resp.success_response({'email': email_data})
            else:
                return resp.error_response(404, 'Email not found')
        
        # Get emails with filters
        emails_result = email_manager.get_emails(
            to_email=to_email,
            from_email=from_email,
            start_date=start_date,
            end_date=end_date,
            is_read=is_read,
            has_attachments=has_attachments,
            limit=limit,
            offset=offset
        )
        
        return resp.success_response(emails_result)
        
    except Exception as e:
        print(f"Error in email handler: {str(e)}")
        return resp.error_response(500, f"Internal server error: {str(e)}")


