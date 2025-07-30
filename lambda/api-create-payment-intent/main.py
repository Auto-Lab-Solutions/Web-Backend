import os
import json
import stripe
import time
import db_utils as db
import response_utils as resp
import request_utils as req
import auth_utils as auth

# Set Stripe secret key from environment
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')

def lambda_handler(event, context):
    try:
        # Get user ID from request body 
        user_id = auth.get_user_id(event)
        if not user_id:
            return resp.error_response("User Id is required for non-staff users.", 401)
        user_record = db.get_user_record(user_id)
        if not user_record:
            return resp.error_response(f"No user record found for userId: {user_id}.")
        
        # Get request parameters
        amount = req.get_body_param(event, 'amount')
        currency = req.get_body_param(event, 'currency', 'aud')
        reference_number = req.get_body_param(event, 'referenceNumber')
        payment_type = req.get_body_param(event, 'type')
        metadata = req.get_body_param(event, 'metadata', {})
        
        # Validate required parameters
        if not amount:
            return resp.error_response("amount is required")
        if not reference_number:
            return resp.error_response("referenceNumber is required")
        if not payment_type:
            return resp.error_response("type is required")
        if payment_type not in ['appointment', 'order']:
            return resp.error_response("type must be 'appointment' or 'order'")
        
        # Validate the reference exists and belongs to the user
        if payment_type == 'appointment':
            record = db.get_appointment(reference_number)
            if not record:
                return resp.error_response("Appointment not found", 404)
            # Check if already paid
            if record.get('paymentStatus') == 'paid':
                return resp.error_response("Payment already completed for this appointment")
        else:  # order
            record = db.get_order(reference_number)
            if not record:
                return resp.error_response("Order not found", 404)
            # Check if already paid
            if record.get('paymentStatus') == 'paid':
                return resp.error_response("Payment already completed for this order")
        
        # Ensure metadata includes required fields
        metadata.update({
            'userId': user_id,
            'referenceNumber': reference_number,
            'type': payment_type
        })
        
        try:
            # Create Stripe payment intent
            payment_intent = stripe.PaymentIntent.create(
                amount=int(amount),
                currency=currency,
                metadata=metadata,
                automatic_payment_methods={
                    'enabled': True,
                }
            )
            
            # Store payment record in database
            payment_data = {
                'paymentIntentId': payment_intent.id,
                'referenceNumber': reference_number,
                'type': payment_type,
                'userId': user_id,
                'amount': float(amount) / 100,  # Convert cents to dollars
                'currency': currency.upper(),
                'status': 'pending',
                'metadata': json.dumps(metadata),
                'createdAt': int(time.time()),
                'updatedAt': int(time.time())
            }
            
            # Create payment record
            success = db.create_payment(payment_data)
            if not success:
                return resp.error_response("Failed to create payment record", 500)
            
            # Update appointment/order with payment intent ID
            update_data = {
                'paymentIntentId': payment_intent.id,
                'paymentStatus': 'pending',
                'updatedAt': int(time.time())
            }
            
            if payment_type == 'appointment':
                success = db.update_appointment(reference_number, update_data)
            else:
                success = db.update_order(reference_number, update_data)
            
            if not success:
                return resp.error_response("Failed to update record with payment intent", 500)
            
            return resp.success_response({
                "clientSecret": payment_intent.client_secret,
                "paymentIntentId": payment_intent.id,
                "amount": int(amount),
                "currency": currency
            })
            
        except stripe.error.StripeError as e:
            print(f"Stripe error: {str(e)}")
            return resp.error_response(f"Payment processing error: {str(e)}", 400)
        
    except Exception as e:
        print(f"Error in create payment intent lambda: {str(e)}")
        return resp.error_response("Internal server error", 500)
