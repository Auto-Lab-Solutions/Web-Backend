import json
import os
import sys
import traceback

# Add common_lib to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'common_lib'))

import db_utils as db
import wsgw_utils as wsgw
import response_utils as resp
import business_logic_utils as biz

# Initialize WebSocket Gateway client
wsgw_client = wsgw.get_apigateway_client()

@biz.handle_business_logic_error
def lambda_handler(event, context):
    """
    Process WebSocket notification requests from SQS queue with enhanced error handling
    """
    try:
        print(f"Processing {len(event.get('Records', []))} WebSocket notification requests")
        
        processed = 0
        failed = 0
        
        # Initialize WebSocket Gateway client
        wsgw_client = wsgw.get_apigateway_client()
        
        # Process each SQS record
        for record in event.get('Records', []):
            try:
                # Parse the message
                message_body = json.loads(record['body'])
                
                # Extract notification data from message
                notification_type = message_body['notification_type']
                user_id = message_body.get('user_id')
                connection_id = message_body.get('connection_id')
                notification_data = message_body['notification_data']
                
                print(f"Processing WebSocket notification: {notification_type} for user: {user_id}")
                
                # Send WebSocket notification
                success = send_websocket_notification(wsgw_client, notification_type, user_id, connection_id, notification_data)
                
                if success:
                    processed += 1
                    print(f"Successfully sent WebSocket notification to user {user_id}")
                else:
                    failed += 1
                    print(f"Failed to send WebSocket notification to user {user_id}")
                    
            except json.JSONDecodeError as e:
                failed += 1
                print(f"Failed to parse SQS message body as JSON: {str(e)}")
            except Exception as e:
                failed += 1
                print(f"Error processing WebSocket notification record: {str(e)}")
                print(f"Traceback: {traceback.format_exc()}")
                # Continue processing other records even if one fails
        
        print(f"WebSocket notification processing complete. Processed: {processed}, Failed: {failed}")
        
        # Return success response using standard response format
        return resp.success_response({
            'message': f'Successfully processed {processed} WebSocket notifications',
            'processed': processed,
            'failed': failed,
            'total_messages': len(event.get('Records', []))
        })
        
    except Exception as e:
        print(f"Critical error in WebSocket notification processing: {str(e)}")
        raise biz.BusinessLogicError(f"WebSocket notification processing failed: {str(e)}", 500)

def send_websocket_notification(wsgw_client, notification_type, user_id, connection_id, notification_data):
    """
    Send WebSocket notification to connected clients
    """
    try:
        # Handle staff broadcast notifications
        if notification_data.get('staff_broadcast'):
            assigned_to = notification_data.get('assigned_to')
            exclude_user_id = notification_data.get('exclude_user_id')
            return send_staff_notifications(wsgw_client, notification_data, assigned_to, exclude_user_id)
        
        # If connection_id is provided, use it directly
        if connection_id:
            return wsgw.send_notification(wsgw_client, connection_id, notification_data)
        
        # If user_id is provided, find their connection
        if user_id:
            user_connection = db.get_connection_by_user_id(user_id)
            if user_connection:
                connection_id = user_connection.get('connectionId')
                if connection_id:
                    return wsgw.send_notification(wsgw_client, connection_id, notification_data)
                else:
                    print(f"No connection ID found for user {user_id}")
                    return False
            else:
                print(f"No connection found for user {user_id}")
                return False
        
        print(f"No connection_id or user_id provided for WebSocket notification")
        return False
            
    except Exception as e:
        print(f"Error sending WebSocket notification: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return False

def send_staff_notifications(wsgw_client, notification_data, assigned_to=None, exclude_user_id=None):
    """
    Send notifications to relevant staff members
    """
    try:
        # Get staff connections
        staff_connections = db.get_assigned_or_all_staff_connections(assigned_to=assigned_to)
        
        success_count = 0
        total_count = 0
        
        for staff_connection in staff_connections:
            # Skip if this connection should be excluded
            if exclude_user_id and staff_connection.get('userId') == exclude_user_id:
                continue
                
            total_count += 1
            connection_id = staff_connection.get('connectionId')
            if connection_id:
                if wsgw.send_notification(wsgw_client, connection_id, notification_data):
                    success_count += 1
        
        print(f"Sent staff notifications: {success_count}/{total_count} successful")
        return success_count > 0
        
    except Exception as e:
        print(f"Error sending staff notifications: {str(e)}")
        return False
