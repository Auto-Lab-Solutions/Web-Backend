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
            
            # Process bounce using EmailSuppressionManager
            result = EmailSuppressionManager.process_bounce(
                email_address, 
                bounce_type, 
                bounce_subtype, 
                notification
            )
            
            if result.get('suppressed'):
                logger.info(f"Suppressed email address due to permanent bounce: {email_address} - {result.get('reason')}")
            else:
                logger.info(f"Recorded transient bounce for: {email_address} - {result.get('reason')}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error processing bounce notification: {str(e)}", exc_info=True)
        return False
