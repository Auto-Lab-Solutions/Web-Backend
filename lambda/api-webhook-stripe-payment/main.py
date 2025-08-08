import os
import time
import json
import stripe
import db_utils as db
import response_utils as resp
import wsgw_utils as wsgw
import sqs_utils as sqs

# Set Stripe configuration
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET')
wsgw_client = wsgw.get_apigateway_client()

def lambda_handler(event, context):
    try:
        # Get the raw body and signature
        payload = event.get('body', '')
        signature_header = event.get('headers', {}).get('Stripe-Signature', '')
        
        if not payload or not signature_header:
            return resp.error_response("Missing payload or signature", 400)
        
        # Verify the webhook signature
        try:
            stripe_event = stripe.Webhook.construct_event(
                payload, signature_header, STRIPE_WEBHOOK_SECRET
            )
        except ValueError:
            print("Invalid payload")
            return resp.error_response("Invalid payload", 400)
        except stripe.error.SignatureVerificationError:
            print("Invalid signature")
            return resp.error_response("Invalid signature", 400)
        
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
        
    except Exception as e:
        print(f"Error in Stripe webhook handler: {str(e)}")
        return resp.error_response("Internal server error", 500)

def handle_payment_succeeded(payment_intent):
    """Handle successful payment"""
    try:
        payment_intent_id = payment_intent['id']
        
        # Update payment record
        payment_update_data = {
            'status': 'paid',
            'receiptUrl': payment_intent.get('charges', {}).get('data', [{}])[0].get('receipt_url'),
            'stripePaymentMethodId': payment_intent.get('payment_method'),
            'updatedAt': int(time.time())
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
            'paidAt': int(time.time()),
            'paymentMethod': 'stripe',
            'paymentAmount': float(payment_intent['amount']) / 100,  # Convert cents to dollars
            'updatedAt': int(time.time())
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
                    sqs.queue_invoice_generation(record, payment_type, payment_intent_id)
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
            'updatedAt': int(time.time())
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
            'updatedAt': int(time.time())
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
            'updatedAt': int(time.time())
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
            'updatedAt': int(time.time())
        }
        
        if payment_type == 'appointment':
            success = db.update_appointment(reference_number, update_data)
            record = db.get_appointment(reference_number)
        else:  # order
            success = db.update_order(reference_number, update_data)
            record = db.get_order(reference_number)
        
        if success and record:
            # Send notification
            send_payment_notification(record, payment_type, 'cancelled')
        
    except Exception as e:
        print(f"Error handling payment canceled: {str(e)}")

def send_payment_notification(record, record_type, status):
    """Send payment status notification via WebSocket"""
    try:
        print(f"Payment notification: {record_type} {record.get(f'{record_type}Id')} status changed to {status}")
        receiverConnections = []
        # Notify customer
        customer_user_id = record.get('createdUserId')
        if customer_user_id:
            customer_connection = db.get_connection_by_user_id(customer_user_id)
            if customer_connection:
                receiverConnections.append(customer_connection)
        # Notify all staff
        staff_connections = db.get_all_staff_connections()
        receiverConnections.extend(staff_connections)

        for connection in receiverConnections:
            wsgw.send_notification(wsgw_client, connection.get('connectionId'), {
                "type": record_type,
                "subtype": "payment-status",
                "success": True if status == 'paid' else False,
                "referenceNumber": record.get(f'{record_type}Id'),
                "paymentStatus": status
            })

    except Exception as e:
        print(f"Error logging payment notification: {str(e)}")



