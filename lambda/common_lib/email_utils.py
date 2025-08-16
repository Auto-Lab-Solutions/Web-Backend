import boto3
import os
import json
from datetime import datetime
from botocore.exceptions import ClientError
import db_utils as db
import response_utils as resp

# Initialize SES client
ses_client = boto3.client('ses')

# Environment variables
NO_REPLY_EMAIL = os.environ.get('MAIL_FROM_ADDRESS')
MAIL_FROM_ADDRESS = os.environ.get('NO_REPLY_EMAIL')
FRONTEND_URL = os.environ.get('FRONTEND_ROOT_URL')
ENVIRONMENT = os.environ.get('ENVIRONMENT')

# Suppression table name (will be passed via environment variable)
SUPPRESSION_TABLE_NAME = os.environ.get('EMAIL_SUPPRESSION_TABLE_NAME')

# Initialize DynamoDB client for suppression checking
dynamodb = boto3.resource('dynamodb')

class EmailTemplate:
    """Email template constants and configurations"""
    
    # Email subjects
    APPOINTMENT_CREATED = "Your Appointment Request Has Been Received"
    APPOINTMENT_UPDATED = "Your Appointment Has Been Updated"
    ORDER_CREATED = "Your Service Order Has Been Created"
    ORDER_UPDATED = "Your Service Order Has Been Updated"
    
    APPOINTMENT_REPORT_READY = "Your Vehicle Report is Ready"
    PAYMENT_CONFIRMED = "Payment Confirmation - Invoice Generated"
    
    # Email types for analytics
    TYPE_APPOINTMENT_CREATED = "appointment_created"
    TYPE_APPOINTMENT_UPDATED = "appointment_updated"
    TYPE_ORDER_CREATED = "order_created"
    TYPE_ORDER_UPDATED = "order_updated"

    TYPE_APPOINTMENT_REPORT = "appointment_report"
    TYPE_PAYMENT_CONFIRMED = "payment_confirmed"

    TYPE_INBOX_EMAIL = "inbox_email"

