import os
import time
import json
import db_utils as db
import response_utils as resp
import request_utils as req
import wsgw_utils as wsgw
import sqs_utils as sqs

PERMITTED_ROLE = 'ADMIN'

wsgw_client = wsgw.get_apigateway_client()

def lambda_handler(event, context):
    """
    Lambda function to confirm manual payments (cash and bank transfers) for appointments and orders.
    
    This function allows authorized staff to manually confirm payments that were made outside 
    of the Stripe payment system, such as cash payments or bank transfers.
    
    Request Parameters:
    - referenceNumber: The appointment or order ID
    - type: 'appointment' or 'order'
    - paymentMethod: 'cash' or 'bank_transfer' (defaults to 'cash' for backward compatibility)
    - revert: Boolean to revert payment status to pending (optional, defaults to false)
    
    Returns:
    - Success response with updated payment status and method
    - Error response if validation fails or operation cannot be completed
    """
    try:
        # Get staff user information
        staff_user_email = req.get_staff_user_email(event)
        if not staff_user_email:
            return resp.error_response("Unauthorized: Staff authentication required", 401)
        
        staff_user_record = db.get_staff_record(staff_user_email)
        if not staff_user_record:
            return resp.error_response(f"No staff record found for email: {staff_user_email}", 404)
        
        # Convert decimals to handle DynamoDB Decimal objects
        staff_user_record = resp.convert_decimal(staff_user_record)
        
        staff_roles = staff_user_record.get('roles', [])
        staff_user_id = staff_user_record.get('userId')

        if not staff_user_id or not staff_roles:
            return resp.error_response("Unauthorized: Invalid staff user record.")

        if PERMITTED_ROLE not in staff_roles:
            return resp.error_response("Unauthorized: Insufficient permissions.")

        # Get request parameters
        reference_number = req.get_body_param(event, 'referenceNumber')
        payment_type = req.get_body_param(event, 'type')
        payment_method = req.get_body_param(event, 'paymentMethod', 'cash')  # Default to cash for backward compatibility
        revert = req.get_body_param(event, 'revert', False)
        
        # Validate required parameters
        if not reference_number:
            return resp.error_response("referenceNumber is required")
        if not payment_type:
            return resp.error_response("type is required")
        if payment_type not in ['appointment', 'order']:
            return resp.error_response("type must be 'appointment' or 'order'")
        if payment_method not in ['cash', 'bank_transfer']:
            return resp.error_response("paymentMethod must be 'cash' or 'bank_transfer'")

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
            return resp.error_response("Payment already confirmed for this record")
        # Check status of the record
        if existing_record.get('status') in ['PENDING', 'CANCELLED']:
            return resp.error_response(f"{payment_type.capitalize()} must be confirmed before payment")
        
        # Update the appointment/order record
        if revert:
            update_data = {
                'paymentStatus': 'pending',
                'paymentConfirmedBy': None,
                'paymentConfirmedAt': None,
                'paymentMethod': None,
                'updatedAt': int(time.time())
            }
        else:
            # Confirm payment with specified method
            update_data = {
                'paymentStatus': 'paid',
                'paymentConfirmedBy': staff_user_id,
                'paymentConfirmedAt': int(time.time()),
                'paymentMethod': payment_method,
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
        
        # Generate invoice if payment was confirmed (not reverted)
        invoice_url = None
        if not revert and updated_record.get('paymentStatus') == 'paid':
            try:
                # Queue invoice generation asynchronously for faster response
                # For manual payments, we create a unique payment_intent_id with method and reference
                payment_intent_id = f"{payment_method}_{reference_number}_{int(time.time())}"
                sqs.queue_invoice_generation(updated_record, payment_type, payment_intent_id)
                print(f"Invoice generation queued for {payment_type} {reference_number} (payment method: {payment_method})")
            except Exception as e:
                print(f"Error queuing invoice generation: {str(e)}")
                # Fallback to synchronous processing if queue fails
                try:
                    payment_intent_id = f"{payment_method}_{reference_number}_{int(time.time())}"
                    # Use shared utility for invoice generation
                    sqs.generate_invoice_synchronously(updated_record, payment_type, payment_intent_id)
                except Exception as sync_error:
                    print(f"Error in synchronous invoice generation fallback: {str(sync_error)}")
        
        # Send payment confirmation notification
        send_payment_confirmation_notification(updated_record, payment_type, 'paid' if not revert else 'pending')

        return resp.success_response({
            "message": "Payment status updated successfully",
            "referenceNumber": reference_number,
            "type": payment_type,
            "paymentStatus": 'paid' if not revert else 'pending',
            "paymentMethod": payment_method if not revert else None,
            "updatedAt": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        })
        
    except Exception as e:
        print(f"Error in confirm payment lambda: {str(e)}")
        return resp.error_response("Internal server error", 500)

def send_payment_confirmation_notification(record, record_type, status):
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
                "success": True if status == 'paid' else False,
                "referenceNumber": record.get(f'{record_type}Id'),
                "paymentStatus": status
            })
    except Exception as e:
        print(f"Error sending payment confirmation notification: {str(e)}")


