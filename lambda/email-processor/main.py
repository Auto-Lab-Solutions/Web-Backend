import json
import os
import boto3
from datetime import datetime
from zoneinfo import ZoneInfo
from email import message_from_string
from email.utils import parsedate_to_datetime, parseaddr
import hashlib
import re
import uuid

try:
    from notification_manager import NotificationManager
except ImportError:
    print("Warning: Could not import NotificationManager, Firebase notifications will be disabled")
    NotificationManager = None

# Try to import the specific function we need
try:
    from notification_manager import queue_email_received_firebase_notification
except ImportError:
    print("Warning: Could not import queue_email_received_firebase_notification")
    queue_email_received_firebase_notification = None

# Import attachment manager
try:
    from attachment_manager import AttachmentManager
except ImportError:
    print("Warning: Could not import AttachmentManager, attachment handling will be disabled")
    AttachmentManager = None

def lambda_handler(event, context):
    """
    Lambda handler for processing emails stored in S3 by SES
    Only triggered by S3 ObjectCreated events
    """
    try:
        print(f"Processing S3 email event: {json.dumps(event)}")
        
        # Process each S3 record in the event
        for record in event.get('Records', []):
            if record.get('eventSource') == 'aws:s3':
                process_s3_email_event(record)
            else:
                print(f"Ignoring non-S3 event source: {record.get('eventSource')}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({'message': 'Email processed successfully'})
        }
        
    except Exception as e:
        print(f"Error processing email: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)})
        }


def process_s3_email_event(record):
    """Process email when it's stored in S3 by SES"""
    try:
        # Extract S3 information
        bucket_name = record['s3']['bucket']['name']
        object_key = record['s3']['object']['key']
        object_size = record['s3']['object']['size']
        
        print(f"Processing email from S3: {bucket_name}/{object_key}")
        
        # Download and parse the email from S3
        email_metadata = extract_email_metadata(bucket_name, object_key, object_size)
        
        # Extract and store attachments if attachment manager is available
        if AttachmentManager and email_metadata.get('hasAttachments', False):
            try:
                print(f"Processing attachments for email: {email_metadata['messageId']}")
                attachment_manager = AttachmentManager()
                
                # Re-download email for attachment processing
                s3_client = boto3.client('s3')
                response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
                email_content = response['Body'].read().decode('utf-8')
                email_message = message_from_string(email_content)
                
                # Extract and store attachments
                attachments = attachment_manager.extract_and_store_attachments(
                    email_message, email_metadata['messageId'], bucket_name, object_key
                )
                
                # Update email metadata with attachment details
                email_metadata['attachments'] = attachments
                email_metadata['attachmentCount'] = len(attachments)
                email_metadata['attachmentIds'] = [att['attachmentId'] for att in attachments] if attachments else []
                
                print(f"Successfully processed {len(attachments)} attachments with IDs: {[att.get('attachmentId') for att in attachments]}")
                
            except Exception as attachment_error:
                print(f"Error processing attachments: {str(attachment_error)}")
                # Continue processing even if attachment handling fails
        
        # Store metadata in DynamoDB
        store_email_metadata(email_metadata)
        
        print(f"Threading - Email metadata after storage: threadId='{email_metadata.get('threadId', 'NOT_SET')}'")
        
        # Update thread activity if thread exists
        if email_metadata.get('threadId'):
            print(f"Threading - Calling update_thread_activity with threadId='{email_metadata['threadId']}', messageId='{email_metadata['messageId']}'")
            update_thread_activity(email_metadata['threadId'], email_metadata['messageId'])
            
            # Check for and merge any duplicate threads with the same lastMessageId
            check_and_merge_duplicate_threads(email_metadata['messageId'])
        else:
            print(f"Threading - WARNING: No threadId found in email metadata, skipping thread activity update")
        
        # Send Firebase notification to staff about new email
        send_new_email_notification(email_metadata)
        
        print(f"Successfully processed email: {email_metadata['messageId']}")
        
    except Exception as e:
        print(f"Error processing S3 email event: {str(e)}")
        raise


