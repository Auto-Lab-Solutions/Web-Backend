from datetime import datetime
from zoneinfo import ZoneInfo
import db_utils as db
import response_utils as resp
import request_utils as req
from notification_manager import notification_manager

valid_statuses = [
    'TYPING',
    'MESSAGE_RECEIVED',
    'MESSAGE_VIEWED',
    'MESSAGE_DELETED',
    'MESSAGE_EDITED'
]

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

    if status == 'TYPING':
        notification = {
            "type": "notification",
            "subtype": "status",
            "success": True,
            "status": status,
            "senderId": action_sender_id,
            "timestamp": int(datetime.now(ZoneInfo('Australia/Perth')).timestamp())
        }
        
        if not action_sender_conn.get('staff'):
            # User is typing - notify assigned staff or all staff
            action_sender_record = db.get_user_record(action_sender_id)
            assigned_to = action_sender_record.get('assignedTo') if action_sender_record else None
            import sync_websocket_utils as sync_ws
            sync_ws.send_staff_websocket_notification(notification, assigned_to=assigned_to)
        else:
            # Staff is typing - notify specific client
            if not client_id:
                return resp.error_response("clientId is required for TYPING status.")
            import sync_websocket_utils as sync_ws
            sync_ws.send_websocket_notification('typing_notification', notification, user_id=client_id)
        
        return resp.success_response(
            { "message": f"Notification queued successfully for TYPING status." },
            success=True
        )

    if not message_id:
        return resp.error_response("messageId is required for this status.")

    message_item = db.get_message(message_id)
    if not message_item:
        return resp.error_response(f"Message with ID {message_id} does not exist.")

    msg_receiver_id = message_item.get('receiverId')
    msg_sender_id = message_item.get('senderId')

    notification = {
        "type": "notification",
        "subtype": "status",
        "success": True,
        "messageId": message_id,
        "status": status,
        "message": message_item.get('message', ''),
        "senderId": msg_sender_id,
        "receiverId": msg_receiver_id,
        "timestamp": int(datetime.now(ZoneInfo('Australia/Perth')).timestamp())
    }

    if status in ['MESSAGE_RECEIVED', 'MESSAGE_VIEWED']:
        if msg_receiver_id == 'ALL':
            msg_receiver_id = action_sender_id
            
        if msg_receiver_id != action_sender_id:
            return resp.error_response("You are not authorized to send RECEIVED/VIEWED notifications for this message.")
        
        # Queue notification to message sender
        import sync_websocket_utils as sync_ws
        sync_ws.send_websocket_notification('message_status_notification', notification, user_id=msg_sender_id)

        update_status = db.update_message_status(
            message_id=message_id,
            status=status
        )
        if not update_status:
            return resp.error_response(f"Failed to update message status for messageId: {message_id}.")
        
        return resp.success_response(
            { "message": f"Notification queued successfully for {status}." }, 
            success=True
        )

    elif status in ['MESSAGE_DELETED', 'MESSAGE_EDITED']:
        skip = False

        if msg_sender_id != action_sender_id:
            return resp.error_response("You are not authorized to send DELETED/EDITED notifications for this message.")
        
        if status == 'MESSAGE_EDITED':
            if not new_message:
                return resp.error_response("newMessage is required for MESSAGE_EDITED status.")
            notification['newMessage'] = new_message
            notification['originalMessage'] = message_item.get('message', '')
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
        
        # Send notification to message receiver(s)
        import sync_websocket_utils as sync_ws
        if msg_receiver_id == 'ALL':
            # Broadcast to all staff
            sync_ws.send_staff_websocket_notification(notification)
        else:
            # Send to specific user
            sync_ws.send_websocket_notification('message_edit_notification', notification, user_id=msg_receiver_id)

        return resp.success_response(
            { "message": f"Notification queued successfully for {status}." }, 
            success=True
        )

    return resp.error_response(f"Unsupported status: {status}")

