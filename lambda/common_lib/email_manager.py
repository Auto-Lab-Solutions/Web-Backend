"""
Email Management Module
Handles email sending, validation, and metadata storage
"""

import boto3
import os
import base64
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime

import permission_utils as perm
from exceptions import BusinessLogicError
from email_utils import (
    send_appointment_created_email,
    send_appointment_updated_email,
    send_order_created_email,
    send_order_updated_email,
    send_report_ready_email,
    send_payment_confirmation_email
)


class EmailManager:
    """Manages email-related business logic"""
    
    @staticmethod
    def send_admin_email(staff_user_email, to_emails, subject, text_content='', html_content='', 
                        attachments=None, cc_emails=None, bcc_emails=None, reply_to=None):
        """Send email through admin interface with full validation"""
        # Validate staff permissions
        staff_context = perm.PermissionValidator.validate_staff_access(
            staff_user_email,
            required_roles=['CUSTOMER_SUPPORT', 'ADMIN']
        )
        
        # Validate required parameters
        if not to_emails:
            raise BusinessLogicError("At least one recipient is required")
        if not subject:
            raise BusinessLogicError("Subject is required")
        if not text_content and not html_content:
            raise BusinessLogicError("Either text or html content is required")
        
        # Normalize email lists
        if isinstance(to_emails, str):
            to_emails = [to_emails]
        cc_emails = cc_emails or []
        bcc_emails = bcc_emails or []
        attachments = attachments or []
        
        # Validate email addresses
        all_emails = to_emails + cc_emails + bcc_emails
        for email_addr in all_emails:
            if not EmailManager._is_valid_email(email_addr):
                raise BusinessLogicError(f"Invalid email address: {email_addr}")
        
        # Set default reply-to
        if not reply_to:
            reply_to = os.environ.get('NO_REPLY_EMAIL') or os.environ.get('MAIL_FROM_ADDRESS')
        
        # Send email
        try:
            email_result = EmailManager._send_email_with_attachments(
                to_emails=to_emails,
                cc_emails=cc_emails,
                bcc_emails=bcc_emails,
                subject=subject,
                text_content=text_content,
                html_content=html_content,
                attachments=attachments,
                reply_to=reply_to
            )
            
            if not email_result['success']:
                raise BusinessLogicError("Failed to send email")
            
            # Store metadata
            try:
                EmailManager._store_sent_email_metadata(email_result)
            except Exception as e:
                print(f"Warning: Could not store sent email metadata: {str(e)}")
            
            return {
                "message": "Email sent successfully",
                "messageId": email_result['message_id'],
                "recipients": email_result['recipients']
            }
            
        except Exception as e:
            print(f"Email sending error: {str(e)}")
            raise BusinessLogicError(f"Failed to send email: {str(e)}", 500)
    
    @staticmethod
    def _is_valid_email(email):
        """Validate email format"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    @staticmethod
    def _send_email_with_attachments(to_emails, cc_emails, bcc_emails, subject, 
                                   text_content, html_content, attachments, reply_to):
        """Send email with SES including attachments"""
        ses_client = boto3.client('ses')
        from_address = os.environ.get('NO_REPLY_EMAIL') or os.environ.get('MAIL_FROM_ADDRESS')
        
        try:
            if attachments:
                # Use raw email for attachments
                msg = MIMEMultipart()
                msg['From'] = from_address
                msg['To'] = ', '.join(to_emails)
                msg['Subject'] = subject
                msg['Reply-To'] = reply_to
                
                if cc_emails:
                    msg['Cc'] = ', '.join(cc_emails)
                
                # Add text/html content
                if html_content:
                    msg.attach(MIMEText(html_content, 'html'))
                if text_content:
                    msg.attach(MIMEText(text_content, 'plain'))
                
                # Add attachments
                for attachment in attachments:
                    attachment_part = MIMEApplication(
                        base64.b64decode(attachment['content']),
                        Name=attachment['filename']
                    )
                    attachment_part['Content-Disposition'] = f'attachment; filename="{attachment["filename"]}"'
                    msg.attach(attachment_part)
                
                # Send raw email
                all_recipients = to_emails + cc_emails + bcc_emails
                response = ses_client.send_raw_email(
                    Source=from_address,
                    Destinations=all_recipients,
                    RawMessage={'Data': msg.as_string()}
                )
            else:
                # Use simple send_email for text/html only
                destination = {'ToAddresses': to_emails}
                if cc_emails:
                    destination['CcAddresses'] = cc_emails
                if bcc_emails:
                    destination['BccAddresses'] = bcc_emails
                
                message = {'Subject': {'Data': subject}}
                
                if html_content and text_content:
                    message['Body'] = {
                        'Html': {'Data': html_content},
                        'Text': {'Data': text_content}
                    }
                elif html_content:
                    message['Body'] = {'Html': {'Data': html_content}}
                else:
                    message['Body'] = {'Text': {'Data': text_content}}
                
                response = ses_client.send_email(
                    Source=from_address,
                    Destination=destination,
                    Message=message,
                    ReplyToAddresses=[reply_to]
                )
            
            return {
                'success': True,
                'message_id': response['MessageId'],
                'recipients': to_emails + cc_emails + bcc_emails
            }
            
        except Exception as e:
            print(f"SES send error: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    @staticmethod
    def _store_sent_email_metadata(email_result):
        """Store email metadata for tracking"""
        dynamodb = boto3.client('dynamodb')
        table_name = os.environ.get('EMAIL_METADATA_TABLE')
        
        if not table_name:
            return
        
        try:
            dynamodb.put_item(
                TableName=table_name,
                Item={
                    'messageId': {'S': email_result['message_id']},
                    'sentAt': {'S': datetime.utcnow().isoformat()},
                    'recipients': {'SS': email_result['recipients']},
                    'status': {'S': 'sent'}
                }
            )
        except Exception as e:
            print(f"Failed to store email metadata: {str(e)}")
    
    @staticmethod
    def send_appointment_created_email(customer_email, customer_name, appointment_data):
        """Send appointment created email"""
        from email_utils import send_appointment_created_email as send_email
        return send_email(customer_email, customer_name, appointment_data)
    
    @staticmethod
    def send_appointment_updated_email(customer_email, customer_name, appointment_data, changes=None, update_type='general'):
        """Send appointment updated email"""
        from email_utils import send_appointment_updated_email as send_email
        return send_email(customer_email, customer_name, appointment_data, changes, update_type)
    
    @staticmethod
    def send_order_created_email(customer_email, customer_name, order_data):
        """Send order created email"""
        from email_utils import send_order_created_email as send_email
        return send_email(customer_email, customer_name, order_data)
    
    @staticmethod
    def send_order_updated_email(customer_email, customer_name, order_data, changes=None, update_type='general'):
        """Send order updated email"""
        from email_utils import send_order_updated_email as send_email
        return send_email(customer_email, customer_name, order_data, changes, update_type)
    
    @staticmethod
    def send_report_ready_email(customer_email, customer_name, appointment_data, report_url):
        """Send report ready email"""
        from email_utils import send_report_ready_email as send_email
        return send_email(customer_email, customer_name, appointment_data, report_url)
    
    @staticmethod
    def send_payment_confirmation_email(customer_email, customer_name, payment_data, invoice_url):
        """Send payment confirmation email"""
        from email_utils import send_payment_confirmation_email as send_email
        return send_email(customer_email, customer_name, payment_data, invoice_url)
