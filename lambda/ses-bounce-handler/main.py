import json
import boto3
import os
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from botocore.exceptions import ClientError

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
ses_client = boto3.client('ses')

# Environment variables
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'production')
SUPPRESSION_TABLE_NAME = os.environ.get('SUPPRESSION_TABLE_NAME')
ANALYTICS_TABLE_NAME = os.environ.get('ANALYTICS_TABLE_NAME')
MAIL_FROM_ADDRESS = os.environ.get('MAIL_FROM_ADDRESS', 'noreply@autolabsolutions.com')

# DynamoDB tables
suppression_table = dynamodb.Table(SUPPRESSION_TABLE_NAME)
analytics_table = dynamodb.Table(ANALYTICS_TABLE_NAME)

# Bounce types that should result in permanent suppression
PERMANENT_BOUNCE_TYPES = [
    'Permanent',
    'Undetermined'  # Treat undetermined as permanent to be safe
]

PERMANENT_BOUNCE_SUBTYPES = [
    'General',
    'NoEmail', 
    'Suppressed',
    'OnAccountSuppressionList'
]

def lambda_handler(event, context):
    """
    Process SES bounce notifications and manage email suppression list
    """
    logger.info(f"Processing SES bounce notification: {json.dumps(event, default=str)}")
    
    processed_count = 0
    error_count = 0
    
    try:
        # Process each SNS record
        for record in event.get('Records', []):
            try:
                # Parse SNS message
                sns_message = json.loads(record['Sns']['Message'])
                
                # Validate that this is a bounce notification
                if sns_message.get('notificationType') != 'Bounce':
                    logger.warning(f"Received non-bounce notification: {sns_message.get('notificationType')}")
                    continue
                
                # Process the bounce
                success = process_bounce_notification(sns_message)
                
                if success:
                    processed_count += 1
                    logger.info("Successfully processed bounce notification")
                else:
                    error_count += 1
                    logger.error("Failed to process bounce notification")
                    
            except Exception as e:
                error_count += 1
                logger.error(f"Error processing SNS record: {str(e)}", exc_info=True)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'Processed {processed_count} bounce notifications, {error_count} errors',
                'processed': processed_count,
                'errors': error_count
            })
        }
        
    except Exception as e:
        logger.error(f"Error processing bounce notifications: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Failed to process bounce notifications',
                'details': str(e)
            })
        }

def process_bounce_notification(notification):
    """
    Process a single bounce notification
    """
    try:
        bounce_info = notification.get('bounce', {})
        mail_info = notification.get('mail', {})
        
        bounce_type = bounce_info.get('bounceType')
        bounce_subtype = bounce_info.get('bounceSubType')
        bounced_recipients = bounce_info.get('bouncedRecipients', [])
        timestamp = bounce_info.get('timestamp')
        message_id = mail_info.get('messageId')
        source_email = mail_info.get('source')
        
        logger.info(f"Processing bounce: type={bounce_type}, subtype={bounce_subtype}, recipients={len(bounced_recipients)}")
        
        # Process each bounced recipient
        for recipient in bounced_recipients:
            email_address = recipient.get('emailAddress')
            status = recipient.get('status')
            diagnostic_code = recipient.get('diagnosticCode')
            action = recipient.get('action')
            
            if not email_address:
                logger.warning("Bounced recipient missing email address")
                continue
            
            # Record bounce analytics
            record_bounce_analytics(
                email_address=email_address,
                bounce_type=bounce_type,
                bounce_subtype=bounce_subtype,
                status=status,
                diagnostic_code=diagnostic_code,
                action=action,
                timestamp=timestamp,
                message_id=message_id,
                source_email=source_email
            )
            
            # Handle suppression based on bounce type
            if should_suppress_email(bounce_type, bounce_subtype):
                suppress_email_address(
                    email_address=email_address,
                    reason='bounce',
                    bounce_type=bounce_type,
                    bounce_subtype=bounce_subtype,
                    timestamp=timestamp,
                    diagnostic_code=diagnostic_code
                )
                
                # Add to SES account-level suppression list
                add_to_ses_suppression_list(email_address, 'BOUNCE')
                
                logger.info(f"Suppressed email address due to permanent bounce: {email_address}")
            else:
                logger.info(f"Recorded transient bounce for: {email_address}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error processing bounce notification: {str(e)}", exc_info=True)
        return False

