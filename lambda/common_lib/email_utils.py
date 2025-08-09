import boto3
import os
import json
from datetime import datetime
from botocore.exceptions import ClientError

# Initialize SES client
ses_client = boto3.client('ses')

# Environment variables
FROM_EMAIL = os.environ.get('FROM_EMAIL', 'noreply@autolabsolutions.com')
FRONTEND_URL = os.environ.get('FRONTEND_ROOT_URL', 'https://autolabsolutions.com')
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'production')

class EmailTemplate:
    """Email template constants and configurations"""
    
    # Email subjects
    APPOINTMENT_CREATED = "Your Appointment Request Has Been Received"
    APPOINTMENT_UPDATED = "Your Appointment Has Been Updated"
    APPOINTMENT_SCHEDULED = "Your Appointment Has Been Scheduled"
    APPOINTMENT_REPORT_READY = "Your Vehicle Report is Ready"
    
    ORDER_CREATED = "Your Service Order Has Been Created"
    ORDER_UPDATED = "Your Service Order Has Been Updated"
    ORDER_SCHEDULED = "Your Service Order Has Been Scheduled"
    ORDER_REPORT_READY = "Your Service Report is Ready"
    
    PAYMENT_CONFIRMED = "Payment Confirmation - Invoice Generated"
    
    # Email types for analytics
    TYPE_APPOINTMENT_CREATED = "appointment_created"
    TYPE_APPOINTMENT_UPDATED = "appointment_updated"
    TYPE_APPOINTMENT_SCHEDULED = "appointment_scheduled"
    TYPE_APPOINTMENT_REPORT = "appointment_report"
    TYPE_ORDER_CREATED = "order_created"
    TYPE_ORDER_UPDATED = "order_updated"
    TYPE_ORDER_SCHEDULED = "order_scheduled"
    TYPE_ORDER_REPORT = "order_report"
    TYPE_PAYMENT_CONFIRMED = "payment_confirmed"

def send_email(to_email, subject, html_body, text_body=None, email_type=None):
    """
    Send email using AWS SES
    
    Args:
        to_email (str): Recipient email address
        subject (str): Email subject
        html_body (str): HTML email body
        text_body (str): Plain text email body (optional)
        email_type (str): Type of email for analytics (optional)
    
    Returns:
        bool: True if email sent successfully, False otherwise
    """
    try:
        # If no text body provided, strip HTML tags for basic text version
        if not text_body:
            import re
            text_body = re.sub('<[^<]+?>', '', html_body)
        
        # Prepare email message
        message = {
            'Subject': {'Data': subject, 'Charset': 'UTF-8'},
            'Body': {
                'Html': {'Data': html_body, 'Charset': 'UTF-8'},
                'Text': {'Data': text_body, 'Charset': 'UTF-8'}
            }
        }
        
        # Send email
        response = ses_client.send_email(
            Source=FROM_EMAIL,
            Destination={'ToAddresses': [to_email]},
            Message=message
        )
        
        message_id = response['MessageId']
        print(f"Email sent successfully to {to_email}. MessageId: {message_id}")
        
        # Log email activity (optional, for analytics)
        if email_type:
            log_email_activity(to_email, email_type, message_id, 'sent')
        
        return True
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_message = e.response['Error']['Message']
        print(f"Failed to send email to {to_email}. Error: {error_code} - {error_message}")
        
        # Log email failure
        if email_type:
            log_email_activity(to_email, email_type, None, 'failed', error_message)
        
        return False
    except Exception as e:
        print(f"Unexpected error sending email to {to_email}: {str(e)}")
        
        # Log email failure
        if email_type:
            log_email_activity(to_email, email_type, None, 'failed', str(e))
        
        return False

def log_email_activity(email, email_type, message_id, status, error_message=None):
    """Log email activity for analytics and debugging"""
    try:
        log_data = {
            'timestamp': int(datetime.now().timestamp()),
            'email': email,
            'type': email_type,
            'message_id': message_id,
            'status': status,
            'environment': ENVIRONMENT
        }
        
        if error_message:
            log_data['error'] = error_message
        
        print(f"Email Activity Log: {json.dumps(log_data)}")
    except Exception as e:
        print(f"Failed to log email activity: {str(e)}")

# Email template functions for specific scenarios

