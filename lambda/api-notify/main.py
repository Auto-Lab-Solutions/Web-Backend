import db_utils as db
import wsgw_utils as wsgw
import response_utils as resp
import request_utils as req

valid_statuses = [
    'TYPING',
    'MESSAGE_RECEIVED',
    'MESSAGE_VIEWED',
    'MESSAGE_DELETED',
    'MESSAGE_EDITED'
]

wsgw_client = wsgw.get_apigateway_client()

def lambda_handler(event, context):
    staff_user_email = req.get_staff_user_email(event)
    user_id = req.get_body_param(event, 'userId')
    client_id = req.get_body_param(event, 'clientId')
    status = req.get_body_param(event, 'status')
    message_id = req.get_body_param(event, 'messageId')
    new_message = req.get_body_param(event, 'newMessage')

    if not status or status not in valid_statuses:
        return resp.error_response("Invalid or missing status. Valid statuses are: " + ", ".join(valid_statuses))
    
    action_sender_id = None

    if staff_user_email:
        staff_user_record = db.get_staff_record(staff_user_email)
        if not staff_user_record:
            return resp.error_response(f"No staff record found for email: {staff_user_email}.")
        action_sender_id = staff_user_record.get('userId')
    else:
        if not user_id:
            return resp.error_response("userId is required for non-staff users.")
        action_sender_id = user_id
    
    action_sender_conn = db.get_connection_by_user_id(action_sender_id)
    if not action_sender_conn:
        return resp.error_response(f"No connection found for userId: {action_sender_id}.")

    receiverConnections = []
    if status == 'TYPING':
        if not action_sender_conn.get('staff'):
            action_sender_record = db.get_user_record(action_sender_id)
            receiverConnections = db.get_assigned_or_all_staff_connections(assigned_to=action_sender_record.get('assignedTo'))
        else:
            if not client_id:
                return resp.error_response("clientId is required for TYPING status.")
            client_conn = db.get_connection_by_user_id(client_id)
            if client_conn:
                receiverConnections.append(client_conn)

        notification = {
            "type": "notification",
            "subtype": "status",
            "success": True,
            "status": status,
            "senderId": action_sender_id
        }

        for receiverConnection in receiverConnections:
            wsgw.send_notification(wsgw_client, receiverConnection.get('connectionId'), notification)
        
        return resp.success_response(
            { "message": f"Notification sent successfully for TYPING status to {len(receiverConnections)} receivers." },
            success=True
        )

    if not message_id:
        return resp.error_response("messageId is required for this status.")

    message_item = db.get_message(message_id)
    if not message_item:
        return resp.error_response(f"Message with ID {message_id} does not exist.")

    notification = {
        "type": "notification",
        "subtype": "status",
        "success": True,
        "messageId": message_id,
        "status": status
    }

    msg_receiver_id = message_item.get('receiverId')
    msg_sender_id = message_item.get('senderId')

    if status in ['MESSAGE_RECEIVED', 'MESSAGE_VIEWED']:
        if msg_receiver_id == 'ALL':
            return resp.success_response(
                { "message": "Cannot send notifications for staff unassigned messages. Skipping." },
                success=False
            )
        if msg_receiver_id != action_sender_id:
            return resp.error_response("You are not authorized to send RECEIVED/VIEWED notifications for this message.")
        
        msg_sender_conn = db.get_connection_by_user_id(msg_sender_id)
        msg_sender_conn_id = msg_sender_conn.get('connectionId') if msg_sender_conn else None
        skip = not msg_sender_conn_id

        if not skip:
            wsgw.send_notification(
                wsgw_client,
                msg_sender_conn_id,
                notification
            )

        update_status = db.update_message_status(
            message_id=message_id,
            status=status
        )
        if not update_status:
            return resp.error_response(f"Failed to update message status for messageId: {message_id}.")
        
        return resp.success_response(
            { "message": f"No connection found for senderId: {msg_sender_id}. Skipping notification." if skip else f"Notification sent successfully for {status}." }, 
            success=not skip
        )

    elif status in ['MESSAGE_DELETED', 'MESSAGE_EDITED']:
        skip = False

        if msg_sender_id != action_sender_id:
            return resp.error_response("You are not authorized to send DELETED/EDITED notifications for this message.")
        
        msg_receiver_connections = []
        if msg_receiver_id == 'ALL':
            msg_receiver_connections = db.get_all_staff_connections()
        else:
            msg_receiver_conn = db.get_connection_by_user_id(msg_receiver_id)
            if msg_receiver_conn:
                msg_receiver_connections.append(msg_receiver_conn)
            skip = not msg_receiver_conn

        if status == 'MESSAGE_EDITED':
            if not new_message:
                return resp.error_response("newMessage is required for MESSAGE_EDITED status.")
            notification['newMessage'] = new_message
            operation_success = db.update_message_content(
                message_id=message_id,
                new_message=new_message
            )
        
        elif status == 'MESSAGE_DELETED':
            operation_success = db.delete_message(message_id)

        if not operation_success:
            return resp.error_response(
                f"Failed to {status.lower()} message with ID: {message_id}. Please try again later."
            )
        
        if not skip:
            for msg_receiver_conn in msg_receiver_connections:
                wsgw.send_notification(
                    wsgw_client,
                    msg_receiver_conn.get('connectionId'),
                    notification
                )

        return resp.success_response(
            { "message": f"No connection found for receiverId: {msg_receiver_id}. Skipping notification." if skip else f"Notification sent successfully for {status}." }, 
            success=not skip
        )

    return resp.error_response(f"Unsupported status: {status}")

