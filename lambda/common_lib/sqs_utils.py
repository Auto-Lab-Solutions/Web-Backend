import os
import time
import json
import boto3

# Initialize SQS client for async invoice generation
sqs_client = boto3.client('sqs')
INVOICE_QUEUE_URL = os.environ.get('INVOICE_QUEUE_URL')

def queue_invoice_generation(record, record_type, payment_intent_id):
    """Queue invoice generation for asynchronous processing"""
    try:
        # Prepare message for SQS queue
        message_body = {
            'record': record,
            'record_type': record_type,
            'payment_intent_id': payment_intent_id,
            'timestamp': int(time.time())
        }
        
        # Send message to SQS queue
        if INVOICE_QUEUE_URL:
            response = sqs_client.send_message(
                QueueUrl=INVOICE_QUEUE_URL,
                MessageBody=json.dumps(message_body),
                MessageAttributes={
                    'RecordType': {
                        'StringValue': record_type,
                        'DataType': 'String'
                    },
                    'PaymentIntentId': {
                        'StringValue': payment_intent_id,
                        'DataType': 'String'
                    }
                }
            )
            print(f"Invoice generation queued with MessageId: {response.get('MessageId')}")
            return True
        else:
            print("Warning: INVOICE_QUEUE_URL not configured, falling back to synchronous processing")
            # Fallback to synchronous processing
            return generate_invoice_synchronously(record, record_type, payment_intent_id)
            
    except Exception as e:
        print(f"Error queuing invoice generation: {str(e)}")
        # Fallback to synchronous processing on queue error
        return generate_invoice_synchronously(record, record_type, payment_intent_id)

def generate_invoice_synchronously(record, record_type, payment_intent_id):
    """Fallback synchronous invoice generation"""
    try:
        import invoice_utils as invc
        import db_utils as db
        
        # For manual payments (cash, bank transfers), we might not have payment_intent_id in the original function signature
        if payment_intent_id and (payment_intent_id.startswith('cash_') or payment_intent_id.startswith('bank_transfer_')):
            invoice_result = invc.create_invoice_for_order_or_appointment(record, record_type)
        else:
            invoice_result = invc.create_invoice_for_order_or_appointment(record, record_type, payment_intent_id)
        
        if invoice_result.get('success'):
            invoice_url = invoice_result.get('invoice_url')
            reference_number = record.get(f'{record_type}Id')
            
            # Update the record with invoice URL
            invoice_update = {'invoiceUrl': invoice_url, 'updatedAt': int(time.time())}
            if record_type == 'appointment':
                db.update_appointment(reference_number, invoice_update)
            else:
                db.update_order(reference_number, invoice_update)
            print(f"Invoice generated synchronously: {invoice_url}")
            return True
        else:
            print(f"Failed to generate invoice: {invoice_result.get('error')}")
            return False
            
    except Exception as e:
        print(f"Error in synchronous invoice generation: {str(e)}")
        return False
