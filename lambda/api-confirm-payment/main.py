import time
import db_utils as db
import response_utils as resp
import request_utils as req
import wsgw_utils as wsgw

PERMITTED_ROLE = 'ADMIN'

wsgw_client = wsgw.get_apigateway_client()

def lambda_handler(event, context):
    try:
        # Get staff user authentication and request parameters
        staff_user_email = req.get_staff_user_email(event)
        appointment_id = req.get_body_param(event, 'appointmentId')
        payment_method = req.get_body_param(event, 'paymentMethod')
        payment_reference = req.get_body_param(event, 'paymentReference')
        payment_amount = req.get_body_param(event, 'paymentAmount')

        # Validate appointment ID and status
        if not appointment_id:
            return resp.error_response("appointmentId is required")
        existing_appointment = db.get_appointment(appointment_id)
        if not existing_appointment:
            return resp.error_response("Appointment not found", 404)
        if existing_appointment.get('paymentCompleted', False):
            return resp.error_response("Payment already completed for this appointment")
        
        if staff_user_email:
            # Validate staff user and permissions
            staff_user_record = db.get_staff_record(staff_user_email)
            if not staff_user_record:
                return resp.error_response(f"No staff record found for email: {staff_user_email}", 404)
            
            staff_roles = staff_user_record.get('roles', [])
            if PERMITTED_ROLE not in staff_roles:
                return resp.error_response("Unauthorized: ADMIN role required", 403)
            
            staff_user_id = staff_user_record.get('userId')
            
            # Prepare payment update data
            update_data = {
                'paymentCompleted': True,
                'paymentConfirmedBy': staff_user_id,
                'paymentConfirmedAt': int(time.time()),
                'updatedAt': int(time.time())
            }
        
        else:
            # Validate payment amount if provided
            appointment_price = existing_appointment.get('price', 0)
            if payment_amount is not None:
                if float(payment_amount) != float(appointment_price):
                    return resp.error_response(f"Payment amount {payment_amount} does not match appointment price {appointment_price}")

            # Add optional payment reference if provided
            if payment_reference:
                update_data['paymentReference'] = payment_reference
            
            # Add payment amount if provided
            if payment_amount is not None:
                update_data['paidAmount'] = float(payment_amount)

        # Update appointment in database
        success = db.update_appointment(appointment_id, update_data)
        if not success:
            return resp.error_response("Failed to confirm payment", 500)
        
        # Get updated appointment for response
        updated_appointment = db.get_appointment(appointment_id)
        
        # Send payment confirmation notification to customer
        send_payment_confirmation_notification(updated_appointment, manual_confirmation=bool(staff_user_email))
        
        return resp.success_response({
            "message": "Payment confirmed successfully",
            "appointmentId": appointment_id,
        })
        
    except Exception as e:
        print(f"Error in confirm payment lambda: {str(e)}")
        return resp.error_response("Internal server error", 500)

def send_payment_confirmation_notification(appointment, manual_confirmation=False):
    receiverConnections = []

    if manual_confirmation:
        customer_user_id = appointment.get('createdUserId')
        if customer_user_id:
            customer_connection = db.get_connection_by_user_id(customer_user_id)
            if customer_connection:
                receiverConnections.append(customer_connection)
    else:
        receiverConnections = db.get_all_staff_connections()

    for connection in receiverConnections:
        wsgw.send_notification(wsgw_client, connection.get('connectionId'), {
            "type": "appointment",
            "subtype": "payment-confirmation",
            "success": True,
            "appointmentId": appointment.get('appointmentId'),
            "appointmentData": resp.convert_decimal(appointment),
            "manualConfirmation": manual_confirmation
        })
