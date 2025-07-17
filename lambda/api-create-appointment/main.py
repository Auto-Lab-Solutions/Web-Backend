from datetime import datetime
import uuid
import db_utils as db
import response_utils as resp
import request_utils as req
import wsgw_utils as wsgw

PERMITTED_ROLE = 'CUSTOMER_SUPPORT'

APPOINTMENTS_LIMIT = 3 # Maximum number of appointments per day
wsgw_client = wsgw.get_apigateway_client()

def lambda_handler(event, context):
    staff_user_email = req.get_staff_user_email(event)
    user_id = req.get_body_param(event, 'userId')
    appointment_data = req.get_body_param(event, 'appointmentData')

    if staff_user_email:
        staff_user_record = db.get_staff_record(staff_user_email)
        if not staff_user_record:
            return resp.error_response(f"No staff record found for email: {staff_user_email}.")
        staff_roles = staff_user_record.get('roles', [])
        if PERMITTED_ROLE not in staff_roles:
            return resp.error_response("Unauthorized: Insufficient permissions.")
        user_id = staff_user_record.get('userId')
    else:
        if not user_id:
            return resp.error_response("userId is required for non-staff users.")

    # Validate appointment data
    valid, msg = validate_appointment_data(appointment_data, staff_user=bool(staff_user_email))
    if not valid:
        return resp.error_response(msg)
    
    # Check if the user has reached the appointment limit for today
    if not staff_user_email:
        today = datetime.now().date()
        appointment_count = db.get_daily_unpaid_appointments_count(user_id, today)
        if appointment_count >= APPOINTMENTS_LIMIT:
            return resp.error_response("Appointment limit reached for today.")

    # Generate unique appointment ID
    appointment_id = str(uuid.uuid4())

    # Get price by service and plan
    price = db.get_service_pricing(
        service_id=appointment_data.get('serviceId'),
        plan_id=appointment_data.get('planId')
    )
    if price is None:
        return resp.error_response("Invalid service or plan. Please check the serviceId and planId provided.")

    # Build appointment data
    appointment_data = db.build_appointment_data(
        appointment_id=appointment_id,
        service_id=appointment_data.get('serviceId'),
        plan_id=appointment_data.get('planId'),
        is_buyer=appointment_data.get('isBuyer', True),
        buyer_data=appointment_data.get('buyerData', {}),
        car_data=appointment_data.get('carData', {}),
        seller_data=appointment_data.get('sellerData', {}),
        notes=appointment_data.get('notes', ''),
        selected_slots=appointment_data.get('selectedSlots', []),
        created_user_id=user_id,
        price=price
    )

    # Create appointment in database
    success = db.create_appointment(appointment_data)
    if not success:
        return resp.error_response("Failed to create appointment")

    staff_connections = db.get_assigned_or_all_staff_connections(assigned_to=user_id)
    notification_data = {
        "type": "appointment",
        "subtype": "create",
        "success": True,
        "appointmentId": appointment_id,
        "appointmentData": appointment_data
    }

    # Send notifications to staff users
    for staff in staff_connections:
        wsgw.send_notification(wsgw_client, staff.get('connectionId'), notification_data)

    # Return success response
    return resp.success_response({
        "message": "Appointment created successfully",
        "appointmentId": appointment_id
    })



