import boto3
import json
import os
from botocore.exceptions import ClientError

# Initialize SQS client
sqs = boto3.client('sqs')

# Environment variables for queue URLs
EMAIL_NOTIFICATION_QUEUE_URL = os.environ.get('EMAIL_NOTIFICATION_QUEUE_URL', '')
WEBSOCKET_NOTIFICATION_QUEUE_URL = os.environ.get('WEBSOCKET_NOTIFICATION_QUEUE_URL', '')
FIREBASE_NOTIFICATION_QUEUE_URL = os.environ.get('FIREBASE_NOTIFICATION_QUEUE_URL', '')

# ===========================================================================
# Email Notification Functions
# ===========================================================================

def queue_email_notification(notification_type, customer_email, customer_name, data):
    """
    Queue an email notification for asynchronous processing
    
    Args:
        notification_type (str): Type of email notification (e.g., 'appointment_created', 'order_updated')
        customer_email (str): Customer email address
        customer_name (str): Customer name
        data (dict): Email data containing all necessary information
    
    Returns:
        bool: True if queued successfully, False otherwise
    """
    try:
        # Prepare the message
        message = {
            'notification_type': notification_type,
            'customer_email': customer_email,
            'customer_name': customer_name,
            'data': data
        }
        
        # Send message to SQS queue
        response = sqs.send_message(
            QueueUrl=EMAIL_NOTIFICATION_QUEUE_URL,
            MessageBody=json.dumps(message),
            MessageAttributes={
                'NotificationType': {
                    'StringValue': notification_type,
                    'DataType': 'String'
                },
                'CustomerEmail': {
                    'StringValue': customer_email,
                    'DataType': 'String'
                }
            }
        )
        
        message_id = response['MessageId']
        print(f"Email notification queued successfully. MessageId: {message_id}")
        return True
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        print(f"Failed to queue email notification. Error: {error_code} - {error_message}")
        return False
    except Exception as e:
        print(f"Unexpected error queuing email notification: {str(e)}")
        return False

def queue_appointment_created_email(customer_email, customer_name, appointment_data):
    """Queue appointment created email notification"""
    return queue_email_notification('appointment_created', customer_email, customer_name, appointment_data)

def queue_appointment_updated_email(customer_email, customer_name, appointment_data, changes=None, update_type='general'):
    """Queue appointment updated email notification"""
    data = appointment_data.copy()
    if changes:
        data['changes'] = changes
    data['update_type'] = update_type
    return queue_email_notification('appointment_updated', customer_email, customer_name, data)

def queue_order_created_email(customer_email, customer_name, order_data):
    """Queue order created email notification"""
    return queue_email_notification('order_created', customer_email, customer_name, order_data)

def queue_order_updated_email(customer_email, customer_name, order_data, changes=None, update_type='general'):
    """Queue order updated email notification"""
    data = order_data.copy()
    if changes:
        data['changes'] = changes
    data['update_type'] = update_type
    return queue_email_notification('order_updated', customer_email, customer_name, data)

def queue_report_ready_email(customer_email, customer_name, appointment_or_order_data, report_url):
    """Queue report ready email notification"""
    data = appointment_or_order_data.copy()
    data['report_url'] = report_url
    return queue_email_notification('report_ready', customer_email, customer_name, data)

def queue_payment_confirmation_email(customer_email, customer_name, payment_data, invoice_url):
    """Queue payment confirmation email notification"""
    data = payment_data.copy()
    data['invoice_url'] = invoice_url
    return queue_email_notification('payment_confirmed', customer_email, customer_name, data)

# ===========================================================================
# WebSocket Notification Functions
# ===========================================================================

def queue_websocket_notification(notification_type, notification_data, user_id=None, connection_id=None):
    """
    Queue a WebSocket notification for asynchronous processing
    
    Args:
        notification_type (str): Type of WebSocket notification
        notification_data (dict): Notification data to send via WebSocket
        user_id (str, optional): User ID to send notification to
        connection_id (str, optional): Specific connection ID to send to
    
    Returns:
        bool: True if queued successfully, False otherwise
    """
    try:
        # Prepare the message
        message = {
            'notification_type': notification_type,
            'notification_data': notification_data
        }
        
        if user_id:
            message['user_id'] = user_id
        if connection_id:
            message['connection_id'] = connection_id
        
        # Prepare message attributes
        message_attributes = {
            'NotificationType': {
                'StringValue': notification_type,
                'DataType': 'String'
            }
        }
        
        if user_id:
            message_attributes['UserId'] = {
                'StringValue': user_id,
                'DataType': 'String'
            }
        
        # Send message to SQS queue
        response = sqs.send_message(
            QueueUrl=WEBSOCKET_NOTIFICATION_QUEUE_URL,
            MessageBody=json.dumps(message),
            MessageAttributes=message_attributes
        )
        
        message_id = response['MessageId']
        print(f"WebSocket notification queued successfully. MessageId: {message_id}")
        return True
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        print(f"Failed to queue WebSocket notification. Error: {error_code} - {error_message}")
        return False
    except Exception as e:
        print(f"Unexpected error queuing WebSocket notification: {str(e)}")
        return False