def extract_email_metadata(bucket_name, object_key, object_size):
    """Extract email metadata from S3 stored email"""
    s3_client = boto3.client('s3')
    
    try:
        # Download the email content from S3
        response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        email_content = response['Body'].read().decode('utf-8')
        
        # Parse the email
        email_message = message_from_string(email_content)
        
        # Extract basic information
        raw_message_id = email_message.get('Message-ID', '').strip('<>')
        if not raw_message_id:
            # Generate a message ID if none exists
            raw_message_id = f"generated-{hashlib.md5(email_content.encode()).hexdigest()}"
        
        # Normalize the message ID for consistent threading
        message_id = normalize_message_id(raw_message_id)
        
        # Extract threading information
        in_reply_to = normalize_message_id(email_message.get('In-Reply-To', '').strip('<>'))
        references = email_message.get('References', '')
        reference_list = [normalize_message_id(ref.strip('<>')) for ref in references.split() if ref.strip('<>')]
        
        # Parse sender and recipients
        from_header = email_message.get('From', '')
        from_name, from_email = parseaddr(from_header)
        
        to_header = email_message.get('To', '')
        to_emails = [parseaddr(addr)[1] for addr in to_header.split(',') if addr.strip()]
        
        cc_header = email_message.get('Cc', '')
        cc_emails = [parseaddr(addr)[1] for addr in cc_header.split(',') if addr.strip()] if cc_header else []
        
        bcc_header = email_message.get('Bcc', '')
        bcc_emails = [parseaddr(addr)[1] for addr in bcc_header.split(',') if addr.strip()] if bcc_header else []
        
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
        tags = generate_email_tags(email_message, body_text, body_html)
        
        # Create TTL (1 year from now)
        ttl = int((datetime.now(ZoneInfo('Australia/Perth')).timestamp()) + (365 * 24 * 60 * 60))
        
        # Determine thread ID using improved threading logic
        thread_id = ""
        subject = email_message.get('Subject', '')
        all_participants = [from_email] + to_emails + cc_emails
        
        print(f"Threading - Processing email with Message-ID: {message_id}, Subject: '{subject}'")
        print(f"Threading - Participants: {all_participants}")
        
        # Step 1: Try to find thread by In-Reply-To header (highest priority)
        if in_reply_to:
            print(f"Threading - Email has In-Reply-To: {in_reply_to}")
            thread_id = get_thread_id_by_message_id(in_reply_to)
            if thread_id:
                print(f"Threading - Found existing thread by In-Reply-To: {thread_id}")
        
        # Step 2: Try to find thread by lastMessageId (handles threading issues)
        if not thread_id:
            thread_id = find_thread_by_last_message_id(message_id)
            if thread_id:
                print(f"Threading - Found existing thread by lastMessageId: {thread_id}")
        
        # Step 3: Try to find thread by subject and participants (legacy support)
        if not thread_id:
            thread_id = find_thread_by_subject_and_participants(
                subject, all_participants
            )
            if thread_id:
                print(f"Threading - Found thread by subject/participants: {thread_id}")
        
        # Step 4: If still no thread found, create a new one (if threading table is available)
        if not thread_id:
            # Filter out our own email address
            our_email = os.environ.get('MAIL_FROM_ADDRESS', '').lower()
            external_participants = [email for email in all_participants if email.lower() != our_email]
            
            print(f"Threading - No existing thread found. Our email: '{our_email}', External participants: {external_participants}")
            
            if external_participants and os.environ.get('EMAIL_THREADS_TABLE'):
                # Use dedicated threads table
                print(f"Threading - Creating new thread with participants={all_participants}, subject='{subject}', created_by='{from_email}'")
                thread_id = create_email_thread(
                    participants=all_participants,
                    subject=subject,
                    created_by=from_email,
                    primary_customer_email=from_email
                )
                if thread_id:
                    print(f"Threading - Successfully created new thread: {thread_id}")
                else:
                    print(f"Threading - ERROR: create_email_thread returned None/empty")
            else:
                print("Threading - EMAIL_THREADS_TABLE not configured or no external participants, skipping thread creation")
        
        print(f"Threading - Final thread_id for email: '{thread_id}'")
        
        return {
            'messageId': message_id,
            'fromEmail': from_email.lower() if from_email else '',
            'fromName': from_name or '',
            'toEmails': [email.lower() for email in to_emails],
            'ccEmails': [email.lower() for email in cc_emails],
            'bccEmails': [email.lower() for email in bcc_emails],
            'subject': subject,
            'receivedDate': received_date,
            'sizeBytes': object_size,
            's3Bucket': bucket_name,
            's3Key': object_key,
            'hasAttachments': has_attachments,
            'attachmentCount': attachment_count,
            'bodyText': body_text[:1000] if body_text else '',  # Store first 1000 chars for search
            'bodyHtml': body_html[:1000] if body_html else '',  # Store first 1000 chars for search
            'contentType': email_message.get_content_type(),
            'isRead': False,
            'isImportant': determine_importance(email_message, body_text, body_html),
            'tags': tags,
            'ttl': ttl,
            'createdAt': datetime.now(ZoneInfo('Australia/Perth')).isoformat(),
            'updatedAt': datetime.now(ZoneInfo('Australia/Perth')).isoformat(),
            # Threading fields (basic implementation)
            'threadId': thread_id,
            'inReplyToMessageId': in_reply_to,
            'references': reference_list,
            # Attachment fields
            'attachmentIds': []  # Will be populated later if attachments are processed
        }
        
    except Exception as e:
        print(f"Error extracting email metadata: {str(e)}")
        raise


