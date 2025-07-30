import os
import stripe
import time
import db_utils as db
import response_utils as resp
import request_utils as req

# Set Stripe secret key from environment
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')

def lambda_handler(event, context):
    try:
        # Authenticate user
        user_id = req.get_body_param(event, 'userId')
        if not user_id:
            return resp.error_response("Authentication required", 401)
        
        # Get request parameters
        payment_intent_id = req.get_body_param(event, 'paymentIntentId')
        
        # Validate required parameters
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
        
        # Verify the payment belongs to the user
        if payment_record.get('userId') != user_id:
            return resp.error_response("Unauthorized access to payment", 403)
        
        # Get the reference number and type from payment record
        reference_number = payment_record.get('referenceNumber')
        payment_type = payment_record.get('type')
        
        # Get the actual record (appointment or order)
        if payment_type == 'appointment':
            record = db.get_appointment(reference_number)
        else:  # order
            record = db.get_order(reference_number)
        
        if not record:
            return resp.error_response(f"{payment_type.capitalize()} not found", 404)
        
        # Update payment record status if not already updated
        if payment_record.get('status') != 'succeeded':
            payment_update_data = {
                'status': 'succeeded',
                'updatedAt': int(time.time())
            }
            db.update_payment_by_intent_id(payment_intent_id, payment_update_data)
        
        # Update the appointment/order record if not already updated
        if record.get('paymentStatus') != 'paid':
            update_data = {
                'paymentStatus': 'paid',
                'paidAt': int(time.time()),
                'paymentAmount': float(payment_intent.amount) / 100,  # Convert cents to dollars
                'updatedAt': int(time.time())
            }
            
            if payment_type == 'appointment':
                db.update_appointment(reference_number, update_data)
            else:
                db.update_order(reference_number, update_data)
        
        return resp.success_response({
            "referenceNumber": reference_number,
            "type": payment_type,
            "amount": payment_intent.amount,
            "paymentStatus": "paid"
        })
        
    except Exception as e:
        print(f"Error in confirm payment success lambda: {str(e)}")
        return resp.error_response("Internal server error", 500)
