"""
Email Attachments API
Handles attachment download and management endpoints
"""

import json
import base64
import response_utils as resp
import request_utils as req
import business_logic_utils as biz
import permission_utils as perm
from email_manager import EmailManager


@perm.handle_permission_error
@biz.handle_business_logic_error
def lambda_handler(event, context):
    """Handle attachment API requests with proper authentication and error handling"""
    
    # Validate staff authentication and permissions
    staff_email = req.get_staff_user_email(event)
    permission_manager = perm.PermissionManager()
    has_permission = permission_manager.check_staff_permission(staff_email, 'email_management')
    if not has_permission:
        raise perm.PermissionError("Insufficient permissions for email management", 403)
    
    # Parse the request
    http_method = event.get('httpMethod', 'GET')
    path_parameters = event.get('pathParameters') or {}
    query_parameters = event.get('queryStringParameters') or {}
    
    # Route the request
    if http_method == 'GET':
        attachment_id = path_parameters.get('attachmentId')
        if attachment_id:
            if 'download' in query_parameters:
                return handle_attachment_download(attachment_id)
            elif 'url' in query_parameters:
                return handle_attachment_url(attachment_id, query_parameters)
            else:
                return handle_get_attachment_info(attachment_id)
        else:
            # Get attachments for an email
            message_id = query_parameters.get('messageId')
            if message_id:
                return handle_get_email_attachments(message_id)
            else:
                raise biz.BusinessLogicError('Missing messageId or attachmentId parameter', 400)
    
    elif http_method == 'DELETE':
        attachment_id = path_parameters.get('attachmentId')
        if attachment_id:
            return handle_delete_attachment(attachment_id)
        else:
            raise biz.BusinessLogicError('Missing attachmentId parameter', 400)
    
    else:
        raise biz.BusinessLogicError('Method not allowed', 405)


def handle_get_email_attachments(message_id):
    """Get all attachments for an email"""
    try:
        attachments = EmailManager.get_email_attachments(message_id)
        stats = EmailManager.get_attachment_stats(message_id)
        
        return resp.success_response({
            'attachments': attachments,
            'stats': stats
        })
        
    except Exception as e:
        print(f"Error getting email attachments: {str(e)}")
        raise biz.BusinessLogicError('Failed to retrieve attachments', 500)


def handle_get_attachment_info(attachment_id):
    """Get attachment metadata"""
    try:
        attachment = EmailManager.get_attachment_by_id(attachment_id)
        
        if not attachment:
            raise biz.BusinessLogicError('Attachment not found', 404)
        
        return resp.success_response({'attachment': attachment})
        
    except biz.BusinessLogicError:
        raise
    except Exception as e:
        print(f"Error getting attachment info: {str(e)}")
        raise biz.BusinessLogicError('Failed to retrieve attachment info', 500)


def handle_attachment_download(attachment_id):
    """Download attachment content directly"""
    try:
        result = EmailManager.get_attachment_content(attachment_id)
        
        if not result:
            raise biz.BusinessLogicError('Attachment not found', 404)
        
        content, content_type, filename = result
        
        # Encode content as base64 for API Gateway
        encoded_content = base64.b64encode(content).decode('utf-8')
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': content_type,
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Content-Length': str(len(content)),
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                'Access-Control-Allow-Methods': 'GET,OPTIONS'
            },
            'body': encoded_content,
            'isBase64Encoded': True
        }
        
    except biz.BusinessLogicError:
        raise
    except Exception as e:
        print(f"Error downloading attachment: {str(e)}")
        raise biz.BusinessLogicError('Failed to download attachment', 500)


def handle_attachment_url(attachment_id, query_parameters):
    """Generate a presigned URL for attachment download"""
    try:
        expires_in = int(query_parameters.get('expires', 3600))  # Default 1 hour
        
        download_url = EmailManager.get_attachment_download_url(attachment_id, expires_in)
        
        if not download_url:
            raise biz.BusinessLogicError('Attachment not found', 404)
        
        return resp.success_response({
            'downloadUrl': download_url,
            'expiresIn': expires_in
        })
        
    except biz.BusinessLogicError:
        raise
    except Exception as e:
        print(f"Error generating download URL: {str(e)}")
        raise biz.BusinessLogicError('Failed to generate download URL', 500)


def handle_delete_attachment(attachment_id):
    """Delete an attachment"""
    try:
        success = EmailManager.delete_attachment(attachment_id)
        
        if success:
            return resp.success_response({'message': 'Attachment deleted successfully'})
        else:
            raise biz.BusinessLogicError('Attachment not found or already deleted', 404)
        
    except biz.BusinessLogicError:
        raise
    except Exception as e:
        print(f"Error deleting attachment: {str(e)}")
        raise biz.BusinessLogicError('Failed to delete attachment', 500)