def should_suppress_email(bounce_type, bounce_subtype):
    """
    Determine if an email should be suppressed based on bounce type/subtype
    """
    if bounce_type in PERMANENT_BOUNCE_TYPES:
        return True
    
    if bounce_subtype in PERMANENT_BOUNCE_SUBTYPES:
        return True
    
    return False

def record_bounce_analytics(email_address, bounce_type, bounce_subtype, status, 
                          diagnostic_code, action, timestamp, message_id, source_email):
    """
    Record bounce analytics in DynamoDB
    """
    try:
        current_time = datetime.utcnow()
        iso_timestamp = current_time.isoformat() + 'Z'
        date_partition = current_time.strftime('%Y-%m-%d')
        
        # TTL: keep analytics data for 2 years
        ttl = int((current_time + timedelta(days=730)).timestamp())
        
        analytics_item = {
            'email': email_address,
            'timestamp': iso_timestamp,
            'event_type': 'bounce',
            'date_partition': date_partition,
            'bounce_type': bounce_type,
            'bounce_subtype': bounce_subtype or 'Unknown',
            'status': status or 'Unknown',
            'diagnostic_code': diagnostic_code or 'Unknown',
            'action': action or 'Unknown',
            'message_id': message_id,
            'source_email': source_email,
            'environment': ENVIRONMENT,
            'ttl': ttl,
            'created_at': iso_timestamp
        }
        
        analytics_table.put_item(Item=analytics_item)
        logger.info(f"Recorded bounce analytics for {email_address}")
        
    except Exception as e:
        logger.error(f"Error recording bounce analytics: {str(e)}", exc_info=True)

def suppress_email_address(email_address, reason, bounce_type=None, bounce_subtype=None, 
                          timestamp=None, diagnostic_code=None):
    """
    Add email address to suppression list
    """
    try:
        current_time = datetime.utcnow()
        iso_timestamp = current_time.isoformat() + 'Z'
        
        # TTL: keep suppression for 1 year for bounces
        ttl = int((current_time + timedelta(days=365)).timestamp())
        
        suppression_item = {
            'email': email_address,
            'suppression_type': reason,
            'created_at': iso_timestamp,
            'bounce_type': bounce_type,
            'bounce_subtype': bounce_subtype,
            'diagnostic_code': diagnostic_code,
            'original_timestamp': timestamp or iso_timestamp,
            'environment': ENVIRONMENT,
            'ttl': ttl,
            'status': 'active'
        }
        
        suppression_table.put_item(Item=suppression_item)
        logger.info(f"Added {email_address} to suppression list for {reason}")
        
    except Exception as e:
        logger.error(f"Error adding email to suppression list: {str(e)}", exc_info=True)

def add_to_ses_suppression_list(email_address, reason):
    """
    Add email address to SES account-level suppression list
    """
    try:
        ses_client.put_suppressed_destination(
            EmailAddress=email_address,
            Reason=reason
        )
        logger.info(f"Added {email_address} to SES suppression list")
        
    except ClientError as e:
        error_code = e.response['Error']['Code']
        if error_code == 'AlreadyExistsException':
            logger.info(f"Email {email_address} already in SES suppression list")
        else:
            logger.error(f"Error adding to SES suppression list: {error_code} - {e.response['Error']['Message']}")
    except Exception as e:
        logger.error(f"Unexpected error adding to SES suppression list: {str(e)}", exc_info=True)

def check_bounce_rate():
    """
    Check current bounce rate and log warnings if too high
    """
    try:
        # Get bounce rate from SES
        response = ses_client.get_send_statistics()
        
        if response.get('SendDataPoints'):
            latest_stats = response['SendDataPoints'][-1]
            bounces = latest_stats.get('Bounces', 0)
            delivery_attempts = latest_stats.get('DeliveryAttempts', 1)
            
            bounce_rate = (bounces / delivery_attempts) * 100 if delivery_attempts > 0 else 0
            
            logger.info(f"Current bounce rate: {bounce_rate:.2f}%")
            
            # AWS SES threshold is 5% for bounces
            if bounce_rate > 4.0:  # Warning at 4%
                logger.warning(f"High bounce rate detected: {bounce_rate:.2f}% (AWS limit is 5%)")
            
            return bounce_rate
        
    except Exception as e:
        logger.error(f"Error checking bounce rate: {str(e)}", exc_info=True)
    
    return None
