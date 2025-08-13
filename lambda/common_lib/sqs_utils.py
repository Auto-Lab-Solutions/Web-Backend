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

        if record_type == "invoice" and payment_intent_id and (
            payment_intent_id.startswith('cash_') or 
            payment_intent_id.startswith('bank_transfer_')
        ):
            invoice_result = invc.generate_invoice_for_payment(record)
        elif payment_intent_id and (payment_intent_id.startswith('cash_') or payment_intent_id.startswith('bank_transfer_')):
            invoice_result = invc.create_invoice_for_order_or_appointment(record, record_type)
        else:
            invoice_result = invc.create_invoice_for_order_or_appointment(record, record_type, payment_intent_id)
        
        if invoice_result.get('success'):
            invoice_url = invoice_result.get('invoice_url')
            print(f"Invoice generated synchronously: {invoice_url}")
            reference_number = record.get(f'{record_type}Id', '')
            
            if (record_type == 'appointment' or record_type == 'order') and reference_number:
                # Update the record with invoice URL
                invoice_update = {'invoiceUrl': invoice_url, 'updatedAt': int(time.time())}
                if record_type == 'appointment':
                    db.update_appointment(reference_number, invoice_update)
                else:
                    db.update_order(reference_number, invoice_update)
                
                # Send payment confirmation email after successful invoice generation
                try:
                    send_payment_confirmation_email_with_invoice(record, record_type, invoice_url, payment_intent_id)
                except Exception as email_error:
                    print(f"Error sending payment confirmation email: {str(email_error)}")
                    # Don't fail the invoice generation if email fails
            
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

def send_payment_confirmation_email_with_invoice(record, record_type, invoice_url, payment_intent_id):
    """Send payment confirmation email with invoice after successful generation"""
    try:
        import email_utils as email
        
        # Get customer information from record
        if record_type == 'order':
            # For orders, get customer data directly from the record
            customer_email = record.get('customerEmail')
            customer_name = record.get('customerName', 'Valued Customer')
        else:  # appointment
            # For appointments, check if it's a buyer or seller
            is_buyer = record.get('isBuyer', True)
            if is_buyer:
                customer_email = record.get('buyerEmail')
                customer_name = record.get('buyerName', 'Valued Customer')
            else:
                customer_email = record.get('sellerEmail')
                customer_name = record.get('sellerName', 'Valued Customer')
        
        # Validate customer email
        if not customer_email:
            print(f"No customer email found in {record_type} record")
            return
        
        # Determine payment method from payment_intent_id
        payment_method = 'Card'  # Default for Stripe payments
        if payment_intent_id and payment_intent_id.startswith('cash_'):
            payment_method = 'Cash'
        elif payment_intent_id and payment_intent_id.startswith('bank_transfer_'):
            payment_method = 'Bank Transfer'
        
        # Prepare payment data for email
        payment_data = {
            'amount': f"{record.get('price', 0):.2f}",
            'paymentMethod': payment_method,
            'referenceNumber': record.get(f'{record_type}Id', 'N/A'),
            'paymentDate': record.get('updatedAt', int(time.time())),
            'invoice_url': invoice_url
        }
        
        # Send payment confirmation email with invoice
        email.send_payment_confirmation_email(customer_email, customer_name, payment_data, invoice_url)
        print(f"Payment confirmation email sent to {customer_email} with invoice: {invoice_url}")
        
    except Exception as e:
        print(f"Error sending payment confirmation email: {str(e)}")
        # Don't fail the invoice generation if email fails
