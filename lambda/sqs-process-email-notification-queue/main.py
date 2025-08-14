import json
import traceback
import db_utils as db
import email_utils as email

def lambda_handler(event, context):
    """
    Process email notification requests from SQS queue
    """
    processed = 0
    failed = 0
    
    try:
        # Process each SQS record
        for record in event.get('Records', []):
            try:
                # Parse the message
                message_body = json.loads(record['body'])
                
                # Extract notification data from message
                notification_type = message_body['notification_type']
                customer_email = message_body['customer_email']
                customer_name = message_body['customer_name']
                data = message_body['data']
                
                print(f"Processing email notification: {notification_type} for {customer_email}")
                
                # Route to appropriate email function based on notification type
                success = send_email_notification(notification_type, customer_email, customer_name, data)
                
                if success:
                    processed += 1
                    print(f"Successfully sent {notification_type} email to {customer_email}")
                else:
                    failed += 1
                    print(f"Failed to send {notification_type} email to {customer_email}")
                    
            except Exception as e:
                failed += 1
                print(f"Error processing email notification record: {str(e)}")
                print(f"Traceback: {traceback.format_exc()}")
                # Continue processing other records even if one fails
                continue
        
        print(f"Email notification processing complete. Processed: {processed}, Failed: {failed}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'Processed {processed} email notifications, {failed} failed',
                'processed': processed,
                'failed': failed
            })
        }
        
    except Exception as e:
        print(f"Error in email notification processor lambda: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': 'Internal server error'})
        }

def send_email_notification(notification_type, customer_email, customer_name, data):
    """
    Route email notifications to appropriate email utility functions
    """
    try:
        if notification_type == 'appointment_created':
            return email.send_appointment_created_email(customer_email, customer_name, data)
            
        elif notification_type == 'appointment_updated':
            changes = data.get('changes')
            update_type = data.get('update_type', 'general')
            return email.send_appointment_updated_email(customer_email, customer_name, data, changes, update_type)
            
        elif notification_type == 'order_created':
            return email.send_order_created_email(customer_email, customer_name, data)
            
        elif notification_type == 'order_updated':
            changes = data.get('changes')
            update_type = data.get('update_type', 'general')
            return email.send_order_updated_email(customer_email, customer_name, data, changes, update_type)
            
        elif notification_type == 'report_ready':
            report_url = data.get('report_url')
            return email.send_report_ready_email(customer_email, customer_name, data, report_url)
            
        elif notification_type == 'payment_confirmed':
            invoice_url = data.get('invoice_url')
            return email.send_payment_confirmation_email(customer_email, customer_name, data, invoice_url)
            
        else:
            print(f"Unknown email notification type: {notification_type}")
            return False
            
    except Exception as e:
        print(f"Error sending {notification_type} email: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        return False
