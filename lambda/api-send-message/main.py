import db_utils as db
import wsgw_utils as wsgw
import response_utils as resp
import request_utils as req

wsgw_client = wsgw.get_apigateway_client()

def lambda_handler(event, context):
    client_id = req.get_body_param(event, 'userId')
    message_id = req.get_body_param(event, 'messageId')
    message = req.get_body_param(event, 'message')
    
    if not client_id or not message_id or not message:
        return resp.error_response("userId, messageId, and message are required.")
    
    client_user_record = db.get_user_record(client_id)
    if not client_user_record:
        return resp.error_response(f"User with userId {client_id} does not exist.")
    
    assigned_to = client_user_record.get('assignedTo')
    receiverConnections = db.get_assigned_or_all_staff_connections(assigned_to=assigned_to)

    notification_data = {
        "type": "message",
        "subtype": "send",
        "success": True,
        "messageId": message_id,
        "message": message,
        "senderId": client_id
    }

    for receiverConnection in receiverConnections:
        wsgw.send_notification(wsgw_client, receiverConnection.get('connectionId'), notification_data)

    new_message_data = db.build_message_data(
        message_id=message_id,
        message=message,
        sender_id=client_id,
        receiver_id=client_user_record.get('assignedTo') if 'assignedTo' in client_user_record else 'ALL'
    )
    success = db.create_message(new_message_data)
    if not success:
        return resp.error_response(f"Failed to store message with ID: {message_id}. Please try again later.")

    return resp.success_response({
        "message": f"Message with ID: {message_id} sent successfully to userId: {client_id}.",
    })  