def queue_appointment_websocket_notification(appointment_id, scenario, update_data, user_id):
    """Queue appointment WebSocket notification"""
    notification_data = {
        "type": "appointment",
        "subtype": "update", 
        "scenario": scenario,
        "appointmentId": appointment_id,
        "changes": list(update_data.keys()) if isinstance(update_data, dict) else []
    }
    return queue_websocket_notification('appointment_update', notification_data, user_id=user_id)

def queue_order_websocket_notification(order_id, scenario, update_data, user_id):
    """Queue order WebSocket notification"""
    notification_data = {
        "type": "order",
        "subtype": "update",
        "scenario": scenario,
        "orderId": order_id,
        "changes": list(update_data.keys()) if isinstance(update_data, dict) else []
    }
    return queue_websocket_notification('order_update', notification_data, user_id=user_id)

def queue_staff_websocket_notification(notification_data, assigned_to=None, exclude_user_id=None):
    """Queue WebSocket notification for staff members"""
    # This will need to be handled differently since it's a broadcast to multiple connections
    # We'll send it as a special notification type that the processor will handle
    notification_data['staff_broadcast'] = True
    if assigned_to:
        notification_data['assigned_to'] = assigned_to
    if exclude_user_id:
        notification_data['exclude_user_id'] = exclude_user_id
    return queue_websocket_notification('staff_notification', notification_data)

# ============================================================================
# Firebase Push Notification Functions
# ============================================================================

def queue_firebase_notification(notification_type, title, body, data=None, target_type='user', staff_user_ids=None, roles=None, excluded_users=None):
    """
    Queue a Firebase push notification for asynchronous processing
    
    Args:
        notification_type (str): Type of notification (e.g., 'order_update', 'appointment_reminder')
        title (str): Notification title
        body (str): Notification body text
        data (dict): Additional data payload (optional)
        target_type (str): 'user' for specific users, 'broadcast' for all staff
        staff_user_ids (list): List of staff user IDs to notify (when target_type='user')
        roles (list): Staff roles to notify (when target_type='broadcast', optional filter)
        excluded_users (list): User IDs to exclude from notification (optional)
    
    Returns:
        bool: True if queued successfully, False otherwise
    """
    try:
        # Prepare the message
        message = {
            'notification_type': notification_type,
            'title': title,
            'body': body,
            'data': data or {},
            'target_type': target_type
        }
        
        if target_type == 'user' and staff_user_ids:
            message['staff_user_ids'] = staff_user_ids if isinstance(staff_user_ids, list) else [staff_user_ids]
        elif target_type == 'broadcast' and roles:
            message['roles'] = roles if isinstance(roles, list) else [roles]
        
        # Add excluded users if specified
        if excluded_users:
            message['excluded_users'] = excluded_users if isinstance(excluded_users, list) else [excluded_users]
        
        # Send message to SQS queue
        if not FIREBASE_NOTIFICATION_QUEUE_URL:
            print("Firebase notifications disabled - queue URL not configured")
            return False
        
        response = sqs.send_message(
            QueueUrl=FIREBASE_NOTIFICATION_QUEUE_URL,
            MessageBody=json.dumps(message),
            MessageAttributes={
                'NotificationType': {
                    'StringValue': notification_type,
                    'DataType': 'String'
                },
                'TargetType': {
                    'StringValue': target_type,
                    'DataType': 'String'
                }
            }
        )
        
        print(f"Firebase notification queued successfully. MessageId: {response['MessageId']}")
        return True
        
    except Exception as e:
        print(f"Failed to queue Firebase notification: {str(e)}")
        return False

# Specific Firebase notification helper functions for common use cases

