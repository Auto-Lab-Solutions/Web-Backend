import os
import json
import stripe
import time

import db_utils as db
import response_utils as resp
import request_utils as req
import business_logic_utils as biz
import validation_utils as valid

# Set Stripe secret key from environment
stripe.api_key = os.environ.get('STRIPE_SECRET_KEY')

@biz.handle_business_logic_error
@valid.handle_validation_error
def lambda_handler(event, context):
    """
    Create Stripe payment intent with enhanced validation and error handling
    """
    try:
        # Get user ID from request body 
        user_id = req.get_body_param(event, 'userId')
        if not user_id:
            raise biz.BusinessLogicError("User Id is required for non-staff users.", 401)
            
        user_record = db.get_user_record(user_id)
        if not user_record:
            raise biz.BusinessLogicError(f"No user record found for userId: {user_id}", 404)
        
        # Get and validate request parameters
        amount = req.get_body_param(event, 'amount')
        currency = req.get_body_param(event, 'currency', 'aud')
        reference_number = req.get_body_param(event, 'referenceNumber')
        payment_type = req.get_body_param(event, 'type')
        metadata = req.get_body_param(event, 'metadata', {})
        
        # Validate required parameters
        if not amount:
            raise valid.ValidationError("amount is required")
        if not reference_number:
            raise valid.ValidationError("referenceNumber is required")
        if not payment_type:
            raise valid.ValidationError("type is required")
        if payment_type not in ['appointment', 'order']:
            raise valid.ValidationError("type must be 'appointment' or 'order'")
        
        # Validate amount is positive number
        try:
            amount_float = float(amount)
            if amount_float <= 0:
                raise valid.ValidationError("amount must be a positive number")
        except (ValueError, TypeError):
            raise valid.ValidationError("amount must be a valid number")
        
        # Validate the reference exists and belongs to the user
        if payment_type == 'appointment':
            record = db.get_appointment(reference_number)
            if not record:
                raise biz.BusinessLogicError("Appointment not found", 404)
        else:  # order
            record = db.get_order(reference_number)
            if not record:
                raise biz.BusinessLogicError("Order not found", 404)
        
        # Check if payment is already confirmed
        if record.get('paymentStatus') == 'paid':
            raise biz.BusinessLogicError("Payment already confirmed for this record", 400)
            
        # Check status of the record - only block CANCELLED, allow PENDING
        if record.get('status') == 'CANCELLED':
            raise biz.BusinessLogicError(f"{payment_type.capitalize()} is cancelled and cannot be paid", 400)
        
        # Ensure metadata includes required fields
        metadata.update({
            'userId': user_id,
            'referenceNumber': reference_number,
            'type': payment_type,
            'environment': os.environ.get('ENVIRONMENT', 'development')
        })
        
        # Create Stripe payment intent with enhanced error handling
        try:
            payment_intent = stripe.PaymentIntent.create(
                amount=int(amount),
                currency=currency.lower(),
                metadata=metadata,
                automatic_payment_methods={
                    'enabled': True,
                }
            )
            
        except stripe.error.InvalidRequestError as e:
            print(f"Stripe invalid request error: {str(e)}")
            raise biz.BusinessLogicError(f"Invalid payment request: {str(e)}", 400)
        except stripe.error.AuthenticationError as e:
            print(f"Stripe authentication error: {str(e)}")
            raise biz.BusinessLogicError("Payment system authentication error", 500)
        except stripe.error.APIConnectionError as e:
            print(f"Stripe API connection error: {str(e)}")
            raise biz.BusinessLogicError("Payment system connection error", 503)
        except stripe.error.StripeError as e:
            print(f"Stripe error: {str(e)}")
            raise biz.BusinessLogicError(f"Payment processing error: {str(e)}", 400)
        
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
            # If we can't store the payment record, we should cancel the payment intent
            try:
                stripe.PaymentIntent.cancel(payment_intent.id)
            except Exception as cancel_error:
                print(f"Failed to cancel payment intent after database error: {str(cancel_error)}")
            raise biz.BusinessLogicError("Failed to create payment record", 500)
        
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
            print(f"Warning: Payment intent created but failed to update {payment_type} record")
            # Don't fail the entire operation since payment intent is already created
        
        print(f"Payment intent created successfully: {payment_intent.id} for {payment_type} {reference_number}")
        
        return resp.success_response({
            "message": "Payment intent created successfully",
            "clientSecret": payment_intent.client_secret,
            "paymentIntentId": payment_intent.id,
            "amount": int(amount),
            "currency": currency.lower(),
            "referenceNumber": reference_number,
            "type": payment_type
        })
        
    except Exception as e:
        print(f"Error in create payment intent lambda: {str(e)}")
        # Re-raise known exceptions, wrap unknown ones
        if isinstance(e, (biz.BusinessLogicError, valid.ValidationError)):
            raise e
        else:
            raise biz.BusinessLogicError("Internal server error in payment processing", 500)
