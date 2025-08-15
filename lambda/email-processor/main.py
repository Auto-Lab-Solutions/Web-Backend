import json, boto3, os, email, uuid
from datetime import datetime
from botocore.exceptions import ClientError

# AWS clients
s3_client = boto3.client('s3')
dynamodb = boto3.client('dynamodb')
ses_client = boto3.client('ses')

# Environment variables
EMAIL_STORAGE_BUCKET = os.environ.get('EMAIL_STORAGE_BUCKET')
EMAIL_METADATA_TABLE = os.environ.get('EMAIL_METADATA_TABLE')

# ------------------  Email Processing Functions ------------------

def lambda_handler(event, context):
    """
    Lambda handler for processing incoming emails stored in S3 by SES
    """
    try:
        print(f"Processing email event: {json.dumps(event)}")
        
        # Process each record in the event
        for record in event.get('Records', []):
            if record.get('eventSource') == 'aws:s3':
                process_s3_email_event(record)
            elif record.get('eventSource') == 'aws:ses':
                process_ses_email_event(record)
        
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
        
        print(f"Processing email from S3: {bucket_name}/{object_key}")
        
        # Download email from S3
        response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
        email_content = response['Body'].read()
        
        # Parse email
        parsed_email = email.message_from_bytes(email_content)
        
        # Extract email metadata
        metadata = extract_email_metadata(parsed_email, object_key, bucket_name)
        
        # Store metadata in DynamoDB
        store_email_metadata(metadata)
        
        print(f"Successfully processed email: {metadata['message_id']}")
        
    except Exception as e:
        print(f"Error processing S3 email event: {str(e)}")
        raise

def process_ses_email_event(record):
    """Process email directly from SES event"""
    try:
        ses_record = record['ses']
        mail = ses_record['mail']
        
        # Create metadata from SES event
        metadata = {
            'message_id': mail['messageId'],
            'to_email': ', '.join([dest['address'] for dest in mail['commonHeaders']['to']]),
            'from_email': mail['commonHeaders']['from'][0],
            'subject': mail['commonHeaders']['subject'],
            'received_date': mail['timestamp'],
            's3_bucket': EMAIL_STORAGE_BUCKET,
            's3_key': f"emails/{mail['messageId']}",
            'size_bytes': 0,
            'has_attachments': False,
            'is_read': False,
            'tags': [],
            'created_at': datetime.utcnow().isoformat() + 'Z'
        }
        
        # Store metadata in DynamoDB
        store_email_metadata(metadata)
        
        print(f"Successfully processed SES email event: {metadata['message_id']}")
        
    except Exception as e:
        print(f"Error processing SES email event: {str(e)}")
        raise

def extract_email_metadata(parsed_email, s3_key, s3_bucket):
    """Extract metadata from parsed email"""
    try:
        # Generate unique email ID
        email_id = str(uuid.uuid4())
        
        # Extract basic headers
        to_email = parsed_email.get('To', '')
        from_email = parsed_email.get('From', '')
        subject = parsed_email.get('Subject', '')
        date_received = parsed_email.get('Date', datetime.utcnow().strftime('%a, %d %b %Y %H:%M:%S %z'))
        
        # Parse date to ISO format
        try:
            from email.utils import parsedate_to_datetime
            parsed_date = parsedate_to_datetime(date_received)
            iso_date = parsed_date.isoformat()
        except:
            iso_date = datetime.utcnow().isoformat() + 'Z'
        
        # Check for attachments
        has_attachments = False
        attachment_count = 0
        
        for part in parsed_email.walk():
            if part.get_content_disposition() == 'attachment':
                has_attachments = True
                attachment_count += 1
        
        # Extract email body
        body_text = ""
        body_html = ""
        
        for part in parsed_email.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                body_text = part.get_payload(decode=True).decode('utf-8', errors='ignore')
            elif content_type == "text/html":
                body_html = part.get_payload(decode=True).decode('utf-8', errors='ignore')
        
        # Get file size from S3 object
        try:
            head_response = s3_client.head_object(Bucket=s3_bucket, Key=s3_key)
            size_bytes = head_response['ContentLength']
        except:
            size_bytes = 0
        
        metadata = {
            'message_id': email_id,
            'to_email': to_email,
            'from_email': from_email,
            'subject': subject,
            'timestamp': int(datetime.utcnow().timestamp()),
            's3_key': s3_key,
            'size': size_bytes,
            'has_attachments': has_attachments,
            'type': 'received',
            'status': 'processed'
        }
        
        return metadata
        
    except Exception as e:
        print(f"Error extracting email metadata: {str(e)}")
        raise

def store_email_metadata(metadata):
    """Store email metadata in DynamoDB"""
    try:
        # Create metadata in proper format for DynamoDB
        result = create_email_metadata(metadata)
        if result:
            print(f"Stored email metadata: {metadata['message_id']}")
        else:
            print(f"Failed to store email metadata: {metadata['message_id']}")
        
    except Exception as e:
        print(f"Error storing email metadata: {str(e)}")
        raise

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
            'type': {'S': metadata_data.get('type', 'received')},
            'status': {'S': metadata_data.get('status', 'processed')}
        }
        
        # Add optional fields
        optional_fields = ['s3_key', 'size', 'reply_to', 'cc', 'bcc', 'has_attachments']
        for field in optional_fields:
            if metadata_data.get(field) is not None:
                if field in ['size', 'timestamp']:
                    item[field] = {'N': str(metadata_data[field])}
                elif field == 'has_attachments':
                    item[field] = {'BOOL': metadata_data[field]}
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

def get_email_content(s3_bucket, s3_key):
    """Retrieve full email content from S3"""
    try:
        response = s3_client.get_object(Bucket=s3_bucket, Key=s3_key)
        email_content = response['Body'].read()
        return email.message_from_bytes(email_content)
    except Exception as e:
        print(f"Error retrieving email content: {str(e)}")
        raise

if __name__ == "__main__":
    # For local testing
    test_event = {
        "Records": [{
            "eventSource": "aws:s3",
            "s3": {
                "bucket": {"name": "test-bucket"},
                "object": {"key": "emails/test-email"}
            }
        }]
    }
    
    print(lambda_handler(test_event, None))
