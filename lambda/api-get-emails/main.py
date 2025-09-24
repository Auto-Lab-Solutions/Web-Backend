import json
import re

import response_utils as resp
import request_utils as req
import permission_utils as perm
import business_logic_utils as biz
from email_manager import EmailManager


@perm.handle_permission_error
@biz.handle_business_logic_error
def lambda_handler(event, context):
    """API Gateway handler for retrieving emails with threading support"""
    
    print(f"Get emails request: {json.dumps(event)}")
    
    # Validate staff authentication and permissions
    staff_email = req.get_staff_user_email(event)
    permission_manager = perm.PermissionManager()
    has_permission = permission_manager.check_staff_permission(staff_email, 'email_management')
    if not has_permission:
        raise perm.PermissionError("Insufficient permissions for email management", 403)
    
    # Initialize email manager
    email_manager = EmailManager()
    
    # Check path parameters to determine the operation
    path_params = event.get('pathParameters', {}) or {}
    
    print(f"Path parameters: {json.dumps(path_params)}")
    
    # Extract thread ID from path if not in path parameters
    # Handle case where API Gateway doesn't capture path parameters correctly
    thread_id = None
    if 'threadId' in path_params:
        thread_id = path_params['threadId']
    else:
        # Try to extract thread ID from the request path
        request_path = event.get('path', '') or event.get('rawPath', '')
        if request_path:
            # Look for pattern like /emails/{uuid}
            uuid_pattern = r'/emails/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})'
            match = re.search(uuid_pattern, request_path, re.IGNORECASE)
            if match:
                thread_id = match.group(1)
                print(f"Extracted thread ID from path: {thread_id}")
    
    # Handle thread-specific operations
    if thread_id:
        print(f"Processing thread-specific request for thread ID: {thread_id}")
        
        # Extract pagination parameters for thread emails
        try:
            limit = int(req.get_query_param(event, 'limit', 50))
        except (ValueError, TypeError):
            limit = 50
        
        try:
            offset = int(req.get_query_param(event, 'offset', 0))
        except (ValueError, TypeError):
            offset = 0
        
        # Get emails in the specific thread
        thread_emails = email_manager.get_thread_emails(
            thread_id=thread_id,
            limit=limit,
            offset=offset
        )
        
        # Check if there was an error (e.g., table not configured)
        if 'error' in thread_emails:
            raise biz.BusinessLogicError(thread_emails['error'], 500)
        
        return resp.success_response(thread_emails)
    
    # Handle email threads listing
    if req.get_query_param(event, 'view') == 'threads':
        # Extract pagination parameters
        try:
            limit = int(req.get_query_param(event, 'limit', 50))
        except (ValueError, TypeError):
            limit = 50
        
        try:
            offset = int(req.get_query_param(event, 'offset', 0))
        except (ValueError, TypeError):
            offset = 0
        
        # Extract filter parameters
        customer_email = req.get_query_param(event, 'customer_email')
        
        # Get email threads
        threads_result = email_manager.get_email_threads(
            staff_email=staff_email,
            customer_email=customer_email,
            limit=limit,
            offset=offset
        )
        
        # Check if there was an error (e.g., table not configured)
        if 'error' in threads_result:
            raise biz.BusinessLogicError(threads_result['error'], 500)
        
        return resp.success_response(threads_result)
    
    # Handle individual email retrieval
    if path_params and path_params.get('id'):
        email_id = path_params['id']
        email_data = email_manager.get_email_by_id_full(email_id)
        
        if not email_data:
            raise biz.BusinessLogicError('Email not found', 404)
        
        # Add attachment information to the email data
        try:
            email_data['attachments'] = email_manager.get_email_attachments(email_id)
            email_data['attachmentStats'] = email_manager.get_attachment_stats(email_id)
        except Exception as e:
            print(f"Warning: Failed to retrieve attachment info for email {email_id}: {str(e)}")
            email_data['attachments'] = []
            email_data['attachmentStats'] = {'count': 0, 'totalSizeBytes': 0, 'totalSizeMB': 0, 'types': []}
        
        # Mark as read when retrieved
        email_manager.update_email_read_status(email_id, True)
        return resp.success_response({'email': email_data})
    
    # Handle traditional email listing (fallback for backward compatibility)
    # Extract pagination parameters
    try:
        limit = int(req.get_query_param(event, 'limit', 50))
    except (ValueError, TypeError):
        limit = 50
    
    try:
        offset = int(req.get_query_param(event, 'offset', 0))
    except (ValueError, TypeError):
        offset = 0

    # Extract filter parameters
    to_email = req.get_query_param(event, 'to_email')
    from_email = req.get_query_param(event, 'from_email')
    start_date = req.get_query_param(event, 'start_date')
    end_date = req.get_query_param(event, 'end_date')
    
    # Convert boolean parameters
    is_read = req.get_query_param(event, 'is_read')
    if is_read is not None:
        is_read = is_read.lower() in ('true', '1', 'yes')
    
    has_attachments = req.get_query_param(event, 'has_attachments')
    if has_attachments is not None:
        has_attachments = has_attachments.lower() in ('true', '1', 'yes')

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
    
    # Check if there was an error (e.g., table not configured)
    if 'error' in emails_result:
        raise biz.BusinessLogicError(emails_result['error'], 500)
    
    return resp.success_response(emails_result)


