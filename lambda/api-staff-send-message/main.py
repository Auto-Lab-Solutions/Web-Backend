import db_utils as db
import wsgw_utils as wsgw
import response_utils as resp
import request_utils as req

PERMITTED_ROLE = 'CUSTOMER_SUPPORT'

wsgw_client = wsgw.get_apigateway_client()

def lambda_handler(event, context):
    staff_user_email = req.get_staff_user_email(event)
    client_id = req.get_body_param(event, 'clientId')
    message_id = req.get_body_param(event, 'messageId')
    message = req.get_body_param(event, 'message')

    if not client_id or not message_id or not message:
        return resp.error_response("clientId, messageId, and message are required.")

    staff_user_record = db.get_staff_record(staff_user_email)
    if not staff_user_record:
        return resp.error_response(f"No staff record found for email: {staff_user_email}.")

    staff_user_id = staff_user_record.get('userId')
    staff_roles = staff_user_record.get('roles', [])
    
    if not staff_user_id or not staff_roles:
        return resp.error_response("Unauthorized: Invalid staff user record.")

    if PERMITTED_ROLE not in staff_roles:
        return resp.error_response("Unauthorized: Insufficient permissions.")
    
    client_user_record = db.get_user_record(client_id)
    if not client_user_record:
        return resp.error_response(f"User with receiverId {client_id} does not exist.")
    elif 'assignedTo' not in client_user_record:
        return resp.error_response(f"User with receiverId {client_id} is not assigned to any staff user.")
    elif client_user_record.get('assignedTo') != staff_user_id:
        return resp.error_response(f"User with receiverId: {client_id} is assigned to a different staff user: {client_user_record.get('assignedTo')}. You cannot send messages to this user.")
    
    notification_data = {
        "type": "message",
        "subtype": "send",
        "success": True,
        "messageId": message_id,
        "message": message,
        "senderId": staff_user_id,
    }
    client_conn = db.get_connection_by_user_id(client_id)
    if client_conn:
        wsgw.send_notification(wsgw_client, client_conn.get('connectionId'), notification_data)

    new_message_data = db.build_message_data(
        message_id=message_id,
        message=message,
        sender_id=staff_user_id,
        receiver_id=client_id
    )
    success = db.create_message(new_message_data)
    if not success:
        return resp.error_response(f"Failed to store message with ID: {message_id}. Please try again later.")

    return resp.success_response({
        "message": f"Message with ID: {message_id} sent successfully to userId: {client_id}.",
    })

