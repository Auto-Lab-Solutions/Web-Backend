"""
Notification Management Module
Handles notification queuing and SQS-related business logic
"""

import os
import time
import json
import boto3
from botocore.exceptions import ClientError
from exceptions import BusinessLogicError


class NotificationManager:
    """Manages notification queuing and SQS operations"""
    
    def __init__(self):
        self.sqs = boto3.client('sqs')
        
        # Queue URLs from environment
        self.email_queue_url = os.environ.get('EMAIL_NOTIFICATION_QUEUE_URL', '')
        self.websocket_queue_url = os.environ.get('WEBSOCKET_NOTIFICATION_QUEUE_URL', '')
        self.firebase_queue_url = os.environ.get('FIREBASE_NOTIFICATION_QUEUE_URL', '')
        self.invoice_queue_url = os.environ.get('INVOICE_QUEUE_URL', '')
    
    # ===============================================================================
    # Email Notification Queue Functions
    # ===============================================================================
    
    def queue_email_notification(self, notification_type, customer_email, customer_name, data):
        """
        Queue an email notification for asynchronous processing
        
        Args:
            notification_type (str): Type of email notification
            customer_email (str): Customer email address
            customer_name (str): Customer name
            data (dict): Email data containing all necessary information
        
        Returns:
            bool: True if queued successfully, False otherwise
        """
        try:
            message = {
                'notification_type': notification_type,
                'customer_email': customer_email,
                'customer_name': customer_name,
                'data': data
            }
            
            response = self.sqs.send_message(
                QueueUrl=self.email_queue_url,
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
            
            print(f"Email notification queued successfully. MessageId: {response['MessageId']}")
            return True
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            print(f"Failed to queue email notification. Error: {error_code} - {error_message}")
            return False
        except Exception as e:
            print(f"Unexpected error queuing email notification: {str(e)}")
            return False
    
    def queue_appointment_created_email(self, customer_email, customer_name, appointment_data):
        """Queue appointment created email notification"""
        if not customer_email or not appointment_data:
            print("Warning: Missing customer email or appointment data for email notification")
            return False
        return self.queue_email_notification('appointment_created', customer_email, customer_name, appointment_data)
    
    def queue_appointment_updated_email(self, customer_email, customer_name, appointment_data, changes=None, update_type='general'):
        """Queue appointment updated email notification"""
        if not customer_email or not appointment_data:
            print("Warning: Missing customer email or appointment data for email notification")
            return False
        
        data = appointment_data.copy() if isinstance(appointment_data, dict) else {}
        if changes:
            data['changes'] = changes
        data['update_type'] = update_type
        return self.queue_email_notification('appointment_updated', customer_email, customer_name, data)
    
    def queue_appointment_cancelled_email(self, customer_email, customer_name, appointment_data, cancellation_reason=None):
        """Queue appointment cancelled email notification"""
        if not customer_email or not appointment_data:
            print("Warning: Missing customer email or appointment data for email notification")
            return False
        
        data = appointment_data.copy() if isinstance(appointment_data, dict) else {}
        if cancellation_reason:
            data['cancellation_reason'] = cancellation_reason
        return self.queue_email_notification('appointment_cancelled', customer_email, customer_name, data)
    
    def queue_appointment_reminder_email(self, customer_email, customer_name, appointment_data, reminder_type='24h'):
        """Queue appointment reminder email notification"""
        if not customer_email or not appointment_data:
            print("Warning: Missing customer email or appointment data for email notification")
            return False
        
        data = appointment_data.copy() if isinstance(appointment_data, dict) else {}
        data['reminder_type'] = reminder_type
        return self.queue_email_notification('appointment_reminder', customer_email, customer_name, data)
    
    def queue_order_created_email(self, customer_email, customer_name, order_data):
        """Queue order created email notification"""
        if not customer_email or not order_data:
            print("Warning: Missing customer email or order data for email notification")
            return False
        return self.queue_email_notification('order_created', customer_email, customer_name, order_data)
    
    def queue_order_updated_email(self, customer_email, customer_name, order_data, changes=None, update_type='general'):
        """Queue order updated email notification"""
        if not customer_email or not order_data:
            print("Warning: Missing customer email or order data for email notification")
            return False
        
        data = order_data.copy() if isinstance(order_data, dict) else {}
        if changes:
            data['changes'] = changes
        data['update_type'] = update_type
        return self.queue_email_notification('order_updated', customer_email, customer_name, data)
    
    def queue_order_status_email(self, customer_email, customer_name, order_data, new_status, status_message=None):
        """Queue order status change email notification"""
        if not customer_email or not order_data:
            print("Warning: Missing customer email or order data for email notification")
            return False
        
        data = order_data.copy() if isinstance(order_data, dict) else {}
        data['new_status'] = new_status
        if status_message:
            data['status_message'] = status_message
        return self.queue_email_notification('order_status_change', customer_email, customer_name, data)
    
    def queue_inquiry_response_email(self, customer_email, customer_name, inquiry_data, response_message):
        """Queue inquiry response email notification"""
        if not customer_email or not inquiry_data:
            print("Warning: Missing customer email or inquiry data for email notification")
            return False
        
        data = inquiry_data.copy() if isinstance(inquiry_data, dict) else {}
        data['response_message'] = response_message
        return self.queue_email_notification('inquiry_response', customer_email, customer_name, data)
    
    def queue_report_ready_email(self, customer_email, customer_name, appointment_or_order_data, report_url):
        """Queue report ready email notification"""
        if not customer_email or not appointment_or_order_data or not report_url:
            print("Warning: Missing required data for report ready email notification")
            return False
        
        data = appointment_or_order_data.copy() if isinstance(appointment_or_order_data, dict) else {}
        data['report_url'] = report_url
        return self.queue_email_notification('report_ready', customer_email, customer_name, data)
    
    def queue_payment_confirmation_email(self, customer_email, customer_name, payment_data, invoice_url=None):
        """Queue payment confirmation email notification"""
        if not customer_email or not payment_data:
            print("Warning: Missing customer email or payment data for email notification")
            return False
        
        data = payment_data.copy() if isinstance(payment_data, dict) else {}
        if invoice_url:
            data['invoice_url'] = invoice_url
        return self.queue_email_notification('payment_confirmed', customer_email, customer_name, data)
    
    def queue_welcome_email(self, customer_email, customer_name, user_data=None):
        """Queue welcome email notification for new customers"""
        if not customer_email:
            print("Warning: Missing customer email for welcome email notification")
            return False
        
        data = user_data.copy() if isinstance(user_data, dict) else {}
        return self.queue_email_notification('welcome', customer_email, customer_name, data)
    
    def queue_password_reset_email(self, customer_email, customer_name, reset_data):
        """Queue password reset email notification"""
        if not customer_email or not reset_data:
            print("Warning: Missing customer email or reset data for password reset email")
            return False
        
        return self.queue_email_notification('password_reset', customer_email, customer_name, reset_data)
    
    # ===============================================================================
    # WebSocket Notification Queue Functions
    # ===============================================================================
    
    def queue_websocket_notification(self, notification_type, notification_data, user_id=None, connection_id=None):
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
            message = {
                'notification_type': notification_type,
                'notification_data': notification_data
            }
            
            if user_id:
                message['user_id'] = user_id
            if connection_id:
                message['connection_id'] = connection_id
            
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
            
            response = self.sqs.send_message(
                QueueUrl=self.websocket_queue_url,
                MessageBody=json.dumps(message),
                MessageAttributes=message_attributes
            )
            
            print(f"WebSocket notification queued successfully. MessageId: {response['MessageId']}")
            return True
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            print(f"Failed to queue WebSocket notification. Error: {error_code} - {error_message}")
            return False
        except Exception as e:
            print(f"Unexpected error queuing WebSocket notification: {str(e)}")
            return False
    
    def queue_appointment_websocket_notification(self, appointment_id, scenario, update_data=None, user_id=None):
        """Queue appointment WebSocket notification"""
        if not appointment_id or not scenario:
            print("Warning: Missing appointment ID or scenario for WebSocket notification")
            return False
        
        notification_data = {
            "type": "appointment",
            "subtype": "update", 
            "scenario": scenario,
            "appointmentId": appointment_id,
            "changes": list(update_data.keys()) if isinstance(update_data, dict) else [],
            "timestamp": int(time.time())
        }
        
        if update_data:
            notification_data["updateData"] = update_data
        
        return self.queue_websocket_notification('appointment_update', notification_data, user_id=user_id)
    
    def queue_order_websocket_notification(self, order_id, scenario, update_data=None, user_id=None):
        """Queue order WebSocket notification"""
        if not order_id or not scenario:
            print("Warning: Missing order ID or scenario for WebSocket notification")
            return False
        
        notification_data = {
            "type": "order",
            "subtype": "update",
            "scenario": scenario,
            "orderId": order_id,
            "changes": list(update_data.keys()) if isinstance(update_data, dict) else [],
            "timestamp": int(time.time())
        }
        
        if update_data:
            notification_data["updateData"] = update_data
        
        return self.queue_websocket_notification('order_update', notification_data, user_id=user_id)
    
    def queue_staff_websocket_notification(self, notification_data, assigned_to=None, exclude_user_id=None):
        """Queue WebSocket notification for staff members"""
        if not notification_data:
            print("Warning: Missing notification data for staff WebSocket notification")
            return False
        
        staff_notification_data = notification_data.copy() if isinstance(notification_data, dict) else {}
        staff_notification_data['staff_broadcast'] = True
        staff_notification_data['timestamp'] = int(time.time())
        
        if assigned_to:
            staff_notification_data['assigned_to'] = assigned_to
        if exclude_user_id:
            staff_notification_data['exclude_user_id'] = exclude_user_id
        
        return self.queue_websocket_notification('staff_notification', staff_notification_data)
    
    def queue_inquiry_websocket_notification(self, inquiry_id, user_id=None, staff_only=False):
        """Queue inquiry WebSocket notification"""
        if not inquiry_id:
            print("Warning: Missing inquiry ID for WebSocket notification")
            return False
        
        notification_data = {
            "type": "inquiry",
            "subtype": "new",
            "inquiryId": inquiry_id,
            "timestamp": int(time.time())
        }
        
        if staff_only:
            return self.queue_staff_websocket_notification(notification_data)
        else:
            return self.queue_websocket_notification('inquiry_update', notification_data, user_id=user_id)
    
    def queue_message_websocket_notification(self, message_id, sender_id, recipient_id, message_type='general'):
        """Queue message WebSocket notification"""
        if not message_id or not sender_id:
            print("Warning: Missing message ID or sender ID for WebSocket notification")
            return False
        
        notification_data = {
            "type": "message",
            "subtype": "new",
            "messageId": message_id,
            "senderId": sender_id,
            "messageType": message_type,
            "timestamp": int(time.time())
        }
        
        return self.queue_websocket_notification('message_update', notification_data, user_id=recipient_id)
    
    def queue_payment_websocket_notification(self, payment_id, reference_id, payment_method, user_id=None):
        """Queue payment WebSocket notification"""
        if not payment_id or not reference_id:
            print("Warning: Missing payment ID or reference ID for WebSocket notification")
            return False
        
        notification_data = {
            "type": "payment",
            "subtype": "confirmed",
            "paymentId": payment_id,
            "referenceId": reference_id,
            "paymentMethod": payment_method,
            "timestamp": int(time.time())
        }
        
        return self.queue_websocket_notification('payment_update', notification_data, user_id=user_id)
    
    # ===============================================================================
    # Firebase Push Notification Queue Functions
    # ===============================================================================
    
    def queue_firebase_notification(self, notification_type, title, body, data=None, target_type='user', staff_user_ids=None, roles=None, excluded_users=None):
        """
        Queue a Firebase push notification for asynchronous processing
        
        Args:
            notification_type (str): Type of notification
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
            if not self.firebase_queue_url:
                print("Firebase notifications disabled - queue URL not configured")
                return False
            
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
            
            if excluded_users:
                message['excluded_users'] = excluded_users if isinstance(excluded_users, list) else [excluded_users]
            
            response = self.sqs.send_message(
                QueueUrl=self.firebase_queue_url,
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
    
    def queue_order_firebase_notification(self, order_id, scenario, staff_user_ids=None):
        """Queue Firebase notification for order updates to staff"""
        if not order_id or not scenario:
            print("Warning: Missing order ID or scenario for Firebase notification")
            return False
        
        titles = {
            'create': 'New Order Created',
            'basic_info': 'Order Details Updated',
            'scheduling': 'Order Scheduling Updated',
            'status': 'Order Status Changed',
            'notes': 'Order Notes Updated',
            'cancelled': 'Order Cancelled',
            'completed': 'Order Completed'
        }
        
        bodies = {
            'create': f'New order #{order_id} has been created',
            'basic_info': f'Order #{order_id} details have been updated',
            'scheduling': f'Order #{order_id} scheduling has been modified',
            'status': f'Order #{order_id} status has changed',
            'notes': f'Post-service notes added to Order #{order_id}',
            'cancelled': f'Order #{order_id} has been cancelled',
            'completed': f'Order #{order_id} has been completed'
        }
        
        title = titles.get(scenario, 'Order Updated')
        body = bodies.get(scenario, f'Order #{order_id} has been updated')
        
        data = {
            'type': 'order',
            'orderId': order_id,
            'scenario': scenario,
            'timestamp': int(time.time())
        }
        
        if staff_user_ids:
            return self.queue_firebase_notification('order_update', title, body, data, 'user', staff_user_ids)
        else:
            return self.queue_firebase_notification('order_update', title, body, data, 'broadcast', roles=['CUSTOMER_SUPPORT', 'CLERK'])
    
    def queue_appointment_firebase_notification(self, appointment_id, scenario, staff_user_ids=None):
        """Queue Firebase notification for appointment updates to staff"""
        if not appointment_id or not scenario:
            print("Warning: Missing appointment ID or scenario for Firebase notification")
            return False
        
        titles = {
            'create': 'New Appointment Booked',
            'updated': 'Appointment Updated',
            'cancelled': 'Appointment Cancelled',
            'confirmed': 'Appointment Confirmed',
            'completed': 'Appointment Completed',
            'reminder': 'Appointment Reminder'
        }
        
        bodies = {
            'create': f'New appointment #{appointment_id} has been booked',
            'updated': f'Appointment #{appointment_id} has been updated',
            'cancelled': f'Appointment #{appointment_id} has been cancelled',
            'confirmed': f'Appointment #{appointment_id} has been confirmed',
            'completed': f'Appointment #{appointment_id} has been completed',
            'reminder': f'Upcoming appointment #{appointment_id} reminder'
        }
        
        title = titles.get(scenario, 'Appointment Updated')
        body = bodies.get(scenario, f'Appointment #{appointment_id} has been updated')
        
        data = {
            'type': 'appointment',
            'appointmentId': appointment_id,
            'scenario': scenario,
            'timestamp': int(time.time())
        }
        
        if staff_user_ids:
            return self.queue_firebase_notification('appointment_update', title, body, data, 'user', staff_user_ids)
        else:
            return self.queue_firebase_notification('appointment_update', title, body, data, 'broadcast', roles=['CUSTOMER_SUPPORT', 'CLERK', 'MECHANIC'])
    
    def queue_payment_firebase_notification(self, reference_id, scenario, amount=None, staff_user_ids=None):
        """Queue Firebase notification for payment updates to staff"""
        if not reference_id or not scenario:
            print("Warning: Missing reference ID or scenario for Firebase notification")
            return False
        
        titles = {
            'cash_payment_confirmed': 'Cash Payment Confirmed',
            'bank_transfer_confirmed': 'Bank Transfer Confirmed',
            'stripe_payment_confirmed': 'Card Payment Confirmed',
            'payment_failed': 'Payment Failed',
            'refund_processed': 'Refund Processed'
        }
        
        bodies = {
            'cash_payment_confirmed': f'Cash payment confirmed for #{reference_id}',
            'bank_transfer_confirmed': f'Bank transfer confirmed for #{reference_id}',
            'stripe_payment_confirmed': f'Card payment confirmed for #{reference_id}',
            'payment_failed': f'Payment failed for #{reference_id}',
            'refund_processed': f'Refund processed for #{reference_id}'
        }
        
        title = titles.get(scenario, 'Payment Update')
        body = bodies.get(scenario, f'Payment update for #{reference_id}')
        
        if amount:
            body += f' (AUD {amount})'
        
        data = {
            'type': 'payment',
            'referenceId': reference_id,
            'scenario': scenario,
            'timestamp': int(time.time())
        }
        
        if amount:
            data['amount'] = str(amount)
        
        if staff_user_ids:
            return self.queue_firebase_notification('payment_update', title, body, data, 'user', staff_user_ids)
        else:
            return self.queue_firebase_notification('payment_update', title, body, data, 'broadcast', roles=['CUSTOMER_SUPPORT', 'CLERK'])
    
    def queue_inquiry_firebase_notification(self, inquiry_id, customer_name=None, staff_user_ids=None):
        """Queue Firebase notification for new inquiry to staff"""
        if not inquiry_id:
            print("Warning: Missing inquiry ID for Firebase notification")
            return False
        
        title = 'New Customer Inquiry'
        body = f'New inquiry #{inquiry_id} has been submitted'
        if customer_name:
            body += f' by {customer_name}'
        
        data = {
            'type': 'inquiry',
            'inquiryId': inquiry_id,
            'timestamp': int(time.time())
        }
        
        if customer_name:
            data['customerName'] = customer_name
        
        if staff_user_ids:
            return self.queue_firebase_notification('new_inquiry', title, body, data, 'user', staff_user_ids)
        else:
            return self.queue_firebase_notification('new_inquiry', title, body, data, 'broadcast', roles=['CUSTOMER_SUPPORT', 'CLERK'])
    
    def queue_message_firebase_notification(self, message_id, sender_name, recipient_type='staff', staff_user_ids=None):
        """Queue Firebase notification for new message to staff or customers"""
        if not message_id or not sender_name:
            print("Warning: Missing message ID or sender name for Firebase notification")
            return False
        
        title = 'New Message'
        body = f'New message from {sender_name}'
        
        data = {
            'type': 'message',
            'messageId': message_id,
            'senderName': sender_name,
            'recipientType': recipient_type,
            'timestamp': int(time.time())
        }
        
        if recipient_type == 'staff':
            if staff_user_ids:
                return self.queue_firebase_notification('new_message', title, body, data, 'user', staff_user_ids)
            else:
                return self.queue_firebase_notification('new_message', title, body, data, 'broadcast', roles=['CUSTOMER_SUPPORT', 'CLERK'])
        else:
            # For customer notifications, would need customer user IDs
            return self.queue_firebase_notification('new_message', title, body, data, 'user', staff_user_ids or [])
    
    def queue_user_assignment_firebase_notification(self, client_id, assigned_staff_name, exclude_user_id=None):
        """Queue Firebase notification for user assignment to staff"""
        if not client_id or not assigned_staff_name:
            print("Warning: Missing client ID or assigned staff name for Firebase notification")
            return False
        
        title = 'User Assignment Update'
        body = f'User {client_id} has been assigned to {assigned_staff_name}'
        
        data = {
            'type': 'user_assignment',
            'clientId': client_id,
            'assignedStaffName': assigned_staff_name,
            'timestamp': int(time.time())
        }
        
        excluded_users = [exclude_user_id] if exclude_user_id else None
        return self.queue_firebase_notification('user_assignment', title, body, data, 'broadcast', 
                                              roles=['CUSTOMER_SUPPORT', 'CLERK'], excluded_users=excluded_users)
    
    def queue_system_notification_firebase(self, title, body, notification_type='system', target_roles=None, urgent=False):
        """Queue system-wide Firebase notification to staff"""
        if not title or not body:
            print("Warning: Missing title or body for system Firebase notification")
            return False
        
        data = {
            'type': 'system',
            'urgent': urgent,
            'timestamp': int(time.time())
        }
        
        roles = target_roles or ['CUSTOMER_SUPPORT', 'CLERK', 'MECHANIC', 'ADMIN']
        return self.queue_firebase_notification(notification_type, title, body, data, 'broadcast', roles=roles)


class InvoiceManager:
    """Manages invoice generation queuing and SQS operations"""
    
    def __init__(self):
        self.sqs = boto3.client('sqs')
        self.invoice_queue_url = os.environ.get('INVOICE_QUEUE_URL', '')
    
    def queue_invoice_generation(self, record, record_type, payment_intent_id):
        """
        Queue invoice generation for asynchronous processing
        
        Args:
            record (dict): Order or appointment record data
            record_type (str): Type of record ('order' or 'appointment')
            payment_intent_id (str): Payment intent identifier
        
        Returns:
            bool: True if queued successfully, False otherwise
        """
        if not record or not record_type or not payment_intent_id:
            print("Warning: Missing required parameters for invoice generation")
            return False
        
        try:
            message_body = {
                'record': record,
                'record_type': record_type,
                'payment_intent_id': payment_intent_id,
                'timestamp': int(time.time()),
                'retry_count': 0
            }
            
            if self.invoice_queue_url:
                response = self.sqs.send_message(
                    QueueUrl=self.invoice_queue_url,
                    MessageBody=json.dumps(message_body),
                    MessageAttributes={
                        'RecordType': {
                            'StringValue': record_type,
                            'DataType': 'String'
                        },
                        'PaymentIntentId': {
                            'StringValue': payment_intent_id,
                            'DataType': 'String'
                        },
                        'Priority': {
                            'StringValue': 'high' if payment_intent_id.startswith('stripe_') else 'normal',
                            'DataType': 'String'
                        }
                    }
                )
                print(f"Invoice generation queued successfully with MessageId: {response.get('MessageId')}")
                return True
            else:
                print("Warning: INVOICE_QUEUE_URL not configured, falling back to synchronous processing")
                return self._generate_invoice_synchronously(record, record_type, payment_intent_id)
                
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            print(f"AWS error queuing invoice generation: {error_code} - {error_message}")
            return self._generate_invoice_synchronously(record, record_type, payment_intent_id)
        except Exception as e:
            print(f"Unexpected error queuing invoice generation: {str(e)}")
            return self._generate_invoice_synchronously(record, record_type, payment_intent_id)
    
    def _generate_invoice_synchronously(self, record, record_type, payment_intent_id):
        """
        Generate invoice synchronously for manual transactions and API calls
        
        Args:
            record (dict): Order or appointment record data
            record_type (str): Type of record ('order' or 'appointment')
            payment_intent_id (str): Payment intent identifier
        
        Returns:
            bool: True if invoice generated successfully, False otherwise
        """
        try:
            import invoice_utils as invc
            import data_retrieval_utils as db
            
            print(f"Generating invoice synchronously for {record_type} with payment_intent_id: {payment_intent_id}")
            
            # Determine invoice generation method based on payment intent and record type
            if record_type == "invoice" and payment_intent_id and (
                payment_intent_id.startswith('cash_') or 
                payment_intent_id.startswith('bank_transfer_')
            ):
                invoice_result = invc.generate_invoice_for_payment(record)
            elif payment_intent_id and (payment_intent_id.startswith('cash_') or payment_intent_id.startswith('bank_transfer_')):
                invoice_result = invc.create_invoice_for_order_or_appointment(record, record_type)
            else:
                invoice_result = invc.create_invoice_for_order_or_appointment(record, record_type, payment_intent_id)
            
            if invoice_result.get('success'):
                invoice_url = invoice_result.get('invoice_url')
                print(f"Invoice generated successfully: {invoice_url}")
                
                reference_number = record.get(f'{record_type}Id', '')
                
                if (record_type in ['appointment', 'order']) and reference_number:
                    # Update the record with invoice URL
                    invoice_update = {
                        'invoiceUrl': invoice_url, 
                        'updatedAt': int(time.time()),
                        'invoiceGeneratedAt': int(time.time())
                    }
                    
                    try:
                        if record_type == 'appointment':
                            db.update_appointment(reference_number, invoice_update)
                        else:
                            db.update_order(reference_number, invoice_update)
                        print(f"Updated {record_type} {reference_number} with invoice URL")
                    except Exception as update_error:
                        print(f"Warning: Failed to update {record_type} with invoice URL: {str(update_error)}")
                    
                    # Send payment confirmation email after successful invoice generation
                    try:
                        self._send_payment_confirmation_email_with_invoice(record, record_type, invoice_url, payment_intent_id)
                    except Exception as email_error:
                        print(f"Warning: Error sending payment confirmation email: {str(email_error)}")
                
                return True
            else:
                error_message = invoice_result.get('error', 'Unknown error')
                print(f"Failed to generate invoice: {error_message}")
                return False
                
        except ImportError as e:
            print(f"Error importing required modules for invoice generation: {str(e)}")
            return False
        except Exception as e:
            print(f"Error in synchronous invoice generation: {str(e)}")
            return False
    
    def process_invoice_generation(self, record, record_type, payment_intent_id):
        """
        Process invoice generation for an order or appointment record
        
        Args:
            record: The order or appointment record
            record_type: 'order' or 'appointment'
            payment_intent_id: Payment intent ID
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            import invoice_utils as invc
            import email_utils as email
            import time
            
            # Generate the invoice
            invoice_result = invc.create_invoice_for_order_or_appointment(
                record, 
                record_type, 
                payment_intent_id
            )
            
            if invoice_result.get('success'):
                invoice_url = invoice_result.get('invoice_url')
                reference_number = record.get(f'{record_type}Id')
                
                # Update the record with invoice URL
                invoice_update = {
                    'invoiceUrl': invoice_url, 
                    'updatedAt': int(time.time())
                }
                
                if record_type == 'appointment':
                    update_success = self.db.update_appointment(reference_number, invoice_update)
                else:
                    update_success = self.db.update_order(reference_number, invoice_update)
                
                if update_success:
                    print(f"Invoice generated and record updated successfully: {invoice_url}")
                    
                    # Send payment confirmation email after successful invoice generation
                    try:
                        self._send_payment_confirmation_email_with_invoice(
                            record, 
                            record_type, 
                            invoice_url,
                            payment_intent_id
                        )
                    except Exception as email_error:
                        print(f"Error sending payment confirmation email: {str(email_error)}")
                        # Don't fail the invoice processing if email fails
                    
                    return True
                else:
                    print(f"Invoice generated but failed to update record: {reference_number}")
                    return False
            else:
                print(f"Failed to generate invoice: {invoice_result.get('error')}")
                return False
                
        except Exception as e:
            print(f"Error in process_invoice_generation: {str(e)}")
            return False
    
    def _send_payment_confirmation_email_with_invoice(self, record, record_type, invoice_url, payment_intent_id):
        """Send payment confirmation email with invoice after successful generation"""
        try:
            import email_utils as email
            import time
            
            # Get customer information from record
            if record_type == 'order':
                # For orders, get customer data directly from the record
                customer_email = record.get('customerEmail')
                customer_name = record.get('customerName', 'Valued Customer')
            else:  # appointment
                # For appointments, check if it's a buyer or seller
                is_buyer = record.get('isBuyer', True)
                if is_buyer:
                    customer_email = record.get('buyerEmail')
                    customer_name = record.get('buyerName', 'Valued Customer')
                else:
                    customer_email = record.get('sellerEmail')
                    customer_name = record.get('sellerName', 'Valued Customer')
            
            # Validate customer email
            if not customer_email:
                print(f"No customer email found in {record_type} record")
                return
            
            # Determine payment method from payment_intent_id
            payment_method = 'Card'  # Default for Stripe payments
            if payment_intent_id and payment_intent_id.startswith('cash_'):
                payment_method = 'Cash'
            elif payment_intent_id and payment_intent_id.startswith('bank_transfer_'):
                payment_method = 'Bank Transfer'
            
            # Prepare payment data for email
            payment_data = {
                'amount': f"{record.get('price', 0):.2f}",
                'paymentMethod': payment_method,
                'referenceNumber': record.get(f'{record_type}Id', 'N/A'),
                'paymentDate': record.get('updatedAt', int(time.time())),
                'invoice_url': invoice_url
            }
            
            # Send payment confirmation email with invoice
            email.send_payment_confirmation_email(customer_email, customer_name, payment_data, invoice_url)
            print(f"Payment confirmation email sent to {customer_email} with invoice: {invoice_url}")
            
        except Exception as e:
            print(f"Error sending payment confirmation email: {str(e)}")
            raise e

    # ===============================================================================
    # Retry Queue Functions
    # ===============================================================================
    
    def queue_invoice_retry(self, original_message_body, retry_count=0, max_retries=3):
        """
        Queue a retry for failed invoice generation
        
        Args:
            original_message_body (dict): Original message body from failed attempt
            retry_count (int): Current retry count
            max_retries (int): Maximum number of retries allowed
        
        Returns:
            bool: True if retry queued successfully, False otherwise
        """
        if retry_count >= max_retries:
            print(f"Maximum retries ({max_retries}) exceeded for invoice generation")
            return False
        
        try:
            retry_message = original_message_body.copy()
            retry_message['retry_count'] = retry_count + 1
            retry_message['retry_timestamp'] = int(time.time())
            
            if self.invoice_queue_url:
                # Add delay for retries (exponential backoff)
                delay_seconds = min(300, 30 * (2 ** retry_count))  # Max 5 minutes
                
                response = self.sqs.send_message(
                    QueueUrl=self.invoice_queue_url,
                    MessageBody=json.dumps(retry_message),
                    DelaySeconds=delay_seconds,
                    MessageAttributes={
                        'RecordType': {
                            'StringValue': retry_message.get('record_type', 'unknown'),
                            'DataType': 'String'
                        },
                        'PaymentIntentId': {
                            'StringValue': retry_message.get('payment_intent_id', 'unknown'),
                            'DataType': 'String'
                        },
                        'RetryCount': {
                            'StringValue': str(retry_count + 1),
                            'DataType': 'Number'
                        }
                    }
                )
                print(f"Invoice generation retry queued with MessageId: {response.get('MessageId')}, retry count: {retry_count + 1}")
                return True
            else:
                print("Warning: INVOICE_QUEUE_URL not configured, cannot queue retry")
                return False
                
        except Exception as e:
            print(f"Error queuing invoice retry: {str(e)}")
            return False


# Create singleton instances for backward compatibility
notification_manager = NotificationManager()
invoice_manager = InvoiceManager()

# Export individual email notification functions for backward compatibility
queue_email_notification = notification_manager.queue_email_notification
queue_appointment_created_email = notification_manager.queue_appointment_created_email
queue_appointment_updated_email = notification_manager.queue_appointment_updated_email
queue_appointment_cancelled_email = notification_manager.queue_appointment_cancelled_email
queue_appointment_reminder_email = notification_manager.queue_appointment_reminder_email
queue_order_created_email = notification_manager.queue_order_created_email
queue_order_updated_email = notification_manager.queue_order_updated_email
queue_order_status_email = notification_manager.queue_order_status_email
queue_inquiry_response_email = notification_manager.queue_inquiry_response_email
queue_report_ready_email = notification_manager.queue_report_ready_email
queue_payment_confirmation_email = notification_manager.queue_payment_confirmation_email
queue_welcome_email = notification_manager.queue_welcome_email
queue_password_reset_email = notification_manager.queue_password_reset_email

# Export individual WebSocket notification functions for backward compatibility
queue_websocket_notification = notification_manager.queue_websocket_notification
queue_appointment_websocket_notification = notification_manager.queue_appointment_websocket_notification
queue_order_websocket_notification = notification_manager.queue_order_websocket_notification
queue_staff_websocket_notification = notification_manager.queue_staff_websocket_notification
queue_inquiry_websocket_notification = notification_manager.queue_inquiry_websocket_notification
queue_message_websocket_notification = notification_manager.queue_message_websocket_notification
queue_payment_websocket_notification = notification_manager.queue_payment_websocket_notification

# Export individual Firebase notification functions for backward compatibility
queue_firebase_notification = notification_manager.queue_firebase_notification
queue_order_firebase_notification = notification_manager.queue_order_firebase_notification
queue_appointment_firebase_notification = notification_manager.queue_appointment_firebase_notification
queue_payment_firebase_notification = notification_manager.queue_payment_firebase_notification
queue_inquiry_firebase_notification = notification_manager.queue_inquiry_firebase_notification
queue_message_firebase_notification = notification_manager.queue_message_firebase_notification
queue_user_assignment_firebase_notification = notification_manager.queue_user_assignment_firebase_notification
queue_system_notification_firebase = notification_manager.queue_system_notification_firebase

# Export individual invoice functions for backward compatibility
queue_invoice_generation = invoice_manager.queue_invoice_generation
