import json
import os
import sys
import logging

# Add common_lib to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'common_lib'))

from email_suppression_manager import EmailSuppressionManager

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Process SES complaint notifications and manage email suppression list
    """
    logger.info(f"Processing SES complaint notification: {json.dumps(event, default=str)}")
    
    processed_count = 0
    error_count = 0
    
    try:
        # Process each SNS record
        for record in event.get('Records', []):
            try:
                # Parse SNS message
                sns_message = json.loads(record['Sns']['Message'])
                
                # Validate that this is a complaint notification
                if sns_message.get('notificationType') != 'Complaint':
                    logger.warning(f"Received non-complaint notification: {sns_message.get('notificationType')}")
                    continue
                
                # Process the complaint
                success = process_complaint_notification(sns_message)
                
                if success:
                    processed_count += 1
                    logger.info("Successfully processed complaint notification")
                else:
                    error_count += 1
                    logger.error("Failed to process complaint notification")
                    
            except Exception as e:
                error_count += 1
                logger.error(f"Error processing SNS record: {str(e)}", exc_info=True)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'Processed {processed_count} complaint notifications, {error_count} errors',
                'processed': processed_count,
                'errors': error_count
            })
        }
        
    except Exception as e:
        logger.error(f"Error processing complaint notifications: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Failed to process complaint notifications',
                'details': str(e)
            })
        }

def process_complaint_notification(notification):
    """
    Process a single complaint notification
    """
    try:
        complaint_info = notification.get('complaint', {})
        mail_info = notification.get('mail', {})
        
        complained_recipients = complaint_info.get('complainedRecipients', [])
        complaint_feedback_type = complaint_info.get('complaintFeedbackType')
        complaint_subtype = complaint_info.get('complaintSubType')
        timestamp = complaint_info.get('timestamp')
        feedback_id = complaint_info.get('feedbackId')
        user_agent = complaint_info.get('userAgent')
        arrival_date = complaint_info.get('arrivalDate')
        
        message_id = mail_info.get('messageId')
        source_email = mail_info.get('source')
        
        logger.info(f"Processing complaint: type={complaint_feedback_type}, subtype={complaint_subtype}, recipients={len(complained_recipients)}")
        
        # Process each complained recipient
        for recipient in complained_recipients:
            email_address = recipient.get('emailAddress')
            
            if not email_address:
                logger.warning("Complained recipient missing email address")
                continue
            
            # Record complaint analytics
            record_complaint_analytics(
                email_address=email_address,
                complaint_feedback_type=complaint_feedback_type,
                complaint_subtype=complaint_subtype,
                timestamp=timestamp,
                feedback_id=feedback_id,
                user_agent=user_agent,
                arrival_date=arrival_date,
                message_id=message_id,
                source_email=source_email
            )
            
            # Always suppress emails that generate complaints
            # Complaints are serious and should always result in suppression
            suppress_email_address(
                email_address=email_address,
                reason='complaint',
                complaint_type=complaint_feedback_type,
                complaint_subtype=complaint_subtype,
                timestamp=timestamp,
                feedback_id=feedback_id
            )
            
            # Add to SES account-level suppression list
            add_to_ses_suppression_list(email_address, 'COMPLAINT')
            
            logger.info(f"Suppressed email address due to complaint: {email_address}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error processing complaint notification: {str(e)}", exc_info=True)
        return False

def record_complaint_analytics(email_address, complaint_feedback_type, complaint_subtype,
                              timestamp, feedback_id, user_agent, arrival_date, 
                              message_id, source_email):
    """
    Record complaint analytics in DynamoDB
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
            'event_type': 'complaint',
            'date_partition': date_partition,
            'complaint_feedback_type': complaint_feedback_type or 'Unknown',
            'complaint_subtype': complaint_subtype or 'Unknown',
            'feedback_id': feedback_id,
            'user_agent': user_agent or 'Unknown',
            'arrival_date': arrival_date or iso_timestamp,
            'message_id': message_id,
            'source_email': source_email,
            'environment': ENVIRONMENT,
            'ttl': ttl,
            'created_at': iso_timestamp
        }
        
        analytics_table.put_item(Item=analytics_item)
        logger.info(f"Recorded complaint analytics for {email_address}")
        
    except Exception as e:
        logger.error(f"Error recording complaint analytics: {str(e)}", exc_info=True)

def suppress_email_address(email_address, reason, complaint_type=None, complaint_subtype=None,
                          timestamp=None, feedback_id=None):
    """
    Add email address to suppression list due to complaint
    """
    try:
        current_time = datetime.utcnow()
        iso_timestamp = current_time.isoformat() + 'Z'
        
        # TTL: keep suppression for 2 years for complaints (longer than bounces)
        ttl = int((current_time + timedelta(days=730)).timestamp())
        
        suppression_item = {
            'email': email_address,
            'suppression_type': reason,
            'created_at': iso_timestamp,
            'complaint_type': complaint_type,
            'complaint_subtype': complaint_subtype,
            'feedback_id': feedback_id,
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

def check_complaint_rate():
    """
    Check current complaint rate and log warnings if too high
    """
    try:
        # Get complaint rate from SES
        response = ses_client.get_send_statistics()
        
        if response.get('SendDataPoints'):
            latest_stats = response['SendDataPoints'][-1]
            complaints = latest_stats.get('Complaints', 0)
            delivery_attempts = latest_stats.get('DeliveryAttempts', 1)
            
            complaint_rate = (complaints / delivery_attempts) * 100 if delivery_attempts > 0 else 0
            
            logger.info(f"Current complaint rate: {complaint_rate:.2f}%")
            
            # AWS SES threshold is 0.1% for complaints
            if complaint_rate > 0.08:  # Warning at 0.08%
                logger.warning(f"High complaint rate detected: {complaint_rate:.2f}% (AWS limit is 0.1%)")
            
            return complaint_rate
        
    except Exception as e:
        logger.error(f"Error checking complaint rate: {str(e)}", exc_info=True)
    
    return None
