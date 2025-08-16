import json
import os

from email_manager import EmailManager

def lambda_handler(event, context):
    """
    Lambda handler for processing incoming emails stored in S3 by SES
    """
    try:
        print(f"Processing email event: {json.dumps(event)}")
        
        # Initialize managers
        email_manager = EmailManager()
        
        # Process each record in the event
        for record in event.get('Records', []):
            if record.get('eventSource') == 'aws:s3':
                process_s3_email_event(email_manager, record)
            elif record.get('eventSource') == 'aws:ses':
                process_ses_email_event(email_manager, record)
        
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


def process_s3_email_event(email_manager, record):
    """Process email when it's stored in S3 by SES"""
    try:
        # Extract S3 information
        bucket_name = record['s3']['bucket']['name']
        object_key = record['s3']['object']['key']
        
        print(f"Processing email from S3: {bucket_name}/{object_key}")
        
        # Use EmailManager to process the S3 email
        result = email_manager.process_s3_email(bucket_name, object_key)
        
        if result['success']:
            print(f"Successfully processed email: {result['message_id']}")
        else:
            print(f"Failed to process email: {result['error']}")
            raise Exception(result['error'])
        
    except Exception as e:
        print(f"Error processing S3 email event: {str(e)}")
        raise


def process_ses_email_event(email_manager, record):
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
            's3_bucket': os.environ.get('EMAIL_STORAGE_BUCKET'),
            's3_key': f"emails/{mail['messageId']}",
            'size_bytes': 0,
            'has_attachments': False,
            'is_read': False,
            'tags': []
        }
        
        # Use EmailManager to store metadata
        result = email_manager.store_email_metadata(metadata)
        
        if result['success']:
            print(f"Successfully processed SES email event: {metadata['message_id']}")
        else:
            print(f"Failed to process SES email event: {result['error']}")
            raise Exception(result['error'])
        
    except Exception as e:
        print(f"Error processing SES email event: {str(e)}")
        raise