def send_email(to_email, subject, html_body, text_body=None, email_type=None):
    """
    Send email using AWS SES with bounce/complaint suppression checking
    
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
        # Check if email is suppressed before attempting to send
        if is_email_suppressed(to_email):
            print(f"Email not sent - recipient {to_email} is suppressed")
            if email_type:
                log_email_activity(to_email, email_type, None, 'suppressed', 'Email address is suppressed')
            return False
        
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
            Source=NO_REPLY_EMAIL,
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
    """Send email when an appointment is created"""
    subject = EmailTemplate.APPOINTMENT_CREATED
    
    # Format appointment details
    services = format_services(appointment_data.get('services', []))
    formatted_timeslots = format_timeslots(appointment_data.get('selectedSlots', []))
    vehicle_info = format_vehicle_info(appointment_data.get('vehicleInfo', {}))
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Appointment Request Received</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; }}
            .container {{ max-width: 600px; margin: 0 auto; background-color: #18181B; color: #F3F4F6; }}
            .header {{ background: linear-gradient(135deg, #27272A 0%, #3F3F46 100%); padding: 40px 30px; text-align: center; }}
            .header h1 {{ color: #22C55E; font-size: 28px; font-weight: 700; margin-bottom: 8px; }}
            .header p {{ color: #a1a1aa; font-size: 16px; }}
            .content {{ padding: 30px; }}
            .greeting {{ font-size: 18px; color: #F3F4F6; margin-bottom: 20px; }}
            .message {{ color: #a1a1aa; margin-bottom: 30px; line-height: 1.7; }}
            .details-card {{ background-color: #27272A; border: 1px solid #3f3f46; border-radius: 12px; padding: 25px; margin: 25px 0; }}
            .details-card h3 {{ color: #22C55E; font-size: 20px; font-weight: 600; margin-bottom: 20px; display: flex; align-items: center; }}
            .details-card h3::before {{ content: "📋"; margin-right: 8px; }}
            .details-table {{ width: 100%; }}
            .details-row {{ display: flex; padding: 12px 0; border-bottom: 1px solid #3f3f46; }}
            .details-row:last-child {{ border-bottom: none; }}
            .details-label {{ font-weight: 600; color: #F3F4F6; width: 140px; flex-shrink: 0; }}
            .details-value {{ color: #a1a1aa; flex: 1; }}
            .highlight {{ color: #22C55E; font-weight: 600; }}
            .price {{ color: #F59E0B; font-weight: 700; font-size: 18px; }}
            .action-buttons {{ text-align: center; margin: 35px 0; }}
            .btn {{ display: inline-block; padding: 14px 28px; margin: 8px; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 16px; transition: all 0.3s ease; }}
            .btn-primary {{ background-color: #22C55E; color: #0F172A; }}
            .btn-secondary {{ background-color: transparent; color: #F3F4F6; border: 2px solid #3f3f46; }}
            .info-box {{ background-color: #3F3F46; border-left: 4px solid #22C55E; padding: 20px; margin: 25px 0; border-radius: 8px; }}
            .info-box p {{ color: #F3F4F6; margin: 0; }}
            .footer {{ background-color: #09090b; padding: 25px 30px; text-align: center; border-top: 1px solid #3f3f46; }}
            .footer p {{ color: #a1a1aa; margin: 0; }}
            .company-name {{ color: #22C55E; font-weight: 600; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🚗 Auto Lab Solutions</h1>
                <p>Your automotive service request has been received</p>
            </div>
            
            <div class="content">
                <p class="greeting">Dear {customer_name},</p>
                
                <p class="message">
                    Thank you for choosing Auto Lab Solutions for your automotive needs. We have successfully received your appointment request and our team will review it shortly.
                </p>
                
                <div class="details-card">
                    <h3>Appointment Details</h3>
                    <table class="details-table">
                        <tr class="details-row">
                            <td class="details-label">Reference ID:</td>
                            <td class="details-value highlight">{appointment_data.get('appointmentId', 'N/A')}</td>
                        </tr>
                        <tr class="details-row">
                            <td class="details-label">Services:</td>
                            <td class="details-value">{services}</td>
                        </tr>
                        <tr class="details-row">
                            <td class="details-label">Total Price:</td>
                            <td class="details-value price">AUD {appointment_data.get('totalPrice', 'N/A')}</td>
                        </tr>
                        <tr class="details-row">
                            <td class="details-label">Selected Slots:</td>
                            <td class="details-value">{formatted_timeslots}</td>
                        </tr>
                        <tr class="details-row">
                            <td class="details-label">Vehicle:</td>
                            <td class="details-value">{vehicle_info}</td>
                        </tr>
                        <tr class="details-row">
                            <td class="details-label">Contact Number:</td>
                            <td class="details-value">{appointment_data.get('customerData', {}).get('phoneNumber', 'N/A')}</td>
                        </tr>
                    </table>
                </div>
                
                <div class="info-box">
                    <p><strong>⏱️ What happens next?</strong> Our team will review your request and contact you within 1 hour to confirm the appointment details and finalize the schedule.</p>
                </div>
                
                <div class="action-buttons">
                    <a href="{FRONTEND_URL}/appointment/{appointment_data.get('appointmentId')}" class="btn btn-primary">💳 Complete Payment</a>
                    <a href="{FRONTEND_URL}/appointment/{appointment_data.get('appointmentId')}" class="btn btn-secondary">📱 Track Status</a>
                </div>
                
                <p class="message">
                    If you have any questions or need to make changes to your appointment, please don't hesitate to contact our support team.
                </p>
            </div>
            
            <div class="footer">
                <p>Best regards,<br><span class="company-name">Auto Lab Solutions Team</span></p>
            </div>
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
    """Send email when an order is created"""
    subject = EmailTemplate.ORDER_CREATED
    
    # Format order details
    items = format_order_items(order_data.get('items', []))
    vehicle_info = format_vehicle_info(order_data.get('vehicleInfo', {}))
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Service Order Created</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; }}
            .container {{ max-width: 600px; margin: 0 auto; background-color: #18181B; color: #F3F4F6; }}
            .header {{ background: linear-gradient(135deg, #27272A 0%, #3F3F46 100%); padding: 40px 30px; text-align: center; }}
            .header h1 {{ color: #22C55E; font-size: 28px; font-weight: 700; margin-bottom: 8px; }}
            .header p {{ color: #a1a1aa; font-size: 16px; }}
            .content {{ padding: 30px; }}
            .greeting {{ font-size: 18px; color: #F3F4F6; margin-bottom: 20px; }}
            .message {{ color: #a1a1aa; margin-bottom: 30px; line-height: 1.7; }}
            .details-card {{ background-color: #27272A; border: 1px solid #3f3f46; border-radius: 12px; padding: 25px; margin: 25px 0; }}
            .details-card h3 {{ color: #22C55E; font-size: 20px; font-weight: 600; margin-bottom: 20px; display: flex; align-items: center; }}
            .details-card h3::before {{ content: "🔧"; margin-right: 8px; }}
            .details-table {{ width: 100%; }}
            .details-row {{ display: flex; padding: 12px 0; border-bottom: 1px solid #3f3f46; }}
            .details-row:last-child {{ border-bottom: none; }}
            .details-label {{ font-weight: 600; color: #F3F4F6; width: 140px; flex-shrink: 0; }}
            .details-value {{ color: #a1a1aa; flex: 1; }}
            .highlight {{ color: #22C55E; font-weight: 600; }}
            .price {{ color: #F59E0B; font-weight: 700; font-size: 18px; }}
            .action-buttons {{ text-align: center; margin: 35px 0; }}
            .btn {{ display: inline-block; padding: 14px 28px; margin: 8px; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 16px; transition: all 0.3s ease; }}
            .btn-primary {{ background-color: #22C55E; color: #0F172A; }}
            .btn-secondary {{ background-color: transparent; color: #F3F4F6; border: 2px solid #3f3f46; }}
            .info-box {{ background-color: #3F3F46; border-left: 4px solid #22C55E; padding: 20px; margin: 25px 0; border-radius: 8px; }}
            .info-box p {{ color: #F3F4F6; margin: 0; }}
            .footer {{ background-color: #09090b; padding: 25px 30px; text-align: center; border-top: 1px solid #3f3f46; }}
            .footer p {{ color: #a1a1aa; margin: 0; }}
            .company-name {{ color: #22C55E; font-weight: 600; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🚗 Auto Lab Solutions</h1>
                <p>Your service order has been created successfully</p>
            </div>
            
            <div class="content">
                <p class="greeting">Dear {customer_name},</p>
                
                <p class="message">
                    Thank you for placing your service order with Auto Lab Solutions. We have received your order and our expert team will begin processing it shortly.
                </p>
                
                <div class="details-card">
                    <h3>Order Details</h3>
                    <table class="details-table">
                        <tr class="details-row">
                            <td class="details-label">Order ID:</td>
                            <td class="details-value highlight">{order_data.get('orderId', 'N/A')}</td>
                        </tr>
                        {f'<tr class="details-row"><td class="details-label">Items:</td><td class="details-value">{items}</td></tr>' if items else ""}
                        <tr class="details-row">
                            <td class="details-label">Vehicle:</td>
                            <td class="details-value">{vehicle_info}</td>
                        </tr>
                        <tr class="details-row">
                            <td class="details-label">Total Amount:</td>
                            <td class="details-value price">AUD {order_data.get('totalPrice', 'N/A')}</td>
                        </tr>
                        <tr class="details-row">
                            <td class="details-label">Contact Number:</td>
                            <td class="details-value">{order_data.get('customerData', {}).get('phoneNumber', 'N/A')}</td>
                        </tr>
                    </table>
                </div>
                
                <div class="info-box">
                    <p><strong>⏱️ What happens next?</strong> Our team will review your order and contact you to confirm the service details and schedule. We'll keep you updated throughout the process.</p>
                </div>
                
                <div class="action-buttons">
                    <a href="{FRONTEND_URL}/order/{order_data.get('orderId')}" class="btn btn-primary">💳 Complete Payment</a>
                    <a href="{FRONTEND_URL}/order/{order_data.get('orderId')}" class="btn btn-secondary">📱 Track Order</a>
                </div>
                
                <p class="message">
                    If you have any questions about your order or need assistance, please don't hesitate to contact our support team.
                </p>
                
                <p class="message">
                    Thank you for choosing Auto Lab Solutions for your automotive service needs!
                </p>
            </div>
            
            <div class="footer">
                <p>Best regards,<br><span class="company-name">Auto Lab Solutions Team</span></p>
            </div>
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

def send_appointment_updated_email(customer_email, customer_name, appointment_data, changes=None, update_type='general'):
    """Send email when appointment is updated"""
    
    # Determine email subject and title based on update type
    if update_type == 'status':
        current_status = appointment_data.get('status', 'Unknown')
        subject = f"Appointment Status Updated - {format_status_display(current_status)}"
        email_title = f"Appointment Status Changed to {format_status_display(current_status)}"
        intro_message = f"Your appointment status has been updated to <strong>{format_status_display(current_status)}</strong>."
    else:
        subject = EmailTemplate.APPOINTMENT_UPDATED
        email_title = "Appointment Updated"
        intro_message = "Your appointment has been updated. Please review the changes below and contact us if you have any questions."
    
    # Format appointment details
    services = format_services(appointment_data.get('services', []))
    vehicle_info = format_vehicle_info(appointment_data.get('vehicleInfo', {}))
    
    # Format changes - if changes not provided, create generic update message
    changes_html = ""
    if changes:
        for field, change in changes.items():
            # For status updates, only show new value (not old → new)
            if update_type == 'status' and field.lower() in ['status', 'appointment status']:
                new_value = change.get('new', 'N/A')
                changes_html += f"<p><strong>{format_field_name(field)}:</strong> {new_value}</p>"
            else:
                old_value = change.get('old', 'N/A')
                new_value = change.get('new', 'N/A')
                changes_html += f"<p><strong>{format_field_name(field)}:</strong> {old_value} → {new_value}</p>"
    else:
        changes_html = "<p>Your appointment details have been updated. Please review the current information below.</p>"
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{email_title}</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; }}
            .container {{ max-width: 600px; margin: 0 auto; background-color: #18181B; color: #F3F4F6; }}
            .header {{ background: linear-gradient(135deg, #27272A 0%, #3F3F46 100%); padding: 40px 30px; text-align: center; }}
            .header h1 {{ color: #F59E0B; font-size: 28px; font-weight: 700; margin-bottom: 8px; }}
            .header p {{ color: #a1a1aa; font-size: 16px; }}
            .content {{ padding: 30px; }}
            .greeting {{ font-size: 18px; color: #F3F4F6; margin-bottom: 20px; }}
            .message {{ color: #a1a1aa; margin-bottom: 30px; line-height: 1.7; }}
            .details-card {{ background-color: #27272A; border: 1px solid #3f3f46; border-radius: 12px; padding: 25px; margin: 25px 0; }}
            .details-card h3 {{ color: #22C55E; font-size: 20px; font-weight: 600; margin-bottom: 20px; display: flex; align-items: center; }}
            .details-card h3::before {{ content: "📋"; margin-right: 8px; }}
            .changes-card {{ background-color: #3F3F46; border-left: 4px solid #F59E0B; border-radius: 12px; padding: 25px; margin: 25px 0; }}
            .changes-card h3 {{ color: #F59E0B; font-size: 20px; font-weight: 600; margin-bottom: 20px; display: flex; align-items: center; }}
            .changes-card h3::before {{ content: "✏️"; margin-right: 8px; }}
            .details-table {{ width: 100%; }}
            .details-row {{ display: flex; padding: 12px 0; border-bottom: 1px solid #3f3f46; }}
            .details-row:last-child {{ border-bottom: none; }}
            .details-label {{ font-weight: 600; color: #F3F4F6; width: 140px; flex-shrink: 0; }}
            .details-value {{ color: #a1a1aa; flex: 1; }}
            .highlight {{ color: #22C55E; font-weight: 600; }}
            .price {{ color: #F59E0B; font-weight: 700; font-size: 18px; }}
            .status {{ padding: 6px 12px; border-radius: 20px; font-weight: 600; font-size: 14px; background-color: #22C55E; color: #0F172A; }}
            .action-buttons {{ text-align: center; margin: 35px 0; }}
            .btn {{ display: inline-block; padding: 14px 28px; margin: 8px; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 16px; transition: all 0.3s ease; }}
            .btn-primary {{ background-color: #22C55E; color: #0F172A; }}
            .btn-secondary {{ background-color: transparent; color: #F3F4F6; border: 2px solid #3f3f46; }}
            .warning-box {{ background-color: #3F3F46; border-left: 4px solid #F59E0B; padding: 20px; margin: 25px 0; border-radius: 8px; }}
            .warning-box p {{ color: #F3F4F6; margin: 0; }}
            .footer {{ background-color: #09090b; padding: 25px 30px; text-align: center; border-top: 1px solid #3f3f46; }}
            .footer p {{ color: #a1a1aa; margin: 0; }}
            .company-name {{ color: #22C55E; font-weight: 600; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🚗 Auto Lab Solutions</h1>
                <p>Appointment update notification</p>
            </div>
            
            <div class="content">
                <p class="greeting">Dear {customer_name},</p>
                
                <p class="message">{intro_message}</p>
                
                <div class="details-card">
                    <h3>Current Appointment Details</h3>
                    <table class="details-table">
                        <tr class="details-row">
                            <td class="details-label">Appointment ID:</td>
                            <td class="details-value highlight">{appointment_data.get('appointmentId', 'N/A')}</td>
                        </tr>
                        <tr class="details-row">
                            <td class="details-label">Services:</td>
                            <td class="details-value">{services}</td>
                        </tr>
                        <tr class="details-row">
                            <td class="details-label">Vehicle:</td>
                            <td class="details-value">{vehicle_info}</td>
                        </tr>
                        <tr class="details-row">
                            <td class="details-label">Current Status:</td>
                            <td class="details-value"><span class="status">{format_status_display(appointment_data.get('status', 'N/A'))}</span></td>
                        </tr>
                    </table>
                </div>
                
                <div class="changes-card">
                    <h3>{'Status Update' if update_type == 'status' else 'Changes Made'}</h3>
                    <div class="changes-content">
                        {changes_html}
                    </div>
                </div>
                
                <div class="action-buttons">
                    <a href="{FRONTEND_URL}/appointment/{appointment_data.get('appointmentId')}" class="btn btn-primary">📱 View Full Details</a>
                </div>
                
                <div class="warning-box">
                    <p><strong>⚠️ Important:</strong> If you have any questions about these changes or need immediate assistance, please contact us right away.</p>
                </div>
            </div>
            
            <div class="footer">
                <p>Best regards,<br><span class="company-name">Auto Lab Solutions Team</span></p>
            </div>
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

def send_order_updated_email(customer_email, customer_name, order_data, changes=None, update_type='general'):
    """Send email when order is updated"""
    
    # Determine email subject and title based on update type
    if update_type == 'status':
        current_status = order_data.get('status', 'Unknown')
        subject = f"Order Status Updated - {format_status_display(current_status)}"
        email_title = f"Order Status Changed to {format_status_display(current_status)}"
        intro_message = f"Your service order status has been updated to <strong>{format_status_display(current_status)}</strong>."
    else:
        subject = EmailTemplate.ORDER_UPDATED
        email_title = "Service Order Updated"
        intro_message = "Your service order has been updated. Please review the changes below."
    
    # Format order details
    items = format_order_items(order_data.get('items', []))
    vehicle_info = format_vehicle_info(order_data.get('vehicleInfo', {}))
    
    # Format changes - if changes not provided, create generic update message
    changes_html = ""
    if changes:
        for field, change in changes.items():
            # For status updates, only show new value (not old → new)
            if update_type == 'status' and field.lower() in ['status', 'order status']:
                new_value = change.get('new', 'N/A')
                changes_html += f"<p><strong>{format_field_name(field)}:</strong> {new_value}</p>"
            else:
                old_value = change.get('old', 'N/A')
                new_value = change.get('new', 'N/A')
                changes_html += f"<p><strong>{format_field_name(field)}:</strong> {old_value} → {new_value}</p>"
    else:
        changes_html = "<p>Your order details have been updated. Please review the current information below.</p>"
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{email_title}</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; }}
            .container {{ max-width: 600px; margin: 0 auto; background-color: #18181B; color: #F3F4F6; }}
            .header {{ background: linear-gradient(135deg, #27272A 0%, #3F3F46 100%); padding: 40px 30px; text-align: center; }}
            .header h1 {{ color: #F59E0B; font-size: 28px; font-weight: 700; margin-bottom: 8px; }}
            .header p {{ color: #a1a1aa; font-size: 16px; }}
            .content {{ padding: 30px; }}
            .greeting {{ font-size: 18px; color: #F3F4F6; margin-bottom: 20px; }}
            .message {{ color: #a1a1aa; margin-bottom: 30px; line-height: 1.7; }}
            .details-card {{ background-color: #27272A; border: 1px solid #3f3f46; border-radius: 12px; padding: 25px; margin: 25px 0; }}
            .details-card h3 {{ color: #22C55E; font-size: 20px; font-weight: 600; margin-bottom: 20px; display: flex; align-items: center; }}
            .details-card h3::before {{ content: "🔧"; margin-right: 8px; }}
            .changes-card {{ background-color: #3F3F46; border-left: 4px solid #F59E0B; border-radius: 12px; padding: 25px; margin: 25px 0; }}
            .changes-card h3 {{ color: #F59E0B; font-size: 20px; font-weight: 600; margin-bottom: 20px; display: flex; align-items: center; }}
            .changes-card h3::before {{ content: "✏️"; margin-right: 8px; }}
            .details-table {{ width: 100%; }}
            .details-row {{ display: flex; padding: 12px 0; border-bottom: 1px solid #3f3f46; }}
            .details-row:last-child {{ border-bottom: none; }}
            .details-label {{ font-weight: 600; color: #F3F4F6; width: 140px; flex-shrink: 0; }}
            .details-value {{ color: #a1a1aa; flex: 1; }}
            .highlight {{ color: #22C55E; font-weight: 600; }}
            .price {{ color: #F59E0B; font-weight: 700; font-size: 18px; }}
            .status {{ padding: 6px 12px; border-radius: 20px; font-weight: 600; font-size: 14px; background-color: #22C55E; color: #0F172A; }}
            .action-buttons {{ text-align: center; margin: 35px 0; }}
            .btn {{ display: inline-block; padding: 14px 28px; margin: 8px; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 16px; transition: all 0.3s ease; }}
            .btn-primary {{ background-color: #22C55E; color: #0F172A; }}
            .footer {{ background-color: #09090b; padding: 25px 30px; text-align: center; border-top: 1px solid #3f3f46; }}
            .footer p {{ color: #a1a1aa; margin: 0; }}
            .company-name {{ color: #22C55E; font-weight: 600; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🚗 Auto Lab Solutions</h1>
                <p>Service order update notification</p>
            </div>
            
            <div class="content">
                <p class="greeting">Dear {customer_name},</p>
                
                <p class="message">{intro_message}</p>
                
                <div class="details-card">
                    <h3>Current Order Details</h3>
                    <table class="details-table">
                        <tr class="details-row">
                            <td class="details-label">Order ID:</td>
                            <td class="details-value highlight">{order_data.get('orderId', 'N/A')}</td>
                        </tr>
                        <tr class="details-row">
                            <td class="details-label">Services:</td>
                            <td class="details-value">{services}</td>
                        </tr>
                        {f'<tr class="details-row"><td class="details-label">Items:</td><td class="details-value">{items}</td></tr>' if items else ""}
                        <tr class="details-row">
                            <td class="details-label">Vehicle:</td>
                            <td class="details-value">{vehicle_info}</td>
                        </tr>
                        <tr class="details-row">
                            <td class="details-label">Current Status:</td>
                            <td class="details-value"><span class="status">{format_status_display(order_data.get('status', 'N/A'))}</span></td>
                        </tr>
                        <tr class="details-row">
                            <td class="details-label">Total Amount:</td>
                            <td class="details-value price">AUD {order_data.get('totalAmount', '0.00')}</td>
                        </tr>
                    </table>
                </div>
                
                <div class="changes-card">
                    <h3>{'Status Update' if update_type == 'status' else 'Changes Made'}</h3>
                    <div class="changes-content">
                        {changes_html}
                    </div>
                </div>
                
                <div class="action-buttons">
                    <a href="{FRONTEND_URL}/order/{order_data.get('orderId')}" class="btn btn-primary">📱 View Updated Order</a>
                </div>
                
                <p class="message">
                    Thank you for choosing Auto Lab Solutions for your automotive service needs!
                </p>
            </div>
            
            <div class="footer">
                <p>Best regards,<br><span class="company-name">Auto Lab Solutions Team</span></p>
            </div>
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

def send_report_ready_email(customer_email, customer_name, appointment_data, report_url):
    """Send email when vehicle/service report is ready"""
    subject = EmailTemplate.APPOINTMENT_REPORT_READY
    appointment_id = appointment_data.get('appointmentId')
    email_type = EmailTemplate.TYPE_APPOINTMENT_REPORT
    
    # Format details
    services = format_services(appointment_data.get('services', []))
    vehicle_info = format_vehicle_info(appointment_data.get('vehicleInfo', {}))
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Vehicle Report Ready</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; }}
            .container {{ max-width: 600px; margin: 0 auto; background-color: #18181B; color: #F3F4F6; }}
            .header {{ background: linear-gradient(135deg, #22C55E 0%, #16A34A 100%); padding: 40px 30px; text-align: center; }}
            .header h1 {{ color: #FFFFFF; font-size: 28px; font-weight: 700; margin-bottom: 8px; }}
            .header p {{ color: #DCFCE7; font-size: 16px; }}
            .content {{ padding: 30px; }}
            .greeting {{ font-size: 18px; color: #F3F4F6; margin-bottom: 20px; }}
            .message {{ color: #a1a1aa; margin-bottom: 30px; line-height: 1.7; }}
            .details-card {{ background-color: #27272A; border: 1px solid #3f3f46; border-radius: 12px; padding: 25px; margin: 25px 0; }}
            .details-card h3 {{ color: #22C55E; font-size: 20px; font-weight: 600; margin-bottom: 20px; display: flex; align-items: center; }}
            .details-card h3::before {{ content: "📋"; margin-right: 8px; }}
            .report-card {{ background-color: #065F46; border: 1px solid #22C55E; border-radius: 12px; padding: 25px; margin: 25px 0; }}
            .report-card h3 {{ color: #22C55E; font-size: 20px; font-weight: 600; margin-bottom: 20px; display: flex; align-items: center; }}
            .report-card h3::before {{ content: "📄"; margin-right: 8px; }}
            .details-table {{ width: 100%; }}
            .details-row {{ display: flex; padding: 12px 0; border-bottom: 1px solid #3f3f46; }}
            .details-row:last-child {{ border-bottom: none; }}
            .details-label {{ font-weight: 600; color: #F3F4F6; width: 140px; flex-shrink: 0; }}
            .details-value {{ color: #a1a1aa; flex: 1; }}
            .highlight {{ color: #22C55E; font-weight: 600; }}
            .status {{ padding: 6px 12px; border-radius: 20px; font-weight: 600; font-size: 14px; background-color: #22C55E; color: #0F172A; }}
            .action-buttons {{ text-align: center; margin: 35px 0; }}
            .btn {{ display: inline-block; padding: 16px 32px; margin: 8px; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 16px; transition: all 0.3s ease; }}
            .btn-primary {{ background-color: #22C55E; color: #0F172A; }}
            .btn-secondary {{ background-color: transparent; color: #F3F4F6; border: 2px solid #3f3f46; }}
            .footer {{ background-color: #09090b; padding: 25px 30px; text-align: center; border-top: 1px solid #3f3f46; }}
            .footer p {{ color: #a1a1aa; margin: 0; }}
            .company-name {{ color: #22C55E; font-weight: 600; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>📄 Report Ready</h1>
                <p>Your vehicle inspection report is now available</p>
            </div>
            
            <div class="content">
                <p class="greeting">Dear {customer_name},</p>
                
                <p class="message">
                    <strong>Excellent news!</strong> We've completed the inspection and analysis of your vehicle. Your comprehensive report is now ready for review and download.
                </p>
                
                <div class="details-card">
                    <h3>Appointment Details</h3>
                    <table class="details-table">
                        <tr class="details-row">
                            <td class="details-label">Appointment ID:</td>
                            <td class="details-value highlight">{appointment_id}</td>
                        </tr>
                        <tr class="details-row">
                            <td class="details-label">Services:</td>
                            <td class="details-value">{services}</td>
                        </tr>
                        <tr class="details-row">
                            <td class="details-label">Vehicle:</td>
                            <td class="details-value">{vehicle_info}</td>
                        </tr>
                        <tr class="details-row">
                            <td class="details-label">Status:</td>
                            <td class="details-value"><span class="status">{appointment_data.get('status', 'Completed')}</span></td>
                        </tr>
                    </table>
                </div>
                
                <div class="report-card">
                    <h3>Report Information</h3>
                    <table class="details-table" style="border-bottom: 1px solid #22C55E;">
                        <tr class="details-row" style="border-bottom: 1px solid #22C55E;">
                            <td class="details-label" style="color: #DCFCE7;">Report Generated:</td>
                            <td class="details-value" style="color: #DCFCE7;">{format_timestamp(int(datetime.now().timestamp()))}</td>
                        </tr>
                        <tr class="details-row" style="border-bottom: none;">
                            <td class="details-label" style="color: #DCFCE7;">Download Link:</td>
                            <td class="details-value">
                                <a href="{report_url}" style="color: #22C55E; font-weight: 600; text-decoration: none;">📥 Click to download</a>
                            </td>
                        </tr>
                    </table>
                </div>
                
                <div class="action-buttons">
                    <a href="{report_url}" class="btn btn-primary">📥 Download Report</a>
                    <a href="{FRONTEND_URL}/appointment/{appointment_id}" class="btn btn-secondary">📱 View Appointment</a>
                </div>
                
                <p class="message">
                    Your report contains detailed findings, recommendations, and any maintenance suggestions for your vehicle. If you have any questions about the report or need clarification on any findings, our expert team is here to help.
                </p>
            </div>
            
            <div class="footer">
                <p>Thank you for choosing <span class="company-name">Auto Lab Solutions</span>!<br>Best regards, Auto Lab Solutions Team</p>
            </div>
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
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Payment Confirmation</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; }}
            .container {{ max-width: 600px; margin: 0 auto; background-color: #18181B; color: #F3F4F6; }}
            .header {{ background: linear-gradient(135deg, #22C55E 0%, #16A34A 100%); padding: 40px 30px; text-align: center; }}
            .header h1 {{ color: #FFFFFF; font-size: 28px; font-weight: 700; margin-bottom: 8px; }}
            .header p {{ color: #DCFCE7; font-size: 16px; }}
            .content {{ padding: 30px; }}
            .greeting {{ font-size: 18px; color: #F3F4F6; margin-bottom: 20px; }}
            .message {{ color: #a1a1aa; margin-bottom: 30px; line-height: 1.7; }}
            .payment-card {{ background-color: #065F46; border: 1px solid #22C55E; border-radius: 12px; padding: 25px; margin: 25px 0; }}
            .payment-card h3 {{ color: #22C55E; font-size: 20px; font-weight: 600; margin-bottom: 20px; display: flex; align-items: center; }}
            .payment-card h3::before {{ content: "💳"; margin-right: 8px; }}
            .details-table {{ width: 100%; }}
            .details-row {{ display: flex; padding: 12px 0; border-bottom: 1px solid #22C55E; }}
            .details-row:last-child {{ border-bottom: none; }}
            .details-label {{ font-weight: 600; color: #DCFCE7; width: 160px; flex-shrink: 0; }}
            .details-value {{ color: #DCFCE7; flex: 1; }}
            .amount {{ color: #F59E0B; font-weight: 700; font-size: 24px; }}
            .status {{ padding: 8px 16px; border-radius: 20px; font-weight: 600; font-size: 14px; background-color: #22C55E; color: #0F172A; }}
            .action-buttons {{ text-align: center; margin: 35px 0; }}
            .btn {{ display: inline-block; padding: 16px 32px; margin: 8px; text-decoration: none; border-radius: 8px; font-weight: 600; font-size: 16px; transition: all 0.3s ease; }}
            .btn-primary {{ background-color: #22C55E; color: #0F172A; }}
            .info-box {{ background-color: #3F3F46; border-left: 4px solid #22C55E; padding: 20px; margin: 25px 0; border-radius: 8px; }}
            .info-box p {{ color: #F3F4F6; margin: 0; }}
            .footer {{ background-color: #09090b; padding: 25px 30px; text-align: center; border-top: 1px solid #3f3f46; }}
            .footer p {{ color: #a1a1aa; margin: 0; }}
            .company-name {{ color: #22C55E; font-weight: 600; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>✅ Payment Confirmed</h1>
                <p>Your payment has been successfully processed</p>
            </div>
            
            <div class="content">
                <p class="greeting">Dear {customer_name},</p>
                
                <p class="message">
                    <strong>Thank you for your payment!</strong> We have successfully received and processed your payment. Your transaction is now complete and your invoice has been generated.
                </p>
                
                <div class="payment-card">
                    <h3>Payment Summary</h3>
                    <table class="details-table">
                        <tr class="details-row">
                            <td class="details-label">Amount Paid:</td>
                            <td class="details-value amount">AUD {amount}</td>
                        </tr>
                        <tr class="details-row">
                            <td class="details-label">Payment Method:</td>
                            <td class="details-value">{payment_method}</td>
                        </tr>
                        <tr class="details-row">
                            <td class="details-label">Payment Date:</td>
                            <td class="details-value">{payment_date}</td>
                        </tr>
                        <tr class="details-row">
                            <td class="details-label">Reference Number:</td>
                            <td class="details-value">{reference_number}</td>
                        </tr>
                        <tr class="details-row">
                            <td class="details-label">Transaction Status:</td>
                            <td class="details-value"><span class="status">✅ Completed</span></td>
                        </tr>
                    </table>
                </div>
                
                <div class="action-buttons">
                    <a href="{invoice_url}" class="btn btn-primary">📄 Download Invoice</a>
                </div>
                
                <div class="info-box">
                    <p><strong>📋 Important:</strong> Please save this invoice for your records. You may need it for warranty claims, tax purposes, or future service references.</p>
                </div>
                
                <p class="message">
                    Your payment confirmation has been recorded in our system. If you need additional documentation or have any questions about this payment, please don't hesitate to contact our support team.
                </p>
                
                <p class="message">
                    <strong>Thank you for choosing Auto Lab Solutions for your automotive service needs!</strong>
                </p>
            </div>
            
            <div class="footer">
                <p>Best regards,<br><span class="company-name">Auto Lab Solutions Team</span></p>
            </div>
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
            categoryName = item.get('categoryName', 'N/A')
            itemName = item.get('itemName', 'N/A')
            quantity = item.get('quantity', 1)
            price = item.get('price', '0.00')
            formatted.append(f"{itemName} (Quantity: {quantity}, Unit Price: AUD {price})")
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

def is_email_suppressed(email_address):
    """
    Check if an email address is suppressed
    
    Args:
        email_address (str): Email address to check
    
    Returns:
        bool: True if suppressed, False otherwise
    """
    if not SUPPRESSION_TABLE_NAME:
        print("Warning: EMAIL_SUPPRESSION_TABLE_NAME not configured, skipping suppression check")
        return False
    
    try:
        suppression_table = dynamodb.Table(SUPPRESSION_TABLE_NAME)
        
        # Query for active suppressions for this email
        response = suppression_table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('email').eq(email_address),
            FilterExpression=boto3.dynamodb.conditions.Attr('status').eq('active')
        )
        
        # If any active suppressions found, email is suppressed
        if response['Items']:
            suppression_reasons = [item['suppression_type'] for item in response['Items']]
            print(f"Email {email_address} is suppressed. Reasons: {suppression_reasons}")
            return True
        
        # Also check SES account-level suppression list
        try:
            ses_client.get_suppressed_destination(EmailAddress=email_address)
            print(f"Email {email_address} is suppressed in SES account-level list")
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == 'NotFoundException':
                # Not found in SES suppression list, which is good
                pass
            else:
                print(f"Error checking SES suppression list: {e}")
        
        return False
        
    except Exception as e:
        print(f"Error checking email suppression status: {str(e)}")
        # In case of error, allow email to be sent (fail open)
        return False

# =================================================================
# Data Preprocessing Utils
# =================================================================

def prepare_email_data_and_changes(updated_record, update_data, record_type):
    """Unified function to prepare both email data and changes for notifications"""
    # Format record data for email
    if record_type == 'appointment':
        email_data = format_appointment_data_for_email(updated_record)
    else:  # order
        email_data = format_order_data_for_email(updated_record)
    
    # Format changes for email with proper value resolution
    changes = format_changes_for_email(update_data, updated_record, record_type)
    
    return email_data, changes


def format_changes_for_email(update_data, updated_record, record_type):
    """Format update data into readable changes for email notifications with proper value resolution"""
    changes = {}
    
    # Define human-readable field names
    field_mappings = {
        'serviceId': 'Service',
        'planId': 'Plan',
        'price': 'Price',
        'status': 'Status',
        'assignedMechanicId': 'Assigned Mechanic',
        'scheduledTimeSlot': 'Scheduled Time',
        'scheduledDate': 'Scheduled Date',
        'isBuyer': 'Customer Type',
        'buyerName': 'Buyer Name',
        'buyerEmail': 'Buyer Email',
        'buyerPhone': 'Buyer Phone',
        'sellerName': 'Seller Name',
        'sellerEmail': 'Seller Email',
        'sellerPhone': 'Seller Phone',
        'carMake': 'Vehicle Make',
        'carModel': 'Vehicle Model',
        'carYear': 'Vehicle Year',
        'carLocation': 'Vehicle Location',
        'notes': 'Notes',
        'postNotes': 'Post-Service Notes',
        'customerName': 'Customer Name',
        'customerEmail': 'Customer Email',
        'customerPhone': 'Customer Phone',
        'deliveryLocation': 'Delivery Location',
        'totalPrice': 'Total Price',
        'items': 'Items'
    }
    
    for field, value in update_data.items():
        if field in ['updatedAt']:  # Skip technical fields
            continue
            
        human_readable_field = field_mappings.get(field, field.title())
        
        # Format specific field types with proper value resolution
        if field == 'scheduledTimeSlot' and isinstance(value, dict):
            if value:
                formatted_value = f"{value.get('date', '')} {value.get('start', '')} - {value.get('end', '')}"
            else:
                formatted_value = "Not scheduled"
        elif field == 'isBuyer':
            formatted_value = "Buyer" if value else "Seller"
        elif field == 'assignedMechanicId':
            if value:
                try:
                    mechanic_record = db.get_staff_record_by_user_id(value)
                    if mechanic_record:
                        mechanic_record = resp.convert_decimal(mechanic_record)
                        formatted_value = mechanic_record.get('name', f"Mechanic ID: {value}")
                    else:
                        formatted_value = f"Mechanic ID: {value}"
                except:
                    formatted_value = f"Mechanic ID: {value}"
            else:
                formatted_value = "Unassigned"
        elif field == 'serviceId' and record_type == 'appointment':
            try:
                plan_id = update_data.get('planId') or updated_record.get('planId')
                if plan_id:
                    service_name, _ = db.get_service_plan_names(value, plan_id)
                    formatted_value = service_name
                else:
                    formatted_value = f"Service ID: {value}"
            except:
                formatted_value = f"Service ID: {value}"
        elif field == 'planId' and record_type == 'appointment':
            try:
                service_id = update_data.get('serviceId') or updated_record.get('serviceId')
                if service_id:
                    _, plan_name = db.get_service_plan_names(service_id, value)
                    formatted_value = plan_name
                else:
                    formatted_value = f"Plan ID: {value}"
            except:
                formatted_value = f"Plan ID: {value}"
        elif field == 'items' and record_type == 'order':
            if isinstance(value, list):
                formatted_value = ", ".join(
                    f"{item.get('itemName', 'Unknown')} (Quantity: {item.get('quantity', 1)}, Unit Price: AUD {item.get('price', 0):.2f})"
                    for item in value if isinstance(item, dict)
                )
            else:
                formatted_value = "Invalid items format"
        elif field in ['price', 'totalPrice'] and isinstance(value, (int, float)):
            formatted_value = f"AUD {value:.2f}"
        else:
            formatted_value = str(value) if value is not None else "Not specified"
        
        changes[human_readable_field] = {
            'new': formatted_value
        }
    
    return changes


def format_appointment_data_for_email(appointment_data):
    """Format appointment data for email notifications"""
    # Get service and plan names
    service_name = "Service"
    plan_name = "Plan"
    
    try:
        service_id = appointment_data.get('serviceId')
        plan_id = appointment_data.get('planId')
        if service_id and plan_id:
            service_name, plan_name = db.get_service_plan_names(service_id, plan_id)
    except Exception as e:
        print(f"Error getting service plan names: {str(e)}")
    
    # Format vehicle info from database fields
    vehicle_info = {
        'make': appointment_data.get('carMake', 'N/A'),
        'model': appointment_data.get('carModel', 'N/A'),
        'year': appointment_data.get('carYear', 'N/A')
    }
    
    # Format scheduled time slot for display
    scheduled_slot = appointment_data.get('scheduledTimeSlot', {})
    time_slot = "TBD"
    if scheduled_slot and isinstance(scheduled_slot, dict):
        date = scheduled_slot.get('date', '')
        start_time = scheduled_slot.get('start', '')
        end_time = scheduled_slot.get('end', '')
        if date and start_time and end_time:
            time_slot = f"{date} {start_time} - {end_time}"
        elif date:
            time_slot = date
    
    # Get mechanic name if assigned
    assigned_mechanic = "Our team"
    assigned_mechanic_id = appointment_data.get('assignedMechanicId')
    if assigned_mechanic_id:
        try:
            mechanic_record = db.get_staff_record_by_user_id(assigned_mechanic_id)
            if mechanic_record:
                assigned_mechanic = mechanic_record.get('name', 'Our team')
        except Exception as e:
            print(f"Error getting mechanic name: {str(e)}")
    
    # Format customer data based on isBuyer flag
    is_buyer = appointment_data.get('isBuyer', True)
    if is_buyer:
        customer_data = {
            'phoneNumber': appointment_data.get('buyerPhone', 'N/A')
        }
    else:
        customer_data = {
            'phoneNumber': appointment_data.get('sellerPhone', 'N/A')
        }
    
    return {
        'appointmentId': appointment_data.get('appointmentId'),
        'serviceName': service_name,
        'planName': plan_name,
        'vehicleInfo': vehicle_info,
        'price': f"{appointment_data.get('price', 0):.2f}",
        'status': appointment_data.get('status', 'Processing'),
        'customerData': customer_data,
        'timeSlot': time_slot,
        'assignedMechanic': assigned_mechanic,
        'vehicleLocation': appointment_data.get('carLocation', 'N/A'),
        'notes': appointment_data.get('notes', ''),
        'postNotes': appointment_data.get('postNotes', '')
    }


def format_order_data_for_email(order_data):
    """Format order data for email notifications"""
    # Format items from database format
    items = []
    order_items = order_data.get('items', [])
    if isinstance(order_items, list):
        for item in order_items:
            # Already deserialized
            category_name, item_name = db.get_category_item_names(
                item.get('categoryId', 0),
                item.get('itemId', 0)
            )
            items.append({
                'categoryName': category_name,
                'itemName': item_name,
                'quantity': item.get('quantity', 1),
                'price': f"{item.get('price', 0):.2f}"
            })
    
    # Format vehicle info from database fields
    vehicle_info = {
        'make': order_data.get('carMake', 'N/A'),
        'model': order_data.get('carModel', 'N/A'),
        'year': order_data.get('carYear', 'N/A')
    }
    
    # Get mechanic name if assigned
    assigned_mechanic = "Our team"
    assigned_mechanic_id = order_data.get('assignedMechanicId')
    if assigned_mechanic_id:
        try:
            mechanic_record = db.get_staff_record_by_user_id(assigned_mechanic_id)
            if mechanic_record:
                assigned_mechanic = mechanic_record.get('name', 'Our team')
        except Exception as e:
            print(f"Error getting mechanic name: {str(e)}")
    
    # Format customer data
    customer_data = {
        'phoneNumber': order_data.get('customerPhone', 'N/A')
    }
    
    return {
        'orderId': order_data.get('orderId'),
        'items': items,
        'vehicleInfo': vehicle_info,
        'totalAmount': f"{order_data.get('totalPrice', 0):.2f}",
        'status': order_data.get('status', 'Processing'),
        'customerData': customer_data,
        'scheduledDate': order_data.get('scheduledDate'),
        'assignedMechanic': assigned_mechanic
    }

def format_status_display(status):
    """Format status for display in emails with proper capitalization and spacing"""
    if not status:
        return "Unknown"
    
    # Status mappings for better display
    status_mappings = {
        'PENDING': 'Pending',
        'SCHEDULED': 'Scheduled',
        'ONGOING': 'In Progress',
        'COMPLETED': 'Completed',
        'DELIVERED': 'Delivered',
        'CANCELLED': 'Cancelled',

        'PAID': 'Paid',
        'CONFIRMED': 'Confirmed'
    }
    
    return status_mappings.get(status.upper(), status.title())

# # Email storage utilities for managing received emails

# def get_emails_from_s3(s3_bucket, s3_key):
#     """
#     Retrieve and parse email from S3
    