def generate_email_tags(email_message, body_text, body_html):
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


def determine_importance(email_message, body_text, body_html):
    """Determine if email is important based on content"""
    subject = email_message.get('Subject', '').lower()
    content = f"{body_text} {body_html}".lower()
    
    # Check for importance indicators
    importance_keywords = [
        'urgent', 'asap', 'emergency', 'important', 'critical',
        'complaint', 'problem', 'issue', 'error', 'failed'
    ]
    
    return any(keyword in subject or keyword in content for keyword in importance_keywords)


def store_email_metadata(metadata):
    """Store email metadata in DynamoDB"""
    dynamodb = boto3.client('dynamodb')
    table_name = os.environ.get('EMAIL_METADATA_TABLE')
    
    if not table_name:
        raise Exception("EMAIL_METADATA_TABLE environment variable not set")
    
    try:
        # Convert metadata to DynamoDB format with correct timestamp
        created_timestamp = int(datetime.now(ZoneInfo('Australia/Perth')).timestamp() * 1000)
        
        item = {
            'messageId': {'S': metadata['messageId']},
            'fromEmail': {'S': metadata['fromEmail']},
            'fromName': {'S': metadata['fromName']},
            'subject': {'S': metadata['subject']},
            'receivedDate': {'S': metadata['receivedDate']},
            'sizeBytes': {'N': str(metadata['sizeBytes'])},
            's3Bucket': {'S': metadata['s3Bucket']},
            's3Key': {'S': metadata['s3Key']},
            'hasAttachments': {'BOOL': metadata['hasAttachments']},
            'attachmentCount': {'N': str(metadata['attachmentCount'])},
            'bodyText': {'S': metadata['bodyText']},
            'bodyHtml': {'S': metadata['bodyHtml']},
            'contentType': {'S': metadata['contentType']},
            'isRead': {'BOOL': metadata['isRead']},
            'isImportant': {'BOOL': metadata['isImportant']},
            'ttl': {'N': str(metadata['ttl'])},
            'createdAt': {'N': str(created_timestamp)},
            'updatedAt': {'S': metadata['updatedAt']},
            # Threading fields (with safety checks)
            'inReplyToMessageId': {'S': metadata.get('inReplyToMessageId', '')}
        }
        
        # Add email address lists only if they have non-empty values
        for field_name, field_key in [('toEmails', 'toEmails'), ('ccEmails', 'ccEmails'), ('bccEmails', 'bccEmails')]:
            emails = metadata.get(field_name, [])
            if emails and any(email.strip() for email in emails):
                non_empty_emails = [email.strip() for email in emails if email.strip()]
                if non_empty_emails:
                    item[field_name] = {'SS': non_empty_emails}
        
        # Add tags only if they have non-empty values
        tags = metadata.get('tags', [])
        if tags and any(tag.strip() for tag in tags):
            non_empty_tags = [tag.strip() for tag in tags if tag.strip()]
            if non_empty_tags:
                item['tags'] = {'SS': non_empty_tags}
        
        # Add references only if they have non-empty values
        references = metadata.get('references', [])
        if references and any(ref.strip() for ref in references):
            non_empty_refs = [ref.strip() for ref in references if ref.strip()]
            if non_empty_refs:
                item['references'] = {'SS': non_empty_refs}
        
        # Add attachment IDs if present
        attachment_ids = metadata.get('attachmentIds', [])
        if attachment_ids and any(att_id.strip() for att_id in attachment_ids):
            non_empty_ids = [att_id.strip() for att_id in attachment_ids if att_id.strip()]
            if non_empty_ids:
                item['attachmentIds'] = {'SS': non_empty_ids}
                print(f"Storing received email {metadata['messageId']} with attachment IDs: {non_empty_ids}")
        
        # Only include threadId if it's not empty (GSI requirement)
        thread_id = metadata.get('threadId', '')
        if thread_id:
            item['threadId'] = {'S': thread_id}
        
        dynamodb.put_item(
            TableName=table_name,
            Item=item
        )
        
        print(f"Successfully stored metadata for message: {metadata['messageId']}")
        
    except Exception as e:
        print(f"Error storing email metadata: {str(e)}")
        raise


