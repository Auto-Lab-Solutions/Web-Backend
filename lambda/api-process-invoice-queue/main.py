import json
import os
import sys
import time

# Add the common_lib directory to the Python path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'common_lib'))

import db_utils as db
import invoice_utils as invc

def lambda_handler(event, context):
    """
    Process invoice generation requests from SQS queue
    """
    try:
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
                
                # Generate the invoice
                invoice_result = invc.create_invoice_for_order_or_appointment(
                    order_or_appointment_record, 
                    record_type, 
                    payment_intent_id
                )
                
                if invoice_result.get('success'):
                    invoice_url = invoice_result.get('invoice_url')
                    reference_number = order_or_appointment_record.get(f'{record_type}Id')
                    
                    # Update the record with invoice URL
                    invoice_update = {
                        'invoiceUrl': invoice_url, 
                        'updatedAt': int(time.time())
                    }
                    
                    if record_type == 'appointment':
                        update_success = db.update_appointment(reference_number, invoice_update)
                    else:
                        update_success = db.update_order(reference_number, invoice_update)
                    
                    if update_success:
                        print(f"Invoice generated and record updated successfully: {invoice_url}")
                    else:
                        print(f"Invoice generated but failed to update record: {reference_number}")
                else:
                    print(f"Failed to generate invoice: {invoice_result.get('error')}")
                    
            except Exception as record_error:
                print(f"Error processing SQS record: {str(record_error)}")
                # Don't raise exception to avoid re-processing the same failed message
                continue
        
        return {
            'statusCode': 200,
            'body': json.dumps('Invoice processing completed')
        }
        
    except Exception as e:
        print(f"Error in invoice processing handler: {str(e)}")
        # Raise exception to trigger SQS retry mechanism
        raise e
