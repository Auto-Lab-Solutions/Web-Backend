import json, boto3, os, base64
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from botocore.exceptions import ClientError

import request_utils as req
import response_utils as resp
import db_utils as db
import email_utils as email_util

# AWS clients
ses_client = boto3.client('ses')
s3_client = boto3.client('s3')
dynamodb = boto3.client('dynamodb')

# Environment variables
MAIL_FROM_ADDRESS = os.environ.get('NO_REPLY_EMAIL')
EMAIL_METADATA_TABLE = os.environ.get('EMAIL_METADATA_TABLE')

# ------------------  Email Sending Functions ------------------
def lambda_handler(event, context):
    """
    API Gateway handler for sending emails and managing templates
    Supports both simple text/html emails and emails with attachments
    """
    try:
        print(f"Email API request: {json.dumps(event)}")
        
        # Validate staff authentication
        staff_email = req.get_staff_user_email(event)
        staff_user_record = db.get_staff_record(staff_email)
        if not staff_user_record:
            return resp.error_response(f"No staff record found for email: {staff_email}.")
        
        # # Check if this is a templates request
        # path = event.get('path', '')
        # if '/templates' in path or event.get('pathParameters', {}).get('proxy') == 'templates':
        #     return get_email_templates_handler(event, context)
        
        # Otherwise handle as send email request
        
        # Validate required fields
        required_fields = ['to', 'subject']
        for field in required_fields:
            # if not body.get(field):
            if not req.get_body_param(event, field):
                return resp.error_response(400, f"Field '{field}' is required")
        
        # Extract email parameters
        to_emails = req.get_body_param(event, 'to')
        cc_emails = req.get_body_param(event, 'cc', [])
        bcc_emails = req.get_body_param(event, 'bcc', [])
        subject = req.get_body_param(event, 'subject')
        text_content = req.get_body_param(event, 'text', '')
        html_content = req.get_body_param(event, 'html', '')
        attachments = req.get_body_param(event, 'attachments', [])
        reply_to = req.get_body_param(event, 'reply_to', MAIL_FROM_ADDRESS)

        # Validate recipients
        if isinstance(to_emails, str):
            to_emails = [to_emails]
        
        if not to_emails:
            return resp.error_response(400, "At least one recipient is required")
        
        # Validate email addresses
        for email_addr in to_emails + cc_emails + bcc_emails:
            if not is_valid_email(email_addr):
                return resp.error_response(400, f"Invalid email address: {email_addr}")
        
        # If no content provided, return error
        if not text_content and not html_content:
            return resp.error_response(400, "Either text or html content is required")
        
        # Send email
        email_result = send_email_with_attachments(
            to_emails=to_emails,
            cc_emails=cc_emails,
            bcc_emails=bcc_emails,
            subject=subject,
            text_content=text_content,
            html_content=html_content,
            attachments=attachments,
            reply_to=reply_to
        )
        
        if email_result['success']:
            # Store sent email metadata
            try:
                store_sent_email_metadata(email_result)
            except Exception as e:
                print(f"Warning: Could not store sent email metadata: {str(e)}")
            
            return resp.success_response({
                'message': 'Email sent successfully',
                'message_id': email_result['message_id'],
                'recipients': email_result['recipients']
            })
        else:
            return resp.error_response(500, f"Failed to send email: {email_result['error']}")
        
    except Exception as e:
        print(f"Error in send email: {str(e)}")
        return resp.error_response(500, f"Internal server error: {str(e)}")