#     Args:
#         s3_bucket (str): S3 bucket name
#         s3_key (str): S3 object key
        
#     Returns:
#         dict: Parsed email data
#     """
#     try:
#         import boto3
#         import email
        
#         s3_client = boto3.client('s3')
        
#         # Download email from S3
#         response = s3_client.get_object(Bucket=s3_bucket, Key=s3_key)
#         email_content = response['Body'].read()
        
#         # Parse email
#         parsed_email = email.message_from_bytes(email_content)
        
#         return {
#             'subject': parsed_email.get('Subject', ''),
#             'from': parsed_email.get('From', ''),
#             'to': parsed_email.get('To', ''),
#             'date': parsed_email.get('Date', ''),
#             'parsed_email': parsed_email
#         }
        
#     except Exception as e:
#         print(f"Error retrieving email from S3: {str(e)}")
#         return None


# def send_email_via_inbox(to_email, subject, html_body, text_body=None, reply_to=None):
#     """
#     Send email via SES that will be stored in the inbox system
    
#     Args:
#         to_email (str): Recipient email address
#         subject (str): Email subject
#         html_body (str): HTML email body
#         text_body (str): Plain text email body (optional)
#         reply_to (str): Reply-to address (optional)
    
#     Returns:
#         dict: Send result
#     """
#     email_type = EmailTemplate.TYPE_INBOX_EMAIL
#     try:
#         # Check if email is suppressed before attempting to send
#         if is_email_suppressed(to_email):
#             print(f"Email not sent - recipient {to_email} is suppressed")
#             log_email_activity(to_email, email_type, None, 'suppressed', 'Email address is suppressed')
#             return False
        
