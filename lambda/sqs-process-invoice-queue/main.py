import json
import os
import sys
import time

# Add common_lib to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'common_lib'))

import db_utils as db
import invoice_utils as invc
import email_utils as email
import response_utils as resp
import business_logic_utils as biz
from notification_manager import invoice_manager


@biz.handle_business_logic_error
def lambda_handler(event, context):
    """
    Process invoice generation requests from SQS queue using enhanced manager pattern
    """
    try:
        print(f"Processing {len(event.get('Records', []))} invoice generation requests")
        
        processed_count = 0
        failed_count = 0
        
        # Process each SQS record
        for record in event.get('Records', []):
            try:
                # Parse the message
                message_body = json.loads(record['body'])
                
                # Extract data from message
                order_or_appointment_record = message_body['record']
                record_type = message_body['record_type']
                payment_intent_id = message_body['payment_intent_id']
                
                print(f"Processing invoice generation for {record_type} - Payment Intent: {payment_intent_id}")
                
                # Use invoice manager for processing
                success = invoice_manager.process_invoice_generation(
                    record=order_or_appointment_record,
                    record_type=record_type,
                    payment_intent_id=payment_intent_id
                )
                
                if success:
                    processed_count += 1
                    print(f"Successfully processed invoice for {record_type}")
                else:
                    failed_count += 1
                    print(f"Failed to process invoice for {record_type}")
                    
            except json.JSONDecodeError as e:
                failed_count += 1
                print(f"Failed to parse SQS message body as JSON: {str(e)}")
            except Exception as e:
                failed_count += 1
                print(f"Error processing invoice generation record: {str(e)}")
                # Continue processing other records even if one fails
        
        print(f"Invoice processing completed - Processed: {processed_count}, Failed: {failed_count}")
        
        # Return success response using standard response format
        return resp.success_response({
            'message': f'Successfully processed {processed_count} invoice generation requests',
            'processed': processed_count,
            'failed': failed_count,
            'total_messages': len(event.get('Records', []))
        })
        
    except Exception as e:
        print(f"Critical error in invoice processing: {str(e)}")
        raise biz.BusinessLogicError(f"Invoice processing failed: {str(e)}", 500)