def send_email_with_attachments(to_emails, cc_emails, bcc_emails, subject, 
                               text_content, html_content, attachments, reply_to):
    """
    Send email using SES with support for attachments
    """
    try:
        # Check if any recipients are suppressed
        all_recipients = to_emails + cc_emails + bcc_emails
        for recipient in all_recipients:
            if email_util.is_email_suppressed(recipient):
                print(f"Recipient {recipient} is suppressed, removing from send list")
                # Remove suppressed email from lists
                if recipient in to_emails:
                    to_emails.remove(recipient)
                if recipient in cc_emails:
                    cc_emails.remove(recipient)
                if recipient in bcc_emails:
                    bcc_emails.remove(recipient)
        
        # Check if we still have recipients after suppression filtering
        if not to_emails and not cc_emails and not bcc_emails:
            return {
                'success': False,
                'error': 'All recipients are suppressed'
            }
        
        # Create message
        msg = MIMEMultipart('mixed')
        msg['Subject'] = subject
        msg['From'] = MAIL_FROM_ADDRESS
        msg['To'] = ', '.join(to_emails)
        
        if cc_emails:
            msg['Cc'] = ', '.join(cc_emails)
        
        if reply_to and reply_to != MAIL_FROM_ADDRESS:
            msg['Reply-To'] = reply_to
        
        # Create message body
        body_part = MIMEMultipart('alternative')
        
        if text_content:
            text_part = MIMEText(text_content, 'plain', 'utf-8')
            body_part.attach(text_part)
        
        if html_content:
            html_part = MIMEText(html_content, 'html', 'utf-8')
            body_part.attach(html_part)
        
        msg.attach(body_part)
        
        # Add attachments
        for attachment in attachments:
            try:
                attachment_part = create_attachment_part(attachment)
                if attachment_part:
                    msg.attach(attachment_part)
            except Exception as e:
                print(f"Error adding attachment {attachment.get('filename', 'unknown')}: {str(e)}")
                # Continue with other attachments
        
        # Prepare destinations
        destinations = []
        if to_emails:
            destinations.extend(to_emails)
        if cc_emails:
            destinations.extend(cc_emails)
        if bcc_emails:
            destinations.extend(bcc_emails)
        
        # Send email using SES
        response = ses_client.send_raw_email(
            Source=MAIL_FROM_ADDRESS,
            Destinations=destinations,
            RawMessage={'Data': msg.as_string()}
        )
        
        message_id = response['MessageId']
        print(f"Email sent successfully. MessageId: {message_id}")
        
        return {
            'success': True,
            'message_id': message_id,
            'recipients': {
                'to': to_emails,
                'cc': cc_emails,
                'bcc': bcc_emails
            },
            'subject': subject,
            'attachments_count': len(attachments)
        }
        
    except Exception as e:
        print(f"Error sending email: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }

def create_attachment_part(attachment):
    """
    Create attachment part from attachment data
    """
    try:
        filename = attachment.get('filename')
        content_type = attachment.get('content_type', 'application/octet-stream')
        data = attachment.get('data')
        
        if not filename or not data:
            print(f"Invalid attachment data: filename={filename}, data_length={len(data) if data else 0}")
            return None
        
        # Decode base64 data
        try:
            attachment_data = base64.b64decode(data)
        except Exception as e:
            print(f"Error decoding base64 attachment data: {str(e)}")
            return None
        
        # Create attachment part
        attachment_part = MIMEApplication(attachment_data)
        attachment_part.add_header(
            'Content-Disposition',
            'attachment',
            filename=filename
        )
        attachment_part.add_header('Content-Type', content_type)
        
        return attachment_part
        
    except Exception as e:
        print(f"Error creating attachment part: {str(e)}")
        return None

def store_sent_email_metadata(email_result):
    """Store sent email metadata in DynamoDB for tracking"""
    try:
        if not email_result.get('success'):
            return False
        
        # Prepare metadata in proper format
        metadata_data = {
            'message_id': email_result['message_id'],
            'to_email': ', '.join(email_result['recipients'].get('to', [])),
            'from_email': MAIL_FROM_ADDRESS,
            'subject': email_result['subject'],
            'timestamp': int(datetime.utcnow().timestamp()),
            'type': 'sent',
            'status': 'delivered'
        }
        
        # Add optional fields
        if email_result['recipients'].get('cc'):
            metadata_data['cc'] = ', '.join(email_result['recipients']['cc'])
        if email_result['recipients'].get('bcc'):
            metadata_data['bcc'] = ', '.join(email_result['recipients']['bcc'])
        if email_result.get('attachments_count', 0) > 0:
            metadata_data['attachment_count'] = email_result['attachments_count']
        
        return create_email_metadata(metadata_data)
        
    except Exception as e:
        print(f"Error storing sent email metadata: {str(e)}")
        return False

def create_email_metadata(metadata_data):
    """Create email metadata record in DynamoDB"""
    try:
        # Convert to DynamoDB format
        item = {
            'message_id': {'S': metadata_data['message_id']},
            'to_email': {'S': metadata_data['to_email']},
            'from_email': {'S': metadata_data['from_email']},
            'subject': {'S': metadata_data['subject']},
            'timestamp': {'N': str(metadata_data['timestamp'])},
            'type': {'S': metadata_data.get('type', 'sent')},
            'status': {'S': metadata_data.get('status', 'delivered')}
        }
        
        # Add optional fields
        optional_fields = ['s3_key', 'size', 'reply_to', 'cc', 'bcc']
        for field in optional_fields:
            if metadata_data.get(field):
                if field in ['size']:
                    item[field] = {'N': str(metadata_data[field])}
                else:
                    item[field] = {'S': str(metadata_data[field])}
        
        dynamodb.put_item(
            TableName=EMAIL_METADATA_TABLE,
            Item=item
        )
        print(f"Email metadata {metadata_data['message_id']} created successfully")
        return True
    except ClientError as e:
        print(f"Error creating email metadata: {e.response['Error']['Message']}")
        return False

def get_email_templates():
    """Get available email templates"""
    # This would typically read from a config file or database
    # For now, return a simple structure
    return {
        'templates': [
            {
                'id': 'appointment_confirmation',
                'name': 'Appointment Confirmation',
                'description': 'Template for appointment confirmations'
            },
            {
                'id': 'order_confirmation',
                'name': 'Order Confirmation', 
                'description': 'Template for order confirmations'
            },
            {
                'id': 'inquiry_response',
                'name': 'Inquiry Response',
                'description': 'Template for responding to inquiries'
            }
        ]
    }

def is_valid_email(email_address):
    """
    Basic email validation
    """
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email_address) is not None

