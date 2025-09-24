import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo
import json
import stripe
import db_utils as db
import response_utils as resp
import business_logic_utils as biz
import validation_utils as val
from exceptions import ValidationError, BusinessLogicError
from notification_manager import notification_manager, invoice_manager

# Set Stripe configuration
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET')

@val.handle_validation_error
@biz.handle_business_logic_error
def lambda_handler(event, context):
    # Get the raw body and signature
    payload = event.get('body', '')
    signature_header = event.get('headers', {}).get('Stripe-Signature', '')
    
    if not payload or not signature_header:
        raise ValidationError("Missing payload or signature")
    
    # Verify the webhook signature
    try:
        stripe_event = stripe.Webhook.construct_event(
            payload, signature_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        print("Invalid payload")
        raise ValidationError("Invalid payload")
    except stripe.error.SignatureVerificationError:
        print("Invalid signature")
        raise ValidationError("Invalid signature")
    
    # Handle the event
    if stripe_event['type'] == 'payment_intent.succeeded':
        handle_payment_succeeded(stripe_event['data']['object'])
    elif stripe_event['type'] == 'payment_intent.payment_failed':
        handle_payment_failed(stripe_event['data']['object'])
    elif stripe_event['type'] == 'payment_intent.canceled':
        handle_payment_canceled(stripe_event['data']['object'])
    else:
        print(f'Unhandled event type: {stripe_event["type"]}')
    
    return resp.success_response({"message": "Webhook processed successfully"})

def handle_payment_succeeded(payment_intent):
    """Handle successful payment"""
    try:
        payment_intent_id = payment_intent['id']
        
        # Update payment record
        payment_update_data = {
            'status': 'paid',
            'receiptUrl': payment_intent.get('charges', {}).get('data', [{}])[0].get('receipt_url'),
            'stripePaymentMethodId': payment_intent.get('payment_method'),
            'updatedAt': int(datetime.now(ZoneInfo('Australia/Perth')).timestamp())
        }
        
        success = db.update_payment_by_intent_id(payment_intent_id, payment_update_data)
        if not success:
            print(f"Failed to update payment record for intent {payment_intent_id}")
            return
        
        # Get payment record to get reference details
        payment_record = db.get_payment_by_intent_id(payment_intent_id)
        if not payment_record:
            print(f"Payment record not found for intent {payment_intent_id}")
            return
        
        reference_number = payment_record.get('referenceNumber')
        payment_type = payment_record.get('type') 
        
        # Update the appointment/order record
        update_data = {
            'paymentStatus': 'paid',
            'paidAt': int(datetime.now(ZoneInfo('Australia/Perth')).timestamp()),
            'paymentMethod': 'stripe',
            'paymentAmount': float(payment_intent['amount']) / 100,  # Convert cents to dollars
            'updatedAt': int(datetime.now(ZoneInfo('Australia/Perth')).timestamp())
        }
        
        if payment_type == 'appointment':
            success = db.update_appointment(reference_number, update_data)
            record = db.get_appointment(reference_number)
        else:  # order
            success = db.update_order(reference_number, update_data)
            record = db.get_order(reference_number)

        print("Success: ", success, "\nRecord: ", record, "\n")
        
        if success and record:
            # Queue invoice generation asynchronously for faster webhook response
            if record.get('paymentStatus') == 'paid':
                try:
                    invoice_manager.queue_invoice_generation(record, payment_type, payment_intent_id)
                    print(f"Invoice generation queued for {payment_type} {reference_number}")
                except Exception as e:
                    print(f"Error queuing invoice generation: {str(e)}")
            
            # Send notification
            send_payment_notification(record, payment_type, 'paid')
        
    except Exception as e:
        print(f"Error handling payment succeeded: {str(e)}")

def handle_payment_failed(payment_intent):
    """Handle failed payment"""
    try:
        payment_intent_id = payment_intent['id']
        
        # Update payment record
        payment_update_data = {
            'status': 'failed',
            'updatedAt': int(datetime.now(ZoneInfo('Australia/Perth')).timestamp())
        }
        
        success = db.update_payment_by_intent_id(payment_intent_id, payment_update_data)
        if not success:
            print(f"Failed to update payment record for intent {payment_intent_id}")
            return
        
        # Get payment record to get reference details
        payment_record = db.get_payment_by_intent_id(payment_intent_id)
        if not payment_record:
            print(f"Payment record not found for intent {payment_intent_id}")
            return
        
        reference_number = payment_record.get('referenceNumber')
        payment_type = payment_record.get('type')
        
        # Update the appointment/order record
        update_data = {
            'paymentStatus': 'failed',
            'updatedAt': int(datetime.now(ZoneInfo('Australia/Perth')).timestamp())
        }
        
        if payment_type == 'appointment':
            success = db.update_appointment(reference_number, update_data)
            record = db.get_appointment(reference_number)
        else:  # order
            success = db.update_order(reference_number, update_data)
            record = db.get_order(reference_number)
        
        if success and record:
            # Send notification
            send_payment_notification(record, payment_type, 'failed')
        
    except Exception as e:
        print(f"Error handling payment failed: {str(e)}")

def handle_payment_canceled(payment_intent):
    """Handle canceled payment"""
    try:
        payment_intent_id = payment_intent['id']
        
        # Update payment record
        payment_update_data = {
            'status': 'cancelled',
            'updatedAt': int(datetime.now(ZoneInfo('Australia/Perth')).timestamp())
        }
        
        success = db.update_payment_by_intent_id(payment_intent_id, payment_update_data)
        if not success:
            print(f"Failed to update payment record for intent {payment_intent_id}")
            return
        
        # Get payment record to get reference details
        payment_record = db.get_payment_by_intent_id(payment_intent_id)
        if not payment_record:
            print(f"Payment record not found for intent {payment_intent_id}")
            return
        
        reference_number = payment_record.get('referenceNumber')
        payment_type = payment_record.get('type')
        
        # Update the appointment/order record
        update_data = {
            'paymentStatus': 'cancelled',
            'updatedAt': int(datetime.now(ZoneInfo('Australia/Perth')).timestamp())
        }
        
        if payment_type == 'appointment':
            success = db.update_appointment(reference_number, update_data)
            record = db.get_appointment(reference_number)
        else:  # order
            success = db.update_order(reference_number, update_data)
            record = db.get_order(reference_number)
        
        if success and record:
            # Cancel associated invoices when Stripe payment is cancelled
            cancelled_invoices = []
            try:
                invoices = db.get_invoices_by_reference(reference_number, payment_type)
                cancelled_invoice_count = 0
                for invoice in invoices:
                    # Only cancel active invoices (not already cancelled)
                    if invoice.get('status') != 'cancelled':
                        invoice_success = db.cancel_invoice(invoice.get('invoiceId'))
                        if invoice_success:
                            cancelled_invoice_count += 1
                            cancelled_invoices.append(invoice.get('invoiceId'))
                            print(f"Cancelled invoice {invoice.get('invoiceId')} for cancelled Stripe payment {reference_number}")
                        else:
                            print(f"Failed to cancel invoice {invoice.get('invoiceId')} for cancelled Stripe payment {reference_number}")
                
                if cancelled_invoice_count > 0:
                    print(f"Cancelled {cancelled_invoice_count} invoices for cancelled Stripe payment {reference_number}")
            except Exception as e:
                print(f"Error cancelling invoices for cancelled Stripe payment {reference_number}: {str(e)}")
                # Don't fail the webhook processing if invoice cancellation fails
            
            # Send WebSocket notification
            send_payment_notification(record, payment_type, 'cancelled')
            
            # Send payment cancellation email notification
            try:
                send_payment_cancellation_notification(record, payment_type, reference_number, cancelled_invoices)
            except Exception as e:
                print(f"Error sending payment cancellation email: {str(e)}")
                # Don't fail the webhook processing if email notification fails
        
    except Exception as e:
        print(f"Error handling payment canceled: {str(e)}")

def send_payment_notification(record, record_type, status):
    """Send payment status notification via WebSocket and Firebase using PaymentManager"""
    try:
        from payment_manager import PaymentManager
        
        print(f"Payment notification: {record_type} {record.get(f'{record_type}Id')} status changed to {status}")
        
        # Use PaymentManager's notification method
        reference_id = record.get(f'{record_type}Id')
        PaymentManager._send_payment_confirmation_notifications(record, record_type, 'stripe', reference_id)
        
    except Exception as e:
        print(f"Error queueing payment notification: {str(e)}")


def send_payment_cancellation_notification(record, record_type, reference_id, cancelled_invoices=None):
    """Send payment cancellation email notification"""
    try:
        from notification_manager import queue_payment_cancellation_email
        import time
        
        # Get customer information from record
        customer_email = None
        customer_name = None
        
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
        
        # Send email notification if customer email is available
        if customer_email and customer_name:
            # Prepare payment data for email
            payment_data = {
                'referenceNumber': reference_id,
                'amount': record.get('totalPrice', record.get('price', '0.00')),
                'paymentMethod': 'Stripe',
                'cancellationDate': datetime.now(ZoneInfo('Australia/Perth')).strftime('%d/%m/%Y'),
                'cancellationReason': 'Stripe payment was cancelled'
            }
            
            # Add cancelled invoice ID if available
            if cancelled_invoices and len(cancelled_invoices) > 0:
                # Use the first cancelled invoice ID
                payment_data['cancelledInvoiceId'] = cancelled_invoices[0]
            
            # Queue cancellation email
            queue_payment_cancellation_email(customer_email, customer_name, payment_data)
            print(f"Payment cancellation email queued for {customer_email}")
        else:
            print(f"Warning: No customer email found for {record_type} {reference_id}, skipping email notification")
            
    except Exception as e:
        print(f"Error sending payment cancellation email notification: {str(e)}")

