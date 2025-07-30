import time
import db_utils as db
import response_utils as resp
import request_utils as req
import wsgw_utils as wsgw

PERMITTED_ROLE = 'ADMIN'

wsgw_client = wsgw.get_apigateway_client()

def lambda_handler(event, context):
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
        revert = req.get_body_param(event, 'revert', False)
        
        # Validate required parameters
        if not reference_number:
            return resp.error_response("referenceNumber is required")
        if not payment_type:
            return resp.error_response("type is required")
        if payment_type not in ['appointment', 'order']:
            return resp.error_response("type must be 'appointment' or 'order'")

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
            # Confirm cash payment
            update_data = {
                'paymentStatus': 'paid',
                'paymentConfirmedBy': staff_user_id,
                'paymentConfirmedAt': int(time.time()),
                'paymentMethod': 'cash',
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
        
        # Send payment confirmation notification
        send_payment_confirmation_notification(updated_record, payment_type, 'paid' if not revert else 'pending')

        return resp.success_response({
            "message": "Payment status updated successfully",
            "referenceNumber": reference_number,
            "type": payment_type,
            "paymentStatus": 'paid' if not revert else 'pending',
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