def send_appointment_created_email(customer_email, customer_name, appointment_data):
    """Send email when appointment is created"""
    subject = EmailTemplate.APPOINTMENT_CREATED
    
    # Format appointment details
    services = format_services(appointment_data.get('services', []))
    formatted_timeslots = format_timeslots(appointment_data.get('selectedSlots', []))
    vehicle_info = format_vehicle_info(appointment_data.get('vehicleInfo', {}))
    
    html_body = f"""
    <html>
    <head></head>
    <body>
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #2c3e50;">Appointment Request Received</h2>
            
            <p>Dear {customer_name},</p>
            
            <p>Thank you for requesting an appointment with Auto Lab Solutions. We have received your request and will process it shortly.</p>
            
            <div style="background-color: #f8f9fa; padding: 20px; border-radius: 5px; margin: 20px 0;">
                <h3 style="color: #2c3e50; margin-top: 0;">Appointment Details:</h3>
                <p><strong>Reference ID:</strong> {appointment_data.get('appointmentId', 'N/A')}</p>
                <p><strong>Services Requested:</strong> {services}</p>
                <p><strong>Selected Slots:</strong> {formatted_timeslots}</p>
                <p><strong>Vehicle Info:</strong> {vehicle_info}</p>
                <p><strong>Contact Number:</strong> {appointment_data.get('customerData', {}).get('phoneNumber', 'N/A')}</p>
            </div>
            
            <p>Our team will review your request and contact you within an hour to confirm the appointment details and schedule.</p>
            
            <p>You can track your appointment status by visiting: <a href="{FRONTEND_URL}/appointment/{appointment_data.get('appointmentId')}">View Appointment</a></p>
            
            <p>If you have any questions, please don't hesitate to contact us.</p>
            
            <p>Best regards,<br>Auto Lab Solutions Team</p>
        </div>
    </body>
    </html>
    """
    
    return send_email(
        customer_email, 
        subject, 
        html_body, 
        email_type=EmailTemplate.TYPE_APPOINTMENT_CREATED
    )

def send_order_created_email(customer_email, customer_name, order_data):
    """Send email when service order is created"""
    subject = EmailTemplate.ORDER_CREATED
    
    # Format order details
    services = format_services(order_data.get('services', []))
    items = format_order_items(order_data.get('items', []))
    vehicle_info = format_vehicle_info(order_data.get('vehicleInfo', {}))
    
    html_body = f"""
    <html>
    <head></head>
    <body>
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #2c3e50;">Service Order Created</h2>
            
            <p>Dear {customer_name},</p>
            
            <p>Thank you for placing your service order with Auto Lab Solutions. We have received your order and will begin processing it shortly.</p>
            
            <div style="background-color: #f8f9fa; padding: 20px; border-radius: 5px; margin: 20px 0;">
                <h3 style="color: #2c3e50; margin-top: 0;">Order Details:</h3>
                <p><strong>Order ID:</strong> {order_data.get('orderId', 'N/A')}</p>
                <p><strong>Services:</strong> {services}</p>
                {f"<p><strong>Items:</strong> {items}</p>" if items else ""}
                <p><strong>Vehicle:</strong> {vehicle_info}</p>
                <p><strong>Total Amount:</strong> ${order_data.get('totalAmount', '0.00')}</p>
                <p><strong>Status:</strong> {order_data.get('status', 'Processing')}</p>
                <p><strong>Contact Number:</strong> {order_data.get('customerData', {}).get('phoneNumber', 'N/A')}</p>
            </div>
            
            <p>Our team will review your order and contact you to confirm the service details and schedule.</p>
            
            <p>You can track your order status by visiting: <a href="{FRONTEND_URL}/orders/{order_data.get('orderId')}">View Order</a></p>
            
            <p>If you have any questions, please don't hesitate to contact us.</p>
            
            <p>Thank you for choosing Auto Lab Solutions!</p>
            
            <p>Best regards,<br>Auto Lab Solutions Team</p>
        </div>
    </body>
    </html>
    """
    
    return send_email(
        customer_email, 
        subject, 
        html_body, 
        email_type=EmailTemplate.TYPE_ORDER_CREATED
    )

