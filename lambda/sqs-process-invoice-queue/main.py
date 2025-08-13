import json
import time
import db_utils as db
import invoice_utils as invc
import email_utils as email


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
                        
                        # Send payment confirmation email after successful invoice generation
                        try:
                            send_payment_confirmation_email_with_invoice(
                                order_or_appointment_record, 
                                record_type, 
                                invoice_url,
                                payment_intent_id
                            )
                        except Exception as email_error:
                            print(f"Error sending payment confirmation email: {str(email_error)}")
                            # Don't fail the invoice processing if email fails
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

def send_payment_confirmation_email_with_invoice(record, record_type, invoice_url, payment_intent_id):
    """Send payment confirmation email with invoice after successful generation"""
    try:
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
        raise e
