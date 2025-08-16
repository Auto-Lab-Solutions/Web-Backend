import request_utils as req
import response_utils as resp
from email_suppression_manager import handle_business_logic_error, BusinessLogicError
from permission_utils import PermissionValidator
import db_utils as db
from notification_manager import notification_manager


@handle_business_logic_error
def lambda_handler(event, context):
    staff_email = req.get_staff_user_email(event)
    client_id = req.get_body_param(event, 'clientId')

    if not staff_email:
        return resp.error_response("Unauthorized: Staff authentication required", 401)

    if not client_id:
        return resp.error_response("clientId is required.")

    # Validate staff permissions
    staff_context = PermissionValidator.validate_staff_access(
        staff_email,
        required_roles=['CUSTOMER_SUPPORT']
    )
    
    staff_user_id = staff_context['user_id']
    
    # Check if client exists
    client_user_record = db.get_user_record(client_id)
    if not client_user_record:
        raise BusinessLogicError(f"User with clientId {client_id} does not exist.", 404)
    
    # Check assignment status
    if 'assignedTo' in client_user_record:
        if client_user_record.get('assignedTo') != staff_user_id:
            raise BusinessLogicError(f"User {client_id} is already assigned to a different staff user: {client_user_record.get('assignedTo')}.", 409)
        else:
            raise BusinessLogicError(f"You have already taken the user with clientId: {client_id}.", 409)

    # Assign user to staff
    assignment_success = db.assign_client_to_staff_user(client_id, staff_user_id)
    if not assignment_success:
        raise BusinessLogicError(f"Failed to assign user {client_id} to staff user {staff_user_id}. Please try again later.", 500)

    # Send notifications
    notification = {
        "type": "notification",
        "subtype": "take-user",
        "success": assignment_success,
        "userId": client_id,
        "staffUserId": staff_user_id,
    }
    
    # Queue notification to all staff except the one who took the user
    notification_manager.queue_staff_websocket_notification(notification, exclude_user_id=staff_user_id)
    
    # Queue Firebase push notification to all staff except the one who took the user
    # Get staff user record to get the staff name for better notification
    staff_user_record = db.get_user_record(staff_user_id)
    staff_name = staff_user_record.get('name', 'Staff Member') if staff_user_record else 'Staff Member'
    notification_manager.queue_user_assignment_firebase_notification(client_id, staff_name, exclude_user_id=staff_user_id)
    
    return resp.success_response({
        "message": f"User {client_id} has been successfully assigned to staff user {staff_user_id}.",
    })
