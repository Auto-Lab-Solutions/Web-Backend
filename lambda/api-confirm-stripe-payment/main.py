import os
import time
import stripe
import db_utils as db
import response_utils as resp
import request_utils as req
import wsgw_utils as wsgw

# Set Stripe secret key from environment
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')

wsgw_client = wsgw.get_apigateway_client()

def lambda_handler(event, context):
    try:
        # Get request parameters
        payment_intent_id = req.get_body_param(event, 'paymentIntentId')
        if not payment_intent_id:
            return resp.error_response("paymentIntentId is required")

        # Verify the payment intent with Stripe
        try:
            payment_intent = stripe.PaymentIntent.retrieve(payment_intent_id)
            if payment_intent.status != 'succeeded':
                return resp.error_response("Payment has not been completed successfully")
        except stripe.error.StripeError as e:
            print(f"Stripe error retrieving payment intent: {str(e)}")
            return resp.error_response("Invalid payment intent", 400)
        
        # Get payment record from database
        payment_record = db.get_payment_by_intent_id(payment_intent_id)
        if not payment_record:
            return resp.error_response("Payment record not found", 404)
        
        # Get the reference number and type from payment record
        reference_number = payment_record.get('referenceNumber')
        payment_type = payment_record.get('type')
        
        # Get the existing record
        if payment_type == 'appointment':
            existing_record = db.get_appointment(reference_number)
            if not existing_record:
                return resp.error_response("Appointment not found", 404)
        else:  # order
            existing_record = db.get_order(reference_number)
            if not existing_record:
                return resp.error_response("Order not found", 404)
        
        # Check if payment is already confirmed
        if existing_record.get('paymentStatus') == 'paid':
            return resp.success_response({
                "message": "Payment already confirmed for this record",
            }, success=False)
        
        # Verify the payment intent ID matches
        if existing_record.get('paymentIntentId') != payment_intent_id:
            return resp.error_response("Payment intent ID does not match record")
        
        # Update payment record in database
        payment_update_data = {
            'status': 'paid',
            'updatedAt': int(time.time())
        }
        success = db.update_payment_by_intent_id(payment_intent_id, payment_update_data)
        if not success:
            print("Warning: Failed to update payment record")
        
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
            updated_record = db.get_appointment(reference_number)
        else:
            success = db.update_order(reference_number, update_data)
            updated_record = db.get_order(reference_number)
        
        if not success:
            return resp.error_response("Failed to confirm payment", 500)
        
        # Generate invoice after successful payment confirmation
        invoice_url = None
        if updated_record.get('paymentStatus') == 'paid':
            try:
                from invoice_utils import create_invoice_for_order_or_appointment
                invoice_result = create_invoice_for_order_or_appointment(updated_record, payment_type, payment_intent_id)
                
                if invoice_result.get('success'):
                    invoice_url = invoice_result.get('invoice_url')
                    # Update the record with invoice URL
                    invoice_update = {'invoiceUrl': invoice_url, 'updatedAt': int(time.time())}
                    if payment_type == 'appointment':
                        db.update_appointment(reference_number, invoice_update)
                    else:
                        db.update_order(reference_number, invoice_update)
                    print(f"Invoice generated successfully: {invoice_url}")
                else:
                    print(f"Failed to generate invoice: {invoice_result.get('error')}")
            except Exception as e:
                print(f"Error generating invoice: {str(e)}")
        
        # Send payment confirmation notification
        send_payment_confirmation_notification(updated_record, payment_type)
        
        return resp.success_response({
            "message": "Payment confirmed successfully",
            "referenceNumber": reference_number,
            "paymentStatus": "paid",
            "invoiceUrl": invoice_url,
            "updatedAt": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        })
        
    except Exception as e:
        print(f"Error in confirm payment lambda: {str(e)}")
        return resp.error_response("Internal server error", 500)

def send_payment_confirmation_notification(record, record_type, status='paid'):
    """Send payment confirmation notification"""
    try:
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
                "success": True,
                "referenceNumber": record.get(f'{record_type}Id'),
                "paymentStatus": "paid"
            })
    except Exception as e:
        print(f"Error sending payment confirmation notification: {str(e)}")
