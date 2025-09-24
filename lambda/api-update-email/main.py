import request_utils as req
import response_utils as resp
import permission_utils as perm
import business_logic_utils as biz

@perm.handle_permission_error
@biz.handle_business_logic_error
def lambda_handler(event, context):
    """Update email metadata like isImportant, isRead, and tags for staff users"""
    
    # Get staff user information and validate permissions
    staff_user_email = req.get_staff_user_email(event)
    
    # Validate staff has email management permissions
    staff_context = perm.PermissionValidator.validate_staff_access(
        staff_user_email, 
        required_roles=['CUSTOMER_SUPPORT', 'ADMIN']
    )
    
    # Get email ID from path parameters
    email_id = req.get_path_param(event, 'emailId')
    if not email_id:
        raise biz.BusinessLogicError("emailId is required in path")
    
    # Get request body
    body = req.get_body(event)
    if not body:
        raise biz.BusinessLogicError("Request body is required")
    
    # Extract update parameters
    is_important = body.get('isImportant')
    is_read = body.get('isRead')
    tags = body.get('tags')
    
    # Validate that at least one field is being updated
    if is_important is None and is_read is None and tags is None:
        raise biz.BusinessLogicError("At least one field (isImportant, isRead, or tags) must be provided")
    
    # Validate tags if provided
    if tags is not None:
        if not isinstance(tags, list):
            raise biz.BusinessLogicError("tags must be an array")
        
        # Validate each tag
        for tag in tags:
            if not isinstance(tag, str) or len(tag.strip()) == 0:
                raise biz.BusinessLogicError("All tags must be non-empty strings")
            if len(tag) > 50:
                raise biz.BusinessLogicError("Tags cannot be longer than 50 characters")
        
        # Limit number of tags
        if len(tags) > 20:
            raise biz.BusinessLogicError("Maximum of 20 tags allowed per email")
    
    # Check if email exists
    existing_email = biz.EmailManager.get_email_by_id_full(email_id)
    if not existing_email:
        raise biz.BusinessLogicError("Email not found", 404)
    
    # Update the email data
    success = biz.EmailManager.update_email_data(
        message_id=email_id,
        is_important=is_important,
        is_read=is_read,
        tags=tags
    )
    
    if not success:
        raise biz.BusinessLogicError("Failed to update email data", 500)
    
    # Return success response with updated data
    result = {
        "message": "Email updated successfully",
        "emailId": email_id,
        "updatedFields": {}
    }
    
    if is_important is not None:
        result["updatedFields"]["isImportant"] = is_important
    if is_read is not None:
        result["updatedFields"]["isRead"] = is_read
    if tags is not None:
        result["updatedFields"]["tags"] = tags
    
    return resp.success_response(result)