def send_appointment_updated_email(customer_email, customer_name, appointment_data, changes=None):
    """Send email when appointment is updated"""
    subject = EmailTemplate.APPOINTMENT_UPDATED
    
    # Format appointment details
    services = format_services(appointment_data.get('services', []))
    vehicle_info = format_vehicle_info(appointment_data.get('vehicleInfo', {}))
    
    # Format changes - if changes not provided, create generic update message
    changes_html = ""
    if changes:
        for field, change in changes.items():
            old_value = change.get('old', 'N/A')
            new_value = change.get('new', 'N/A')
            changes_html += f"<p><strong>{format_field_name(field)}:</strong> {old_value} → {new_value}</p>"
    else:
        changes_html = "<p>Your appointment details have been updated. Please review the current information below.</p>"
    
    html_body = f"""
    <html>
    <head></head>
    <body>
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #2c3e50;">Appointment Updated</h2>
            
            <p>Dear {customer_name},</p>
            
            <p>Your appointment has been updated. Please review the changes below and contact us if you have any questions.</p>
            
            <div style="background-color: #f8f9fa; padding: 20px; border-radius: 5px; margin: 20px 0;">
                <h3 style="color: #2c3e50; margin-top: 0;">Appointment Details:</h3>
                <p><strong>Appointment ID:</strong> {appointment_data.get('appointmentId', 'N/A')}</p>
                <p><strong>Services:</strong> {services}</p>
                <p><strong>Vehicle:</strong> {vehicle_info}</p>
                <p><strong>Current Status:</strong> {appointment_data.get('status', 'N/A')}</p>
            </div>
            
            <div style="background-color: #fff3cd; padding: 20px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #ffc107;">
                <h3 style="color: #856404; margin-top: 0;">Changes Made:</h3>
                {changes_html}
            </div>
            
            <p>You can view your updated appointment by visiting: <a href="{FRONTEND_URL}/appointment/{appointment_data.get('appointmentId')}">View Appointment</a></p>
            
            <p>If you have any questions about these changes, please contact us immediately.</p>
            
            <p>Best regards,<br>Auto Lab Solutions Team</p>
        </div>
    </body>
    </html>
    """
    
    return send_email(
        customer_email, 
        subject, 
        html_body, 
        email_type=EmailTemplate.TYPE_APPOINTMENT_UPDATED
    )

def send_order_updated_email(customer_email, customer_name, order_data, changes=None):
    """Send email when order is updated"""
    subject = EmailTemplate.ORDER_UPDATED
    
    # Format order details
    services = format_services(order_data.get('services', []))
    items = format_order_items(order_data.get('items', []))
    vehicle_info = format_vehicle_info(order_data.get('vehicleInfo', {}))
    
    # Format changes - if changes not provided, create generic update message
    changes_html = ""
    if changes:
        for field, change in changes.items():
            old_value = change.get('old', 'N/A')
            new_value = change.get('new', 'N/A')
            changes_html += f"<p><strong>{format_field_name(field)}:</strong> {old_value} → {new_value}</p>"
    else:
        changes_html = "<p>Your order details have been updated. Please review the current information below.</p>"
    
    html_body = f"""
    <html>
    <head></head>
    <body>
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #2c3e50;">Service Order Updated</h2>
            
            <p>Dear {customer_name},</p>
            
            <p>Your service order has been updated. Please review the changes below.</p>
            
            <div style="background-color: #f8f9fa; padding: 20px; border-radius: 5px; margin: 20px 0;">
                <h3 style="color: #2c3e50; margin-top: 0;">Order Details:</h3>
                <p><strong>Order ID:</strong> {order_data.get('orderId', 'N/A')}</p>
                <p><strong>Services:</strong> {services}</p>
                {f"<p><strong>Items:</strong> {items}</p>" if items else ""}
                <p><strong>Vehicle:</strong> {vehicle_info}</p>
                <p><strong>Current Status:</strong> {order_data.get('status', 'N/A')}</p>
                <p><strong>Total Amount:</strong> ${order_data.get('totalAmount', '0.00')}</p>
            </div>
            
            <div style="background-color: #fff3cd; padding: 20px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #ffc107;">
                <h3 style="color: #856404; margin-top: 0;">Changes Made:</h3>
                {changes_html}
            </div>
            
            <p>You can view your updated order by visiting: <a href="{FRONTEND_URL}/orders/{order_data.get('orderId')}">View Order</a></p>
            
            <p>Thank you for choosing Auto Lab Solutions!</p>
            
            <p>Best regards,<br>Auto Lab Solutions Team</p>
        </div>
    </body>
    </html>
    """
    
    return send_email(
        customer_email, 
        subject, 
        html_body, 
        email_type=EmailTemplate.TYPE_ORDER_UPDATED
    )