def send_new_email_notification(email_metadata):
    """Send Firebase notification to staff about new email received"""
    try:
        # Check if Firebase notifications are enabled via environment variable
        enable_firebase = os.environ.get('ENABLE_FIREBASE_NOTIFICATIONS', 'false').lower()
        if enable_firebase != 'true':
            print("Firebase notifications disabled via ENABLE_FIREBASE_NOTIFICATIONS setting, skipping notification")
            return
        
        # Check if Firebase notifications are configured
        firebase_queue_url = os.environ.get('FIREBASE_NOTIFICATION_QUEUE_URL', '')
        if not firebase_queue_url:
            print("Firebase notification queue URL not configured, skipping notification")
            return
        
        # IMPORTANT: Verify this is an email RECEIVED at our receiving address (not sent by us)
        receiving_address = os.environ.get('MAIL_RECEIVING_ADDRESS', 'mail@autolabsolutions.com').lower()
        to_emails = email_metadata.get('toEmails', [])
        cc_emails = email_metadata.get('ccEmails', [])
        bcc_emails = email_metadata.get('bccEmails', [])
        
        # Check if our receiving address is in any of the recipient fields
        all_recipients = to_emails + cc_emails + bcc_emails
        is_received_email = any(receiving_address == email.lower() for email in all_recipients if email)
        
        if not is_received_email:
            print(f"Email not addressed to receiving address ({receiving_address}), skipping Firebase notification")
            print(f"Email recipients - To: {to_emails}, CC: {cc_emails}, BCC: {bcc_emails}")
            return
        
        print(f"Confirmed: Email received at {receiving_address}, proceeding with Firebase notification")
        
        # Use the dedicated function if available
        if queue_email_received_firebase_notification:
            success = queue_email_received_firebase_notification(email_metadata)
            if success:
                print(f"Successfully queued Firebase notification for email from {email_metadata.get('fromEmail', 'unknown')}")
            else:
                print(f"Failed to queue Firebase notification for email from {email_metadata.get('fromEmail', 'unknown')}")
            return
        
        # Fallback to using NotificationManager directly
        if not NotificationManager:
            print("NotificationManager not available, skipping Firebase notification")
            return
        
        # Initialize notification manager
        notification_manager = NotificationManager()
        
        # Extract email information for notification
        from_email = email_metadata.get('fromEmail', 'Unknown sender')
        from_name = email_metadata.get('fromName', '')
        subject = email_metadata.get('subject', 'No subject')
        is_important = email_metadata.get('isImportant', False)
        tags = email_metadata.get('tags', [])
        
        # Create notification title and body
        sender_display = from_name if from_name else from_email
        title = "New Email Received"
        body = f"From: {sender_display}"
        
        if subject:
            body += f"\nSubject: {subject}"
        
        # Add urgency indicator if marked as important
        if is_important:
            title = "🔥 Urgent Email Received"
            body = f"⚠️ {body}"
        
        # Determine target roles based on email tags and importance
        target_roles = ['CUSTOMER_SUPPORT', 'CLERK']
        
        # If it's an appointment-related email, also notify mechanics
        if 'appointment' in tags:
            target_roles.append('MECHANIC')
        
        # If it's urgent or complaint, notify admin too
        if is_important or 'complaint' in tags or 'urgent' in tags:
            target_roles.append('ADMIN')
        
        # Prepare notification data
        notification_data = {
            'type': 'email_received',
            'messageId': email_metadata.get('messageId'),
            'fromEmail': from_email,
            'fromName': from_name,
            'subject': subject,
            'isImportant': is_important,
            'tags': tags,
            'receivedDate': email_metadata.get('receivedDate'),
            'timestamp': int(datetime.now(ZoneInfo('Australia/Perth')).timestamp())
        }
        
        # Queue Firebase notification
        success = notification_manager.queue_firebase_notification(
            notification_type='email_received',
            title=title,
            body=body,
            data=notification_data,
            target_type='broadcast',
            roles=target_roles
        )
        
        if success:
            print(f"Successfully queued Firebase notification for email from {from_email}")
        else:
            print(f"Failed to queue Firebase notification for email from {from_email}")
            
    except Exception as e:
        print(f"Error sending Firebase notification: {str(e)}")
        # Don't raise the exception to avoid failing the entire email processing


