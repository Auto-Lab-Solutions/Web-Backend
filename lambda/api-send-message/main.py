import db_utils as db
import response_utils as resp
import request_utils as req
import notification_utils as notify

PERMITTED_ROLE = 'CUSTOMER_SUPPORT'


def lambda_handler(event, context):
    staff_user_email = req.get_staff_user_email(event)
    client_id = req.get_body_param(event, 'clientId')
    message_id = req.get_body_param(event, 'messageId')
    message = req.get_body_param(event, 'message')

    if not client_id or not message_id or not message:
        return resp.error_response("userId, messageId, and message are required.")

    if staff_user_email:
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
        if 'assignedTo' not in client_user_record:
            return resp.error_response(f"User with receiverId {client_id} is not assigned to any staff user.")
        if client_user_record.get('assignedTo') != staff_user_id:
            assigned_to = client_user_record.get('assignedTo')
            return resp.error_response(
                f"User with receiverId: {client_id} is assigned to a different staff user: {assigned_to}. You cannot send messages to this user."
            )

        notification_data = {
            "type": "message",
            "subtype": "send",
            "success": True,
            "messageId": message_id,
            "message": message,
            "senderId": staff_user_id,
        }
        
        # Queue notification to specific client
        notify.queue_websocket_notification('message_notification', notification_data, user_id=client_id)

        if not store_message(message_id, message, staff_user_id, client_id):
            return resp.error_response(f"Failed to store message with ID: {message_id}. Please try again later.")

        return resp.success_response({
            "message": f"Message with ID: {message_id} sent successfully to userId: {client_id}.",
        })

    # Client sending message
    client_user_record = db.get_user_record(client_id)
    if not client_user_record:
        return resp.error_response(f"User with userId {client_id} does not exist.")

    assigned_to = client_user_record.get('assignedTo')
    receiver_connections = db.get_assigned_or_all_staff_connections(assigned_to=assigned_to)

    notification_data = {
        "type": "message",
        "subtype": "send",
        "success": True,
        "messageId": message_id,
        "message": message,
        "senderId": client_id
    }
    
    # Queue notification to assigned staff or all staff if unassigned
    notify.queue_staff_websocket_notification(notification_data, assigned_to=assigned_to)
    
    # Queue Firebase push notification to assigned staff or all staff
    if assigned_to:
        notify.queue_message_firebase_notification(message_id, 'client_message', [assigned_to])
    else:
        notify.queue_message_firebase_notification(message_id, 'client_message')

    receiver_id = assigned_to if assigned_to else 'ALL'
    if not store_message(message_id, message, client_id, receiver_id):
        return resp.error_response(f"Failed to store message with ID: {message_id}. Please try again later.")

    return resp.success_response({
        "message": f"Message with ID: {message_id} sent successfully from user {client_id}.",
    })



def store_message(message_id, message, sender_id, receiver_id):
    new_message_data = db.build_message_data(
        message_id=message_id,
        message=message,
        sender_id=sender_id,
        receiver_id=receiver_id
    )
    return db.create_message(new_message_data)