def send_appointment_scheduled_email(customer_email, customer_name, appointment_data):
    """Send email when appointment is scheduled with mechanic and date/time"""
    subject = EmailTemplate.APPOINTMENT_SCHEDULED
    
    # Format appointment details
    services = format_services(appointment_data.get('services', []))
    vehicle_info = format_vehicle_info(appointment_data.get('vehicleInfo', {}))
    scheduled_date = format_timestamp(appointment_data.get('scheduledDate'))
    time_slot = appointment_data.get('timeSlot', 'TBD')
    mechanic_name = appointment_data.get('assignedMechanic', 'Our team')
    location = appointment_data.get('location', 'Auto Lab Solutions Service Center')
    
    html_body = f"""
    <html>
    <head></head>
    <body>
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #2c3e50;">Appointment Scheduled</h2>
            
            <p>Dear {customer_name},</p>
            
            <p>Great news! Your appointment has been scheduled with one of our experienced mechanics.</p>
            
            <div style="background-color: #f8f9fa; padding: 20px; border-radius: 5px; margin: 20px 0;">
                <h3 style="color: #2c3e50; margin-top: 0;">Appointment Details:</h3>
                <p><strong>Appointment ID:</strong> {appointment_data.get('appointmentId', 'N/A')}</p>
                <p><strong>Services:</strong> {services}</p>
                <p><strong>Vehicle:</strong> {vehicle_info}</p>
            </div>
            
            <div style="background-color: #e8f5e8; padding: 20px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #27ae60;">
                <h3 style="color: #27ae60; margin-top: 0;">Scheduled Details:</h3>
                <p><strong>Date:</strong> {scheduled_date}</p>
                <p><strong>Time Slot:</strong> {time_slot}</p>
                <p><strong>Assigned Mechanic:</strong> {mechanic_name}</p>
                <p><strong>Location:</strong> {location}</p>
            </div>
            
            <div style="background-color: #fff3cd; padding: 15px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #ffc107;">
                <h4 style="color: #856404; margin-top: 0;">Important Reminders:</h4>
                <ul style="color: #856404;">
                    <li>Please arrive 15 minutes before your scheduled time</li>
                    <li>Bring your vehicle registration and any relevant documents</li>
                    <li>If you need to reschedule, please contact us at least 24 hours in advance</li>
                </ul>
            </div>
            
            <p>You can view your appointment details by visiting: <a href="{FRONTEND_URL}/appointment/{appointment_data.get('appointmentId')}">View Appointment</a></p>
            
            <p>We look forward to serving you!</p>
            
            <p>Best regards,<br>Auto Lab Solutions Team</p>
        </div>
    </body>
    </html>
    """
    
    return send_email(
        customer_email, 
        subject, 
        html_body, 
        email_type=EmailTemplate.TYPE_APPOINTMENT_SCHEDULED
    )

def send_order_scheduled_email(customer_email, customer_name, order_data):
    """Send email when order is scheduled with mechanic and date/time"""
    subject = EmailTemplate.ORDER_SCHEDULED
    
    # Format order details
    services = format_services(order_data.get('services', []))
    items = format_order_items(order_data.get('items', []))
    vehicle_info = format_vehicle_info(order_data.get('vehicleInfo', {}))
    scheduled_date = format_timestamp(order_data.get('scheduledDate'))
    time_slot = order_data.get('timeSlot', 'TBD')
    mechanic_name = order_data.get('assignedMechanic', 'Our team')
    
    html_body = f"""
    <html>
    <head></head>
    <body>
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #2c3e50;">Service Order Scheduled</h2>
            
            <p>Dear {customer_name},</p>
            
            <p>Your service order has been scheduled for completion.</p>
            
            <div style="background-color: #f8f9fa; padding: 20px; border-radius: 5px; margin: 20px 0;">
                <h3 style="color: #2c3e50; margin-top: 0;">Order Details:</h3>
                <p><strong>Order ID:</strong> {order_data.get('orderId', 'N/A')}</p>
                <p><strong>Services:</strong> {services}</p>
                {f"<p><strong>Items:</strong> {items}</p>" if items else ""}
                <p><strong>Vehicle:</strong> {vehicle_info}</p>
                <p><strong>Total Amount:</strong> ${order_data.get('totalAmount', '0.00')}</p>
            </div>
            
            <div style="background-color: #e8f5e8; padding: 20px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #27ae60;">
                <h3 style="color: #27ae60; margin-top: 0;">Scheduled Details:</h3>
                <p><strong>Date:</strong> {scheduled_date}</p>
                <p><strong>Time Slot:</strong> {time_slot}</p>
                <p><strong>Assigned Mechanic:</strong> {mechanic_name}</p>
                <p><strong>Estimated Duration:</strong> {order_data.get('estimatedDuration', 'TBD')}</p>
            </div>
            
            <p>You can track your order progress by visiting: <a href="{FRONTEND_URL}/orders/{order_data.get('orderId')}">View Order</a></p>
            
            <p>Thank you for choosing Auto Lab Solutions!</p>
            
            <p>Best regards,<br>Auto Lab Solutions Team</p>
        </div>
    </body>
    </html>
    """
    
    return send_email(
        customer_email, 
        subject, 
        html_body, 
        email_type=EmailTemplate.TYPE_ORDER_SCHEDULED
    )