# # Handler for email templates (can be used as separate endpoint)
# def get_email_templates_handler(event, context):
#     """
#     API Gateway handler for retrieving email templates
#     """
#     try:
#         # Validate staff authentication
#         auth_result = auth.validate_staff_auth(event)
#         if not auth_result['success']:
#             return resp.error_response(401, auth_result['message'])
        
#         templates = {
#             'appointment_reminder': {
#                 'subject': 'Appointment Reminder - Auto Lab Solutions',
#                 'text': '''Dear {customer_name},

# This is a reminder that you have an appointment scheduled with Auto Lab Solutions.

# Appointment Details:
# - Date: {appointment_date}
# - Time: {appointment_time}
# - Service: {service_type}
# - Vehicle: {vehicle_details}

# If you need to reschedule or cancel, please contact us as soon as possible.

# Best regards,
# Auto Lab Solutions Team''',
#                 'html': '''<h2>Appointment Reminder</h2>
# <p>Dear {customer_name},</p>
# <p>This is a reminder that you have an appointment scheduled with Auto Lab Solutions.</p>
# <h3>Appointment Details:</h3>
# <ul>
# <li><strong>Date:</strong> {appointment_date}</li>
# <li><strong>Time:</strong> {appointment_time}</li>
# <li><strong>Service:</strong> {service_type}</li>
# <li><strong>Vehicle:</strong> {vehicle_details}</li>
# </ul>
# <p>If you need to reschedule or cancel, please contact us as soon as possible.</p>
# <p>Best regards,<br>Auto Lab Solutions Team</p>'''
#             },
#             'service_completed': {
#                 'subject': 'Service Completed - Auto Lab Solutions',
#                 'text': '''Dear {customer_name},

# Your vehicle service has been completed successfully.

# Service Details:
# - Date: {service_date}
# - Service: {service_type}
# - Vehicle: {vehicle_details}
# - Total Cost: ${total_cost}

# {report_link}

# Thank you for choosing Auto Lab Solutions!

# Best regards,
# Auto Lab Solutions Team''',
#                 'html': '''<h2>Service Completed</h2>
# <p>Dear {customer_name},</p>
# <p>Your vehicle service has been completed successfully.</p>
# <h3>Service Details:</h3>
# <ul>
# <li><strong>Date:</strong> {service_date}</li>
# <li><strong>Service:</strong> {service_type}</li>
# <li><strong>Vehicle:</strong> {vehicle_details}</li>
# <li><strong>Total Cost:</strong> ${total_cost}</li>
# </ul>
# {report_link}
# <p>Thank you for choosing Auto Lab Solutions!</p>
# <p>Best regards,<br>Auto Lab Solutions Team</p>'''
#             }
#         }
        
#         return resp.success_response({'templates': templates})
        
#     except Exception as e:
#         print(f"Error getting email templates: {str(e)}")
#         return resp.error_response(500, f"Internal server error: {str(e)}")

# if __name__ == "__main__":
#     # For local testing
#     test_event = {
#         'body': json.dumps({
#             'to': ['test@example.com'],
#             'subject': 'Test Email',
#             'text': 'This is a test email',
#             'html': '<p>This is a test email</p>'
#         }),
#         'headers': {'Authorization': 'Bearer test-token'}
#     }
    
#     print(lambda_handler(test_event, None))