#         # If no text body provided, strip HTML tags for basic text version
#         if not text_body:
#             import re
#             text_body = re.sub('<[^<]+?>', '', html_body)
        
#         # Prepare email message
#         message = {
#             'Subject': {'Data': subject, 'Charset': 'UTF-8'},
#             'Body': {
#                 'Html': {'Data': html_body, 'Charset': 'UTF-8'},
#                 'Text': {'Data': text_body, 'Charset': 'UTF-8'}
#             }
#         }
        
#         # Send email
#         response = ses_client.send_email(
#             Source=MAIL_FROM_ADDRESS,
#             Destination={'ToAddresses': [to_email]},
#             Message=message
#         )
        
#         message_id = response['MessageId']
#         print(f"Email sent successfully to {to_email}. MessageId: {message_id}")
        
#         # Log email activity (optional, for analytics)
#         log_email_activity(to_email, email_type, message_id, 'sent')
        
#         return True
        
#     except ClientError as e:
#         error_code = e.response['Error']['Code']
#         error_message = e.response['Error']['Message']
#         print(f"Failed to send email to {to_email}. Error: {error_code} - {error_message}")
#         # Log email failure
#         log_email_activity(to_email, email_type, None, 'failed', error_message)
#         return False
    
#     except Exception as e:
#         print(f"Unexpected error sending email to {to_email}: {str(e)}")    
#         # Log email failure
#         log_email_activity(to_email, email_type, None, 'failed', str(e))
#         return False
    