def send_report_ready_email(customer_email, customer_name, appointment_or_order_data, report_url):
    """Send email when vehicle/service report is ready"""
    is_appointment = 'appointmentId' in appointment_or_order_data
    
    if is_appointment:
        subject = EmailTemplate.APPOINTMENT_REPORT_READY
        item_type = "appointment"
        item_id = appointment_or_order_data.get('appointmentId')
        email_type = EmailTemplate.TYPE_APPOINTMENT_REPORT
    else:
        subject = EmailTemplate.ORDER_REPORT_READY
        item_type = "service order"
        item_id = appointment_or_order_data.get('orderId')
        email_type = EmailTemplate.TYPE_ORDER_REPORT
    
    # Format details
    services = format_services(appointment_or_order_data.get('services', []))
    vehicle_info = format_vehicle_info(appointment_or_order_data.get('vehicleInfo', {}))
    
    html_body = f"""
    <html>
    <head></head>
    <body>
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #2c3e50;">Your Report is Ready</h2>
            
            <p>Dear {customer_name},</p>
            
            <p>Great news! The report for your {item_type} is now ready for review.</p>
            
            <div style="background-color: #f8f9fa; padding: 20px; border-radius: 5px; margin: 20px 0;">
                <h3 style="color: #2c3e50; margin-top: 0;">{item_type.title()} Details:</h3>
                <p><strong>{item_type.title()} ID:</strong> {item_id}</p>
                <p><strong>Services:</strong> {services}</p>
                <p><strong>Vehicle:</strong> {vehicle_info}</p>
                <p><strong>Status:</strong> {appointment_or_order_data.get('status', 'Completed')}</p>
            </div>
            
            <div style="background-color: #e8f5e8; padding: 20px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #27ae60;">
                <h3 style="color: #27ae60; margin-top: 0;">Report Details:</h3>
                <p><strong>Report Generated:</strong> {format_timestamp(int(datetime.now().timestamp()))}</p>
                <p><strong>Report Type:</strong> {appointment_or_order_data.get('reportType', 'Service Report')}</p>
            </div>
            
            <div style="text-align: center; margin: 30px 0;">
                <a href="{report_url}" style="background-color: #3498db; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">Download Report</a>
            </div>
            
            <p>You can also view your {item_type} and report by visiting: <a href="{FRONTEND_URL}/{item_type}s/{item_id}">View {item_type.title()}</a></p>
            
            <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <p><strong>Note:</strong> This report contains important information about your vehicle's condition and the services performed. Please keep it for your records.</p>
            </div>
            
            <p>If you have any questions about the report, please don't hesitate to contact us.</p>
            
            <p>Thank you for choosing Auto Lab Solutions!</p>
            
            <p>Best regards,<br>Auto Lab Solutions Team</p>
        </div>
    </body>
    </html>
    """
    
    return send_email(
        customer_email, 
        subject, 
        html_body, 
        email_type=email_type
    )

