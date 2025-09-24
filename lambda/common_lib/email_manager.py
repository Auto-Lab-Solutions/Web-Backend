"""
Email Management Module
Handles email sending, validation, metadata storage, and threading
"""

import boto3
import os
import base64
import re
import uuid
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from email import message_from_string
from email.utils import parseaddr, parsedate_to_datetime
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List, Dict, Optional

try:
    from attachment_manager import AttachmentManager
except ImportError:
    print("Warning: Could not import AttachmentManager")
    AttachmentManager = None
from email_utils import EmailTemplate
import hashlib

import permission_utils as perm
from exceptions import BusinessLogicError
from email_threading_manager import EmailThreadingManager
from email_utils import (
    send_appointment_created_email,
    send_appointment_updated_email,
    send_order_created_email,
    send_order_updated_email,
    send_report_ready_email,
    send_payment_confirmation_email
)


class EmailManager:
    """Manages email-related business logic including threading"""
    
    @staticmethod
    def normalize_message_id(message_id):
        """
        Normalize Message-ID by removing AWS SES suffixes for consistent threading
        Args:
            message_id: Original Message-ID string
        Returns:
            Normalized Message-ID string or None if input is empty
        """
        if not message_id:
            return None
        
        # Strip the @email.amazonses.com suffix if present
        if message_id.endswith('@email.amazonses.com'):
            return message_id[:-len('@email.amazonses.com')]
        
        return message_id
    
    @staticmethod
    def send_admin_email(staff_user_email, to_emails, subject, text_content='', html_content='', 
                        attachments=None, cc_emails=None, bcc_emails=None, reply_to=None,
                        thread_id=None, in_reply_to_message_id=None):
        """Send email through admin interface with full validation and threading support"""
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
        
        # Apply professional formatting if only text content is provided
        if text_content and not html_content:
            from email_utils import create_professional_admin_email, create_comprehensive_admin_email_text
            
            # Extract customer name from first recipient if possible
            primary_recipient = to_emails[0] if isinstance(to_emails, list) else to_emails
            customer_name = EmailManager._extract_name_from_email(primary_recipient)
            
            # Extract staff name from staff email - make it more casual
            staff_name = EmailManager._extract_name_from_email(staff_user_email)
            if not staff_name:
                staff_name = "the team at Auto Lab Solutions"
            else:
                # Make staff name more casual (e.g., "John Smith" becomes "John from Auto Lab Solutions")
                first_name = staff_name.split()[0] if staff_name else "the team"
                staff_name = f"{first_name} from Auto Lab Solutions"
            
            # Create professional HTML template
            html_content = create_professional_admin_email(
                subject=subject,
                message_content=text_content,
                staff_name=staff_name,
                customer_name=customer_name
            )
            
            # Create comprehensive text version that includes all HTML content
            text_content = create_comprehensive_admin_email_text(
                subject=subject,
                message_content=text_content,
                staff_name=staff_name,
                customer_name=customer_name
            )
        
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
        
        # Initialize enhanced threading manager
        threading_manager = EmailThreadingManager()
        
        # Prepare threading headers for outbound email
        threading_headers = threading_manager.prepare_outbound_email_headers(
            to_emails=to_emails,
            cc_emails=cc_emails,
            subject=subject,
            sender_email=staff_user_email,
            in_reply_to_message_id=in_reply_to_message_id
        )
        
        # Extract thread information
        thread_id_to_use = threading_headers.get('X-Thread-ID')
        message_id = threading_headers.get('Message-ID')
        
        # Update subject if this is a reply
        final_subject = threading_headers.get('Subject', subject)
        
        # Set default reply-to
        if not reply_to:
            reply_to = os.environ.get('MAIL_FROM_ADDRESS')
        
        # Send email with threading headers
        try:
            # Initialize attachment metadata list for tracking
            attachment_metadata_list = []
            
            email_result = EmailManager._send_email_with_attachments(
                to_emails=to_emails,
                cc_emails=cc_emails,
                bcc_emails=bcc_emails,
                subject=final_subject,
                text_content=text_content,
                html_content=html_content,
                attachments=attachments,
                reply_to=reply_to,
                threading_headers=threading_headers,
                attachment_metadata_list=attachment_metadata_list  # Pass for population
            )
            
            if not email_result['success']:
                error_msg = email_result.get('error', 'Unknown error')
                raise BusinessLogicError(f"Failed to send email: {error_msg}")
            
            # Get attachment metadata from email result
            attachment_metadata_list = email_result.get('attachment_metadata', [])
            
            # Update thread activity
            if thread_id_to_use and message_id:
                threading_manager.update_thread_after_send(thread_id_to_use, message_id)
            
            # Store metadata with threading and attachment information
            try:
                EmailManager._store_sent_email_metadata(
                    email_result=email_result,
                    subject=final_subject,
                    text_content=text_content,
                    html_content=html_content,
                    cc_emails=cc_emails,
                    bcc_emails=bcc_emails,
                    attachments=attachments,
                    attachment_metadata_list=attachment_metadata_list,
                    thread_id=thread_id_to_use,
                    in_reply_to_message_id=in_reply_to_message_id,
                    email_type=EmailTemplate.TYPE_ADMIN_MESSAGE
                )
                
            except Exception as e:
                print(f"Warning: Could not store sent email metadata: {str(e)}")
            
            return {
                "message": "Email sent successfully",
                "messageId": email_result['message_id'],
                "threadId": thread_id_to_use,
                "recipients": email_result['recipients']
            }
            
        except BusinessLogicError:
            raise  # Re-raise BusinessLogicError as-is
        except Exception as e:
            print(f"Email sending error: {str(e)}")
            # Provide more detailed error information
            if "content" in str(e).lower():
                raise BusinessLogicError(f"Failed to send email: Invalid attachment format. Attachments must have 'content', 'data', or 'base64' field with base64-encoded data", 400)
            else:
                raise BusinessLogicError(f"Failed to send email: {str(e)}", 500)
    
    @staticmethod
    def _is_valid_email(email):
        """Validate email format"""
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    @staticmethod
    def _extract_name_from_email(email):
        """Extract a display name from an email address"""
        if not email:
            return None
        
        # Remove domain part
        local_part = email.split('@')[0] if '@' in email else email
        
        # Handle common patterns
        if '.' in local_part:
            # Convert john.doe to John Doe
            parts = local_part.split('.')
            return ' '.join(word.capitalize() for word in parts if word)
        elif '_' in local_part:
            # Convert john_doe to John Doe
            parts = local_part.split('_')
            return ' '.join(word.capitalize() for word in parts if word)
        else:
            # Just capitalize the single word
            return local_part.capitalize()
    
    @staticmethod
    def _send_email_with_attachments(to_emails, cc_emails, bcc_emails, subject, 
                                   text_content, html_content, attachments, reply_to,
                                   threading_headers=None, attachment_metadata_list=None):
        """Send email with SES including attachments and proper threading headers"""
        ses_client = boto3.client('ses')
        from_address = os.environ.get('MAIL_FROM_ADDRESS')
        
        # Initialize attachment metadata list if not provided
        if attachment_metadata_list is None:
            attachment_metadata_list = []
        
        # Check if MAIL_FROM_ADDRESS is configured
        if not from_address:
            print("Error: MAIL_FROM_ADDRESS environment variable not configured")
            return {
                'success': False,
                'error': 'MAIL_FROM_ADDRESS not configured'
            }
        
        threading_headers = threading_headers or {}
        
        try:
            # Use raw email for proper threading headers, attachments, or when threading headers are present
            if attachments or threading_headers:
                # Use raw email for full control over headers
                msg = MIMEMultipart()
                msg['From'] = from_address
                msg['To'] = ', '.join(to_emails)
                msg['Subject'] = subject
                if reply_to:
                    msg['Reply-To'] = reply_to
                
                # Add threading headers for proper email client compatibility
                if threading_headers.get('Message-ID'):
                    msg['Message-ID'] = threading_headers['Message-ID']
                
                if threading_headers.get('In-Reply-To'):
                    msg['In-Reply-To'] = threading_headers['In-Reply-To']
                
                if threading_headers.get('References'):
                    msg['References'] = threading_headers['References']
                
                if cc_emails:
                    msg['Cc'] = ', '.join(cc_emails)
                
                # Add text/html content
                if html_content:
                    msg.attach(MIMEText(html_content, 'html'))
                if text_content:
                    msg.attach(MIMEText(text_content, 'plain'))
                
                # Add attachments and store them  
                if attachments:
                    for attachment_index, attachment in enumerate(attachments):
                        try:
                            # Handle different attachment formats
                            if isinstance(attachment, dict):
                                # Check for different possible keys for content
                                attachment_content = None
                                filename = attachment.get('filename', f'attachment_{attachment_index}')
                                
                                if 'content' in attachment:
                                    attachment_content = attachment['content']
                                elif 'data' in attachment:
                                    attachment_content = attachment['data']
                                elif 'base64' in attachment:
                                    attachment_content = attachment['base64']
                                else:
                                    print(f"Warning: Attachment missing content data: {attachment.keys()}")
                                    continue
                                
                                # Decode base64 content
                                if isinstance(attachment_content, str):
                                    try:
                                        decoded_content = base64.b64decode(attachment_content)
                                    except Exception as decode_error:
                                        print(f"Warning: Failed to decode attachment content: {str(decode_error)}")
                                        continue
                                else:
                                    # Content might already be bytes
                                    decoded_content = attachment_content
                                
                                # Store attachment separately (for sent emails)
                                try:
                                    if AttachmentManager:
                                        attachment_manager = AttachmentManager()
                                        stored_attachment = attachment_manager.store_sent_email_attachment(
                                            message_id=threading_headers.get('Message-ID', '').strip('<>'),
                                            attachment_content=decoded_content,
                                            filename=filename,
                                            attachment_index=attachment_index
                                        )
                                        if stored_attachment:
                                            attachment_metadata_list.append(stored_attachment)
                                            print(f"Successfully stored sent email attachment: {filename} with ID: {stored_attachment.get('attachmentId')}")
                                        else:
                                            print(f"Failed to store sent email attachment: {filename}")
                                except Exception as storage_error:
                                    print(f"Warning: Failed to store attachment separately: {str(storage_error)}")
                                
                                # Add to email
                                attachment_part = MIMEApplication(
                                    decoded_content,
                                    Name=filename
                                )
                                attachment_part['Content-Disposition'] = f'attachment; filename="{filename}"'
                                msg.attach(attachment_part)
                            else:
                                print(f"Warning: Invalid attachment format: {type(attachment)}")
                        except Exception as attach_error:
                            print(f"Warning: Failed to process attachment: {str(attach_error)}")
                            # Continue with other attachments instead of failing completely
                
                # Send raw email
                all_recipients = to_emails + cc_emails + bcc_emails
                response = ses_client.send_raw_email(
                    Source=from_address,
                    Destinations=all_recipients,
                    RawMessage={'Data': msg.as_string()}
                )
                
                # Extract Message-ID from the sent email for proper tracking
                final_message_id = threading_headers.get('Message-ID', response['MessageId'])
                # Remove angle brackets if present
                if final_message_id.startswith('<') and final_message_id.endswith('>'):
                    final_message_id = final_message_id[1:-1]
                
            else:
                # Use simple send_email for text/html only (legacy compatibility)
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
                
                send_params = {
                    'Source': from_address,
                    'Destination': destination,
                    'Message': message
                }
                
                if reply_to:
                    send_params['ReplyToAddresses'] = [reply_to]
                
                response = ses_client.send_email(**send_params)
                final_message_id = response['MessageId']
            
            return {
                'success': True,
                'message_id': final_message_id,
                'recipients': to_emails + cc_emails + bcc_emails,
                'to_emails': to_emails,
                'cc_emails': cc_emails,
                'bcc_emails': bcc_emails,
                'attachment_metadata': attachment_metadata_list
            }
            
        except Exception as e:
            error_msg = str(e)
            print(f"SES send error: {error_msg}")
            
            # Provide more specific error messages
            if "content" in error_msg.lower():
                error_msg = "Invalid attachment format. Attachments must contain 'content', 'data', or 'base64' field with base64-encoded data."
            elif "filename" in error_msg.lower():
                error_msg = "Invalid attachment format. Attachments must contain 'filename' field."
            elif "base64" in error_msg.lower():
                error_msg = "Invalid attachment content. Content must be valid base64-encoded data."
            
            return {
                'success': False,
                'error': error_msg
            }
    
    @staticmethod
    def _store_sent_email_metadata(email_result, subject, text_content, html_content, 
                                 cc_emails, bcc_emails, attachments, thread_id=None,
                                 in_reply_to_message_id=None, email_type=None, 
                                 attachment_metadata_list=None):
        """Store sent email metadata for tracking with threading and attachment support"""
        try:
            # Initialize attachment metadata list if not provided
            if attachment_metadata_list is None:
                attachment_metadata_list = []
            # Create metadata structure for sent emails
            metadata = {
                'messageId': email_result['message_id'],
                'fromEmail': os.environ.get('MAIL_FROM_ADDRESS', '').lower(),
                'fromName': 'Auto Lab Solutions',
                'toEmails': [email.lower() for email in email_result.get('to_emails', [])],
                'ccEmails': [email.lower() for email in cc_emails],
                'bccEmails': [email.lower() for email in bcc_emails],
                'subject': subject,
                'receivedDate': datetime.now(ZoneInfo('Australia/Perth')).isoformat(),
                'sizeBytes': len(text_content) + len(html_content),
                's3Bucket': '',
                's3Key': '',
                'hasAttachments': len(attachments) > 0,
                'attachmentCount': len(attachments),
                'bodyText': text_content[:1000] if text_content else '',
                'bodyHtml': html_content[:1000] if html_content else '',
                'contentType': 'application/sent-email',
                'emailType': email_type or 'MANUAL',  # Default to MANUAL if not specified
                'isRead': True,  # Sent emails are considered "read"
                'isImportant': False,
                'tags': ['sent'],
                'ttl': int((datetime.now(ZoneInfo('Australia/Perth')).timestamp()) + (365 * 24 * 60 * 60)),
                'createdAt': datetime.now(ZoneInfo('Australia/Perth')).isoformat(),
                'updatedAt': datetime.now(ZoneInfo('Australia/Perth')).isoformat(),
                # Threading fields
                'threadId': thread_id or '',
                'inReplyToMessageId': in_reply_to_message_id or '',
                'references': [in_reply_to_message_id] if in_reply_to_message_id else [],
                # Attachment metadata
                'attachmentIds': [att['attachmentId'] for att in attachment_metadata_list] if attachment_metadata_list else []
            }
            
            # Debug logging for attachment IDs
            if attachment_metadata_list:
                attachment_ids = [att['attachmentId'] for att in attachment_metadata_list]
                print(f"Storing email metadata with attachment IDs: {attachment_ids}")
            else:
                print("Storing email metadata with no attachments")
            
            # Store using the new method
            result = EmailManager.store_email_metadata(metadata)
            if not result['success']:
                print(f"Warning: Failed to store sent email metadata: {result['error']}")
                
        except Exception as e:
            print(f"Warning: Could not store sent email metadata: {str(e)}")
    
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
    
    @staticmethod
    def send_payment_cancellation_email(customer_email, customer_name, payment_data):
        """Send payment cancellation email"""
        from email_utils import send_payment_cancellation_email as send_email
        return send_email(customer_email, customer_name, payment_data)
    
    @staticmethod
    def send_payment_reactivation_email(customer_email, customer_name, payment_data):
        """Send payment reactivation email"""
        from email_utils import send_payment_reactivation_email as send_email
        return send_email(customer_email, customer_name, payment_data)
    
    # Threading Management Methods
    
    @staticmethod
    def _create_email_thread(participants, subject, created_by, primary_customer_email=None):
        """Create a new email thread"""
        thread_id = str(uuid.uuid4())
        dynamodb = boto3.client('dynamodb')
        table_name = os.environ.get('EMAIL_THREADS_TABLE')
        
        if not table_name:
            raise BusinessLogicError("EMAIL_THREADS_TABLE not configured")
        
        try:
            # Normalize subject for thread grouping (remove Re:, Fwd:, etc.)
            normalized_subject = EmailManager._normalize_subject(subject)
            
            # Create TTL (2 years from now for threads, longer than emails since threads are metadata)
            ttl = int((datetime.now(ZoneInfo('Australia/Perth')).timestamp()) + (2 * 365 * 24 * 60 * 60))
            
            item = {
                'threadId': {'S': thread_id},
                'normalizedSubject': {'S': normalized_subject},
                'originalSubject': {'S': subject},
                'participants': {'SS': list(set([email.lower() for email in participants]))},
                'createdBy': {'S': created_by.lower()},
                'primaryCustomerEmail': {'S': primary_customer_email.lower() if primary_customer_email else ''},
                'messageCount': {'N': '0'},
                'lastMessageId': {'S': ''},
                'lastActivityDate': {'S': datetime.now(ZoneInfo('Australia/Perth')).isoformat()},
                'isActive': {'BOOL': True},
                'ttl': {'N': str(ttl)},
                'createdAt': {'S': datetime.now(ZoneInfo('Australia/Perth')).isoformat()},
                'updatedAt': {'S': datetime.now(ZoneInfo('Australia/Perth')).isoformat()}
            }
            
            dynamodb.put_item(TableName=table_name, Item=item)
            return thread_id
            
        except Exception as e:
            print(f"Error creating email thread: {str(e)}")
            raise BusinessLogicError(f"Failed to create email thread: {str(e)}")
    
    @staticmethod
    def _get_thread_id_by_message_id(message_id):
        """Get thread ID for a given message ID"""
        dynamodb = boto3.client('dynamodb')
        email_table = os.environ.get('EMAIL_METADATA_TABLE')
        
        if not email_table:
            return None
        
        try:
            response = dynamodb.get_item(
                TableName=email_table,
                Key={'messageId': {'S': message_id}}
            )
            
            if 'Item' in response:
                item = response['Item']
                # Check if threadId field exists in the item
                if 'threadId' in item:
                    return item['threadId'].get('S', '')
                else:
                    # Legacy email without threading
                    return None
            
        except Exception as e:
            print(f"Error getting thread ID by message ID: {str(e)}")
        
        return None
    
    @staticmethod
    def _update_thread_activity(thread_id, latest_message_id):
        """Update thread with latest activity"""
        if not thread_id:
            return
        
        # Normalize the message ID for consistent storage
        normalized_message_id = EmailManager.normalize_message_id(latest_message_id)
        if not normalized_message_id:
            print(f"Warning: Could not normalize message ID for thread update: {latest_message_id}")
            normalized_message_id = latest_message_id
        
        dynamodb = boto3.client('dynamodb')
        threads_table = os.environ.get('EMAIL_THREADS_TABLE')
        
        if not threads_table:
            raise BusinessLogicError("EMAIL_THREADS_TABLE not configured")
        
        try:
            # Always increment the count when _update_thread_activity is called
            # The calling code should ensure this function is only called once per new message
            dynamodb.update_item(
                TableName=threads_table,
                Key={'threadId': {'S': thread_id}},
                UpdateExpression='SET #lastMessageId = :messageId, #lastActivityDate = :date, #messageCount = #messageCount + :inc, #updatedAt = :date',
                ExpressionAttributeNames={
                    '#lastMessageId': 'lastMessageId',
                    '#lastActivityDate': 'lastActivityDate',
                    '#messageCount': 'messageCount',
                    '#updatedAt': 'updatedAt'
                },
                ExpressionAttributeValues={
                    ':messageId': {'S': normalized_message_id},
                    ':date': {'S': datetime.now(ZoneInfo('Australia/Perth')).isoformat()},
                    ':inc': {'N': '1'}
                }
            )
            
        except Exception as e:
            print(f"Error updating thread activity: {str(e)}")
    
    @staticmethod
    def _normalize_subject(subject):
        """Normalize email subject for thread grouping"""
        if not subject:
            return ""
        
        # Remove common prefixes
        normalized = re.sub(r'^(re:|fwd?:|fw:)\s*', '', subject.lower().strip())
        normalized = re.sub(r'\s+', ' ', normalized)  # Normalize whitespace
        return normalized
    
    @staticmethod
    def _find_thread_by_last_message_id(message_id):
        """Find existing thread by lastMessageId to prevent duplicate threads"""
        dynamodb = boto3.client('dynamodb')
        table_name = os.environ.get('EMAIL_THREADS_TABLE')
        
        if not table_name:
            return None
        
        # Normalize the message ID for consistent comparison
        normalized_message_id = EmailManager.normalize_message_id(message_id)
        if not normalized_message_id:
            return None
        
        try:
            # Search for threads with normalized message ID
            response = dynamodb.scan(
                TableName=table_name,
                FilterExpression='#lastMessageId = :messageId AND #isActive = :isActive',
                ExpressionAttributeNames={
                    '#lastMessageId': 'lastMessageId',
                    '#isActive': 'isActive'
                },
                ExpressionAttributeValues={
                    ':messageId': {'S': normalized_message_id},
                    ':isActive': {'BOOL': True}
                }
            )
            
            items = response.get('Items', [])
            if items:
                thread_id = items[0]['threadId']['S']
                print(f"Found existing thread by normalized lastMessageId '{normalized_message_id}': {thread_id}")
                return thread_id
            
            # Also search for SES format if not already included
            if '@email.amazonses.com' not in normalized_message_id:
                ses_format_id = f"{normalized_message_id}@email.amazonses.com"
                response_ses = dynamodb.scan(
                    TableName=table_name,
                    FilterExpression='#lastMessageId = :messageId AND #isActive = :isActive',
                    ExpressionAttributeNames={
                        '#lastMessageId': 'lastMessageId',
                        '#isActive': 'isActive'
                    },
                    ExpressionAttributeValues={
                        ':messageId': {'S': ses_format_id},
                        ':isActive': {'BOOL': True}
                    }
                )
                
                items_ses = response_ses.get('Items', [])
                if items_ses:
                    thread_id = items_ses[0]['threadId']['S']
                    print(f"Found existing thread by SES format lastMessageId '{ses_format_id}': {thread_id}")
                    return thread_id
                
        except Exception as e:
            print(f"Error finding thread by lastMessageId: {str(e)}")
        
        return None

    @staticmethod
    def _find_thread_by_subject_and_participants(subject, participants):
        """Find existing thread by normalized subject and participants with improved matching"""
        dynamodb = boto3.client('dynamodb')
        table_name = os.environ.get('EMAIL_THREADS_TABLE')
        
        if not table_name:
            print("EMAIL_THREADS_TABLE not configured for thread search")
            return None
        
        try:
            normalized_subject = EmailManager._normalize_subject(subject)
            if not normalized_subject:
                print("No normalized subject available for thread matching")
                return None
            
            # Normalize participants for consistent comparison
            normalized_participants = set([email.lower().strip() for email in participants if email])
            print(f"Threading - Searching for subject: '{normalized_subject}', participants: {list(normalized_participants)}")
            
            # Search for threads with same normalized subject
            response = dynamodb.scan(
                TableName=table_name,
                FilterExpression='#normalizedSubject = :subject AND #isActive = :isActive',
                ExpressionAttributeNames={
                    '#normalizedSubject': 'normalizedSubject',
                    '#isActive': 'isActive'
                },
                ExpressionAttributeValues={
                    ':subject': {'S': normalized_subject},
                    ':isActive': {'BOOL': True}
                }
            )
            
            # Check if any participants match
            for item in response.get('Items', []):
                thread_participants = set(item.get('participants', {}).get('SS', []))
                thread_id = item.get('threadId', {}).get('S', '')
                
                print(f"Threading - Comparing with thread {thread_id}: participants {list(thread_participants)}")
                
                # If there's any overlap in participants, consider it the same thread
                common_participants = normalized_participants & thread_participants
                if common_participants:
                    print(f"Threading - Found matching thread {thread_id} with common participants: {list(common_participants)}")
                    return thread_id
            
            print(f"Threading - No matching thread found for subject '{normalized_subject}' and participants {list(normalized_participants)}")
            return None
            
        except Exception as e:
            print(f"Error finding thread by subject and participants: {str(e)}")
            return None
    
    @staticmethod
    def get_email_threads(staff_email=None, customer_email=None, limit=50, offset=0):
        """Get email threads with filtering and pagination"""
        dynamodb = boto3.client('dynamodb')
        table_name = os.environ.get('EMAIL_THREADS_TABLE')
        
        if not table_name:
            return {'threads': [], 'total': 0, 'error': 'EMAIL_THREADS_TABLE not configured'}
        
        try:
            # Build filter expression
            filter_expression_parts = ['#isActive = :isActive']
            expression_attribute_values = {':isActive': {'BOOL': True}}
            expression_attribute_names = {'#isActive': 'isActive'}
            
            if customer_email:
                filter_expression_parts.append('contains(#participants, :customerEmail)')
                expression_attribute_names['#participants'] = 'participants'
                expression_attribute_values[':customerEmail'] = {'S': customer_email.lower()}
            
            scan_params = {
                'TableName': table_name,
                'FilterExpression': ' AND '.join(filter_expression_parts),
                'ExpressionAttributeValues': expression_attribute_values,
                'ExpressionAttributeNames': expression_attribute_names
            }
            
            response = dynamodb.scan(**scan_params)
            
            # Convert to readable format
            threads = []
            for item in response.get('Items', []):
                thread = EmailManager._convert_dynamodb_thread_to_readable(item)
                threads.append(thread)
            
            # Sort by last activity (newest first)
            threads.sort(key=lambda x: x['lastActivityDate'], reverse=True)
            
            # Apply pagination
            total_count = len(threads)
            paginated_threads = threads[offset:offset + limit]
            
            return {
                'threads': paginated_threads,
                'total': total_count,
                'offset': offset,
                'limit': limit
            }
            
        except Exception as e:
            print(f"Error retrieving email threads: {str(e)}")
            return {'threads': [], 'total': 0, 'error': str(e)}
    
    @staticmethod
    def get_thread_emails(thread_id, limit=50, offset=0):
        """Get all emails in a specific thread with thread metadata for composition"""
        dynamodb = boto3.client('dynamodb')
        email_table = os.environ.get('EMAIL_METADATA_TABLE')
        threads_table = os.environ.get('EMAIL_THREADS_TABLE')
        
        if not email_table:
            return {'emails': [], 'total': 0, 'error': 'EMAIL_METADATA_TABLE not configured'}
        
        try:
            # First, get thread metadata for composition info
            thread_metadata = None
            if threads_table:
                try:
                    thread_response = dynamodb.get_item(
                        TableName=threads_table,
                        Key={'threadId': {'S': thread_id}}
                    )
                    if 'Item' in thread_response:
                        thread_metadata = EmailManager._convert_dynamodb_thread_to_readable(thread_response['Item'])
                        print(f"Retrieved thread metadata for composition: {thread_metadata.get('composeToEmail', 'No compose email found')}")
                except Exception as thread_error:
                    print(f"Warning: Could not retrieve thread metadata: {str(thread_error)}")
            
            # Get emails in the thread (existing logic)
            # Try to use ThreadIdIndex first (more efficient if available)
            all_emails = []
            try:
                # Attempt to query using ThreadIdIndex
                last_evaluated_key = None
                
                while True:
                    # Build query parameters for ThreadIdIndex
                    query_params = {
                        'TableName': email_table,
                        'IndexName': 'ThreadIdIndex',
                        'KeyConditionExpression': '#threadId = :threadId',
                        'ExpressionAttributeNames': {'#threadId': 'threadId'},
                        'ExpressionAttributeValues': {':threadId': {'S': thread_id}},
                        'ScanIndexForward': True  # Sort by receivedDate ascending (oldest first)
                    }
                    
                    # Add pagination if we have a last evaluated key
                    if last_evaluated_key:
                        query_params['ExclusiveStartKey'] = last_evaluated_key
                    
                    response = dynamodb.query(**query_params)
                    
                    # Process items from this page
                    for item in response.get('Items', []):
                        email = EmailManager._convert_dynamodb_item_to_email(item)
                        all_emails.append(email)
                    
                    # Check if there are more items
                    last_evaluated_key = response.get('LastEvaluatedKey')
                    if not last_evaluated_key:
                        break
                
                print(f"Successfully used ThreadIdIndex to retrieve {len(all_emails)} emails for thread {thread_id}")
                
            except Exception as index_error:
                print(f"ThreadIdIndex not available or failed ({str(index_error)}), falling back to scan")
                
                # Fallback to scan if ThreadIdIndex doesn't exist or fails
                all_emails = []
                last_evaluated_key = None
                
                while True:
                    # Build scan parameters
                    scan_params = {
                        'TableName': email_table,
                        'FilterExpression': '#threadId = :threadId',
                        'ExpressionAttributeNames': {'#threadId': 'threadId'},
                        'ExpressionAttributeValues': {':threadId': {'S': thread_id}}
                    }
                    
                    # Add pagination if we have a last evaluated key
                    if last_evaluated_key:
                        scan_params['ExclusiveStartKey'] = last_evaluated_key
                    
                    response = dynamodb.scan(**scan_params)
                    
                    # Process items from this page
                    for item in response.get('Items', []):
                        email = EmailManager._convert_dynamodb_item_to_email(item)
                        all_emails.append(email)
                    
                    # Check if there are more items to scan
                    last_evaluated_key = response.get('LastEvaluatedKey')
                    if not last_evaluated_key:
                        break
                    
                    # Safety check: if we have too many emails, something might be wrong
                    if len(all_emails) > 10000:  # Reasonable limit for a single thread
                        print(f"Warning: Thread {thread_id} has over 10,000 emails, stopping scan")
                        break
                
                # Sort by received date since scan doesn't guarantee order
                all_emails.sort(key=lambda x: x['receivedDate'])
                print(f"Fallback scan retrieved {len(all_emails)} emails for thread {thread_id}")
            
            # Filter to last 2 months (using createdAt or receivedDate)
            now = int(datetime.now(ZoneInfo('Australia/Perth')).timestamp())
            two_months_ago = now - 60 * 24 * 60 * 60  # 60 days in seconds
            def email_in_last_2_months(email):
                # Try createdAt (int or str), fallback to receivedDate (str, try parse to timestamp)
                try:
                    if int(email.get('createdAt', 0)) >= two_months_ago:
                        return True
                except Exception:
                    pass
                # Try receivedDate as ISO or epoch string
                from datetime import datetime
                received = email.get('receivedDate')
                if received:
                    try:
                        # Try epoch int/str
                        if int(received) >= two_months_ago:
                            return True
                    except Exception:
                        try:
                            # Try ISO format
                            dt = datetime.fromisoformat(received.replace('Z', '+00:00'))
                            if int(dt.timestamp()) >= two_months_ago:
                                return True
                        except Exception:
                            pass
                return False
            filtered_emails = [email for email in all_emails if email_in_last_2_months(email)]
            # Apply pagination after filtering
            total_count = len(filtered_emails)
            paginated_emails = filtered_emails[offset:offset + limit]
            result = {
                'emails': paginated_emails,
                'total': total_count,
                'offset': offset,
                'limit': limit,
                'threadId': thread_id
            }
            
            # Add thread metadata for composition if available
            if thread_metadata:
                result['threadMetadata'] = thread_metadata
                # Add specific compose helpers
                result['composeToEmail'] = thread_metadata.get('composeToEmail', '')
                result['threadSubject'] = thread_metadata.get('originalSubject', '')
                result['customerParticipants'] = thread_metadata.get('customerParticipants', [])
            
            return result
            
        except Exception as e:
            print(f"Error retrieving thread emails: {str(e)}")
            return {'emails': [], 'total': 0, 'error': str(e)}
    
    @staticmethod
    def _convert_dynamodb_thread_to_readable(item):
        """Convert DynamoDB thread item to readable format with compose-friendly data"""
        
        # Get basic thread data
        participants = item.get('participants', {}).get('SS', [])
        primary_customer_email = item.get('primaryCustomerEmail', {}).get('S', '')
        
        # Get company email for filtering
        company_email = os.environ.get('MAIL_FROM_ADDRESS', '').lower()
        
        # Filter out company email from participants to get customer emails
        customer_participants = [email for email in participants if email.lower() != company_email]
        
        # Determine the best recipient for compose
        compose_to_email = primary_customer_email
        if not compose_to_email and customer_participants:
            # If no primary customer email, use the first customer participant
            compose_to_email = customer_participants[0]
        
        return {
            'threadId': item.get('threadId', {}).get('S', ''),
            'normalizedSubject': item.get('normalizedSubject', {}).get('S', ''),
            'originalSubject': item.get('originalSubject', {}).get('S', ''),
            'participants': participants,
            'customerParticipants': customer_participants,  # New: customers only (excluding company)
            'createdBy': item.get('createdBy', {}).get('S', ''),
            'primaryCustomerEmail': primary_customer_email,
            'composeToEmail': compose_to_email,  # New: recommended email for compose "To" field
            'messageCount': int(item.get('messageCount', {}).get('N', '0')),
            'lastMessageId': item.get('lastMessageId', {}).get('S', ''),
            'lastActivityDate': item.get('lastActivityDate', {}).get('S', ''),
            'isActive': item.get('isActive', {}).get('BOOL', True),
            'tags': item.get('tags', {}).get('SS', []),
            'ttl': int(item.get('ttl', {}).get('N', '0')) if item.get('ttl', {}).get('N') else None,
            'createdAt': item.get('createdAt', {}).get('S', ''),
            'updatedAt': item.get('updatedAt', {}).get('S', '')
        }
    
    @staticmethod
    def process_s3_email(bucket_name, object_key):
        """Process email stored in S3 and extract metadata"""
        try:
            # Extract email metadata from S3 stored email
            email_metadata = EmailManager._extract_email_metadata_from_s3(bucket_name, object_key)
            
            # Store metadata in DynamoDB
            result = EmailManager.store_email_metadata(email_metadata)
            
            if result['success']:
                return {
                    'success': True,
                    'message_id': email_metadata['messageId']
                }
            else:
                return {
                    'success': False,
                    'error': result['error']
                }
                
        except Exception as e:
            print(f"Error processing S3 email: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    @staticmethod
    def _extract_email_metadata_from_s3(bucket_name, object_key):
        """Extract email metadata from S3 stored email with threading support"""
        s3_client = boto3.client('s3')
        
        try:
            # Get object info
            head_response = s3_client.head_object(Bucket=bucket_name, Key=object_key)
            object_size = head_response['ContentLength']
            
            # Download the email content from S3
            response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
            email_content = response['Body'].read().decode('utf-8')
            
            # Parse the email
            email_message = message_from_string(email_content)
            
            # Extract basic information
            message_id = email_message.get('Message-ID', '').strip('<>')
            if not message_id:
                # Generate a message ID if none exists
                message_id = f"generated-{hashlib.md5(email_content.encode()).hexdigest()}"
            
            # Extract threading information
            in_reply_to = email_message.get('In-Reply-To', '').strip('<>')
            references = email_message.get('References', '')
            reference_list = [ref.strip('<>') for ref in references.split() if ref.strip('<>')]
            
            # Parse sender and recipients
            from_header = email_message.get('From', '')
            from_name, from_email = parseaddr(from_header)
            
            to_header = email_message.get('To', '')
            to_emails = [parseaddr(addr)[1] for addr in to_header.split(',') if addr.strip()]
            
            cc_header = email_message.get('Cc', '')
            cc_emails = [parseaddr(addr)[1] for addr in cc_header.split(',') if addr.strip()] if cc_header else []
            
            # Parse date
            date_header = email_message.get('Date')
            received_date = datetime.now(ZoneInfo('Australia/Perth')).isoformat()
            if date_header:
                try:
                    parsed_date = parsedate_to_datetime(date_header)
                    received_date = parsed_date.isoformat()
                except:
                    pass
            
            # Check for attachments
            has_attachments = False
            attachment_count = 0
            for part in email_message.walk():
                if part.get_content_disposition() == 'attachment':
                    has_attachments = True
                    attachment_count += 1
            
            # Extract plain text content for analysis
            body_text = ""
            body_html = ""
            
            if email_message.is_multipart():
                for part in email_message.walk():
                    content_type = part.get_content_type()
                    if content_type == "text/plain":
                        try:
                            body_text = part.get_payload(decode=True).decode('utf-8')
                        except:
                            pass
                    elif content_type == "text/html":
                        try:
                            body_html = part.get_payload(decode=True).decode('utf-8')
                        except:
                            pass
            else:
                try:
                    content_type = email_message.get_content_type()
                    if content_type == "text/plain":
                        body_text = email_message.get_payload(decode=True).decode('utf-8')
                    elif content_type == "text/html":
                        body_html = email_message.get_payload(decode=True).decode('utf-8')
                except:
                    pass
            
            # Generate tags based on content analysis
            tags = EmailManager._generate_email_tags(email_message, body_text, body_html)
            
            # Determine thread ID
            thread_id = None
            subject = email_message.get('Subject', '')
            
            if in_reply_to:
                # This is a reply, try to find existing thread
                thread_id = EmailManager._get_thread_id_by_message_id(in_reply_to)
            
            if not thread_id:
                # Try to find thread by normalized subject and participants
                thread_id = EmailManager._find_thread_by_subject_and_participants(
                    subject, [from_email] + to_emails + cc_emails
                )
            
            if not thread_id:
                # Create new thread - use appropriate method based on table availability
                all_participants = [from_email] + to_emails + cc_emails
                # Filter out our own email address
                our_email = os.environ.get('MAIL_FROM_ADDRESS', '').lower()
                external_participants = [email for email in all_participants if email.lower() != our_email]
                
                if external_participants:
                    # Use dedicated threads table
                    thread_id = EmailManager._create_email_thread(
                        participants=all_participants,
                        subject=subject,
                        created_by=from_email,
                        primary_customer_email=from_email
                    )
            
            # Create TTL (1 year from now)
            ttl = int((datetime.now(ZoneInfo('Australia/Perth')).timestamp()) + (365 * 24 * 60 * 60))
            
            metadata = {
                'messageId': message_id,
                'fromEmail': from_email.lower() if from_email else '',
                'fromName': from_name or '',
                'toEmails': [email.lower() for email in to_emails],
                'ccEmails': [email.lower() for email in cc_emails],
                'bccEmails': [],  # BCC information not available in email headers
                'subject': subject,
                'receivedDate': received_date,
                'sizeBytes': object_size,
                's3Bucket': bucket_name,
                's3Key': object_key,
                'hasAttachments': has_attachments,
                'attachmentCount': attachment_count,
                'bodyText': body_text[:1000] if body_text else '',
                'bodyHtml': body_html[:1000] if body_html else '',
                'contentType': email_message.get_content_type(),
                'isRead': False,
                'isImportant': EmailManager._determine_importance(email_message, body_text, body_html),
                'tags': tags,
                'ttl': ttl,
                'createdAt': datetime.now(ZoneInfo('Australia/Perth')).isoformat(),
                'updatedAt': datetime.now(ZoneInfo('Australia/Perth')).isoformat(),
                # Threading fields
                'threadId': thread_id or '',
                'inReplyToMessageId': in_reply_to,
                'references': reference_list
            }
            
            # Update thread activity if thread exists
            if thread_id:
                EmailManager._update_thread_activity(thread_id, message_id)
            
            return metadata
            
        except Exception as e:
            print(f"Error extracting email metadata from S3: {str(e)}")
            raise
    
    @staticmethod
    def _generate_email_tags(email_message, body_text, body_html):
        """Generate tags based on email content"""
        tags = []
        
        # Check subject for common patterns
        subject = email_message.get('Subject', '').lower()
        
        if any(word in subject for word in ['appointment', 'booking', 'schedule']):
            tags.append('appointment')
        
        if any(word in subject for word in ['order', 'purchase', 'buy']):
            tags.append('order')
        
        if any(word in subject for word in ['payment', 'invoice', 'bill', 'receipt']):
            tags.append('payment')
        
        if any(word in subject for word in ['urgent', 'asap', 'emergency']):
            tags.append('urgent')
        
        if any(word in subject for word in ['inquiry', 'question', 'help', 'support']):
            tags.append('inquiry')
        
        # Check content for additional patterns
        content = f"{body_text} {body_html}".lower()
        
        if any(word in content for word in ['lab result', 'test result', 'report']):
            tags.append('lab-result')
        
        if any(word in content for word in ['complaint', 'problem', 'issue']):
            tags.append('complaint')
        
        return list(set(tags))  # Remove duplicates
    
    @staticmethod
    def _determine_importance(email_message, body_text, body_html):
        """Determine if email is important based on content"""
        subject = email_message.get('Subject', '').lower()
        content = f"{body_text} {body_html}".lower()
        
        # Check for importance indicators
        importance_keywords = [
            'urgent', 'asap', 'emergency', 'important', 'critical',
            'complaint', 'problem', 'issue', 'error', 'failed'
        ]
        
        return any(keyword in subject or keyword in content for keyword in importance_keywords)
    
    @staticmethod
    def store_email_metadata(metadata):
        """Store email metadata in DynamoDB with enhanced structure and threading support"""
        dynamodb = boto3.client('dynamodb')
        table_name = os.environ.get('EMAIL_METADATA_TABLE')
        
        if not table_name:
            return {'success': False, 'error': 'EMAIL_METADATA_TABLE environment variable not set'}
        
        try:
            # Convert metadata to DynamoDB format
            created_timestamp = int(datetime.now(ZoneInfo('Australia/Perth')).timestamp() * 1000)
            
            item = {
                'messageId': {'S': metadata['messageId']},
                'fromEmail': {'S': metadata['fromEmail']},
                'fromName': {'S': metadata.get('fromName', '')},
                'subject': {'S': metadata.get('subject', '')},
                'receivedDate': {'S': metadata['receivedDate']},
                'sizeBytes': {'N': str(metadata.get('sizeBytes', 0))},
                's3Bucket': {'S': metadata.get('s3Bucket', '')},
                's3Key': {'S': metadata.get('s3Key', '')},
                'hasAttachments': {'BOOL': metadata.get('hasAttachments', False)},
                'attachmentCount': {'N': str(metadata.get('attachmentCount', 0))},
                'bodyText': {'S': metadata.get('bodyText', '')},
                'bodyHtml': {'S': metadata.get('bodyHtml', '')},
                'contentType': {'S': metadata.get('contentType', '')},
                'emailType': {'S': metadata.get('emailType', 'MANUAL')},  # Track email type
                'isRead': {'BOOL': metadata.get('isRead', False)},
                'isImportant': {'BOOL': metadata.get('isImportant', False)},
                'ttl': {'N': str(metadata.get('ttl', 0))},
                'createdAt': {'N': str(created_timestamp)},
                'updatedAt': {'S': metadata.get('updatedAt', datetime.now(ZoneInfo('Australia/Perth')).isoformat())},
                'inReplyToMessageId': {'S': metadata.get('inReplyToMessageId', '')}
            }
            
            # Add email address lists only if they have non-empty values
            for field_name in ['toEmails', 'ccEmails', 'bccEmails']:
                emails = metadata.get(field_name, [])
                if emails and any(email.strip() for email in emails if email):
                    non_empty_emails = [email.strip() for email in emails if email and email.strip()]
                    if non_empty_emails:
                        item[field_name] = {'SS': non_empty_emails}
            
            # Add optional string set fields only if they have non-empty values
            tags = metadata.get('tags', [])
            if tags and any(tag.strip() for tag in tags):  # Only add if there are non-empty tags
                # Filter out empty strings
                non_empty_tags = [tag.strip() for tag in tags if tag.strip()]
                if non_empty_tags:
                    item['tags'] = {'SS': non_empty_tags}
            
            references = metadata.get('references', [])
            if references and any(ref.strip() for ref in references):  # Only add if there are non-empty references
                # Filter out empty strings
                non_empty_refs = [ref.strip() for ref in references if ref.strip()]
                if non_empty_refs:
                    item['references'] = {'SS': non_empty_refs}
            
            # Add attachment IDs if present
            attachment_ids = metadata.get('attachmentIds', [])
            if attachment_ids and any(att_id.strip() for att_id in attachment_ids):
                non_empty_ids = [att_id.strip() for att_id in attachment_ids if att_id.strip()]
                if non_empty_ids:
                    item['attachmentIds'] = {'SS': non_empty_ids}
                    print(f"Storing email {metadata['messageId']} with attachment IDs: {non_empty_ids}")
                else:
                    print(f"Email {metadata['messageId']} has empty attachment IDs")
            else:
                print(f"Email {metadata['messageId']} has no attachment IDs")
            
            # Only add threadId if it has a non-empty value (GSI key cannot be empty string)
            thread_id = metadata.get('threadId', '')
            if thread_id and thread_id.strip():
                item['threadId'] = {'S': thread_id}
            
            dynamodb.put_item(
                TableName=table_name,
                Item=item
            )
            
            return {'success': True, 'message_id': metadata['messageId']}
            
        except Exception as e:
            print(f"Error storing email metadata: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    @staticmethod
    def get_emails(to_email=None, from_email=None, start_date=None, end_date=None, 
                   is_read=None, has_attachments=None, limit=50, offset=0):
        """Retrieve emails with filtering and pagination"""
        dynamodb = boto3.client('dynamodb')
        table_name = os.environ.get('EMAIL_METADATA_TABLE')
        
        if not table_name:
            return {'emails': [], 'total': 0, 'error': 'EMAIL_METADATA_TABLE not configured'}
        
        try:
            # Build filter expression
            filter_expression_parts = []
            expression_attribute_values = {}
            expression_attribute_names = {}
            
            if to_email:
                filter_expression_parts.append('contains(#toEmails, :toEmailValue)')
                expression_attribute_names['#toEmails'] = 'toEmails'
                expression_attribute_values[':toEmailValue'] = {'S': to_email.lower()}
            
            if from_email:
                filter_expression_parts.append('#fromEmail = :fromEmail')
                expression_attribute_names['#fromEmail'] = 'fromEmail'
                expression_attribute_values[':fromEmail'] = {'S': from_email.lower()}
            
            if start_date:
                filter_expression_parts.append('#receivedDate >= :startDate')
                expression_attribute_names['#receivedDate'] = 'receivedDate'
                expression_attribute_values[':startDate'] = {'S': start_date}
            
            if end_date:
                filter_expression_parts.append('#receivedDate <= :endDate')
                if '#receivedDate' not in expression_attribute_names:
                    expression_attribute_names['#receivedDate'] = 'receivedDate'
                expression_attribute_values[':endDate'] = {'S': end_date}
            
            if is_read is not None:
                filter_expression_parts.append('#isRead = :isRead')
                expression_attribute_names['#isRead'] = 'isRead'
                expression_attribute_values[':isRead'] = {'BOOL': bool(is_read)}
            
            if has_attachments is not None:
                filter_expression_parts.append('#hasAttachments = :hasAttachments')
                expression_attribute_names['#hasAttachments'] = 'hasAttachments'
                expression_attribute_values[':hasAttachments'] = {'BOOL': bool(has_attachments)}
            
            # Use the appropriate index based on filters
            scan_params = {
                'TableName': table_name,
                'Limit': limit + offset  # We'll handle offset in post-processing
            }
            
            if filter_expression_parts:
                scan_params['FilterExpression'] = ' AND '.join(filter_expression_parts)
                scan_params['ExpressionAttributeValues'] = expression_attribute_values
                scan_params['ExpressionAttributeNames'] = expression_attribute_names
            
            # Use appropriate query strategy based on filters
            # If filtering by specific email, use scan with filters
            if from_email and not to_email:
                # Use scan with fromEmail filter (assuming no GSI for fromEmail)
                response = dynamodb.scan(**scan_params)
            else:
                # Use scan for complex filters or simple queries
                response = dynamodb.scan(**scan_params)
            
            # Convert DynamoDB items to readable format
            emails = []
            for item in response.get('Items', []):
                email = EmailManager._convert_dynamodb_item_to_email(item)
                emails.append(email)
            
            print(f"Retrieved {len(emails)} emails from DynamoDB")
            
            # Debug log a sample email if available
            if emails and (emails[0].get('hasAttachments') or emails[0].get('attachmentCount', 0) > 0):
                sample_email = emails[0]
                print(f"Sample email with attachments - ID: {sample_email.get('messageId')}, attachmentIds: {sample_email.get('attachmentIds')}, count: {sample_email.get('attachmentCount')}")
            
            # Sort by received date (newest first)
            emails.sort(key=lambda x: x['receivedDate'], reverse=True)
            
            # Apply offset and limit
            total_count = len(emails)
            paginated_emails = emails[offset:offset + limit]
            
            return {
                'emails': paginated_emails,
                'total': total_count,
                'offset': offset,
                'limit': limit
            }
            
        except Exception as e:
            print(f"Error retrieving emails: {str(e)}")
            return {'emails': [], 'total': 0, 'error': str(e)}
    
    @staticmethod
    def get_email_by_id_full(message_id):
        """Retrieve full email data including S3 content"""
        dynamodb = boto3.client('dynamodb')
        table_name = os.environ.get('EMAIL_METADATA_TABLE')
        
        if not table_name:
            return None
        
        try:
            # Get metadata from DynamoDB
            response = dynamodb.get_item(
                TableName=table_name,
                Key={'messageId': {'S': message_id}}
            )
            
            if 'Item' not in response:
                return None
            
            email_metadata = EmailManager._convert_dynamodb_item_to_email(response['Item'])
            
            # If this is a received email (has S3 data), get the full content
            if email_metadata.get('s3Bucket') and email_metadata.get('s3Key'):
                try:
                    s3_client = boto3.client('s3')
                    s3_response = s3_client.get_object(
                        Bucket=email_metadata['s3Bucket'],
                        Key=email_metadata['s3Key']
                    )
                    email_content = s3_response['Body'].read().decode('utf-8')
                    
                    # Parse full email content
                    email_message = message_from_string(email_content)
                    
                    # Extract full body content
                    body_text = ""
                    body_html = ""
                    attachments = []
                    
                    if email_message.is_multipart():
                        for part in email_message.walk():
                            content_type = part.get_content_type()
                            content_disposition = part.get_content_disposition()
                            
                            if content_disposition == 'attachment':
                                # Handle attachment
                                filename = part.get_filename()
                                if filename:
                                    attachments.append({
                                        'filename': filename,
                                        'content_type': content_type,
                                        'size': len(part.get_payload(decode=True) or b'')
                                    })
                            elif content_type == "text/plain":
                                try:
                                    body_text = part.get_payload(decode=True).decode('utf-8')
                                except:
                                    pass
                            elif content_type == "text/html":
                                try:
                                    body_html = part.get_payload(decode=True).decode('utf-8')
                                except:
                                    pass
                    else:
                        content_type = email_message.get_content_type()
                        if content_type == "text/plain":
                            body_text = email_message.get_payload(decode=True).decode('utf-8')
                        elif content_type == "text/html":
                            body_html = email_message.get_payload(decode=True).decode('utf-8')
                    
                    # Update metadata with full content
                    email_metadata['fullBodyText'] = body_text
                    email_metadata['fullBodyHtml'] = body_html
                    email_metadata['attachments'] = attachments
                    
                except Exception as s3_error:
                    print(f"Warning: Could not retrieve full email content from S3: {str(s3_error)}")
            
            return email_metadata
            
        except Exception as e:
            print(f"Error retrieving email by ID: {str(e)}")
            return None
    
    @staticmethod
    def update_email_read_status(message_id, is_read):
        """Update the read status of an email"""
        dynamodb = boto3.client('dynamodb')
        table_name = os.environ.get('EMAIL_METADATA_TABLE')
        
        if not table_name:
            return False
        
        try:
            dynamodb.update_item(
                TableName=table_name,
                Key={'messageId': {'S': message_id}},
                UpdateExpression='SET #isRead = :isRead, #updatedAt = :updatedAt',
                ExpressionAttributeNames={
                    '#isRead': 'isRead',
                    '#updatedAt': 'updatedAt'
                },
                ExpressionAttributeValues={
                    ':isRead': {'BOOL': is_read},
                    ':updatedAt': {'S': datetime.now(ZoneInfo('Australia/Perth')).isoformat()}
                }
            )
            return True
            
        except Exception as e:
            print(f"Error updating email read status: {str(e)}")
            return False
    
    @staticmethod
    def update_email_data(message_id, is_important=None, is_read=None, tags=None):
        """Update email metadata like isImportant, isRead, and tags"""
        dynamodb = boto3.client('dynamodb')
        table_name = os.environ.get('EMAIL_METADATA_TABLE')
        
        if not table_name:
            return False
        
        try:
            # Build update expression dynamically based on provided parameters
            update_expressions = []
            expression_attribute_names = {}
            expression_attribute_values = {}
            
            # Always update the updatedAt timestamp
            update_expressions.append('#updatedAt = :updatedAt')
            expression_attribute_names['#updatedAt'] = 'updatedAt'
            expression_attribute_values[':updatedAt'] = {'S': datetime.now(ZoneInfo('Australia/Perth')).isoformat()}
            
            if is_important is not None:
                update_expressions.append('#isImportant = :isImportant')
                expression_attribute_names['#isImportant'] = 'isImportant'
                expression_attribute_values[':isImportant'] = {'BOOL': bool(is_important)}
            
            if is_read is not None:
                update_expressions.append('#isRead = :isRead')
                expression_attribute_names['#isRead'] = 'isRead'
                expression_attribute_values[':isRead'] = {'BOOL': bool(is_read)}
            
            # Separate SET and REMOVE operations
            set_expressions = []
            remove_expressions = []
            
            if tags is not None:
                if isinstance(tags, list) and len(tags) > 0:
                    # Validate tags are strings
                    validated_tags = [str(tag).strip() for tag in tags if str(tag).strip()]
                    if validated_tags:
                        set_expressions.append('#tags = :tags')
                        expression_attribute_names['#tags'] = 'tags'
                        expression_attribute_values[':tags'] = {'SS': validated_tags}
                    else:
                        # No valid tags - remove the attribute entirely
                        remove_expressions.append('#tags')
                        expression_attribute_names['#tags'] = 'tags'
                else:
                    # Empty tags - remove the attribute entirely
                    remove_expressions.append('#tags')
                    expression_attribute_names['#tags'] = 'tags'
            
            # Add other SET expressions to set_expressions list
            for expr in update_expressions:
                if not expr.startswith('REMOVE'):
                    set_expressions.append(expr)
            
            # Build the UpdateExpression properly
            update_expression_parts = []
            if set_expressions:
                update_expression_parts.append('SET ' + ', '.join(set_expressions))
            if remove_expressions:
                update_expression_parts.append('REMOVE ' + ', '.join(remove_expressions))
            
            if not update_expression_parts:
                return False
            
            dynamodb.update_item(
                TableName=table_name,
                Key={'messageId': {'S': message_id}},
                UpdateExpression=' '.join(update_expression_parts),
                ExpressionAttributeNames=expression_attribute_names,
                ExpressionAttributeValues=expression_attribute_values
            )
            return True
            
        except Exception as e:
            print(f"Error updating email data: {str(e)}")
            return False
    
    @staticmethod
    def _convert_dynamodb_item_to_email(item):
        """Convert DynamoDB item to readable email format with threading support"""
        message_id = item.get('messageId', {}).get('S', '')
        attachment_ids = item.get('attachmentIds', {}).get('SS', []) if 'attachmentIds' in item else []
        has_attachments = item.get('hasAttachments', {}).get('BOOL', False)
        attachment_count = int(item.get('attachmentCount', {}).get('N', '0'))
        
        # Debug logging for attachment fields
        if has_attachments or attachment_count > 0:
            print(f"Converting email {message_id}: hasAttachments={has_attachments}, attachmentCount={attachment_count}, attachmentIds={attachment_ids}")
        
        return {
            'messageId': item.get('messageId', {}).get('S', ''),
            'fromEmail': item.get('fromEmail', {}).get('S', ''),
            'fromName': item.get('fromName', {}).get('S', ''),
            'toEmails': item.get('toEmails', {}).get('SS', []),
            'ccEmails': item.get('ccEmails', {}).get('SS', []),
            'bccEmails': item.get('bccEmails', {}).get('SS', []),
            'subject': item.get('subject', {}).get('S', ''),
            'receivedDate': item.get('receivedDate', {}).get('S', ''),
            'sizeBytes': int(item.get('sizeBytes', {}).get('N', '0')),
            's3Bucket': item.get('s3Bucket', {}).get('S', ''),
            's3Key': item.get('s3Key', {}).get('S', ''),
            'hasAttachments': has_attachments,
            'attachmentCount': attachment_count,
            'bodyText': item.get('bodyText', {}).get('S', ''),
            'bodyHtml': item.get('bodyHtml', {}).get('S', ''),
            'contentType': item.get('contentType', {}).get('S', ''),
            'isRead': item.get('isRead', {}).get('BOOL', False),
            'isImportant': item.get('isImportant', {}).get('BOOL', False),
            'tags': item.get('tags', {}).get('SS', []),
            'createdAt': item.get('createdAt', {}).get('S', ''),
            'updatedAt': item.get('updatedAt', {}).get('S', ''),
            # Threading fields (with fallbacks for existing records)
            'threadId': item.get('threadId', {}).get('S', '') if 'threadId' in item else '',
            'inReplyToMessageId': item.get('inReplyToMessageId', {}).get('S', '') if 'inReplyToMessageId' in item else '',
            'references': item.get('references', {}).get('SS', []) if 'references' in item else [],
            # Attachment fields
            'attachmentIds': attachment_ids
        }
    
    # Attachment Management Methods
    
    @staticmethod
    def get_email_attachments(message_id: str) -> List[Dict]:
        """Get all attachments for a specific email"""
        if not AttachmentManager:
            return []
        
        try:
            attachment_manager = AttachmentManager()
            return attachment_manager.get_attachments_for_email(message_id)
        except Exception as e:
            print(f"Error retrieving attachments for email {message_id}: {str(e)}")
            return []
    
    @staticmethod
    def get_attachment_by_id(attachment_id: str) -> Optional[Dict]:
        """Get attachment metadata by attachment ID"""
        if not AttachmentManager:
            return None
        
        try:
            attachment_manager = AttachmentManager()
            return attachment_manager.get_attachment_by_id(attachment_id)
        except Exception as e:
            print(f"Error retrieving attachment {attachment_id}: {str(e)}")
            return None
    
    @staticmethod
    def get_attachment_download_url(attachment_id: str, expires_in: int = 3600) -> Optional[str]:
        """Generate a presigned URL for attachment download"""
        if not AttachmentManager:
            return None
        
        try:
            attachment_manager = AttachmentManager()
            return attachment_manager.get_attachment_download_url(attachment_id, expires_in)
        except Exception as e:
            print(f"Error generating download URL for attachment {attachment_id}: {str(e)}")
            return None
    
    @staticmethod
    def get_attachment_content(attachment_id: str):
        """Get attachment content for direct download"""
        if not AttachmentManager:
            return None
        
        try:
            attachment_manager = AttachmentManager()
            return attachment_manager.get_attachment_content(attachment_id)
        except Exception as e:
            print(f"Error retrieving attachment content for {attachment_id}: {str(e)}")
            return None
    
    @staticmethod
    def delete_attachment(attachment_id: str) -> bool:
        """Delete an attachment"""
        if not AttachmentManager:
            return False
        
        try:
            attachment_manager = AttachmentManager()
            return attachment_manager.delete_attachment(attachment_id)
        except Exception as e:
            print(f"Error deleting attachment {attachment_id}: {str(e)}")
            return False
    
    @staticmethod
    def get_attachment_stats(message_id: str) -> Dict:
        """Get attachment statistics for an email"""
        if not AttachmentManager:
            return {'count': 0, 'totalSizeBytes': 0, 'totalSizeMB': 0, 'types': []}
        
        try:
            attachment_manager = AttachmentManager()
            return attachment_manager.get_attachment_stats(message_id)
        except Exception as e:
            print(f"Error getting attachment stats for email {message_id}: {str(e)}")
            return {'count': 0, 'totalSizeBytes': 0, 'totalSizeMB': 0, 'types': []}
