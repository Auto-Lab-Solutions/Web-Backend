"""
Synchronous WebSocket notification utilities for messaging scenarios only.
This module handles real-time websocket notifications for messaging without queuing.
"""
import time
from datetime import datetime
from zoneinfo import ZoneInfo
import db_utils as db
import wsgw_utils as wsgw


def send_message_websocket_notification(message_id, sender_id, recipient_id, message_content=None, message_type='general'):
    """
    Send WebSocket notification for new message synchronously (messaging scenarios only)
    
    Args:
        message_id (str): Message ID
        sender_id (str): Sender user ID
        recipient_id (str): Recipient user ID or "ALL" for staff broadcast
        message_content (str, optional): Message content
        message_type (str): Type of message (default: 'general')
    
    Returns:
        bool: True if notification sent successfully, False otherwise
    """
    try:
        # Get complete message data if not provided
        if not message_content:
            message_data = db.get_message(message_id)
            if message_data:
                message_content = message_data.get('message', '')
            else:
                print(f"Warning: Could not retrieve message data for messageId {message_id}")
                message_content = "Message content unavailable"
        
        notification_data = {
            "type": "message",
            "subtype": "new",
            "messageId": message_id,
            "senderId": sender_id,
            "receiverId": recipient_id,
            "message": message_content,
            "messageType": message_type,
            "timestamp": int(datetime.now(ZoneInfo('Australia/Perth')).timestamp()),
            "received": False,
            "viewed": False
        }
        
        # Get WebSocket Gateway client
        wsgw_client = wsgw.get_apigateway_client()
        if not wsgw_client:
            print("Failed to create WebSocket Gateway client")
            return False
        
        # Handle broadcasting to all staff
        if recipient_id == "ALL":
            return send_staff_notification(wsgw_client, notification_data)
        else:
            return send_user_notification(wsgw_client, notification_data, recipient_id)
            
    except Exception as e:
        print(f"Error sending message WebSocket notification: {str(e)}")
        return False


def send_staff_websocket_notification(notification_data, assigned_to=None, exclude_user_id=None):
    """
    Send WebSocket notification to staff members synchronously (messaging scenarios only)
    
    Args:
        notification_data (dict): Notification data to send
        assigned_to (str, optional): Send only to specific assigned staff member
        exclude_user_id (str, optional): Exclude specific user from notification
    
    Returns:
        bool: True if notification sent successfully, False otherwise
    """
    try:
        # Get WebSocket Gateway client
        wsgw_client = wsgw.get_apigateway_client()
        if not wsgw_client:
            print("Failed to create WebSocket Gateway client")
            return False
        
        # Add staff broadcast flag and timestamp
        staff_notification_data = notification_data.copy() if isinstance(notification_data, dict) else {}
        staff_notification_data['staff_broadcast'] = True
        staff_notification_data['timestamp'] = int(datetime.now(ZoneInfo('Australia/Perth')).timestamp())
        
        if assigned_to:
            staff_notification_data['assigned_to'] = assigned_to
        if exclude_user_id:
            staff_notification_data['exclude_user_id'] = exclude_user_id
        
        return send_staff_notification(wsgw_client, staff_notification_data, assigned_to, exclude_user_id)
        
    except Exception as e:
        print(f"Error sending staff WebSocket notification: {str(e)}")
        return False


def send_websocket_notification(notification_type, notification_data, user_id=None, connection_id=None):
    """
    Send WebSocket notification synchronously (messaging scenarios only)
    
    Args:
        notification_type (str): Type of WebSocket notification
        notification_data (dict): Notification data to send
        user_id (str, optional): User ID to send notification to
        connection_id (str, optional): Specific connection ID to send to
    
    Returns:
        bool: True if notification sent successfully, False otherwise
    """
    try:
        # Get WebSocket Gateway client
        wsgw_client = wsgw.get_apigateway_client()
        if not wsgw_client:
            print("Failed to create WebSocket Gateway client")
            return False
        
        # Handle staff broadcast notifications
        if notification_data.get('staff_broadcast'):
            assigned_to = notification_data.get('assigned_to')
            exclude_user_id = notification_data.get('exclude_user_id')
            return send_staff_notification(wsgw_client, notification_data, assigned_to, exclude_user_id)
        
        # If connection_id is provided, use it directly
        if connection_id:
            return wsgw.send_notification(wsgw_client, connection_id, notification_data)
        
        # If user_id is provided, find their connection
        if user_id:
            return send_user_notification(wsgw_client, notification_data, user_id)
        
        print(f"No connection_id or user_id provided for WebSocket notification")
        return False
            
    except Exception as e:
        print(f"Error sending WebSocket notification: {str(e)}")
        return False


def send_user_notification(wsgw_client, notification_data, user_id):
    """
    Send notification to a specific user
    
    Args:
        wsgw_client: WebSocket Gateway client
        notification_data (dict): Notification data to send
        user_id (str): User ID to send notification to
    
    Returns:
        bool: True if notification sent successfully, False otherwise
    """
    try:
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
            
    except Exception as e:
        print(f"Error sending notification to user {user_id}: {str(e)}")
        return False


def send_staff_notification(wsgw_client, notification_data, assigned_to=None, exclude_user_id=None):
    """
    Send notifications to relevant staff members
    
    Args:
        wsgw_client: WebSocket Gateway client
        notification_data (dict): Notification data to send
        assigned_to (str, optional): Send only to specific assigned staff member
        exclude_user_id (str, optional): Exclude specific user from notification
    
    Returns:
        bool: True if at least one notification sent successfully, False otherwise
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
