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
from email import message_from_string
from email.utils import parseaddr, parsedate_to_datetime
from datetime import datetime, timezone
import hashlib

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
        """Store sent email metadata for tracking"""
        try:
            # Create metadata structure for sent emails
            metadata = {
                'messageId': email_result['message_id'],
                'fromEmail': os.environ.get('NO_REPLY_EMAIL', ''),
                'fromName': 'Auto Lab Solutions',
                'toEmail': email_result['recipients'][0].lower() if email_result['recipients'] else '',
                'toEmails': [email.lower() for email in email_result['recipients']],
                'ccEmails': [],
                'subject': 'Sent Email',  # Subject not available in email_result
                'receivedDate': datetime.now(timezone.utc).isoformat(),
                'sizeBytes': 0,
                's3Bucket': '',
                's3Key': '',
                'hasAttachments': False,
                'attachmentCount': 0,
                'bodyText': '',
                'bodyHtml': '',
                'contentType': 'application/sent-email',
                'isRead': True,  # Sent emails are considered "read"
                'isImportant': False,
                'tags': ['sent'],
                'ttl': int((datetime.now(timezone.utc).timestamp()) + (365 * 24 * 60 * 60)),
                'createdAt': datetime.now(timezone.utc).isoformat(),
                'updatedAt': datetime.now(timezone.utc).isoformat()
            }
            
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
        """Extract email metadata from S3 stored email"""
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
            
            # Parse sender and recipients
            from_header = email_message.get('From', '')
            from_name, from_email = parseaddr(from_header)
            
            to_header = email_message.get('To', '')
            to_emails = [parseaddr(addr)[1] for addr in to_header.split(',') if addr.strip()]
            
            cc_header = email_message.get('Cc', '')
            cc_emails = [parseaddr(addr)[1] for addr in cc_header.split(',') if addr.strip()] if cc_header else []
            
            # Parse date
            date_header = email_message.get('Date')
            received_date = datetime.now(timezone.utc).isoformat()
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
            
            # Create TTL (1 year from now)
            ttl = int((datetime.now(timezone.utc).timestamp()) + (365 * 24 * 60 * 60))
            
            return {
                'messageId': message_id,
                'fromEmail': from_email.lower() if from_email else '',
                'fromName': from_name or '',
                'toEmails': [email.lower() for email in to_emails],
                'toEmail': to_emails[0].lower() if to_emails else '',
                'ccEmails': [email.lower() for email in cc_emails],
                'subject': email_message.get('Subject', ''),
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
                'createdAt': datetime.now(timezone.utc).isoformat(),
                'updatedAt': datetime.now(timezone.utc).isoformat()
            }
            
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
        """Store email metadata in DynamoDB with enhanced structure"""
        dynamodb = boto3.client('dynamodb')
        table_name = os.environ.get('EMAIL_METADATA_TABLE')
        
        if not table_name:
            return {'success': False, 'error': 'EMAIL_METADATA_TABLE environment variable not set'}
        
        try:
            # Convert metadata to DynamoDB format
            item = {
                'messageId': {'S': metadata['messageId']},
                'fromEmail': {'S': metadata['fromEmail']},
                'fromName': {'S': metadata.get('fromName', '')},
                'toEmail': {'S': metadata['toEmail']},
                'toEmails': {'SS': metadata['toEmails']} if metadata.get('toEmails') else {'SS': ['']},
                'ccEmails': {'SS': metadata.get('ccEmails', [])} if metadata.get('ccEmails') else {'SS': ['']},
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
                'isRead': {'BOOL': metadata.get('isRead', False)},
                'isImportant': {'BOOL': metadata.get('isImportant', False)},
                'tags': {'SS': metadata.get('tags', [])} if metadata.get('tags') else {'SS': ['']},
                'ttl': {'N': str(metadata.get('ttl', 0))},
                'createdAt': {'S': metadata.get('createdAt', datetime.now(timezone.utc).isoformat())},
                'updatedAt': {'S': metadata.get('updatedAt', datetime.now(timezone.utc).isoformat())}
            }
            
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
                filter_expression_parts.append('#toEmail = :toEmail')
                expression_attribute_names['#toEmail'] = 'toEmail'
                expression_attribute_values[':toEmail'] = {'S': to_email.lower()}
            
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
            
            # If filtering by specific email, use the appropriate GSI
            if to_email and not from_email:
                scan_params['IndexName'] = 'ToEmailIndex'
                # Convert to query
                del scan_params['FilterExpression']
                response = dynamodb.query(**scan_params)
            elif from_email and not to_email:
                scan_params['IndexName'] = 'FromEmailIndex'
                # Convert to query
                del scan_params['FilterExpression']
                response = dynamodb.query(**scan_params)
            else:
                # Use scan for complex filters
                response = dynamodb.scan(**scan_params)
            
            # Convert DynamoDB items to readable format
            emails = []
            for item in response.get('Items', []):
                email = EmailManager._convert_dynamodb_item_to_email(item)
                emails.append(email)
            
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
                    ':updatedAt': {'S': datetime.now(timezone.utc).isoformat()}
                }
            )
            return True
            
        except Exception as e:
            print(f"Error updating email read status: {str(e)}")
            return False
    
    @staticmethod
    def _convert_dynamodb_item_to_email(item):
        """Convert DynamoDB item to readable email format"""
        return {
            'messageId': item.get('messageId', {}).get('S', ''),
            'fromEmail': item.get('fromEmail', {}).get('S', ''),
            'fromName': item.get('fromName', {}).get('S', ''),
            'toEmail': item.get('toEmail', {}).get('S', ''),
            'toEmails': item.get('toEmails', {}).get('SS', []),
            'ccEmails': item.get('ccEmails', {}).get('SS', []),
            'bccEmails': item.get('bccEmails', {}).get('SS', []),
            'subject': item.get('subject', {}).get('S', ''),
            'receivedDate': item.get('receivedDate', {}).get('S', ''),
            'sizeBytes': int(item.get('sizeBytes', {}).get('N', '0')),
            's3Bucket': item.get('s3Bucket', {}).get('S', ''),
            's3Key': item.get('s3Key', {}).get('S', ''),
            'hasAttachments': item.get('hasAttachments', {}).get('BOOL', False),
            'attachmentCount': int(item.get('attachmentCount', {}).get('N', '0')),
            'bodyText': item.get('bodyText', {}).get('S', ''),
            'bodyHtml': item.get('bodyHtml', {}).get('S', ''),
            'contentType': item.get('contentType', {}).get('S', ''),
            'isRead': item.get('isRead', {}).get('BOOL', False),
            'isImportant': item.get('isImportant', {}).get('BOOL', False),
            'tags': item.get('tags', {}).get('SS', []),
            'createdAt': item.get('createdAt', {}).get('S', ''),
            'updatedAt': item.get('updatedAt', {}).get('S', '')
        }
