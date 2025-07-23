from datetime import datetime
import time
import db_utils as db
import response_utils as resp
import request_utils as req
import wsgw_utils as wsgw

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
        
        staff_roles = staff_user_record.get('roles', [])
        staff_user_id = staff_user_record.get('userId')
        
        # Get appointment ID from path parameters
        appointment_id = req.get_path_param(event, 'appointmentId')
        if not appointment_id:
            return resp.error_response("appointmentId is required in path")
        
        # Get existing appointment
        existing_appointment = db.get_appointment(appointment_id)
        if not existing_appointment:
            return resp.error_response("Appointment not found", 404)
        
        current_status = existing_appointment.get('status', '')
        assigned_mechanic_id = existing_appointment.get('assignedMechanicId', '')
        
        # Get request body
        body = req.get_body(event)
        if not body:
            return resp.error_response("Request body is required")
        
        # Determine update scenario and validate permissions
        update_data = {}
        scenario = determine_update_scenario(body)
        
        # Validate permissions based on scenario
        permission_result = validate_permissions(scenario, staff_roles, current_status, staff_user_id, assigned_mechanic_id)
        if not permission_result['allowed']:
            return resp.error_response(permission_result['message'], 403)
        
        # Process updates based on scenario
        if scenario == 'basic_info':
            # Scenario 1: Update basic appointment info
            update_data = process_basic_info_updates(body, existing_appointment)
            
        elif scenario == 'scheduling':
            # Scenario 2: Update scheduling information
            update_data = process_scheduling_updates(body, existing_appointment)
            
        elif scenario == 'status':
            # Scenario 3: Update status
            new_status = body.get('status')
            if not validate_status_transition(current_status, new_status, staff_roles, staff_user_id, assigned_mechanic_id):
                return resp.error_response(f"Invalid status transition from {current_status} to {new_status}", 400)
            if current_status == 'PENDING' and new_status == 'SCHEDULED' and not (existing_appointment.get('scheduledTimeSlot') and existing_appointment.get('assignedMechanicId')):
                return resp.error_response("Cannot schedule appointment without scheduled time slot and assigned mechanic", 400)
            update_data['status'] = new_status
            
        elif scenario == 'reports':
            # Scenario 4: Update reports and post notes
            update_data = process_reports_updates(body, existing_appointment)
        
        if not update_data:
            return resp.error_response("No valid update data provided")
        elif update_data.get('statusCode') == 400:
            return update_data
        
        # Add updated timestamp
        update_data['updatedAt'] = int(time.time())
        
        # Update appointment in database
        success = db.update_appointment(appointment_id, update_data)
        if not success:
            return resp.error_response("Failed to update appointment", 500)
        
        # Get updated appointment for response
        updated_appointment = db.get_appointment(appointment_id)
        
        # Send notifications to relevant staff
        send_update_notifications(appointment_id, scenario, update_data, updated_appointment)
        
        return resp.success_response({
            "message": "Appointment updated successfully",
            "appointment": resp.convert_decimal(updated_appointment)
        })
        
    except Exception as e:
        print(f"Error in update appointment lambda: {str(e)}")
        return resp.error_response("Internal server error", 500)


def determine_update_scenario(body):
    """Determine which update scenario this request falls under"""
    if 'status' in body:
        return 'status'
    elif 'reports' in body or 'postNotes' in body:
        return 'reports'
    elif 'scheduledTimeSlot' in body or 'assignedMechanicId' in body:
        return 'scheduling'
    else:
        return 'basic_info'


def validate_permissions(scenario, staff_roles, current_status, staff_user_id, assigned_mechanic_id):
    """Validate if the user has permission for this update scenario"""
    
    if scenario == 'basic_info':
        # Scenario 1: Basic info updates
        if 'CUSTOMER_SUPPORT' not in staff_roles:
            return {'allowed': False, 'message': 'Unauthorized: CUSTOMER_SUPPORT role required'}
        if current_status not in ['PENDING', 'SCHEDULED', 'ONGOING']:
            return {'allowed': False, 'message': f'Cannot update basic info when status is {current_status}'}
            
    elif scenario == 'scheduling':
        # Scenario 2: Scheduling updates
        if 'CUSTOMER_SUPPORT' not in staff_roles:
            return {'allowed': False, 'message': 'Unauthorized: CUSTOMER_SUPPORT role required'}
        if current_status not in ['PENDING', 'SCHEDULED']:
            return {'allowed': False, 'message': f'Cannot update scheduling when status is {current_status}'}
            
    elif scenario == 'status':
        # Scenario 3: Status updates - validation done in validate_status_transition
        pass
        
    elif scenario == 'reports':
        # Scenario 4: Reports and post notes
        if 'MECHANIC' not in staff_roles:
            return {'allowed': False, 'message': 'Unauthorized: MECHANIC role required'}
        if current_status != 'COMPLETED':
            return {'allowed': False, 'message': f'Cannot update reports when status is {current_status}'}
        if assigned_mechanic_id != staff_user_id:
            return {'allowed': False, 'message': 'Unauthorized: You must be assigned to this appointment'}
    
    return {'allowed': True, 'message': ''}


