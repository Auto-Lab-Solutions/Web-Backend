from datetime import datetime
import db_utils as db
import response_utils as resp
import request_utils as req

def lambda_handler(event, context):
    try:
        staff_user_email = req.get_staff_user_email(event)
        appointment_id = req.get_path_param(event, 'appointmentId')
        user_id = req.get_query_param(event, 'userId')
        
        # Determine if this is a staff user or customer user
        if staff_user_email:
            # Staff user scenarios (1 & 2)
            staff_user_record = db.get_staff_record(staff_user_email)
            if not staff_user_record:
                return resp.error_response(f"No staff record found for email: {staff_user_email}", 404)
            
            staff_roles = staff_user_record.get('roles', [])
            staff_user_id = staff_user_record.get('userId')
            
            if appointment_id:
                # Get single appointment by ID
                appointment = db.get_appointment(appointment_id)
                if not appointment:
                    return resp.error_response("Appointment not found", 404)
                
                return resp.success_response({
                    "appointment": resp.convert_decimal(appointment)
                })
            else:
                # Get multiple appointments based on role
                if 'CUSTOMER_SUPPORT' in staff_roles:
                    # Scenario 1: CUSTOMER_SUPPORT - get all appointments
                    appointments = db.get_all_appointments()
                elif 'MECHANIC' in staff_roles:
                    # Scenario 2: MECHANIC - get appointments assigned to them
                    appointments = db.get_appointments_by_assigned_mechanic(staff_user_id)
                else:
                    return resp.error_response("Unauthorized: Invalid staff role", 403)
                
                # Apply query parameter filters if provided
                appointments = apply_query_filters(appointments, event)
                
                return resp.success_response({
                    "appointments": resp.convert_decimal(appointments),
                    "count": len(appointments)
                })
        else:
            # Scenario 3: Customer user
            if not user_id:
                return resp.error_response("userId is required for non-staff users")
            
            if appointment_id:
                # Get single appointment by ID - verify ownership
                appointment = db.get_appointment(appointment_id)
                if not appointment:
                    return resp.error_response("Appointment not found", 404)
                
                # Check if this user created the appointment
                if appointment.get('createdUserId') != user_id:
                    return resp.error_response("Unauthorized: You can only view appointments you created", 403)
                
                # Get assigned mechanic details if available
                mechanic_details = None
                assigned_mechanic_id = appointment.get('assignedMechanicId')
                if assigned_mechanic_id:
                    mechanic_record = db.get_staff_record_by_user_id(assigned_mechanic_id)
                    if mechanic_record:
                        mechanic_details = {
                            "userName": mechanic_record.get('userName', ''),
                            "userEmail": mechanic_record.get('userEmail', ''),
                            "contactNumber": mechanic_record.get('contactNumber', '')
                        }
                
                response_data = {
                    "appointment": resp.convert_decimal(appointment)
                }
                
                # Add mechanic details if available
                if mechanic_details:
                    response_data["assignedMechanic"] = mechanic_details
                
                return resp.success_response(response_data)
            else:
                # Get all appointments created by this user
                appointments = db.get_appointments_by_created_user(user_id)
                
                # Apply query parameter filters if provided
                appointments = apply_query_filters(appointments, event)
                
                return resp.success_response({
                    "appointments": resp.convert_decimal(appointments),
                    "count": len(appointments)
                })
        
    except Exception as e:
        print(f"Error in get appointments lambda: {str(e)}")
        return resp.error_response("Internal server error", 500)


def apply_query_filters(appointments, event):
    """Apply query parameter filters to the appointments list"""
    if not appointments:
        return appointments
    
    # Get filter parameters from query string
    status = req.get_query_param(event, 'status')
    start_date = req.get_query_param(event, 'startDate')
    end_date = req.get_query_param(event, 'endDate')
    service_id = req.get_query_param(event, 'serviceId')
    plan_id = req.get_query_param(event, 'planId')
    
    filtered_appointments = appointments
    
    # Filter by status
    if status:
        filtered_appointments = [
            apt for apt in filtered_appointments 
            if apt.get('status', '').upper() == status.upper()
        ]
    
    # Filter by date range
    if start_date:
        if end_date:
            # Filter by date range
            filtered_appointments = [
                apt for apt in filtered_appointments 
                if start_date <= apt.get('createdDate', '') <= end_date
            ]
        else:
            # Filter by single date
            filtered_appointments = [
                apt for apt in filtered_appointments 
                if apt.get('createdDate', '') == start_date
            ]
    
    # Filter by service ID
    if service_id:
        try:
            service_id_int = int(service_id)
            filtered_appointments = [
                apt for apt in filtered_appointments 
                if apt.get('serviceId') == service_id_int
            ]
        except ValueError:
            pass  # Invalid service ID format, skip filter
    
    # Filter by plan ID
    if plan_id:
        try:
            plan_id_int = int(plan_id)
            filtered_appointments = [
                apt for apt in filtered_appointments 
                if apt.get('planId') == plan_id_int
            ]
        except ValueError:
            pass  # Invalid plan ID format, skip filter
    
    return filtered_appointments