def get_thread_id_by_message_id(message_id):
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


def normalize_message_id(message_id):
    """Normalize Message-ID to ensure consistent format for threading"""
    if not message_id:
        return ""
    
    # Remove angle brackets if present
    normalized = message_id.strip('<>')
    
    # Remove @email.amazonses.com suffix if present (SES adds this)
    if normalized.endswith('@email.amazonses.com'):
        normalized = normalized[:-len('@email.amazonses.com')]
    
    return normalized


def normalize_subject(subject):
    """Normalize email subject for thread grouping"""
    if not subject:
        return ""
    
    # Convert to lowercase
    normalized = subject.lower().strip()
    
    # Remove common reply/forward prefixes
    while True:
        old_normalized = normalized
        normalized = re.sub(r'^(re:|fw:|fwd:|forward:)\s*', '', normalized)
        if normalized == old_normalized:
            break
    
    # Remove extra whitespace
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    
    return normalized


    return None


def find_thread_by_last_message_id(message_id):
    """Find existing thread by lastMessageId to prevent duplicate threads"""
    threads_table = os.environ.get('EMAIL_THREADS_TABLE')
    if not threads_table:
        print("EMAIL_THREADS_TABLE not configured, skipping lastMessageId search")
        return None
    
    # Normalize the message ID for consistent comparison
    normalized_message_id = normalize_message_id(message_id)
    if not normalized_message_id:
        return None
    
    dynamodb = boto3.client('dynamodb')
    
    try:
        print(f"Threading - Searching for threads with lastMessageId: '{normalized_message_id}'")
        
        # Scan for threads with matching lastMessageId (normalized)
        response = dynamodb.scan(
            TableName=threads_table,
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
        
        # Also search for the original (unnormalized) format in case of existing data
        if '@email.amazonses.com' not in normalized_message_id:
            # Try with SES suffix as well
            ses_format_id = f"{normalized_message_id}@email.amazonses.com"
            
            response_ses = dynamodb.scan(
                TableName=threads_table,
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
            
            # Combine results
            all_items = response.get('Items', []) + response_ses.get('Items', [])
        else:
            all_items = response.get('Items', [])
        
        # Return the first matching thread
        if all_items:
            thread_id = all_items[0]['threadId']['S']
            print(f"Threading - Found existing thread by lastMessageId '{normalized_message_id}': {thread_id}")
            return thread_id
    
    except Exception as e:
        print(f"Threading - Error finding thread by lastMessageId: {str(e)}")
    
    return None


def find_thread_by_subject_and_participants(subject, participants):
    """Find existing thread by normalized subject and participants with improved matching"""
    threads_table = os.environ.get('EMAIL_THREADS_TABLE')
    if not threads_table:
        print("EMAIL_THREADS_TABLE not configured, skipping thread search")
        return None

    dynamodb = boto3.client('dynamodb')
    normalized_subject = normalize_subject(subject)

    if not normalized_subject:
        print("No normalized subject available for thread matching")
        return None

    try:
        # Normalize and sort participants for consistent comparison
        normalized_participants = sorted([email.lower().strip() for email in participants if email])
        print(f"Threading - Searching for subject: '{normalized_subject}', participants: {normalized_participants}")

        # Scan for threads with matching subject
        response = dynamodb.scan(
            TableName=threads_table,
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

        # Check each thread for participant match
        for item in response.get('Items', []):
            thread_participants = item.get('participants', {}).get('SS', [])
            thread_participants_normalized = sorted([p.lower().strip() for p in thread_participants])
            
            print(f"Threading - Comparing with thread {item['threadId']['S']}: participants {thread_participants_normalized}")

            # Check if participants have sufficient overlap (at least one common participant)
            common_participants = set(normalized_participants) & set(thread_participants_normalized)
            if common_participants:
                thread_id = item['threadId']['S']
                print(f"Threading - Found matching thread {thread_id} with common participants: {list(common_participants)}")
                return thread_id

        print(f"Threading - No matching thread found for subject '{normalized_subject}' and participants {normalized_participants}")

    except Exception as e:
        print(f"Error finding thread by subject and participants: {str(e)}")

    return None
def create_email_thread(participants, subject, created_by, primary_customer_email=None):
    """Create a new email thread with enhanced validation and logging"""
    threads_table = os.environ.get('EMAIL_THREADS_TABLE')
    print(f"Threading - create_email_thread called with:")
    print(f"Threading - threads_table: '{threads_table}'")
    print(f"Threading - participants: {participants}")
    print(f"Threading - subject: '{subject}'")
    print(f"Threading - created_by: '{created_by}'")
    print(f"Threading - primary_customer_email: '{primary_customer_email}'")
    
    if not threads_table:
        print("Threading - ERROR: EMAIL_THREADS_TABLE not configured, skipping thread creation")
        return None

    dynamodb = boto3.client('dynamodb')
    thread_id = str(uuid.uuid4())

    try:
        # Normalize participants
        unique_participants = list(set(email.lower().strip() for email in participants if email))
        normalized_subject = normalize_subject(subject)
        
        print(f"Threading - Creating new thread:")
        print(f"Threading - Thread ID: {thread_id}")
        print(f"Threading - Subject: '{subject}' -> Normalized: '{normalized_subject}'")
        print(f"Threading - Participants: {unique_participants}")
        print(f"Threading - Created by: {created_by}")

        # Determine customer email (first non-staff email)
        our_email = os.environ.get('MAIL_FROM_ADDRESS', '').lower()
        customer_email = primary_customer_email
        if not customer_email:
            for participant in unique_participants:
                if participant != our_email:
                    customer_email = participant
                    break

        print(f"Threading - Customer email determined: '{customer_email}'")

        # Create TTL (2 years from now for threads, longer than emails since threads are metadata)
        ttl = int((datetime.now(ZoneInfo('Australia/Perth')).timestamp()) + (2 * 365 * 24 * 60 * 60))
        created_timestamp = int(datetime.now(ZoneInfo('Australia/Perth')).timestamp() * 1000)

        item = {
            'threadId': {'S': thread_id},
            'normalizedSubject': {'S': normalized_subject},
            'originalSubject': {'S': subject},
            'participants': {'SS': unique_participants},
            'createdBy': {'S': created_by.lower() if created_by else ''},
            'primaryCustomerEmail': {'S': customer_email.lower() if customer_email else ''},
            'messageCount': {'N': '0'},
            'lastMessageId': {'S': ''},
            'lastActivityDate': {'S': datetime.now(ZoneInfo('Australia/Perth')).isoformat()},
            'isActive': {'BOOL': True},
            'ttl': {'N': str(ttl)},
            'createdAt': {'N': str(created_timestamp)},
            'updatedAt': {'S': datetime.now(ZoneInfo('Australia/Perth')).isoformat()}
        }

        print(f"Threading - About to create DynamoDB item: {item}")
        
        put_result = dynamodb.put_item(TableName=threads_table, Item=item)
        print(f"Threading - DynamoDB put_item result: {put_result}")
        print(f"Threading - Successfully created new email thread: {thread_id}")
        return thread_id

    except Exception as e:
        print(f"Threading - ERROR: Exception in create_email_thread: {str(e)}")
        print(f"Threading - Exception type: {type(e).__name__}")
        import traceback
        print(f"Threading - Full traceback: {traceback.format_exc()}")
        return None
def update_thread_activity(thread_id, latest_message_id):
    """Update thread with latest activity with enhanced logging"""
    print(f"Threading - update_thread_activity called with thread_id='{thread_id}', message_id='{latest_message_id}'")
    
    if not thread_id:
        print("Threading - ERROR: No thread ID provided for activity update")
        return
    
    # Normalize the message ID for consistency
    normalized_message_id = normalize_message_id(latest_message_id)
    print(f"Threading - Normalized message ID: '{latest_message_id}' -> '{normalized_message_id}'")
    
    if not normalized_message_id:
        print(f"Threading - ERROR: Message ID normalization failed for: '{latest_message_id}'")
        return
    
    dynamodb = boto3.client('dynamodb')
    threads_table = os.environ.get('EMAIL_THREADS_TABLE')
    
    print(f"Threading - EMAIL_THREADS_TABLE environment variable: '{threads_table}'")
    
    if not threads_table:
        print("Threading - ERROR: EMAIL_THREADS_TABLE not configured, skipping thread update")
        return
    
    try:
        print(f"Threading - Attempting to update thread {thread_id} with latest message {normalized_message_id}")
        
        # Always increment the count when update_thread_activity is called
        # The calling code should ensure this function is only called once per new message
        update_result = dynamodb.update_item(
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
            },
            ReturnValues='ALL_NEW'  # Return the updated item
        )
        
        # Log the updated messageCount
        updated_count = update_result.get('Attributes', {}).get('messageCount', {}).get('N', 'UNKNOWN')
        print(f"Threading - SUCCESS: Updated thread {thread_id}, new messageCount: {updated_count}")
        print(f"Threading - DynamoDB response: {update_result}")
        
    except Exception as e:
        print(f"Threading - ERROR: Failed to update thread activity for thread {thread_id}: {str(e)}")
        print(f"Threading - Exception type: {type(e).__name__}")
        import traceback
        print(f"Threading - Full traceback: {traceback.format_exc()}")
        
        print(f"Threading - Successfully updated thread activity: {thread_id} with message: {normalized_message_id}")
        
    except Exception as e:
        print(f"Threading - Error updating thread activity for thread {thread_id}: {str(e)}")


def check_and_merge_duplicate_threads(message_id):
    """Check for and merge duplicate threads that share the same lastMessageId"""
    threads_table = os.environ.get('EMAIL_THREADS_TABLE')
    email_table = os.environ.get('EMAIL_METADATA_TABLE')
    
    if not threads_table or not email_table:
        print("Threading - Tables not configured, skipping duplicate thread check")
        return
    
    # Normalize the message ID for consistent comparison
    normalized_message_id = normalize_message_id(message_id)
    if not normalized_message_id:
        return
    
    dynamodb = boto3.client('dynamodb')
    
    try:
        print(f"Threading - Checking for duplicate threads with lastMessageId: '{normalized_message_id}'")
        
        # Find all threads with the same normalized lastMessageId
        all_matching_threads = []
        
        # Search for normalized format
        response = dynamodb.scan(
            TableName=threads_table,
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
        all_matching_threads.extend(response.get('Items', []))
        
        # Also search for SES format if not already included
        if '@email.amazonses.com' not in normalized_message_id:
            ses_format_id = f"{normalized_message_id}@email.amazonses.com"
            response_ses = dynamodb.scan(
                TableName=threads_table,
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
            all_matching_threads.extend(response_ses.get('Items', []))
        
        # Remove duplicates based on threadId
        unique_threads = {}
        for thread in all_matching_threads:
            thread_id = thread['threadId']['S']
            if thread_id not in unique_threads:
                unique_threads[thread_id] = thread
        
        duplicate_threads = list(unique_threads.values())
        
        if len(duplicate_threads) > 1:
            print(f"Threading - Found {len(duplicate_threads)} duplicate threads with lastMessageId: {normalized_message_id}")
            
            # Sort by creation date to find the earliest thread (keep this one)
            duplicate_threads.sort(key=lambda x: x.get('createdAt', {}).get('S', ''))
            primary_thread = duplicate_threads[0]
            duplicate_thread_ids = [t['threadId']['S'] for t in duplicate_threads[1:]]
            
            primary_thread_id = primary_thread['threadId']['S']
            print(f"Threading - Keeping primary thread: {primary_thread_id}")
            print(f"Threading - Merging duplicate threads: {duplicate_thread_ids}")
            
            # Update emails in duplicate threads to point to the primary thread
            for dup_thread_id in duplicate_thread_ids:
                try:
                    # Find all emails in the duplicate thread
                    email_response = dynamodb.scan(
                        TableName=email_table,
                        FilterExpression='#threadId = :threadId',
                        ExpressionAttributeNames={'#threadId': 'threadId'},
                        ExpressionAttributeValues={':threadId': {'S': dup_thread_id}}
                    )
                    
                    # Update each email to point to the primary thread
                    for email_item in email_response.get('Items', []):
                        email_message_id = email_item.get('messageId', {}).get('S', '')
                        if email_message_id:
                            dynamodb.update_item(
                                TableName=email_table,
                                Key={'messageId': {'S': email_message_id}},
                                UpdateExpression='SET #threadId = :primaryThreadId, #updatedAt = :updatedAt',
                                ExpressionAttributeNames={
                                    '#threadId': 'threadId',
                                    '#updatedAt': 'updatedAt'
                                },
                                ExpressionAttributeValues={
                                    ':primaryThreadId': {'S': primary_thread_id},
                                    ':updatedAt': {'S': datetime.now(ZoneInfo('Australia/Perth')).isoformat()}
                                }
                            )
                            print(f"Threading - Moved email {email_message_id} from thread {dup_thread_id} to {primary_thread_id}")
                    
                    # Deactivate the duplicate thread
                    dynamodb.update_item(
                        TableName=threads_table,
                        Key={'threadId': {'S': dup_thread_id}},
                        UpdateExpression='SET #isActive = :isActive, #updatedAt = :updatedAt',
                        ExpressionAttributeNames={
                            '#isActive': 'isActive',
                            '#updatedAt': 'updatedAt'
                        },
                        ExpressionAttributeValues={
                            ':isActive': {'BOOL': False},
                            ':updatedAt': {'S': datetime.now(ZoneInfo('Australia/Perth')).isoformat()}
                        }
                    )
                    print(f"Threading - Deactivated duplicate thread: {dup_thread_id}")
                    
                except Exception as merge_error:
                    print(f"Threading - Error merging thread {dup_thread_id}: {str(merge_error)}")
            
            print(f"Threading - Completed merge of duplicate threads for message: {normalized_message_id}")
        else:
            print(f"Threading - No duplicate threads found for message: {normalized_message_id}")
        
    except Exception as e:
        print(f"Threading - Error checking for duplicate threads: {str(e)}")
