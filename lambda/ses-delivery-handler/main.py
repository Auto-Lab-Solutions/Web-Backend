import json
import os
import logging

# Add common_lib to the path
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'common_lib'))

from email_suppression_manager import EmailSuppressionManager

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

def lambda_handler(event, context):
    """
    Process SES delivery notifications for analytics
    """
    logger.info(f"Processing SES delivery notification: {json.dumps(event, default=str)}")
    
    processed_count = 0
    error_count = 0
    
    try:
        # Process each SNS record
        for record in event.get('Records', []):
            try:
                # Parse SNS message
                sns_message = json.loads(record['Sns']['Message'])
                
                # Validate that this is a delivery notification
                if sns_message.get('notificationType') != 'Delivery':
                    logger.warning(f"Received non-delivery notification: {sns_message.get('notificationType')}")
                    continue
                
                # Process the delivery
                success = process_delivery_notification(sns_message)
                
                if success:
                    processed_count += 1
                    logger.info("Successfully processed delivery notification")
                else:
                    error_count += 1
                    logger.error("Failed to process delivery notification")
                    
            except Exception as e:
                error_count += 1
                logger.error(f"Error processing SNS record: {str(e)}", exc_info=True)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'Processed {processed_count} delivery notifications, {error_count} errors',
                'processed': processed_count,
                'errors': error_count
            })
        }
        
    except Exception as e:
        logger.error(f"Error processing delivery notifications: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Failed to process delivery notifications',
                'details': str(e)
            })
        }

def process_delivery_notification(notification):
    """
    Process a single delivery notification
    """
    try:
        delivery_info = notification.get('delivery', {})
        mail_info = notification.get('mail', {})
        
        timestamp = delivery_info.get('timestamp')
        processing_time_millis = delivery_info.get('processingTimeMillis')
        recipients = delivery_info.get('recipients', [])
        smtp_response = delivery_info.get('smtpResponse')
        reporting_mta = delivery_info.get('reportingMTA')
        remote_mta_ip = delivery_info.get('remoteMtaIp')
        
        message_id = mail_info.get('messageId')
        source_email = mail_info.get('source')
        
        logger.info(f"Processing delivery: recipients={len(recipients)}, processing_time={processing_time_millis}ms")
        
        # Process each delivered recipient
        for email_address in recipients:
            if not email_address:
                logger.warning("Delivery recipient missing email address")
                continue
            
            # Record delivery analytics using EmailSuppressionManager
            EmailSuppressionManager._record_delivery_analytics(
                email_address=email_address,
                timestamp=timestamp,
                processing_time_millis=processing_time_millis,
                smtp_response=smtp_response,
                reporting_mta=reporting_mta,
                remote_mta_ip=remote_mta_ip,
                message_id=message_id,
                source_email=source_email
            )
            
            logger.debug(f"Recorded successful delivery for: {email_address}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error processing delivery notification: {str(e)}", exc_info=True)
        return False
