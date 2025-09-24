import boto3
import os
import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from botocore.exceptions import ClientError
import response_utils as resp

# Initialize SES client
ses_client = boto3.client('ses')

# Environment variables
NO_REPLY_EMAIL = os.environ.get('NO_REPLY_EMAIL')
MAIL_FROM_ADDRESS = os.environ.get('MAIL_FROM_ADDRESS')
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

    APPOINTMENT_REPORT_READY = "Your Inspection Report is Ready"
    PAYMENT_CONFIRMED = "Payment Confirmation - Invoice Generated"
    PAYMENT_CANCELLED = "Payment Cancelled - Notification"
    PAYMENT_REACTIVATED = "Payment Reactivated - Invoice Restored"
    
    # Email types for analytics
    TYPE_APPOINTMENT_CREATED = "appointment_created"
    TYPE_APPOINTMENT_UPDATED = "appointment_updated"
    TYPE_ORDER_CREATED = "order_created"
    TYPE_ORDER_UPDATED = "order_updated"

    TYPE_APPOINTMENT_REPORT = "appointment_report"
    TYPE_PAYMENT_CONFIRMED = "payment_confirmed"
    TYPE_PAYMENT_CANCELLED = "payment_cancelled"
    TYPE_PAYMENT_REACTIVATED = "payment_reactivated"

    TYPE_INBOX_EMAIL = "inbox_email"
    TYPE_ADMIN_MESSAGE = "admin_message"

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
        # Check if NO_REPLY_EMAIL is configured
        if not NO_REPLY_EMAIL:
            print("Error: NO_REPLY_EMAIL environment variable not configured")
            if email_type:
                log_email_activity(to_email, email_type, None, 'failed', 'NO_REPLY_EMAIL not configured')
            return False
        
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
            'timestamp': int(datetime.now(ZoneInfo('Australia/Perth')).timestamp()),
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
    
    # Debug: Print original appointment data structure
    print(f"DEBUG send_appointment_created_email: Original data keys: {list(appointment_data.keys())}")
    if 'assignedMechanic' in appointment_data:
        print(f"DEBUG send_appointment_created_email: Original assignedMechanic: {appointment_data.get('assignedMechanic')}")
    
    # Format appointment details using table format and get formatted data
    try:
        formatted_appointment_data = format_appointment_data_for_email(appointment_data)
        # Override the original appointment_data with formatted data to ensure mechanic name is available
        appointment_data = {**appointment_data, **formatted_appointment_data}
        print(f"DEBUG send_appointment_created_email: After formatting, assignedMechanic: {appointment_data.get('assignedMechanic')}")
    except Exception as e:
        print(f"Error formatting appointment data: {str(e)}")
        # Fallback: ensure assignedMechanic exists
        if 'assignedMechanic' not in appointment_data:
            appointment_data = {**appointment_data, 'assignedMechanic': 'Our team'}
    
    services_table = format_services_table(appointment_data.get('services', []))
    formatted_timeslots = format_timeslots_table(appointment_data.get('selectedSlots', []))
    vehicle_info = format_vehicle_info(appointment_data.get('vehicleInfo', {}))
    
    # Check if we have services to display
    has_services = bool(appointment_data.get('services'))
    
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
            .header {{ background: linear-gradient(135deg, #27272A 0%, #3F3F46 100%); padding: 24px 16px; text-align: center; }}
            .header h1 {{ color: #22C55E; font-size: 26px; font-weight: 700; margin-bottom: 8px; white-space: nowrap; }}
            .header p {{ color: #a1a1aa; font-size: 14px; }}
            .content {{ padding: 20px 16px; }}
            .greeting {{ font-size: 16px; color: #F3F4F6; margin-bottom: 15px; }}
            .message {{ color: #a1a1aa; margin-bottom: 20px; line-height: 1.6; }}
            .details-card {{ background-color: #27272A; border: 1px solid #3f3f46; border-radius: 8px; padding: 20px 16px; margin: 20px 0; }}
            .details-card h3 {{ color: #06B6D4; font-size: 18px; font-weight: 600; margin-bottom: 20px; text-align: center; }}
            .details-table {{ width: 100%; }}
            .details-row {{ padding: 16px 0; border-bottom: 1px solid #3f3f46; }}
            .details-row:last-child {{ border-bottom: none; }}
            .details-label {{ font-weight: 600; color: #F3F4F6; margin-bottom: 6px; display: inline-block; width: 140px; vertical-align: top; }}
            .details-value {{ color: #a1a1aa; display: inline-block; }}
            .details-value.services {{ display: block; margin-top: 6px; }}
            .service-line {{ display: block; margin-bottom: 4px; }}
            .timeslots-table {{ width: 100%; margin-top: 12px; }}
            .timeslots-table th {{ background-color: #3f3f46; color: #F3F4F6; padding: 10px; text-align: left; font-size: 12px; }}
            .timeslots-table td {{ padding: 10px; border-bottom: 1px solid #3f3f46; color: #a1a1aa; font-size: 12px; }}
            .timeslots-table tr:last-child td {{ border-bottom: none; }}
            .services-table {{ width: 100%; margin-top: 12px; }}
            .services-table th {{ background-color: #3f3f46; color: #F3F4F6; padding: 10px; text-align: left; font-size: 12px; }}
            .services-table td {{ padding: 10px; border-bottom: 1px solid #3f3f46; color: #a1a1aa; font-size: 12px; }}
            .services-table tr:last-child td {{ border-bottom: none; }}
            .highlight {{ color: #22C55E; font-weight: 600; }}
            .price {{ color: #F59E0B; font-weight: 700; font-size: 16px; }}
            .status {{ padding: 4px 10px; border-radius: 16px; font-weight: 600; font-size: 12px; background-color: #22C55E; color: #0F172A; }}
            .action-buttons {{ text-align: center; margin: 25px 0; }}
            .btn {{ display: inline-block; padding: 12px 18px; margin: 6px; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 14px; transition: all 0.3s ease; }}
            .btn-primary {{ background-color: #22C55E; color: #0F172A; }}
            .btn-secondary {{ background-color: transparent; color: #F3F4F6; border: 2px solid #3f3f46; }}
            .btn-view {{ background: linear-gradient(135deg, #3B82F6, #1E40AF); color: white; border: none; box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3); }}
            .btn-view:hover {{ background: linear-gradient(135deg, #2563EB, #1D4ED8); transform: translateY(-1px); box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4); }}
            .btn-view-primary {{ background: linear-gradient(135deg, #3B82F6, #1E40AF); color: white; border: none; box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3); padding: 14px 24px; font-size: 15px; }}
            .btn-view-primary:hover {{ background: linear-gradient(135deg, #2563EB, #1D4ED8); transform: translateY(-1px); box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4); }}
            .info-box {{ background-color: #3F3F46; border-left: 4px solid #22C55E; padding: 16px; margin: 20px 0; border-radius: 6px; }}
            .info-box p {{ color: #F3F4F6; margin: 0; }}
            .next-steps {{ margin: 12px 0 0 0; }}
            .footer {{ background-color: #09090b; padding: 20px 16px; text-align: center; border-top: 1px solid #3f3f46; }}
            .footer p {{ color: #a1a1aa; margin: 0; line-height: 1.5; }}
            .company-name {{ color: #22C55E; font-weight: 600; }}
            .contact-email {{ color: #22C55E; text-decoration: none; font-weight: 600; }}
            @media only screen and (max-width: 480px) {{
                .header {{ padding: 18px 12px; }}
                .header h1 {{ font-size: 22px; }}
                .content {{ padding: 16px 12px; }}
                .details-card {{ padding: 16px 12px; margin: 16px 0; }}
                .details-label {{ font-size: 13px; }}
                .details-value {{ font-size: 13px; }}
                .btn {{ padding: 10px 15px; font-size: 13px; margin: 4px; }}
                .footer {{ padding: 16px 12px; }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>✨ Auto Lab Solutions</h1>
                <p>Your automotive service request has been received</p>
            </div>
            
            <div class="content">
                <p class="greeting">Dear {customer_name},</p>
                
                <p class="message">
                    Thank you for choosing Auto Lab Solutions for your automotive needs. 🚗 We have successfully received your appointment request and our team will review it shortly.
                </p>
                
                <div class="details-card">
                    <h3>📋 Appointment Details</h3>
                    <div class="details-table">
                        <div class="details-row">
                            <span class="details-label">Appointment ID:</span>
                            <span class="details-value highlight">{appointment_data.get('appointmentId', 'N/A')}</span>
                        </div>
                        {f'<div class="details-section"><h4 style="margin: 15px 0 10px 0; color: #374151;">Services:</h4>{services_table}</div>' if has_services else ""}
                        <div class="details-row">
                            <span class="details-label">Selected Slots:</span>
                            <span class="details-value">
                                {formatted_timeslots}
                            </span>
                        </div>
                        <div class="details-row">
                            <span class="details-label">Vehicle:</span>
                            <span class="details-value">{vehicle_info}</span>
                        </div>
                        <div class="details-row">
                            <span class="details-label">Contact Number:</span>
                            <span class="details-value">{appointment_data.get('customerData', {}).get('phoneNumber', 'N/A')}</span>
                        </div>
                        {f'<div class="details-row"><span class="details-label">Assigned Mechanic:</span><span class="details-value">{appointment_data.get("assignedMechanic", "Our team")}</span></div>' if appointment_data.get('assignedMechanic') and appointment_data.get('assignedMechanic') != 'Our team' else ""}
                        <div class="details-row">
                            <span class="details-label">Status:</span>
                            <span class="details-value"><span class="status">{format_status_display(appointment_data.get('status', 'PENDING'))}</span></span>
                        </div>
                        <div class="details-row">
                            <span class="details-label">Total Amount:</span>
                            <span class="details-value price">AUD {appointment_data.get('totalPrice', '0.00')}</span>
                        </div>
                    </div>
                </div>
                
                <div class="info-box">
                    <p><strong>⏱️ What happens next?</strong></p>
                    
                    <p class="next-steps">Our team will review your request and contact you within an hour to confirm the appointment details and finalize the schedule.</p>
                </div>
                
                <div class="action-buttons">
                    <a href="{FRONTEND_URL}/appointment/{appointment_data.get('appointmentId')}" class="btn btn-primary">💳 Complete Payment</a>
                </div>
                
                <p class="message">
                    If you have any questions or need to make changes to your appointment, please feel free to contact our support team by replying to this email. 📧 <a href="mailto:{MAIL_FROM_ADDRESS}" class="contact-email">{MAIL_FROM_ADDRESS}</a>
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
    
    # Debug: Print original order data structure
    print(f"DEBUG send_order_created_email: Original data keys: {list(order_data.keys())}")
    if 'assignedMechanic' in order_data:
        print(f"DEBUG send_order_created_email: Original assignedMechanic: {order_data.get('assignedMechanic')}")
    
    # Format order details using table format and get formatted data
    try:
        # Use the existing format function to get properly formatted data including mechanic name
        formatted_order_data = format_order_data_for_email(order_data)
        # Override the original order_data with formatted data to ensure mechanic name is available
        order_data = {**order_data, **formatted_order_data}
        print(f"DEBUG send_order_created_email: After formatting, assignedMechanic: {order_data.get('assignedMechanic')}")
    except Exception as e:
        print(f"Error formatting order data: {str(e)}")
        # Fallback: ensure assignedMechanic exists
        if 'assignedMechanic' not in order_data:
            order_data = {**order_data, 'assignedMechanic': 'Our team'}
    
    items_table = format_order_items_table(order_data.get('items', []))
    vehicle_info = format_vehicle_info(order_data.get('vehicleInfo', {}))
    
    # Check if we have items to display
    has_items = bool(order_data.get('items'))
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Service Order Created</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            .header {{ background: linear-gradient(135deg, #27272A 0%, #3F3F46 100%); padding: 24px 16px; text-align: center; }}
            .header h1 {{ color: #22C55E; font-size: 26px; font-weight: 700; margin-bottom: 8px; white-space: nowrap; }}
            .header p {{ color: #a1a1aa; font-size: 14px; }}
            .content {{ padding: 20px 16px; }}
            .greeting {{ font-size: 16px; color: #F3F4F6; margin-bottom: 15px; }}
            .message {{ color: #a1a1aa; margin-bottom: 20px; line-height: 1.6; }}
            .details-card {{ background-color: #27272A; border: 1px solid #3f3f46; border-radius: 8px; padding: 20px 16px; margin: 20px 0; }}
            .details-card h3 {{ color: #06B6D4; font-size: 18px; font-weight: 600; margin-bottom: 20px; text-align: center; }}
            .details-table {{ width: 100%; }}
            .details-row {{ padding: 16px 0; border-bottom: 1px solid #3f3f46; }}
            .details-row:last-child {{ border-bottom: none; }}
            .details-label {{ font-weight: 600; color: #F3F4F6; margin-bottom: 6px; display: inline-block; width: 140px; vertical-align: top; }}
            .details-value {{ color: #a1a1aa; display: inline-block; }}
            .details-value.services {{ display: block; margin-top: 6px; }}
            .service-line {{ display: block; margin-bottom: 4px; }}
            .order-items-table {{ width: 100%; margin-top: 12px; }}
            .order-items-table th {{ background-color: #3f3f46; color: #F3F4F6; padding: 10px; text-align: left; font-size: 12px; }}
            .order-items-table td {{ padding: 10px; border-bottom: 1px solid #3f3f46; color: #a1a1aa; font-size: 12px; }}
            .order-items-table tr:last-child td {{ border-bottom: none; }}
            .highlight {{ color: #22C55E; font-weight: 600; }}
            .price {{ color: #F59E0B; font-weight: 700; font-size: 16px; }}
            .status {{ padding: 4px 10px; border-radius: 16px; font-weight: 600; font-size: 12px; background-color: #22C55E; color: #0F172A; }}
            .action-buttons {{ text-align: center; margin: 25px 0; }}
            .btn {{ display: inline-block; padding: 12px 18px; margin: 6px; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 14px; transition: all 0.3s ease; }}
            .btn-primary {{ background-color: #22C55E; color: #0F172A; }}
            .btn-secondary {{ background-color: transparent; color: #F3F4F6; border: 2px solid #3f3f46; }}
            .btn-view {{ background: linear-gradient(135deg, #3B82F6, #1E40AF); color: white; border: none; box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3); }}
            .btn-view:hover {{ background: linear-gradient(135deg, #2563EB, #1D4ED8); transform: translateY(-1px); box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4); }}
            .btn-view-primary {{ background: linear-gradient(135deg, #3B82F6, #1E40AF); color: white; border: none; box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3); padding: 14px 24px; font-size: 15px; }}
            .btn-view-primary:hover {{ background: linear-gradient(135deg, #2563EB, #1D4ED8); transform: translateY(-1px); box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4); }}
            .info-box {{ background-color: #3F3F46; border-left: 4px solid #22C55E; padding: 16px; margin: 20px 0; border-radius: 6px; }}
            .info-box p {{ color: #F3F4F6; margin: 0; }}
            .next-steps {{ margin: 12px 0 0 0; }}
            .footer {{ background-color: #09090b; padding: 20px 16px; text-align: center; border-top: 1px solid #3f3f46; }}
            .footer p {{ color: #a1a1aa; margin: 0; line-height: 1.5; }}
            .company-name {{ color: #22C55E; font-weight: 600; }}
            .contact-email {{ color: #22C55E; text-decoration: none; font-weight: 600; }}
            @media only screen and (max-width: 480px) {{
                .header {{ padding: 18px 12px; }}
                .header h1 {{ font-size: 22px; }}
                .content {{ padding: 16px 12px; }}
                .details-card {{ padding: 16px 12px; margin: 16px 0; }}
                .details-label {{ font-size: 13px; }}
                .details-value {{ font-size: 13px; }}
                .btn {{ padding: 10px 15px; font-size: 13px; margin: 4px; }}
                .footer {{ padding: 16px 12px; }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>✨ Auto Lab Solutions</h1>
                <p>Your service order has been created successfully</p>
            </div>
            
            <div class="content">
                <p class="greeting">Dear {customer_name},</p>
                
                <p class="message">
                    Thank you for placing your service order with Auto Lab Solutions. 🔧 We have received your order and our expert team will begin processing it shortly.
                </p>
                
                <div class="details-card">
                    <h3>🛒 Order Details</h3>
                    <div class="details-table">
                        <div class="details-row">
                            <span class="details-label">Order ID:</span>
                            <span class="details-value highlight">{order_data.get('orderId', 'N/A')}</span>
                        </div>
                        {f'<div class="details-section"><h4 style="margin: 15px 0 10px 0; color: #374151;">Items:</h4>{items_table}</div>' if has_items else ""}
                        <div class="details-row">
                            <span class="details-label">Vehicle:</span>
                            <span class="details-value">{vehicle_info}</span>
                        </div>
                        <div class="details-row">
                            <span class="details-label">Contact Number:</span>
                            <span class="details-value">{order_data.get('customerData', {}).get('phoneNumber', 'N/A')}</span>
                        </div>
                        {f'<div class="details-row"><span class="details-label">Assigned Mechanic:</span><span class="details-value">{order_data.get("assignedMechanic", "Our team")}</span></div>' if order_data.get('assignedMechanic') and order_data.get('assignedMechanic') != 'Our team' else ""}
                        <div class="details-row">
                            <span class="details-label">Status:</span>
                            <span class="details-value"><span class="status">{format_status_display(order_data.get('status', 'PENDING'))}</span></span>
                        </div>
                        <div class="details-row">
                            <span class="details-label">Total Amount:</span>
                            <span class="details-value price">AUD {order_data.get('totalPrice', '0.00')}</span>
                        </div>
                    </div>
                </div>
                
                <div class="info-box">
                    <p><strong>⏱️ What happens next?</strong></p>
                    
                    <p class="next-steps">Our team will review your order and contact you to confirm the service details and schedule. We'll keep you updated throughout the process.</p>
                </div>
                
                <div class="action-buttons">
                    <a href="{FRONTEND_URL}/order/{order_data.get('orderId')}" class="btn btn-primary">💳 Complete Payment</a>
                </div>
                
                <p class="message">
                    If you have any questions about your order or need assistance, please feel free to contact our support team by replying to this email. 📧 <a href="mailto:{MAIL_FROM_ADDRESS}" class="contact-email">{MAIL_FROM_ADDRESS}</a>
                </p>
                
                <p class="message">
                    Thank you for choosing Auto Lab Solutions for your automotive service needs! 🚗
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
    elif update_type == 'scheduling':
        subject = "Appointment Scheduling Update"
        email_title = "Appointment Scheduling Update"
        intro_message = "Your appointment scheduling has been updated. Please review the details below."
    else:
        subject = EmailTemplate.APPOINTMENT_UPDATED
        email_title = "Appointment Updated"
        intro_message = "Your appointment has been updated. Please review the changes below and contact us if you have any questions."
    
    # Format appointment details using table format and get formatted data
    try:
        # Use the existing format function to get properly formatted data including mechanic name
        formatted_appointment_data = format_appointment_data_for_email(appointment_data)
        # Override the original appointment_data with formatted data to ensure mechanic name is available
        appointment_data = {**appointment_data, **formatted_appointment_data}
    except Exception as e:
        print(f"Error formatting appointment data: {str(e)}")
        # Fallback: ensure assignedMechanic exists
        if 'assignedMechanic' not in appointment_data:
            appointment_data = {**appointment_data, 'assignedMechanic': 'Our team'}
    
    services_table = format_services_table(appointment_data.get('services', []))
    formatted_timeslots = format_timeslots_table(appointment_data.get('selectedSlots', []))
    vehicle_info = format_vehicle_info(appointment_data.get('vehicleInfo', {}))
    
    # Check if we have services to display
    has_services = bool(appointment_data.get('services'))
    
    # Format changes with structured table format
    changes_html = format_changes_table(changes, update_type)
    
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
            .header {{ background: linear-gradient(135deg, #27272A 0%, #3F3F46 100%); padding: 24px 16px; text-align: center; }}
            .header h1 {{ color: #22C55E; font-size: 26px; font-weight: 700; margin-bottom: 8px; white-space: nowrap; }}
            .header p {{ color: #a1a1aa; font-size: 14px; }}
            .content {{ padding: 20px 16px; }}
            .greeting {{ font-size: 16px; color: #F3F4F6; margin-bottom: 15px; }}
            .message {{ color: #a1a1aa; margin-bottom: 20px; line-height: 1.6; }}
            .details-card {{ background-color: #27272A; border: 1px solid #3f3f46; border-radius: 8px; padding: 20px 16px; margin: 20px 0; }}
            .details-card h3 {{ color: #06B6D4; font-size: 18px; font-weight: 600; margin-bottom: 20px; text-align: center; }}
            .changes-card {{ background-color: #3F3F46; border-left: 4px solid #F59E0B; border-radius: 8px; padding: 20px 16px; margin: 20px 0; }}
            .changes-card h3 {{ color: #F59E0B; font-size: 18px; font-weight: 600; margin-bottom: 20px; text-align: center; }}
            .changes-table {{ width: 100%; }}
            .changes-row {{ padding: 16px 0; border-bottom: 1px solid #52525B; display: flex; align-items: flex-start; }}
            .changes-row:last-child {{ border-bottom: none; }}
            .changes-label {{ font-weight: 600; color: #F3F4F6; margin-bottom: 6px; display: inline-block; width: 140px; vertical-align: top; flex-shrink: 0; }}
            .changes-value {{ color: #a1a1aa; display: inline-block; flex: 1; }}
            .change-transition {{ margin-top: 4px; }}
            .change-from {{ margin-bottom: 4px; font-size: 13px; }}
            .change-to {{ font-size: 13px; }}
            .old-value {{ color: #F59E0B; font-weight: 600; }}
            .new-value {{ color: #22C55E; font-weight: 600; }}
            .details-table {{ width: 100%; }}
            .details-row {{ padding: 12px 0; border-bottom: 1px solid #3f3f46; }}
            .details-row:last-child {{ border-bottom: none; }}
            .details-label {{ font-weight: 600; color: #F3F4F6; margin-bottom: 6px; display: inline-block; width: 140px; vertical-align: top; }}
            .details-value {{ color: #a1a1aa; display: inline-block; }}
            .details-value.inline {{ display: inline; }}
            .highlight {{ color: #22C55E; font-weight: 600; }}
            .price {{ color: #F59E0B; font-weight: 700; font-size: 16px; }}
            .status {{ padding: 4px 10px; border-radius: 16px; font-weight: 600; font-size: 12px; background-color: #22C55E; color: #0F172A; }}
            .action-buttons {{ text-align: center; margin: 25px 0; }}
            .btn {{ display: inline-block; padding: 12px 18px; margin: 6px; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 14px; transition: all 0.3s ease; }}
            .btn-primary {{ background-color: #22C55E; color: #0F172A; }}
            .btn-secondary {{ background-color: transparent; color: #F3F4F6; border: 2px solid #3f3f46; }}
            .btn-view {{ background: linear-gradient(135deg, #3B82F6, #1E40AF); color: white; border: none; box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3); }}
            .btn-view:hover {{ background: linear-gradient(135deg, #2563EB, #1D4ED8); transform: translateY(-1px); box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4); }}
            .btn-view-primary {{ background: linear-gradient(135deg, #3B82F6, #1E40AF); color: white; border: none; box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3); padding: 14px 24px; font-size: 15px; }}
            .btn-view-primary:hover {{ background: linear-gradient(135deg, #2563EB, #1D4ED8); transform: translateY(-1px); box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4); }}
            .warning-box {{ background-color: #3F3F46; border-left: 4px solid #F59E0B; padding: 16px; margin: 20px 0; border-radius: 6px; }}
            .warning-box p {{ color: #F3F4F6; margin: 0; }}
            .footer {{ background-color: #09090b; padding: 20px 16px; text-align: center; border-top: 1px solid #3f3f46; }}
            .footer p {{ color: #a1a1aa; margin: 0; line-height: 1.5; }}
            .company-name {{ color: #22C55E; font-weight: 600; }}
            .contact-email {{ color: #22C55E; text-decoration: none; font-weight: 600; }}
            @media only screen and (max-width: 480px) {{
                .header {{ padding: 18px 12px; }}
                .header h1 {{ font-size: 22px; }}
                .content {{ padding: 16px 12px; }}
                .details-card {{ padding: 16px 12px; margin: 16px 0; }}
                .changes-card {{ padding: 16px 12px; margin: 16px 0; }}
                .details-label {{ font-size: 13px; }}
                .details-value {{ font-size: 13px; }}
                .changes-label {{ font-size: 13px; width: 120px; }}
                .changes-value {{ font-size: 13px; }}
                .change-from, .change-to {{ font-size: 12px; }}
                .btn {{ padding: 10px 15px; font-size: 13px; margin: 4px; }}
                .footer {{ padding: 16px 12px; }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>✨ Auto Lab Solutions</h1>
                <p>Appointment update notification</p>
            </div>
            
            <div class="content">
                <p class="greeting">Dear {customer_name},</p>
                
                <p class="message">{intro_message} 🔄</p>
                
                <div class="details-card">
                    <h3>📋 Current Appointment Details</h3>
                    <div class="details-table">
                        <div class="details-row">
                            <span class="details-label">Appointment ID:</span>
                            <span class="details-value highlight">{appointment_data.get('appointmentId', 'N/A')}</span>
                        </div>
                        {f'<div class="details-section"><h4 style="margin: 15px 0 10px 0; color: #374151;">Services:</h4>{services_table}</div>' if has_services else ""}
                        <div class="details-row">
                            <span class="details-label">Selected Slots:</span>
                            <span class="details-value">
                                {formatted_timeslots}
                            </span>
                        </div>
                        <div class="details-row">
                            <span class="details-label">Vehicle:</span>
                            <span class="details-value">{vehicle_info}</span>
                        </div>
                        <div class="details-row">
                            <span class="details-label">Contact Number:</span>
                            <span class="details-value">{appointment_data.get('customerData', {}).get('phoneNumber', 'N/A')}</span>
                        </div>
                        {f'<div class="details-row"><span class="details-label">Assigned Mechanic:</span><span class="details-value">{appointment_data.get("assignedMechanic", "Our team")}</span></div>' if appointment_data.get('assignedMechanic') and appointment_data.get('assignedMechanic') != 'Our team' else ""}
                        <div class="details-row">
                            <span class="details-label">Status:</span>
                            <span class="details-value"><span class="status">{format_status_display(appointment_data.get('status', 'N/A'))}</span></span>
                        </div>
                        <div class="details-row">
                            <span class="details-label">Total Amount:</span>
                            <span class="details-value price">AUD {appointment_data.get('totalPrice', '0.00')}</span>
                        </div>
                    </div>
                </div>
                
                <div class="changes-card">
                    <h3>{'📊 Status Update' if update_type == 'status' else '📅 Scheduling Update' if update_type == 'scheduling' else '✏️ Changes Made'}</h3>
                    <div class="changes-content">
                        {changes_html}
                    </div>
                </div>
                
                {generate_update_action_buttons(appointment_data, 'appointment', FRONTEND_URL)}
                
                {f'''
                <div class="warning-box" style="background-color: #065F46; border-left: 4px solid #22C55E;">
                    <p><strong>📄 Inspection Report:</strong></p>
                    <p style="margin: 12px 0 0 0;">We will send you an inspection report soon with detailed findings and recommendations. Keep an eye on your email! 📧</p>
                </div>
                ''' if update_type == 'status' and appointment_data.get('status', '').upper() == 'COMPLETED' and any(
                    'inspection' in service.get('serviceName', '').lower() 
                    for service in appointment_data.get('services', []) 
                    if isinstance(service, dict)
                ) else ''}
                
                <div class="warning-box">
                    <p><strong>⚠️ Important:</strong></p>
                    
                    <p style="margin: 12px 0 0 0;">If you have any questions about these changes, please feel free to contact us by replying to this email. 📧 <a href="mailto:{MAIL_FROM_ADDRESS}" class="contact-email">{MAIL_FROM_ADDRESS}</a></p>
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

    print("order data:", order_data)
    
    # Determine email subject and title based on update type
    if update_type == 'status':
        current_status = order_data.get('status', 'Unknown')
        subject = f"Order Status Updated - {format_status_display(current_status)}"
        email_title = f"Order Status Changed to {format_status_display(current_status)}"
        intro_message = f"Your service order status has been updated to <strong>{format_status_display(current_status)}</strong>."
    elif update_type == 'scheduling':
        subject = "Order Scheduling Update"
        email_title = "Order Scheduling Update"
        intro_message = "Your service order scheduling has been updated. Please review the details below."
    else:
        subject = EmailTemplate.ORDER_UPDATED
        email_title = "Service Order Updated"
        intro_message = "Your service order has been updated. Please review the changes below."
    
    # Format order details using table format and get formatted data
    try:
        # Use the existing format function to get properly formatted data including mechanic name
        formatted_order_data = format_order_data_for_email(order_data)
        # Override the original order_data with formatted data to ensure mechanic name is available
        order_data = {**order_data, **formatted_order_data}
    except Exception as e:
        print(f"Error formatting order data: {str(e)}")
        # Fallback: ensure assignedMechanic exists
        if 'assignedMechanic' not in order_data:
            order_data = {**order_data, 'assignedMechanic': 'Our team'}
    
    items_table = format_order_items_table(order_data.get('items', []))
    services_table = format_services_table(order_data.get('services', []))
    vehicle_info = format_vehicle_info(order_data.get('vehicleInfo', {}))
    
    # Check if we have items or services to display
    has_items = bool(order_data.get('items'))
    has_services = bool(order_data.get('services'))
    
    # Format changes with structured table format
    changes_html = format_changes_table(changes, update_type)
    
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
            .header {{ background: linear-gradient(135deg, #27272A 0%, #3F3F46 100%); padding: 24px 16px; text-align: center; }}
            .header h1 {{ color: #22C55E; font-size: 26px; font-weight: 700; margin-bottom: 8px; white-space: nowrap; }}
            .header p {{ color: #a1a1aa; font-size: 14px; }}
            .content {{ padding: 20px 16px; }}
            .greeting {{ font-size: 16px; color: #F3F4F6; margin-bottom: 15px; }}
            .message {{ color: #a1a1aa; margin-bottom: 20px; line-height: 1.6; }}
            .details-card {{ background-color: #27272A; border: 1px solid #3f3f46; border-radius: 8px; padding: 20px 16px; margin: 20px 0; }}
            .details-card h3 {{ color: #06B6D4; font-size: 18px; font-weight: 600; margin-bottom: 20px; text-align: center; }}
            .changes-card {{ background-color: #3F3F46; border-left: 4px solid #F59E0B; border-radius: 8px; padding: 20px 16px; margin: 20px 0; }}
            .changes-card h3 {{ color: #F59E0B; font-size: 18px; font-weight: 600; margin-bottom: 20px; text-align: center; }}
            .changes-table {{ width: 100%; }}
            .changes-row {{ padding: 16px 0; border-bottom: 1px solid #52525B; display: flex; align-items: flex-start; }}
            .changes-row:last-child {{ border-bottom: none; }}
            .changes-label {{ font-weight: 600; color: #F3F4F6; margin-bottom: 6px; display: inline-block; width: 140px; vertical-align: top; flex-shrink: 0; }}
            .changes-value {{ color: #a1a1aa; display: inline-block; flex: 1; }}
            .change-transition {{ margin-top: 4px; }}
            .change-from {{ margin-bottom: 4px; font-size: 13px; }}
            .change-to {{ font-size: 13px; }}
            .old-value {{ color: #F59E0B; font-weight: 600; }}
            .new-value {{ color: #22C55E; font-weight: 600; }}
            .details-table {{ width: 100%; }}
            .details-row {{ padding: 12px 0; border-bottom: 1px solid #3f3f46; }}
            .details-row:last-child {{ border-bottom: none; }}
            .details-label {{ font-weight: 600; color: #F3F4F6; margin-bottom: 6px; display: inline-block; width: 140px; vertical-align: top; }}
            .details-value {{ color: #a1a1aa; display: inline-block; }}
            .details-value.inline {{ display: inline; }}
            .highlight {{ color: #22C55E; font-weight: 600; }}
            .price {{ color: #F59E0B; font-weight: 700; font-size: 16px; }}
            .status {{ padding: 4px 10px; border-radius: 16px; font-weight: 600; font-size: 12px; background-color: #22C55E; color: #0F172A; }}
            .action-buttons {{ text-align: center; margin: 25px 0; }}
            .btn {{ display: inline-block; padding: 12px 18px; margin: 6px; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 14px; transition: all 0.3s ease; }}
            .btn-primary {{ background-color: #22C55E; color: #0F172A; }}
            .btn-view {{ background: linear-gradient(135deg, #3B82F6, #1E40AF); color: white; border: none; box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3); }}
            .btn-view:hover {{ background: linear-gradient(135deg, #2563EB, #1D4ED8); transform: translateY(-1px); box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4); }}
            .btn-view-primary {{ background: linear-gradient(135deg, #3B82F6, #1E40AF); color: white; border: none; box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3); padding: 14px 24px; font-size: 15px; }}
            .btn-view-primary:hover {{ background: linear-gradient(135deg, #2563EB, #1D4ED8); transform: translateY(-1px); box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4); }}
            .footer {{ background-color: #09090b; padding: 20px 16px; text-align: center; border-top: 1px solid #3f3f46; }}
            .footer p {{ color: #a1a1aa; margin: 0; line-height: 1.5; }}
            .company-name {{ color: #22C55E; font-weight: 600; }}
            .contact-email {{ color: #22C55E; text-decoration: none; font-weight: 600; }}
            @media only screen and (max-width: 480px) {{
                .header {{ padding: 18px 12px; }}
                .header h1 {{ font-size: 22px; }}
                .content {{ padding: 16px 12px; }}
                .details-card {{ padding: 16px 12px; margin: 16px 0; }}
                .changes-card {{ padding: 16px 12px; margin: 16px 0; }}
                .details-label {{ font-size: 13px; }}
                .details-value {{ font-size: 13px; }}
                .changes-label {{ font-size: 13px; width: 120px; }}
                .changes-value {{ font-size: 13px; }}
                .change-from, .change-to {{ font-size: 12px; }}
                .btn {{ padding: 10px 15px; font-size: 13px; margin: 4px; }}
                .footer {{ padding: 16px 12px; }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>✨ Auto Lab Solutions</h1>
                <p>Service order update notification</p>
            </div>
            
            <div class="content">
                <p class="greeting">Dear {customer_name},</p>
                
                <p class="message">{intro_message} 🔄</p>
                
                <div class="details-card">
                    <h3>🛒 Current Order Details</h3>
                    <div class="details-table">
                        <div class="details-row">
                            <span class="details-label">Order ID:</span>
                            <span class="details-value highlight">{order_data.get('orderId', 'N/A')}</span>
                        </div>
                        {f'<div class="details-section"><h4 style="margin: 15px 0 10px 0; color: #374151;">Services:</h4>{services_table}</div>' if has_services else ""}
                        {f'<div class="details-section"><h4 style="margin: 15px 0 10px 0; color: #374151;">Items:</h4>{items_table}</div>' if has_items else ""}
                        <div class="details-row">
                            <span class="details-label">Vehicle:</span>
                            <span class="details-value">{vehicle_info}</span>
                        </div>
                        <div class="details-row">
                            <span class="details-label">Contact Number:</span>
                            <span class="details-value">{order_data.get('customerData', {}).get('phoneNumber', 'N/A')}</span>
                        </div>
                        {f'<div class="details-row"><span class="details-label">Assigned Mechanic:</span><span class="details-value">{order_data.get("assignedMechanic", "Our team")}</span></div>' if order_data.get('assignedMechanic') and order_data.get('assignedMechanic') != 'Our team' else ""}
                        <div class="details-row">
                            <span class="details-label">Status:</span>
                            <span class="details-value"><span class="status">{format_status_display(order_data.get('status', 'N/A'))}</span></span>
                        </div>
                        <div class="details-row">
                            <span class="details-label">Total Amount:</span>
                            <span class="details-value price">AUD {order_data.get('totalPrice', '0.00')}</span>
                        </div>
                    </div>
                </div>
                
                <div class="changes-card">
                    <h3>{'📊 Status Update' if update_type == 'status' else '📅 Scheduling Update' if update_type == 'scheduling' else '✏️ Changes Made'}</h3>
                    <div class="changes-content">
                        {changes_html}
                    </div>
                </div>
                
                {generate_update_action_buttons(order_data, 'order', FRONTEND_URL)}
                
                <p class="message">
                    If you have any questions about these changes or need assistance, please feel free to contact our support team by replying to this email. 📧 <a href="mailto:{MAIL_FROM_ADDRESS}" class="contact-email">{MAIL_FROM_ADDRESS}</a>
                </p>
                
                <p class="message">
                    Thank you for choosing Auto Lab Solutions for your automotive service needs! 🚗
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
    
    # Format details using table format and get formatted data
    try:
        # Use the existing format function to get properly formatted data including mechanic name
        formatted_appointment_data = format_appointment_data_for_email(appointment_data)
        # Override the original appointment_data with formatted data to ensure mechanic name is available
        appointment_data = {**appointment_data, **formatted_appointment_data}
    except Exception as e:
        print(f"Error formatting appointment data: {str(e)}")
        # Fallback: ensure assignedMechanic exists
        if 'assignedMechanic' not in appointment_data:
            appointment_data = {**appointment_data, 'assignedMechanic': 'Our team'}
    
    services_table = format_services_table(appointment_data.get('services', []))
    formatted_timeslots = format_timeslots_table(appointment_data.get('selectedSlots', []))
    vehicle_info = format_vehicle_info(appointment_data.get('vehicleInfo', {}))
    
    # Check if we have services to display
    has_services = bool(appointment_data.get('services'))
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Inspection Report is Ready</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; }}
            .container {{ max-width: 600px; margin: 0 auto; background-color: #18181B; color: #F3F4F6; }}
            .header {{ background: linear-gradient(135deg, #22C55E 0%, #16A34A 100%); padding: 24px 16px; text-align: center; }}
            .header h1 {{ color: #FFFFFF; font-size: 26px; font-weight: 700; margin-bottom: 8px; white-space: nowrap; }}
            .header p {{ color: #DCFCE7; font-size: 14px; }}
            .content {{ padding: 20px 16px; }}
            .greeting {{ font-size: 16px; color: #F3F4F6; margin-bottom: 15px; }}
            .message {{ color: #a1a1aa; margin-bottom: 20px; line-height: 1.6; }}
            .details-card {{ background-color: #27272A; border: 1px solid #3f3f46; border-radius: 8px; padding: 20px 16px; margin: 20px 0; }}
            .details-card h3 {{ color: #06B6D4; font-size: 18px; font-weight: 600; margin-bottom: 20px; text-align: center; }}
            .report-card {{ background-color: #065F46; border: 1px solid #22C55E; border-radius: 8px; padding: 20px 16px; margin: 20px 0; }}
            .report-card h3 {{ color: #FFFFFF; font-size: 18px; font-weight: 600; margin-bottom: 20px; text-align: center; }}
            .details-table {{ width: 100%; }}
            .details-row {{ padding: 16px 0; border-bottom: 1px solid #3f3f46; }}
            .details-row:last-child {{ border-bottom: none; }}
            .details-label {{ font-weight: 600; color: #F3F4F6; margin-bottom: 6px; display: inline-block; width: 140px; vertical-align: top; }}
            .details-value {{ color: #a1a1aa; display: inline-block; }}
            .details-value.services {{ display: block; margin-top: 6px; }}
            .service-line {{ display: block; margin-bottom: 4px; }}
            .highlight {{ font-weight: 600; }}
            .status {{ padding: 4px 10px; border-radius: 16px; font-weight: 600; font-size: 12px; background-color: #22C55E; color: #0F172A; }}
            .action-buttons {{ text-align: center; margin: 25px 0; }}
            .btn {{ display: inline-block; padding: 12px 18px; margin: 6px; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 14px; transition: all 0.3s ease; }}
            .btn-primary {{ background-color: #22C55E; color: #0F172A; }}
            .btn-secondary {{ background-color: transparent; color: #F3F4F6; border: 2px solid #3f3f46; }}
            .btn-view {{ background: linear-gradient(135deg, #3B82F6, #1E40AF); color: white; border: none; box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3); }}
            .btn-view:hover {{ background: linear-gradient(135deg, #2563EB, #1D4ED8); transform: translateY(-1px); box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4); }}
            .btn-view-primary {{ background: linear-gradient(135deg, #3B82F6, #1E40AF); color: white; border: none; box-shadow: 0 2px 8px rgba(59, 130, 246, 0.3); padding: 14px 24px; font-size: 15px; }}
            .btn-view-primary:hover {{ background: linear-gradient(135deg, #2563EB, #1D4ED8); transform: translateY(-1px); box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4); }}
            .footer {{ background-color: #09090b; padding: 20px 16px; text-align: center; border-top: 1px solid #3f3f46; }}
            .footer p {{ color: #a1a1aa; margin: 0; line-height: 1.5; }}
            .company-name {{ color: #22C55E; font-weight: 600; }}
            .contact-email {{ color: #22C55E; text-decoration: none; font-weight: 600; }}
            @media only screen and (max-width: 480px) {{
                .header {{ padding: 18px 12px; }}
                .header h1 {{ font-size: 22px; }}
                .content {{ padding: 16px 12px; }}
                .details-card {{ padding: 16px 12px; margin: 16px 0; }}
                .report-card {{ padding: 16px 12px; margin: 16px 0; }}
                .details-label {{ font-size: 13px; }}
                .details-value {{ font-size: 13px; }}
                .btn {{ padding: 10px 15px; font-size: 13px; margin: 4px; }}
                .footer {{ padding: 16px 12px; }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>✨ Auto Lab Solutions</h1>
                <p>Your vehicle inspection report is now available</p>
            </div>
            
            <div class="content">
                <p class="greeting">Dear {customer_name},</p>
                
                <p class="message">
                    <strong>Excellent news!</strong> 🎉 We've completed the inspection and analysis of your vehicle. Your comprehensive report is now ready for review.
                </p>
                
                <div class="details-card">
                    <h3>📋 Appointment Details</h3>
                    <div class="details-table">
                        <div class="details-row">
                            <span class="details-label">Appointment ID:</span>
                            <span class="details-value highlight">{appointment_id}</span>
                        </div>
                        {f'<div class="details-section"><h4 style="margin: 15px 0 10px 0; color: #374151;">Services:</h4>{services_table}</div>' if has_services else ""}
                        <div class="details-row">
                            <span class="details-label">Selected Slots:</span>
                            <span class="details-value">
                                {formatted_timeslots}
                            </span>
                        </div>
                        <div class="details-row">
                            <span class="details-label">Vehicle:</span>
                            <span class="details-value">{vehicle_info}</span>
                        </div>
                        <div class="details-row">
                            <span class="details-label">Contact Number:</span>
                            <span class="details-value">{appointment_data.get('customerData', {}).get('phoneNumber', 'N/A')}</span>
                        </div>
                        {f'<div class="details-row"><span class="details-label">Assigned Mechanic:</span><span class="details-value">{appointment_data.get("assignedMechanic", "Our team")}</span></div>' if appointment_data.get('assignedMechanic') and appointment_data.get('assignedMechanic') != 'Our team' else ""}
                        <div class="details-row">
                            <span class="details-label">Status:</span>
                            <span class="details-value"><span class="status">{format_status_display(appointment_data.get('status', 'Completed'))}</span></span>
                        </div>
                        <div class="details-row">
                            <span class="details-label">Total Amount:</span>
                            <span class="details-value price">AUD {appointment_data.get('totalPrice', '0.00')}</span>
                        </div>
                    </div>
                </div>
                
                <div class="report-card">
                    <h3>📄 Report Information</h3>
                    <div class="details-table" style="border-bottom: 1px solid #22C55E;">
                        <div class="details-row" style="border-bottom: 1px solid #22C55E;">
                            <span class="details-label" style="color: #DCFCE7;">Report File:</span>
                            <span class="details-value" style="color: #DCFCE7;">{appointment_data.get('approvedReport', {}).get('fileName', 'Inspection Report')}</span>
                        </div>
                        <div class="details-row" style="border-bottom: 1px solid #22C55E;">
                            <span class="details-label" style="color: #DCFCE7;">Submitted At:</span>
                            <span class="details-value" style="color: #DCFCE7;">{format_timestamp(appointment_data.get('approvedReport', {}).get('approvedAt', int(datetime.now(ZoneInfo('Australia/Perth')).timestamp())))}</span>
                        </div>
                    </div>
                </div>
                
                <div class="action-buttons">
                    {f'<a href="{report_url}" class="btn btn-primary">📄 View Report</a>' if report_url else '<span class="btn btn-primary" style="opacity: 0.5; cursor: not-allowed;">📥 Report Preparing...</span>'}
                    <a href="{FRONTEND_URL}/appointment/{appointment_id}" class="btn btn-view">👁️ View Appointment</a>
                </div>
                
                <p class="message">
                    Your report contains detailed findings, recommendations, and any maintenance suggestions for your vehicle. 🔧 If you have any questions about the report or need clarification on any findings, please feel free to contact our expert team by replying to this email. 📧 <a href="mailto:{MAIL_FROM_ADDRESS}" class="contact-email">{MAIL_FROM_ADDRESS}</a>
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
    
    payment_method = payment_data.get('paymentMethod', 'Stripe')
    amount = payment_data.get('amount', '0.00')
    reference_number = payment_data.get('referenceNumber', 'N/A')
    payment_date = payment_data.get('paymentDate', datetime.now(ZoneInfo('Australia/Perth')).strftime('%d/%m/%Y'))

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
            .header {{ background: linear-gradient(135deg, #22C55E 0%, #16A34A 100%); padding: 24px 16px; text-align: center; }}
            .header h1 {{ color: #FFFFFF; font-size: 26px; font-weight: 700; margin-bottom: 8px; white-space: nowrap; }}
            .header p {{ color: #DCFCE7; font-size: 14px; }}
            .content {{ padding: 20px 16px; }}
            .greeting {{ font-size: 16px; color: #F3F4F6; margin-bottom: 15px; }}
            .message {{ color: #a1a1aa; margin-bottom: 20px; line-height: 1.6; }}
            .payment-card {{ background-color: #065F46; border: 1px solid #22C55E; border-radius: 8px; padding: 20px 16px; margin: 20px 0; }}
            .payment-card h3 {{ color: #FFFFFF; font-size: 18px; font-weight: 600; margin-bottom: 20px; text-align: center; }}
            .details-table {{ width: 100%; }}
            .details-row {{ padding: 16px 0; border-bottom: 1px solid #22C55E; }}
            .details-row:last-child {{ border-bottom: none; }}
            .details-label {{ font-weight: 600; color: #DCFCE7; margin-bottom: 6px; display: inline-block; width: 140px; vertical-align: top; }}
            .details-value {{ color: #DCFCE7; display: inline-block; }}
            .amount {{ color: #F59E0B; font-weight: 700; font-size: 20px; }}
            .status {{ padding: 6px 12px; border-radius: 16px; font-weight: 600; font-size: 12px; background-color: #22C55E; color: #0F172A; }}
            .action-buttons {{ text-align: center; margin: 25px 0; }}
            .btn {{ display: inline-block; padding: 12px 18px; margin: 6px; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 14px; transition: all 0.3s ease; }}
            .btn-primary {{ background-color: #22C55E; color: #0F172A; }}
            .info-box {{ background-color: #3F3F46; border-left: 4px solid #22C55E; padding: 16px; margin: 20px 0; border-radius: 6px; }}
            .info-box p {{ color: #F3F4F6; margin: 0; }}
            .footer {{ background-color: #09090b; padding: 20px 16px; text-align: center; border-top: 1px solid #3f3f46; }}
            .footer p {{ color: #a1a1aa; margin: 0; line-height: 1.5; }}
            .company-name {{ color: #22C55E; font-weight: 600; }}
            .contact-email {{ color: #22C55E; text-decoration: none; font-weight: 600; }}
            @media only screen and (max-width: 480px) {{
                .header {{ padding: 18px 12px; }}
                .header h1 {{ font-size: 22px; }}
                .content {{ padding: 16px 12px; }}
                .payment-card {{ padding: 16px 12px; margin: 16px 0; }}
                .details-label {{ font-size: 13px; }}
                .details-value {{ font-size: 13px; }}
                .btn {{ padding: 10px 15px; font-size: 13px; margin: 4px; }}
                .footer {{ padding: 16px 12px; }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>✨ Auto Lab Solutions</h1>
                <p>Your payment has been successfully processed</p>
            </div>
            
            <div class="content">
                <p class="greeting">Dear {customer_name},</p>
                
                <p class="message">
                    <strong>Thank you for your payment!</strong> 💳 We have successfully received and processed your payment. Your transaction is now complete and your invoice has been generated.
                </p>
                
                <div class="payment-card">
                    <h3>✅ Payment Summary</h3>
                    <div class="details-table">
                        <div class="details-row">
                            <span class="details-label">Amount Paid:</span>
                            <span class="details-value amount">AUD {amount}</span>
                        </div>
                        <div class="details-row">
                            <span class="details-label">Payment Date:</span>
                            <span class="details-value">{payment_date}</span>
                        </div>
                        <div class="details-row">
                            <span class="details-label">Payment Method:</span>
                            <span class="details-value">{payment_method}</span>
                        </div>
                        <div class="details-row">
                            <span class="details-label">Reference Number:</span>
                            <span class="details-value">{reference_number}</span>
                        </div>
                        <div class="details-row">
                            <span class="details-label">Transaction Status:</span>
                            <span class="details-value"><span class="status">✅ Completed</span></span>
                        </div>
                    </div>
                </div>
                
                <div class="action-buttons">
                    <a href="{invoice_url}" class="btn btn-primary">📄 View Invoice</a>
                </div>
                
                <div class="info-box">
                    <p><strong>📋 Important:</strong></p>
                    
                    <p style="margin: 12px 0 0 0;">Please save this invoice for your records. You may need it for warranty claims, tax purposes, or future service references.</p>
                </div>
                
                <p class="message">
                    Your payment confirmation has been recorded in our system. 📊 If you need additional documentation or have any questions about this payment, please feel free to contact our support team by replying to this email. 📧 <a href="mailto:{MAIL_FROM_ADDRESS}" class="contact-email">{MAIL_FROM_ADDRESS}</a>
                </p>
                
                <p class="message">
                    <strong>Thank you for choosing Auto Lab Solutions for your automotive service needs!</strong> 🚗
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

def format_quantity(quantity):
    """Format quantity to display as integer (remove decimal points)"""
    if quantity is None:
        return 1
    try:
        # Convert to float first (in case it's a string), then to int to remove decimal points
        return int(float(quantity))
    except (ValueError, TypeError):
        # If conversion fails, return the original value or default to 1
        return quantity if quantity else 1

def format_timestamp(timestamp):
    """Format timestamp to readable date string"""
    if not timestamp:
        return "N/A"
    
    try:
        if isinstance(timestamp, str):
            timestamp = int(timestamp)
        
        dt = datetime.fromtimestamp(timestamp, ZoneInfo('Australia/Perth'))
        return dt.strftime("%B %d, %Y at %I:%M %p")
    except (ValueError, TypeError):
        return "N/A"
    
def format_timeslots_table(timeslots):
    """Format list of timeslots into a table structure for email"""
    if not timeslots:
        return "No specific time slots selected"
    
    table_html = """
    <table class="timeslots-table" style="width: 100%; margin-top: 12px; border-collapse: collapse;">
        <thead>
            <tr>
                <th style="background-color: #3f3f46; color: #F3F4F6; padding: 10px; text-align: left; font-size: 12px; border: 1px solid #3f3f46;">📅 Date</th>
                <th style="background-color: #3f3f46; color: #F3F4F6; padding: 10px; text-align: left; font-size: 12px; border: 1px solid #3f3f46;">⏰ Time</th>
                <th style="background-color: #3f3f46; color: #F3F4F6; padding: 10px; text-align: left; font-size: 12px; border: 1px solid #3f3f46;">🎯 Priority</th>
            </tr>
        </thead>
        <tbody>
    """
    
    for slot in timeslots:
        if isinstance(slot, dict):
            date = slot.get('date', 'N/A')
            start = slot.get('start', 'N/A')
            end = slot.get('end', 'N/A')
            priority = slot.get('priority', 'N/A')
            time_range = f"{start} - {end}" if start != 'N/A' and end != 'N/A' else 'N/A'
            
            table_html += f"""
            <tr>
                <td style="padding: 10px; border: 1px solid #3f3f46; color: #a1a1aa; font-size: 12px;">{date}</td>
                <td style="padding: 10px; border: 1px solid #3f3f46; color: #a1a1aa; font-size: 12px;">{time_range}</td>
                <td style="padding: 10px; border: 1px solid #3f3f46; color: #a1a1aa; font-size: 12px;">{priority}</td>
            </tr>
            """
        else:
            table_html += f"""
            <tr>
                <td colspan="3" style="padding: 10px; border: 1px solid #3f3f46; color: #a1a1aa; font-size: 12px;">{str(slot)}</td>
            </tr>
            """
    
    table_html += """
        </tbody>
    </table>
    """
    
    return table_html

def format_services_table(services):
    """Format list of services into a table structure for email"""
    if not services:
        return "No services selected"
    
    table_html = """
    <table class="services-table" style="width: 100%; margin-top: 12px; border-collapse: collapse;">
        <thead>
            <tr>
                <th style="background-color: #3f3f46; color: #F3F4F6; padding: 10px; text-align: left; font-size: 12px; border: 1px solid #3f3f46;">🔧 Service</th>
                <th style="background-color: #3f3f46; color: #F3F4F6; padding: 10px; text-align: left; font-size: 12px; border: 1px solid #3f3f46;">📋 Plan</th>
            </tr>
        </thead>
        <tbody>
    """
    
    for service in services:
        if isinstance(service, dict):
            service_name = service.get('serviceName', 'N/A')
            plan_name = service.get('planName', 'N/A')
            
            table_html += f"""
            <tr>
                <td style="padding: 10px; border: 1px solid #3f3f46; color: #a1a1aa; font-size: 12px;">{service_name}</td>
                <td style="padding: 10px; border: 1px solid #3f3f46; color: #a1a1aa; font-size: 12px;">{plan_name}</td>
            </tr>
            """
        else:
            table_html += f"""
            <tr>
                <td colspan="2" style="padding: 10px; border: 1px solid #3f3f46; color: #a1a1aa; font-size: 12px;">{str(service)}</td>
            </tr>
            """
    
    table_html += """
        </tbody>
    </table>
    """
    
    return table_html

def format_order_items_table(items):
    """Format list of order items into a table structure for email"""
    if not items:
        return "No items in this order"
    
    table_html = """
    <table class="items-table" style="width: 100%; margin-top: 12px; border-collapse: collapse;">
        <thead>
            <tr>
                <th style="background-color: #3f3f46; color: #F3F4F6; padding: 10px; text-align: left; font-size: 12px; border: 1px solid #3f3f46;">🔧 Item</th>
                <th style="background-color: #3f3f46; color: #F3F4F6; padding: 10px; text-align: center; font-size: 12px; border: 1px solid #3f3f46;">📦 Qty</th>
                <th style="background-color: #3f3f46; color: #F3F4F6; padding: 10px; text-align: right; font-size: 12px; border: 1px solid #3f3f46;">💵 Unit Price</th>
                <th style="background-color: #3f3f46; color: #F3F4F6; padding: 10px; text-align: right; font-size: 12px; border: 1px solid #3f3f46;">💰 Total Price</th>
            </tr>
        </thead>
        <tbody>
    """
    
    for item in items:
        if isinstance(item, dict):
            category_name = item.get('categoryName', 'N/A')
            item_name = item.get('itemName', 'N/A')
            quantity = item.get('quantity', 1)
            # Format quantity as integer to avoid decimal points
            quantity_display = format_quantity(quantity)
            unitPrice = item.get('unitPrice', '0.00')
            totalPrice = item.get('totalPrice', '0.00')
            
            # Combine category and item name
            combined_name = f"{item_name}"

            table_html += f"""
            <tr>
                <td style="padding: 10px; border: 1px solid #3f3f46; color: #a1a1aa; font-size: 12px;">{combined_name}</td>
                <td style="padding: 10px; border: 1px solid #3f3f46; color: #a1a1aa; font-size: 12px; text-align: center;">{quantity_display}</td>
                <td style="padding: 10px; border: 1px solid #3f3f46; color: #F59E0B; font-size: 12px; text-align: right; font-weight: 600;">AUD {unitPrice}</td>
                <td style="padding: 10px; border: 1px solid #3f3f46; color: #F59E0B; font-size: 12px; text-align: right; font-weight: 600;">AUD {totalPrice}</td>
            </tr>
            """
        else:
            table_html += f"""
            <tr>
                <td colspan="4" style="padding: 10px; border: 1px solid #3f3f46; color: #a1a1aa; font-size: 12px;">{str(item)}</td>
            </tr>
            """
    
    table_html += """
        </tbody>
    </table>
    """
    
    return table_html

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

def format_status_display(status):
    """Format status for display with user-friendly text"""
    if not status:
        return 'N/A'
    
    status_mapping = {
        'PENDING': 'Pending Review',
        'CONFIRMED': 'Confirmed',
        'SCHEDULED': 'Scheduled',
        'IN_PROGRESS': 'In Progress',
        'COMPLETED': 'Completed',
        'CANCELLED': 'Cancelled'
    }
    
    return status_mapping.get(status.upper(), status.replace('_', ' ').title())

def format_field_name(field):
    """Format field names for display"""
    field_mapping = {
        'status': 'Status',
        'order_status': 'Order Status',
        'appointment_status': 'Appointment Status',
        'totalAmount': 'Total Amount',
        'total_amount': 'Total Amount',
        'scheduledDate': 'Scheduled Date',
        'scheduled_date': 'Scheduled Date',
        'timeSlot': 'Time Slot',
        'time_slot': 'Time Slot',
        'vehicleInfo': 'Vehicle Information',
        'vehicle_info': 'Vehicle Information'
    }
    
    return field_mapping.get(field, field.replace('_', ' ').replace('-', ' ').title())

def format_changes_table(changes, update_type='general'):
    """Format changes in a structured table format for email display"""
    if not changes:
        if update_type == 'scheduling':
            return """
            <div class="changes-table">
                <div class="changes-row">
                    <span class="changes-label">Update:</span>
                    <span class="changes-value">Scheduling details have been updated. Please review the current information below.</span>
                </div>
            </div>
            """
        else:
            return """
            <div class="changes-table">
                <div class="changes-row">
                    <span class="changes-label">Update:</span>
                    <span class="changes-value">Details have been updated. Please review the current information below.</span>
                </div>
            </div>
            """
    
    table_html = '<div class="changes-table">'
    
    for field, change in changes.items():
        old_value = change.get('old', 'N/A')
        new_value = change.get('new', 'N/A')
        
        # Handle different update types
        if update_type == 'status' and field.lower() in ['status', 'appointment status', 'order status']:
            table_html += f'''
            <div class="changes-row">
                <span class="changes-label">📊 Status Update:</span>
                <span class="changes-value"><span class="status">{format_status_display(new_value)}</span></span>
            </div>
            '''
        elif update_type == 'scheduling' and field.lower() in ['scheduling update']:
            table_html += f'''
            <div class="changes-row">
                <span class="changes-label">📅 Scheduling:</span>
                <span class="changes-value">{new_value}</span>
            </div>
            '''
        else:
            # Standard field updates with before/after display
            field_display = format_field_name(field)
            
            if old_value != 'N/A' and new_value != 'N/A':
                table_html += f'''
                <div class="changes-row">
                    <span class="changes-label">{field_display}:</span>
                    <span class="changes-value">
                        <div class="change-transition">
                            <div class="change-from">From: <span class="old-value">{old_value}</span></div>
                            <div class="change-to">To: <span class="new-value">{new_value}</span></div>
                        </div>
                    </span>
                </div>
                '''
            else:
                table_html += f'''
                <div class="changes-row">
                    <span class="changes-label">{field_display}:</span>
                    <span class="changes-value">{new_value}</span>
                </div>
                '''
    
    table_html += '</div>'
    return table_html

def generate_update_action_buttons(data, record_type, frontend_url):
    """Generate action buttons for update emails based on payment status and record type"""
    record_id = data.get('appointmentId' if record_type == 'appointment' else 'orderId', 'N/A')
    payment_status = data.get('paymentStatus', '').lower()
    status = data.get('status', '').lower()
    
    # Determine if payment is needed based on payment status and overall status
    payment_completed = payment_status in ['paid', 'completed', 'successful', 'confirmed']
    work_completed = status in ['completed', 'finished', 'delivered', 'closed']
    
    # Payment is needed if:
    # 1. Payment status indicates it's not completed
    # 2. Overall status suggests work is still pending/ongoing
    # 3. No clear payment status is provided (default to needing payment)
    payment_needed = (
        not payment_completed and 
        not work_completed and
        record_id != 'N/A'
    )
    
    # Determine appropriate view button text based on record type
    view_button_text = "👁️ View Appointment" if record_type == 'appointment' else "👁️ View Order"
    
    if payment_needed:
        # Show ONLY payment button if payment is needed
        return f'''
        <div class="action-buttons">
            <a href="{frontend_url}/{record_type}/{record_id}" class="btn btn-primary">💳 Complete Payment</a>
        </div>
        '''
    else:
        # Show ONLY view button if payment is complete or not needed
        return f'''
        <div class="action-buttons">
            <a href="{frontend_url}/{record_type}/{record_id}" class="btn btn-view-primary">{view_button_text}</a>
        </div>
        '''

def format_services(services):
    """Format list of services into a readable string with service name and plan name on separate lines"""
    if not services:
        return "N/A"
    
    formatted = []
    for service in services:
        if isinstance(service, dict):
            service_name = service.get('serviceName', 'N/A')
            plan_name = service.get('planName', 'N/A')
            formatted.append(f'<span class="service-line">Service name: {service_name}</span><span class="service-line">Plan name: {plan_name}</span>')
        else:
            formatted.append(str(service))
    
    return '<br>'.join(formatted) if formatted else "N/A"

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
            # Format quantity as integer to avoid decimal points
            quantity_display = format_quantity(quantity)
            unitPrice = item.get('unitPrice', '0.00')
            totalPrice = item.get('totalPrice', '0.00')

            # Combine category and item name
            combined_name = f"{itemName}"
            formatted.append(f"{combined_name} (Quantity: {quantity_display}, Unit Price: AUD {unitPrice}, Total: AUD {totalPrice})")
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
            # Use SES v2 client for suppression checking
            sesv2_client = boto3.client('sesv2')
            sesv2_client.get_suppressed_destination(EmailAddress=email_address)
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
    print("Updated Record: ", updated_record)
    print("Update Data: ", update_data)

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
        'unitPrice': 'Unit Price',
        'status': 'Status',
        'scheduledTimeSlot': 'Scheduled Time',
        'scheduledDate': 'Scheduled Date',
        'assignedMechanic': 'Assigned Mechanic',
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
        'totalPrice': 'Total Amount',
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
        elif field == 'serviceId' and record_type == 'appointment':
            # Use resolved service name if available, otherwise show ID
            service_name = updated_record.get('serviceName')
            if service_name:
                formatted_value = service_name
            else:
                formatted_value = f"Service ID: {value}"
        elif field == 'planId' and record_type == 'appointment':
            # Use resolved plan name if available, otherwise show ID
            plan_name = updated_record.get('planName')
            if plan_name:
                formatted_value = plan_name
            else:
                formatted_value = f"Plan ID: {value}"
        elif field == 'items' and record_type == 'order':
            if isinstance(value, list):
                formatted_value = ", ".join(
                    f"{item.get('categoryName', 'Unknown')} - {item.get('itemName', 'Unknown')} (Quantity: {format_quantity(item.get('quantity', 1))}, Unit Price: AUD {item.get('unitPrice', 0):.2f}, Total: AUD {item.get('totalPrice', 0):.2f})" for item in value
                )
            else:
                formatted_value = "Invalid items format"
        elif field in ['unitPrice', 'totalPrice'] and isinstance(value, (int, float)):
            formatted_value = f"AUD {value:.2f}"
        else:
            formatted_value = str(value) if value is not None else "Not specified"
        
        changes[human_readable_field] = {
            'new': formatted_value
        }
    
    return changes


def format_appointment_data_for_email(appointment_data):
    """Format appointment data for email notifications"""
    # Debug: Print the keys in appointment_data to understand structure
    print(f"DEBUG: Appointment data keys: {list(appointment_data.keys())}")
    if 'assignedMechanic' in appointment_data:
        print(f"DEBUG: assignedMechanic found: {appointment_data.get('assignedMechanic')}")
    
    # Get service and plan names (should be provided by calling function)
    service_name = appointment_data.get('serviceName', 'Service')
    plan_name = appointment_data.get('planName', 'Plan')
    
    # Format vehicle info (should be provided by calling function)
    if 'vehicleInfo' in appointment_data and isinstance(appointment_data['vehicleInfo'], dict):
        vehicle_info = appointment_data['vehicleInfo']
    else:
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
    assigned_mechanic = appointment_data.get('assignedMechanic', 'Our team')
    print(f"DEBUG: Using assignedMechanic: {assigned_mechanic}")
    
    # Format customer data based on isBuyer flag (only if not already formatted)
    if 'customerData' in appointment_data and isinstance(appointment_data['customerData'], dict):
        # Use existing formatted customer data
        customer_data = appointment_data['customerData']
    else:
        # Format customer data from raw fields
        is_buyer = appointment_data.get('isBuyer', True)
        if is_buyer:
            customer_data = {
                'phoneNumber': appointment_data.get('buyerPhone', 'N/A')
            }
        else:
            customer_data = {
                'phoneNumber': appointment_data.get('sellerPhone', 'N/A')
            }
    
    # Handle services (check if already formatted)
    services = appointment_data.get('services', [])
    if not isinstance(services, list):
        services = []
    
    # Handle selected slots for display
    selected_slots = appointment_data.get('selectedSlots', [])
    
    # Calculate total price - try multiple possible fields and ensure it's formatted correctly
    total_price = None
    if appointment_data.get('totalPrice'):
        total_price = appointment_data.get('totalPrice')
    elif appointment_data.get('price'):
        total_price = appointment_data.get('price')
    else:
        # If no total price found, try to calculate from services
        services = appointment_data.get('services', [])
        if services:
            calculated_total = 0
            for service in services:
                service_total = 0
                if 'totalPrice' in service:
                    service_total = float(service.get('totalPrice', 0))
                elif 'price' in service:
                    service_total = float(service.get('price', 0))
                calculated_total += service_total
            
            if calculated_total > 0:
                total_price = calculated_total
    
    # Format the price properly
    if total_price is not None:
        try:
            # Ensure it's a number and format it
            if isinstance(total_price, str):
                # Remove any currency symbols and convert to float
                total_price = float(total_price.replace('AUD', '').replace('$', '').strip())
            total_price_formatted = f"{float(total_price):.2f}"
        except (ValueError, TypeError):
            total_price_formatted = "0.00"
    else:
        total_price_formatted = "0.00"
    
    return {
        'appointmentId': appointment_data.get('appointmentId'),
        'serviceName': service_name,
        'planName': plan_name,
        'services': services,
        'vehicleInfo': vehicle_info,
        'totalPrice': total_price_formatted,  # Use consistent key name
        'price': total_price_formatted,  # Keep for backward compatibility
        'status': appointment_data.get('status', 'Processing'),
        'customerData': customer_data,
        'timeSlot': time_slot,
        'assignedMechanic': assigned_mechanic,
        'vehicleLocation': appointment_data.get('carLocation', 'N/A'),
        'notes': appointment_data.get('notes', ''),
        'postNotes': appointment_data.get('postNotes', ''),
        'selectedSlots': selected_slots
    }


def format_order_data_for_email(order_data):
    """Format order data for email notifications"""
    # Debug: Print the keys in order_data to understand structure
    print(f"DEBUG: Order data keys: {list(order_data.keys())}")
    if 'assignedMechanic' in order_data:
        print(f"DEBUG: assignedMechanic found: {order_data.get('assignedMechanic')}")
    
    # Format items (should be provided by calling function with proper names)
    items = order_data.get('items', [])
    
    # Format vehicle info (should be provided by calling function)
    if 'vehicleInfo' in order_data and isinstance(order_data['vehicleInfo'], dict):
        vehicle_info = order_data['vehicleInfo']
    else:
        vehicle_info = {
            'make': order_data.get('carMake', 'N/A'),
            'model': order_data.get('carModel', 'N/A'),
            'year': order_data.get('carYear', 'N/A')
        }
    
    # Get mechanic name if assigned
    assigned_mechanic = order_data.get('assignedMechanic', 'Our team')
    print(f"DEBUG: Using assignedMechanic: {assigned_mechanic}")
    
    # Handle services (orders can have services too)
    services = order_data.get('services', [])
    if not isinstance(services, list):
        services = []
    
    # Format customer data
    if 'customerData' in order_data and isinstance(order_data['customerData'], dict):
        # Use existing formatted customer data
        customer_data = order_data['customerData']
    else:
        # Format customer data from raw fields
        customer_data = {
            'phoneNumber': order_data.get('customerPhone', 'N/A')
        }
    
    # Calculate total price - try multiple possible fields and ensure it's formatted correctly
    total_price = None
    if order_data.get('totalPrice'):
        total_price = order_data.get('totalPrice')
    elif order_data.get('totalAmount'):
        total_price = order_data.get('totalAmount')
    elif order_data.get('price'):
        total_price = order_data.get('price')
    else:
        # If no total price found, try to calculate from items
        items = order_data.get('items', [])
        if items:
            calculated_total = 0
            for item in items:
                item_total = 0
                if 'totalPrice' in item:
                    item_total = float(item.get('totalPrice', 0))
                elif 'unitPrice' in item and 'quantity' in item:
                    unit_price = float(item.get('unitPrice', 0))
                    quantity = float(item.get('quantity', 1))
                    item_total = unit_price * quantity
                calculated_total += item_total
            
            if calculated_total > 0:
                total_price = calculated_total
    
    # Format the price properly
    if total_price is not None:
        try:
            # Ensure it's a number and format it
            if isinstance(total_price, str):
                # Remove any currency symbols and convert to float
                total_price = float(total_price.replace('AUD', '').replace('$', '').strip())
            total_price_formatted = f"{float(total_price):.2f}"
        except (ValueError, TypeError):
            total_price_formatted = "0.00"
    else:
        total_price_formatted = "0.00"
    
    return {
        'orderId': order_data.get('orderId'),
        'items': items,
        'services': services,
        'vehicleInfo': vehicle_info,
        'totalPrice': total_price_formatted,  # Use consistent formatting
        'status': order_data.get('status', 'Processing'),
        'customerData': customer_data,
        'scheduledDate': order_data.get('scheduledDate'),
        'assignedMechanic': assigned_mechanic,
        'deliveryLocation': order_data.get('deliveryLocation', ''),
        'notes': order_data.get('notes', ''),
        'postNotes': order_data.get('postNotes', '')
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

    

def create_professional_admin_email(subject, message_content, staff_name=None, customer_name=None):
    """
    Create a friendly and approachable HTML email for admin messages
    
    Args:
        subject (str): Email subject
        message_content (str): The admin's message content (plain text)
        staff_name (str): Name of the staff member sending the email
        customer_name (str): Name of the customer (if known)
    
    Returns:
        str: Friendly HTML email template
    """
    # Format the message content for HTML (preserve line breaks)
    formatted_message = message_content.replace('\n', '<br>')
    
    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{subject}</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; }}
            .container {{ max-width: 600px; margin: 0 auto; background-color: #18181B; color: #F3F4F6; }}
            .header {{ background: linear-gradient(135deg, #27272A 0%, #3F3F46 100%); padding: 24px 16px; text-align: center; }}
            .header h1 {{ color: #22C55E; font-size: 26px; font-weight: 700; margin-bottom: 8px; white-space: nowrap; }}
            .header p {{ color: #a1a1aa; font-size: 14px; }}
            .content {{ padding: 20px 16px; }}
            .greeting {{ font-size: 16px; color: #F3F4F6; margin-bottom: 15px; }}
            .message {{ color: #a1a1aa; margin-bottom: 20px; line-height: 1.8; font-size: 15px; }}
            .message-content {{ background-color: #27272A; border-left: 4px solid #22C55E; padding: 14px; margin: 20px 0; border-radius: 6px; }}
            .message-content p {{ color: #F3F4F6; margin: 0; line-height: 1.8; font-size: 15px; }}
            .info-box {{ background-color: #3F3F46; border-left: 4px solid #06B6D4; padding: 16px; margin: 20px 0; border-radius: 6px; }}
            .info-box p {{ color: #F3F4F6; margin: 0; }}
            .action-buttons {{ text-align: center; margin: 25px 0; }}
            .btn {{ display: inline-block; padding: 12px 18px; margin: 6px; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 14px; transition: all 0.3s ease; }}
            .btn-primary {{ background-color: #22C55E; color: #0F172A; }}
            .btn-secondary {{ background-color: transparent; color: #F3F4F6; border: 2px solid #3f3f46; }}
            .footer {{ background-color: #09090b; padding: 20px 16px; text-align: center; border-top: 1px solid #3f3f46; }}
            .footer p {{ color: #a1a1aa; margin: 0; line-height: 1.5; }}
            .company-name {{ color: #22C55E; font-weight: 600; }}
            .contact-email {{ color: #22C55E; text-decoration: none; font-weight: 600; }}
            .staff-signature {{ color: #F3F4F6; font-weight: 600; margin-bottom: 5px; }}
            @media only screen and (max-width: 480px) {{
                .header {{ padding: 18px 12px; }}
                .header h1 {{ font-size: 22px; }}
                .content {{ padding: 16px 12px; }}
                .message-content {{ padding: 12px 10px; margin: 16px 0; }}
                .btn {{ padding: 10px 15px; font-size: 13px; margin: 4px; }}
                .footer {{ padding: 16px 12px; }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>✨ Auto Lab Solutions</h1>
                <p>Your trusted car care partner</p>
            </div>
            
            <div class="content">
                
                <div class="message-content">
                    <p>{formatted_message}</p>
                </div>
                
                <div class="info-box">
                    <p><strong>� Got questions or want to chat?</strong></p>
                    <p>Just hit reply to this email and we'll get back to you quickly. We love hearing from our customers!</p>
                </div>
                
                <div class="action-buttons">
                    <a href="{FRONTEND_URL}" class="btn btn-primary">🌐 Check Our Portal</a>
                    <a href="mailto:{MAIL_FROM_ADDRESS}" class="btn btn-secondary">� Drop Us a Line</a>
                </div>
                
                <p class="message">
                    Thanks for choosing us for your car care needs. We really appreciate your trust in Auto Lab Solutions! �
                </p>
            </div>
            
            <div class="footer">
                <p class="staff-signature">Cheers,</p>
                <p><span class="company-name">Auto Lab Solutions</span><br>
            </div>
        </div>
    </body>
    </html>
    """
    
    return html_body


def create_comprehensive_admin_email_text(subject, message_content, staff_name=None, customer_name=None):
    """
    Create a comprehensive plain text version that includes all content from the HTML template
    
    Args:
        subject (str): Email subject
        message_content (str): The admin's message content (plain text)
        staff_name (str): Name of the staff member sending the email
        customer_name (str): Name of the customer (if known)
    
    Returns:
        str: Comprehensive plain text email content
    """
    
    # Create comprehensive text version with all content
    text_body = f"""

{message_content}

---

Got questions or want to chat?
Just reply to this email and we'll get back to you quickly. We love hearing from our customers!

You can also:
• Check our portal: {FRONTEND_URL if FRONTEND_URL else '[Portal URL]'}
• Drop us a line: {MAIL_FROM_ADDRESS if MAIL_FROM_ADDRESS else '[Support Email]'}

Thanks for choosing us for your car care needs. We really appreciate your trust in Auto Lab Solutions! 😊

Cheers,
Auto Lab Solutions
    """.strip()
    
    return text_body


def send_payment_cancellation_email(customer_email, customer_name, payment_data):
    """Send email when payment is cancelled/reverted"""
    subject = EmailTemplate.PAYMENT_CANCELLED
    
    payment_method = payment_data.get('paymentMethod', 'Payment')
    amount = payment_data.get('amount', '0.00')
    reference_number = payment_data.get('referenceNumber', 'N/A')
    cancellation_date = payment_data.get('cancellationDate', datetime.now(ZoneInfo('Australia/Perth')).strftime('%d/%m/%Y'))
    cancellation_reason = payment_data.get('cancellationReason', 'Payment was cancelled by staff')
    cancelled_invoice_id = payment_data.get('cancelledInvoiceId', None)

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Payment Cancelled</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; }}
            .container {{ max-width: 600px; margin: 0 auto; background-color: #18181B; color: #F3F4F6; }}
            .header {{ background: linear-gradient(135deg, #EF4444 0%, #DC2626 100%); padding: 24px 16px; text-align: center; }}
            .header h1 {{ color: #FFFFFF; font-size: 26px; font-weight: 700; margin-bottom: 8px; white-space: nowrap; }}
            .header p {{ color: #FEE2E2; font-size: 14px; }}
            .content {{ padding: 20px 16px; }}
            .greeting {{ font-size: 16px; color: #F3F4F6; margin-bottom: 15px; }}
            .message {{ color: #a1a1aa; margin-bottom: 20px; line-height: 1.6; }}
            .payment-card {{ background-color: #7F1D1D; border: 1px solid #EF4444; border-radius: 8px; padding: 20px 16px; margin: 20px 0; }}
            .payment-card h3 {{ color: #FFFFFF; font-size: 18px; font-weight: 600; margin-bottom: 20px; text-align: center; }}
            .details-table {{ width: 100%; }}
            .details-row {{ padding: 16px 0; border-bottom: 1px solid #EF4444; }}
            .details-row:last-child {{ border-bottom: none; }}
            .details-label {{ font-weight: 600; color: #FEE2E2; margin-bottom: 6px; display: inline-block; width: 140px; vertical-align: top; }}
            .details-value {{ color: #FEE2E2; display: inline-block; }}
            .amount {{ color: #F59E0B; font-weight: 700; font-size: 20px; }}
            .status {{ padding: 6px 12px; border-radius: 16px; font-weight: 600; font-size: 12px; background-color: #EF4444; color: #FFFFFF; }}
            .action-buttons {{ text-align: center; margin: 25px 0; }}
            .btn {{ display: inline-block; padding: 12px 18px; margin: 6px; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 14px; transition: all 0.3s ease; }}
            .btn-primary {{ background-color: #22C55E; color: #0F172A; }}
            .info-box {{ background-color: #3F3F46; border-left: 4px solid #EF4444; padding: 16px; margin: 20px 0; border-radius: 6px; }}
            .info-box p {{ color: #F3F4F6; margin: 0; }}
            .footer {{ background-color: #09090b; padding: 20px 16px; text-align: center; border-top: 1px solid #3f3f46; }}
            .footer p {{ color: #a1a1aa; margin: 0; line-height: 1.5; }}
            .company-name {{ color: #22C55E; font-weight: 600; }}
            .contact-email {{ color: #22C55E; text-decoration: none; font-weight: 600; }}
            @media only screen and (max-width: 480px) {{
                .header {{ padding: 18px 12px; }}
                .header h1 {{ font-size: 22px; }}
                .content {{ padding: 16px 12px; }}
                .payment-card {{ padding: 16px 12px; margin: 16px 0; }}
                .details-label {{ font-size: 13px; }}
                .details-value {{ font-size: 13px; }}
                .btn {{ padding: 10px 15px; font-size: 13px; margin: 4px; }}
                .footer {{ padding: 16px 12px; }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>✨ Auto Lab Solutions</h1>
                <p>Payment cancellation notification</p>
            </div>
            
            <div class="content">
                <p class="greeting">Dear {customer_name},</p>
                
                <p class="message">
                    <strong>Your payment has been cancelled.</strong> ❌ We are writing to inform you that your payment has been cancelled and any associated invoices have been voided.
                </p>
                
                <div class="payment-card">
                    <h3>❌ Cancelled Payment Details</h3>
                    <div class="details-table">
                        <div class="details-row">
                            <span class="details-label">Cancelled Amount:</span>
                            <span class="details-value amount">AUD {amount}</span>
                        </div>
                        <div class="details-row">
                            <span class="details-label">Cancellation Date:</span>
                            <span class="details-value">{cancellation_date}</span>
                        </div>
                        <div class="details-row">
                            <span class="details-label">Payment Method:</span>
                            <span class="details-value">{payment_method}</span>
                        </div>
                        <div class="details-row">
                            <span class="details-label">Reference Number:</span>
                            <span class="details-value">{reference_number}</span>
                        </div>
                        <div class="details-row">
                            <span class="details-label">Status:</span>
                            <span class="details-value"><span class="status">❌ Cancelled</span></span>
                        </div>
                        {f'<div class="details-row"><span class="details-label">Cancelled Invoice:</span><span class="details-value highlight">{cancelled_invoice_id}</span></div>' if cancelled_invoice_id else ""}
                    </div>
                </div>
                
                <div class="info-box">
                    <p><strong>ℹ️ What this means:</strong></p>
                    <p>• Your payment has been cancelled by our staff</p>
                    {f'<p>• Invoice {cancelled_invoice_id} has been cancelled and is no longer valid</p>' if cancelled_invoice_id else '<p>• Any associated invoices have been cancelled and are no longer valid</p>'}
                    <p>• No further charges will be applied to this transaction</p>
                </div>
                
                <div class="info-box">
                    <p><strong>❓ Questions or Concerns?</strong></p>
                    <p>If you have any questions about this cancellation or need assistance, please don't hesitate to contact us. We're here to help!</p>
                </div>
                
                <div class="action-buttons">
                    <a href="{FRONTEND_URL if FRONTEND_URL else '#'}" class="btn btn-primary">🌐 Visit Portal</a>
                </div>
            </div>
            
            <div class="footer">
                <p>Thanks for your understanding.</p>
                <br>
                <p><span class="company-name">Auto Lab Solutions</span></p>
                <p>Questions? Contact us at <a href="mailto:{MAIL_FROM_ADDRESS if MAIL_FROM_ADDRESS else 'support@autolabsolutions.com.au'}" class="contact-email">{MAIL_FROM_ADDRESS if MAIL_FROM_ADDRESS else 'support@autolabsolutions.com.au'}</a></p>
            </div>
        </div>
    </body>
    </html>
    """

    # Create plain text version
    text_body = f"""
    Payment Cancelled - Auto Lab Solutions

    Dear {customer_name},

    Your payment has been cancelled.

    We are writing to inform you that your payment has been cancelled and any associated invoices have been voided.

    Cancelled Payment Details:
    • Cancelled Amount: AUD {amount}
    • Cancellation Date: {cancellation_date}
    • Payment Method: {payment_method}
    • Reference Number: {reference_number}
    • Status: Cancelled
    {f'• Cancelled Invoice: {cancelled_invoice_id}' if cancelled_invoice_id else ''}

    What this means:
    • Your payment has been cancelled by our staff
    {f'• Invoice {cancelled_invoice_id} has been cancelled and is no longer valid' if cancelled_invoice_id else '• Any associated invoices have been cancelled and are no longer valid'}
    • No further charges will be applied to this transaction

    Questions or Concerns?
    If you have any questions about this cancellation or need assistance, please don't hesitate to contact us. We're here to help!

    Thanks for your understanding.

    Auto Lab Solutions
    Questions? Contact us at {MAIL_FROM_ADDRESS if MAIL_FROM_ADDRESS else 'support@autolabsolutions.com.au'}
    """

    try:
        return send_email(customer_email, subject, html_body, text_body, EmailTemplate.TYPE_PAYMENT_CANCELLED)
    except Exception as e:
        print(f"Error sending payment cancellation email: {str(e)}")
        return False


def send_payment_reactivation_email(customer_email, customer_name, payment_data):
    """Send email when payment/invoice is reactivated"""
    subject = EmailTemplate.PAYMENT_REACTIVATED
    
    payment_method = payment_data.get('paymentMethod', 'Payment')
    amount = payment_data.get('amount', '0.00')
    reference_number = payment_data.get('referenceNumber', 'N/A')
    reactivation_date = payment_data.get('reactivationDate', datetime.now(ZoneInfo('Australia/Perth')).strftime('%d/%m/%Y'))
    reactivation_reason = payment_data.get('reactivationReason', 'Payment was reactivated by staff')
    reactivated_invoice_id = payment_data.get('reactivatedInvoiceId', None)

    html_body = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Payment Reactivated</title>
        <style>
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif; line-height: 1.6; }}
            .container {{ max-width: 600px; margin: 0 auto; background-color: #18181B; color: #F3F4F6; }}
            .header {{ background: linear-gradient(135deg, #22C55E 0%, #16A34A 100%); padding: 24px 16px; text-align: center; }}
            .header h1 {{ color: #FFFFFF; font-size: 26px; font-weight: 700; margin-bottom: 8px; white-space: nowrap; }}
            .header p {{ color: #DCFCE7; font-size: 14px; }}
            .content {{ padding: 20px 16px; }}
            .greeting {{ font-size: 16px; color: #F3F4F6; margin-bottom: 15px; }}
            .message {{ color: #a1a1aa; margin-bottom: 20px; line-height: 1.6; }}
            .payment-card {{ background-color: #14532D; border: 1px solid #22C55E; border-radius: 8px; padding: 20px 16px; margin: 20px 0; }}
            .payment-card h3 {{ color: #FFFFFF; font-size: 18px; font-weight: 600; margin-bottom: 20px; text-align: center; }}
            .details-table {{ width: 100%; }}
            .details-row {{ padding: 16px 0; border-bottom: 1px solid #22C55E; }}
            .details-row:last-child {{ border-bottom: none; }}
            .details-label {{ font-weight: 600; color: #DCFCE7; margin-bottom: 6px; display: inline-block; width: 140px; vertical-align: top; }}
            .details-value {{ color: #DCFCE7; display: inline-block; }}
            .amount {{ color: #F59E0B; font-weight: 700; font-size: 20px; }}
            .status {{ padding: 6px 12px; border-radius: 16px; font-weight: 600; font-size: 12px; background-color: #22C55E; color: #0F172A; }}
            .action-buttons {{ text-align: center; margin: 25px 0; }}
            .btn {{ display: inline-block; padding: 12px 18px; margin: 6px; text-decoration: none; border-radius: 6px; font-weight: 600; font-size: 14px; transition: all 0.3s ease; }}
            .btn-primary {{ background-color: #22C55E; color: #0F172A; }}
            .info-box {{ background-color: #3F3F46; border-left: 4px solid #22C55E; padding: 16px; margin: 20px 0; border-radius: 6px; }}
            .info-box p {{ color: #F3F4F6; margin: 0; }}
            .footer {{ background-color: #09090b; padding: 20px 16px; text-align: center; border-top: 1px solid #3f3f46; }}
            .footer p {{ color: #a1a1aa; margin: 0; line-height: 1.5; }}
            .company-name {{ color: #22C55E; font-weight: 600; }}
            .contact-email {{ color: #22C55E; text-decoration: none; font-weight: 600; }}
            @media only screen and (max-width: 480px) {{
                .header {{ padding: 18px 12px; }}
                .header h1 {{ font-size: 22px; }}
                .content {{ padding: 16px 12px; }}
                .payment-card {{ padding: 16px 12px; margin: 16px 0; }}
                .details-label {{ font-size: 13px; }}
                .details-value {{ font-size: 13px; }}
                .btn {{ padding: 10px 15px; font-size: 13px; margin: 4px; }}
                .footer {{ padding: 16px 12px; }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>✨ Auto Lab Solutions</h1>
                <p>Payment reactivation notification</p>
            </div>
            
            <div class="content">
                <p class="greeting">Dear {customer_name},</p>
                
                <p class="message">
                    <strong>Great news! Your payment has been reactivated.</strong> ✅ We are pleased to inform you that your payment has been successfully reactivated and your invoice has been restored.
                </p>
                
                <div class="payment-card">
                    <h3>✅ Reactivated Payment Details</h3>
                    <div class="details-table">
                        <div class="details-row">
                            <span class="details-label">Payment Amount:</span>
                            <span class="details-value amount">AUD {amount}</span>
                        </div>
                        <div class="details-row">
                            <span class="details-label">Reactivation Date:</span>
                            <span class="details-value">{reactivation_date}</span>
                        </div>
                        <div class="details-row">
                            <span class="details-label">Payment Method:</span>
                            <span class="details-value">{payment_method}</span>
                        </div>
                        <div class="details-row">
                            <span class="details-label">Reference Number:</span>
                            <span class="details-value">{reference_number}</span>
                        </div>
                        <div class="details-row">
                            <span class="details-label">Status:</span>
                            <span class="details-value"><span class="status">ACTIVE</span></span>
                        </div>"""

    # Add invoice ID section if provided
    if reactivated_invoice_id:
        html_body += f"""
                        <div class="details-row">
                            <span class="details-label">Invoice ID:</span>
                            <span class="details-value">{reactivated_invoice_id}</span>
                        </div>"""

    html_body += f"""
                    </div>
                </div>
                
                <div class="info-box">
                    <p><strong>What this means:</strong></p>
                    <p>• Your payment is now active and valid</p>
                    <p>• Your invoice has been restored and is accessible</p>
                    <p>• All associated services are now confirmed</p>
                    <p>• No further action is required from you</p>
                </div>
                
                <p class="message">
                    <strong>Reason for reactivation:</strong> {reactivation_reason}
                </p>
                
                <div class="action-buttons">
                    <a href="{FRONTEND_URL}" class="btn btn-primary">Visit Dashboard</a>
                </div>
                
                <p class="message">
                    If you have any questions about this reactivation, please don't hesitate to contact our support team.
                </p>
                
                <p class="message">
                    Thank you for choosing Auto Lab Solutions for your automotive needs!
                </p>
            </div>
            
            <div class="footer">
                <p class="company-name">Auto Lab Solutions</p>
                <p>Questions? Contact us at <a href="mailto:{MAIL_FROM_ADDRESS if MAIL_FROM_ADDRESS else 'support@autolabsolutions.com.au'}" class="contact-email">{MAIL_FROM_ADDRESS if MAIL_FROM_ADDRESS else 'support@autolabsolutions.com.au'}</a></p>
            </div>
        </div>
    </body>
    </html>
    """

    text_body = f"""
    Auto Lab Solutions
    Payment Reactivated

    Dear {customer_name},

    Great news! Your payment has been reactivated.

    We are pleased to inform you that your payment has been successfully reactivated and your invoice has been restored.

    Reactivated Payment Details:
    - Payment Amount: AUD {amount}
    - Reactivation Date: {reactivation_date}
    - Payment Method: {payment_method}
    - Reference Number: {reference_number}
    - Status: ACTIVE"""

    if reactivated_invoice_id:
        text_body += f"\n    - Invoice ID: {reactivated_invoice_id}"

    text_body += f"""

    What this means:
    • Your payment is now active and valid
    • Your invoice has been restored and is accessible
    • All associated services are now confirmed
    • No further action is required from you

    Reason for reactivation: {reactivation_reason}

    If you have any questions about this reactivation, please don't hesitate to contact our support team.

    Thank you for choosing Auto Lab Solutions for your automotive needs!

    Auto Lab Solutions
    Questions? Contact us at {MAIL_FROM_ADDRESS if MAIL_FROM_ADDRESS else 'support@autolabsolutions.com.au'}
    """

    try:
        return send_email(customer_email, subject, html_body, text_body, EmailTemplate.TYPE_PAYMENT_REACTIVATED)
    except Exception as e:
        print(f"Error sending payment reactivation email: {str(e)}")
        return False