def queue_order_firebase_notification(order_id, scenario, staff_user_ids=None):
    """Queue Firebase notification for order updates to staff"""
    titles = {
        'basic_info': 'Order Details Updated',
        'scheduling': 'Order Scheduling Updated',
        'status': 'Order Status Changed',
        'notes': 'Order Notes Updated'
    }
    
    bodies = {
        'basic_info': f'Order #{order_id} details have been updated',
        'scheduling': f'Order #{order_id} scheduling has been modified',
        'status': f'Order #{order_id} status has changed',
        'notes': f'Post-service notes added to Order #{order_id}'
    }
    
    title = titles.get(scenario, 'Order Updated')
    body = bodies.get(scenario, f'Order #{order_id} has been updated')
    
    data = {
        'type': 'order',
        'orderId': order_id,
        'scenario': scenario
    }
    
    if staff_user_ids:
        return queue_firebase_notification('order_update', title, body, data, 'user', staff_user_ids)
    else:
        # Broadcast to all customer support and clerk staff
        return queue_firebase_notification('order_update', title, body, data, 'broadcast', roles=['CUSTOMER_SUPPORT', 'CLERK'])

def queue_appointment_firebase_notification(appointment_id, scenario, staff_user_ids=None):
    """Queue Firebase notification for appointment updates to staff"""
    titles = {
        'created': 'New Appointment Booked',
        'updated': 'Appointment Updated',
        'cancelled': 'Appointment Cancelled',
        'confirmed': 'Appointment Confirmed'
    }
    
    bodies = {
        'created': f'New appointment #{appointment_id} has been booked',
        'updated': f'Appointment #{appointment_id} has been updated',
        'cancelled': f'Appointment #{appointment_id} has been cancelled',
        'confirmed': f'Appointment #{appointment_id} has been confirmed'
    }
    
    title = titles.get(scenario, 'Appointment Updated')
    body = bodies.get(scenario, f'Appointment #{appointment_id} has been updated')
    
    data = {
        'type': 'appointment',
        'appointmentId': appointment_id,
        'scenario': scenario
    }
    
    if staff_user_ids:
        return queue_firebase_notification('appointment_update', title, body, data, 'user', staff_user_ids)
    else:
        # Broadcast to all customer support, clerk, and mechanic staff
        return queue_firebase_notification('appointment_update', title, body, data, 'broadcast', roles=['CUSTOMER_SUPPORT', 'CLERK', 'MECHANIC'])

def queue_inquiry_firebase_notification(inquiry_id, staff_user_ids=None):
    """Queue Firebase notification for new inquiry to staff"""
    title = 'New Customer Inquiry'
    body = f'New inquiry #{inquiry_id} has been submitted'
    
    data = {
        'type': 'inquiry',
        'inquiryId': inquiry_id
    }
    
    if staff_user_ids:
        return queue_firebase_notification('new_inquiry', title, body, data, 'user', staff_user_ids)
    else:
        # Broadcast to all customer support and clerk staff
        return queue_firebase_notification('new_inquiry', title, body, data, 'broadcast', roles=['CUSTOMER_SUPPORT', 'CLERK'])

def queue_message_firebase_notification(message_id, sender_name, staff_user_ids=None):
    """Queue Firebase notification for new message to staff"""
    title = 'New Customer Message'
    body = f'New message from {sender_name}'
    
    data = {
        'type': 'message',
        'messageId': message_id,
        'senderName': sender_name
    }
    
    if staff_user_ids:
        return queue_firebase_notification('new_message', title, body, data, 'user', staff_user_ids)
    else:
        # Broadcast to all customer support and clerk staff
        return queue_firebase_notification('new_message', title, body, data, 'broadcast', roles=['CUSTOMER_SUPPORT', 'CLERK'])

def queue_payment_firebase_notification(payment_id, amount, order_id=None, staff_user_ids=None):
    """Queue Firebase notification for payment confirmation to staff"""
    title = 'Payment Received'
    body = f'Payment of ${amount} has been confirmed'
    if order_id:
        body += f' for Order #{order_id}'
    
    data = {
        'type': 'payment',
        'paymentId': payment_id,
        'amount': str(amount)
    }
    if order_id:
        data['orderId'] = order_id
    
    if staff_user_ids:
        return queue_firebase_notification('payment_confirmed', title, body, data, 'user', staff_user_ids)
    else:
        # Broadcast to all customer support and clerk staff
        return queue_firebase_notification('payment_confirmed', title, body, data, 'broadcast', roles=['CUSTOMER_SUPPORT', 'CLERK'])

def queue_user_assignment_firebase_notification(client_id, assigned_staff_id, exclude_user_id=None):
    """Queue Firebase notification for user assignment to staff"""
    title = 'User Assignment Update'
    body = f'User {client_id} has been assigned to a staff member'
    
    data = {
        'type': 'user_assignment',
        'clientId': client_id,
        'assignedStaffId': assigned_staff_id
    }
    
    # Broadcast to all customer support and clerk staff except the one who performed the action
    return queue_firebase_notification('user_assignment', title, body, data, 'broadcast', roles=['CUSTOMER_SUPPORT', 'CLERK'], excluded_users=[exclude_user_id] if exclude_user_id else None)