def validate_status_transition(current_status, new_status, staff_roles, staff_user_id, assigned_mechanic_id):
    """Validate if the status transition is allowed"""
    
    # Customer Support allowed transitions
    cs_transitions = {
        'PENDING': ['SCHEDULED', 'CANCELLED'],
        'SCHEDULED': ['PENDING', 'CANCELLED'],
        'ONGOING': ['SCHEDULED', 'CANCELLED'],
        'CANCELLED': ['PENDING', 'SCHEDULED']
    }
    
    # Mechanic allowed transitions (must be assigned)
    mechanic_transitions = {
        'SCHEDULED': ['ONGOING'],
        'ONGOING': ['COMPLETED', 'SCHEDULED'],
        'COMPLETED': ['ONGOING']
    }
    
    if 'CUSTOMER_SUPPORT' in staff_roles and new_status in cs_transitions.get(current_status, []):
        return True
    
    if ('MECHANIC' in staff_roles and 
        assigned_mechanic_id == staff_user_id and 
        new_status in mechanic_transitions.get(current_status, [])):
        return True
    
    return False


def process_basic_info_updates(body, existing_appointment):
    """Process basic appointment information updates"""
    update_data = {}
    
    # Service and plan updates
    if 'serviceId' in body:
        update_data['serviceId'] = body['serviceId']
        # Update price if service or plan changed
        plan_id = body.get('planId', existing_appointment.get('planId'))
        price = db.get_service_pricing(body['serviceId'], plan_id)
        if price is None:
            return resp.error_response("Invalid service or plan. Please check the serviceId and planId provided.")
        update_data['price'] = price
    
    if 'planId' in body:
        update_data['planId'] = body['planId']
        # Update price if service or plan changed
        service_id = body.get('serviceId', existing_appointment.get('serviceId'))
        price = db.get_service_pricing(service_id, body['planId'])
        if price is None:
            return resp.error_response("Invalid service or plan. Please check the serviceId and planId provided.")
        update_data['price'] = price
    
    if 'isBuyer' in body:
        update_data['isBuyer'] = body['isBuyer']
    
    # Buyer data updates
    if 'buyerData' in body:
        buyer_data = body['buyerData']
        if 'name' in buyer_data:
            update_data['buyerName'] = buyer_data['name']
        if 'email' in buyer_data:
            update_data['buyerEmail'] = buyer_data['email']
        if 'phoneNumber' in buyer_data:
            update_data['buyerPhone'] = buyer_data['phoneNumber']
    
    # Car data updates
    if 'carData' in body:
        car_data = body['carData']
        if 'make' in car_data:
            update_data['carMake'] = car_data['make']
        if 'model' in car_data:
            update_data['carModel'] = car_data['model']
        if 'year' in car_data:
            update_data['carYear'] = str(car_data['year'])
        if 'location' in car_data:
            update_data['carLocation'] = car_data['location']
    
    # Seller data updates
    if 'sellerData' in body:
        seller_data = body['sellerData']
        if 'name' in seller_data:
            update_data['sellerName'] = seller_data['name']
        if 'email' in seller_data:
            update_data['sellerEmail'] = seller_data['email']
        if 'phoneNumber' in seller_data:
            update_data['sellerPhone'] = seller_data['phoneNumber']
    
    # Notes update
    if 'notes' in body:
        update_data['notes'] = body['notes']
    
    return update_data


def process_scheduling_updates(body, existing_appointment):
    """Process scheduling-related updates"""
    update_data = {}
    
    if 'scheduledTimeSlot' in body:
        scheduled_slot = body['scheduledTimeSlot']
        if isinstance(scheduled_slot, dict) and scheduled_slot:
            # Pass the raw data, let db_utils handle DynamoDB formatting
            update_data['scheduledTimeSlot'] = {
                'date': scheduled_slot.get('date', ''),
                'start': scheduled_slot.get('start', ''),
                'end': scheduled_slot.get('end', '')
            }
            # Also update scheduledDate for indexing
            update_data['scheduledDate'] = scheduled_slot.get('date', '')
        else:
            # Clear the scheduled time slot and date if empty
            update_data['scheduledTimeSlot'] = {}
            update_data['scheduledDate'] = ''
    
    if 'assignedMechanicId' in body:
        mechanic_id = body['assignedMechanicId']
        # Validate mechanic exists if not empty
        if mechanic_id:
            mechanic_record = db.get_staff_record_by_user_id(mechanic_id)
            if not mechanic_record or 'MECHANIC' not in mechanic_record.get('roles', []):
                return resp.error_response("Invalid mechanic ID")
        update_data['assignedMechanicId'] = mechanic_id
    
    return update_data


def process_reports_updates(body, existing_appointment):
    """Process reports and post notes updates"""
    update_data = {}
    
    if 'postNotes' in body:
        update_data['postNotes'] = body['postNotes']
    
    if 'reports' in body:
        reports = body['reports']
        if isinstance(reports, list):
            # Pass the raw data, let db_utils handle DynamoDB formatting
            update_data['reports'] = reports
    
    return update_data


def send_update_notifications(appointment_id, scenario, update_data, updated_appointment):
    """Send notifications to created user about the appointment update"""
    notification_data = {
        "type": "appointment",
        "subtype": "update",
        "scenario": scenario,
        "appointmentId": appointment_id,
        "changes": list(update_data.keys())
    }
    
    # Get connections of customer user and send notification
    customer_user_connection = db.get_connection_by_user_id(updated_appointment.get('createdUserId'))
    if customer_user_connection:
        wsgw.send_notification(
            wsgw_client,
            customer_user_connection.get('connectionId'),
            notification_data
        )
    



