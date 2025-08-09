import db_utils as db
import response_utils as resp
import request_utils as req
import notification_utils as notify

PERMITTED_ROLE = 'CUSTOMER_SUPPORT'

def lambda_handler(event, context):
    staff_email = req.get_staff_user_email(event)
    client_id = req.get_body_param(event, 'clientId')

    if not staff_email:
        return resp.error_response("Unauthorized: Staff authentication required", 401)

    if not client_id:
        return resp.error_response("clientId is required.")

    staff_user_record = db.get_staff_record(staff_email)
    if not staff_user_record:
        return resp.error_response(f"No staff record found for email: {staff_email}.")
    
    staff_user_id = staff_user_record.get('userId')
    staff_roles = staff_user_record.get('roles', [])
    
    if not staff_user_id or not staff_roles:
        return resp.error_response("Unauthorized: Invalid staff user record.")

    if PERMITTED_ROLE not in staff_roles:
        return resp.error_response("Unauthorized: Insufficient permissions.")

    client_user_record = db.get_user_record(client_id)
    if not client_user_record:
        return resp.error_response(f"User with clientId {client_id} does not exist.")
    elif 'assignedTo' in client_user_record:
        if client_user_record.get('assignedTo') != staff_user_id:
            return resp.error_response(f"User {client_id} is already assigned to a different staff user: {client_user_record.get('assignedTo')}.")
        else:
            return resp.error_response(f"You have already taken the user with clientId: {client_id}.")

    assignment_success = db.assign_client_to_staff_user(client_id, staff_user_id)

    if not assignment_success:
        return resp.error_response(f"Failed to assign user {client_id} to staff user {staff_user_id}. Please try again later.")

    notification = {
        "type": "notification",
        "subtype": "take-user",
        "success": assignment_success,
        "userId": client_id,
        "staffUserId": staff_user_id,
    }
    
    # Queue notification to all staff except the one who took the user
    notify.queue_staff_websocket_notification(notification, exclude_user_id=staff_user_id)
    
    # Queue Firebase push notification to all staff except the one who took the user  
    # Note: Firebase notification helper will handle excluding the staff user who took the action
    notify.queue_user_assignment_firebase_notification(client_id, staff_user_id, exclude_user_id=staff_user_id)
    
    return resp.success_response({
        "message": f"User {client_id} has been successfully assigned to staff user {staff_user_id}.",
    })