def send_payment_confirmation_email(customer_email, customer_name, payment_data, invoice_url):
    """Send email when payment is confirmed and invoice is generated"""
    subject = EmailTemplate.PAYMENT_CONFIRMED
    
    payment_method = payment_data.get('paymentMethod', 'Card')
    amount = payment_data.get('amount', '0.00')
    reference_number = payment_data.get('referenceNumber', 'N/A')
    payment_date = format_timestamp(payment_data.get('paymentDate', int(datetime.now().timestamp())))
    
    html_body = f"""
    <html>
    <head></head>
    <body>
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2 style="color: #27ae60;">Payment Confirmation</h2>
            
            <p>Dear {customer_name},</p>
            
            <p>Thank you for your payment! We have successfully received and processed your payment.</p>
            
            <div style="background-color: #e8f5e8; padding: 20px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #27ae60;">
                <h3 style="color: #27ae60; margin-top: 0;">Payment Details:</h3>
                <p><strong>Amount Paid:</strong> ${amount}</p>
                <p><strong>Payment Method:</strong> {payment_method}</p>
                <p><strong>Payment Date:</strong> {payment_date}</p>
                <p><strong>Reference Number:</strong> {reference_number}</p>
                <p><strong>Transaction Status:</strong> Completed</p>
            </div>
            
            <div style="text-align: center; margin: 30px 0;">
                <a href="{invoice_url}" style="background-color: #3498db; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; display: inline-block;">Download Invoice</a>
            </div>
            
            <div style="background-color: #f8f9fa; padding: 15px; border-radius: 5px; margin: 20px 0;">
                <p><strong>Important:</strong> Please save this invoice for your records. You may need it for warranty claims or tax purposes.</p>
            </div>
            
            <p>If you have any questions about this payment or need additional documentation, please contact our billing department.</p>
            
            <p>Thank you for choosing Auto Lab Solutions!</p>
            
            <p>Best regards,<br>Auto Lab Solutions Team</p>
        </div>
    </body>
    </html>
    """
    
    return send_email(
        customer_email, 
        subject, 
        html_body, 
        email_type=EmailTemplate.TYPE_PAYMENT_CONFIRMED
    )

def format_vehicle_info(vehicle_info):
    """Format vehicle information into a readable string"""
    if not vehicle_info:
        return "N/A"
    
    make = vehicle_info.get('make', 'N/A')
    model = vehicle_info.get('model', 'N/A')
    year = vehicle_info.get('year', 'N/A')
    
    return f"{make} {model} ({year})"

def format_timestamp(timestamp):
    """Format timestamp to readable date string"""
    if not timestamp:
        return "N/A"
    
    try:
        if isinstance(timestamp, str):
            timestamp = int(timestamp)
        
        dt = datetime.fromtimestamp(timestamp)
        return dt.strftime("%B %d, %Y at %I:%M %p")
    except (ValueError, TypeError):
        return "N/A"
    
def format_timeslots(timeslots):
    """Format list of timeslots into a readable string"""
    if not timeslots:
        return "N/A"
    
    formatted = []
    for slot in timeslots:
        if isinstance(slot, dict):
            date = slot.get('date', 'N/A')
            start = slot.get('start', 'N/A')
            end = slot.get('end', 'N/A')
            priority = slot.get('priority', 'N/A')
            formatted.append(f"{date} {start} - {end} (Priority: {priority})")
        else:
            formatted.append(str(slot))
    
    return ', '.join(formatted) if formatted else "N/A"

def format_services(services):
    """Format list of services into a readable string"""
    if not services:
        return "N/A"
    
    formatted = []
    for service in services:
        if isinstance(service, dict):
            service_name = service.get('serviceName', 'N/A')
            plan_name = service.get('planName', 'N/A')
            formatted.append(f"{service_name} - ({plan_name})")
        else:
            formatted.append(str(service))
    
    return ', '.join(formatted) if formatted else "N/A"

def format_order_items(items):
    """Format list of order items into a readable string"""
    if not items:
        return ""
    
    formatted = []
    for item in items:
        if isinstance(item, dict):
            name = item.get('name', 'Item')
            quantity = item.get('quantity', 1)
            price = item.get('price', '0.00')
            formatted.append(f"{name} (Qty: {quantity}) - ${price}")
        else:
            formatted.append(str(item))
    
    return ', '.join(formatted) if formatted else ""

def format_field_name(field_name):
    """Format field name for display (convert snake_case to Title Case)"""
    return field_name.replace('_', ' ').title()

def verify_email_address(email_address):
    """Verify an email address with SES (for production use)"""
    try:
        response = ses_client.verify_email_identity(EmailAddress=email_address)
        print(f"Verification email sent to {email_address}")
        return True
    except ClientError as e:
        print(f"Failed to verify email {email_address}: {e}")
        return False

def get_send_quota():
    """Get current SES sending quota and rate"""
    try:
        response = ses_client.get_send_quota()
        return {
            'sent_last_24h': response.get('SentLast24Hours', 0),
            'max_24h': response.get('Max24HourSend', 0),
            'max_send_rate': response.get('MaxSendRate', 0)
        }
    except ClientError as e:
        print(f"Failed to get send quota: {e}")
        return None
