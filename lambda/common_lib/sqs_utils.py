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
            result = generate_invoice_synchronously(record, record_type, payment_intent_id)
            return result.get('success', False)
            
    except Exception as e:
        print(f"Error queuing invoice generation: {str(e)}")
        # Fallback to synchronous processing on queue error
        result = generate_invoice_synchronously(record, record_type, payment_intent_id)
        return result.get('success', False)

def generate_invoice_synchronously(record, record_type, payment_intent_id):
    """Generate invoice synchronously for manual transactions and API calls"""
    try:
        import invoice_utils as invc
        import db_utils as db
        
        # Check if this is a manual transaction (from api-generate-invoice)
        if record_type == "invoice" and payment_intent_id and (
            payment_intent_id.startswith('cash_') or 
            payment_intent_id.startswith('bank_transfer_')
        ):
            # Use the new API data creation function for manual transactions
            invoice_result = create_invoice_from_api_data(record)
            
            if invoice_result.get('success'):
                print(f"Manual invoice generated synchronously: {invoice_result.get('file_url')}")
                
                # Return detailed invoice result for API responses
                return {
                    'success': True,
                    'invoice_result': invoice_result
                }
            else:
                print(f"Failed to generate manual invoice: {invoice_result.get('error')}")
                return {
                    'success': False,
                    'error': invoice_result.get('error', 'Unknown error')
                }
        else:
            # Use existing logic for appointment/order records
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
                
                # Return detailed invoice result for API responses
                return {
                    'success': True,
                    'invoice_result': invoice_result
                }
            else:
                print(f"Failed to generate invoice: {invoice_result.get('error')}")
                return {
                    'success': False,
                    'error': invoice_result.get('error', 'Unknown error')
                }
            
    except Exception as e:
        print(f"Error in synchronous invoice generation: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }

def create_invoice_from_api_data(record_data):
    """
    Create invoice directly from API record data structure
    
    Args:
        record_data (dict): Record data from api-generate-invoice
        
    Returns:
        dict: Invoice generation result
    """
    try:
        import invoice_utils as invc
        
        # Create invoice generator
        generator = invc.InvoiceGenerator()
        
        # Use generate_invoice_from_payment which now supports the API data structure
        result = generator.generate_invoice_from_payment(record_data)
        
        return result
        
    except Exception as e:
        print(f"Error creating invoice from API data: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }
