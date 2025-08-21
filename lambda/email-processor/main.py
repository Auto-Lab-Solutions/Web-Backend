import json
import os
import boto3
from datetime import datetime, timezone
from email import message_from_string
from email.utils import parsedate_to_datetime, parseaddr
import hashlib
import re

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
        
        # Store metadata in DynamoDB
        store_email_metadata(email_metadata)
        
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
        
        bcc_header = email_message.get('Bcc', '')
        bcc_emails = [parseaddr(addr)[1] for addr in bcc_header.split(',') if addr.strip()] if bcc_header else []
        
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
        tags = generate_email_tags(email_message, body_text, body_html)
        
        # Create TTL (1 year from now)
        ttl = int((datetime.now(timezone.utc).timestamp()) + (365 * 24 * 60 * 60))
        
        return {
            'messageId': message_id,
            'fromEmail': from_email.lower() if from_email else '',
            'fromName': from_name or '',
            'toEmails': [email.lower() for email in to_emails],
            'ccEmails': [email.lower() for email in cc_emails],
            'bccEmails': [email.lower() for email in bcc_emails],
            'subject': email_message.get('Subject', ''),
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
            'createdAt': datetime.now(timezone.utc).isoformat(),
            'updatedAt': datetime.now(timezone.utc).isoformat()
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
        # Convert metadata to DynamoDB format
        item = {
            'messageId': {'S': metadata['messageId']},
            'fromEmail': {'S': metadata['fromEmail']},
            'fromName': {'S': metadata['fromName']},
            'toEmails': {'SS': metadata['toEmails']} if metadata['toEmails'] else {'SS': ['']},
            'ccEmails': {'SS': metadata['ccEmails']} if metadata['ccEmails'] else {'SS': ['']},
            'bccEmails': {'SS': metadata['bccEmails']} if metadata['bccEmails'] else {'SS': ['']},
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
            'tags': {'SS': metadata['tags']} if metadata['tags'] else {'SS': ['']},
            'ttl': {'N': str(metadata['ttl'])},
            'createdAt': {'S': metadata['createdAt']},
            'updatedAt': {'S': metadata['updatedAt']}
        }
        
        dynamodb.put_item(
            TableName=table_name,
            Item=item
        )
        
        print(f"Successfully stored metadata for message: {metadata['messageId']}")
        
    except Exception as e:
        print(f"Error storing email metadata: {str(e)}")
        raise
