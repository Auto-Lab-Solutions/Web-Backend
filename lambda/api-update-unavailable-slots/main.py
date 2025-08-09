from datetime import datetime
import db_utils as db
import response_utils as resp
import request_utils as req

PERMITTED_ROLE = 'ADMIN'

def lambda_handler(event, context):
    # Get staff user information
    staff_user_email = req.get_staff_user_email(event)
    if not staff_user_email:
        return resp.error_response("Unauthorized: Staff authentication required", 401)
        
    staff_user_record = db.get_staff_record(staff_user_email)
    if not staff_user_record:
        return resp.error_response(f"No staff record found for email: {staff_user_email}", 404)
    
    staff_roles = staff_user_record.get('roles', [])
    if PERMITTED_ROLE not in staff_roles:
        return resp.error_response("Unauthorized: Insufficient permissions", 403)
    
    # Get parameters from query parameters or body
    date = req.get_query_param(event, 'date') or req.get_body_param(event, 'date')
    start_date = req.get_query_param(event, 'startDate') or req.get_body_param(event, 'startDate')
    end_date = req.get_query_param(event, 'endDate') or req.get_body_param(event, 'endDate')
    operation = req.get_body_param(event, 'operation') or 'get'
    time_slots = req.get_body_param(event, 'timeSlots')
    
    # Check if using date range or single date
    using_date_range = start_date and end_date
    using_single_date = date
    
    if not (using_date_range or using_single_date) or not operation:
        return resp.error_response("Either 'date' or both 'startDate' and 'endDate' are required, along with 'operation'.")
    
    if using_date_range and using_single_date:
        return resp.error_response("Cannot specify both single 'date' and date range ('startDate'/'endDate'). Use one or the other.")
    
    # Validate date format(s)
    try:
        if using_single_date:
            datetime.strptime(date, '%Y-%m-%d')
        else:  # using_date_range
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
            if end_dt < start_dt:
                return resp.error_response("End date must be on or after start date")
    except ValueError:
        return resp.error_response("Date(s) must be in YYYY-MM-DD format")
    
    # Handle different operations
    if operation == 'get':
        # Get unavailable slots
        if using_single_date:
            unavailable_slots = db.get_unavailable_slots(date)
            if not unavailable_slots:
                return resp.success_response({
                    "date": date,
                    "timeSlots": []
                })
            return resp.success_response({
                "date": date,
                "timeSlots": unavailable_slots.get('timeSlots', [])
            })
        else:  # using_date_range
            unavailable_slots_range = db.get_unavailable_slots_range(start_date, end_date)
            return resp.success_response({
                "startDate": start_date,
                "endDate": end_date,
                "unavailableSlotsByDate": unavailable_slots_range
            })
    
    elif operation in ['create', 'update']:
        # Validate time slots for create/update operations
        if not time_slots or not isinstance(time_slots, list):
            return resp.error_response("timeSlots array is required for create/update operations")
        
        # Validate time slot format
        for slot in time_slots:
            if not isinstance(slot, dict) or 'startTime' not in slot or 'endTime' not in slot:
                return resp.error_response("Each time slot must have startTime and endTime")
            
            # Validate time format (HH:MM)
            try:
                datetime.strptime(slot['startTime'], '%H:%M')
                datetime.strptime(slot['endTime'], '%H:%M')
            except ValueError:
                return resp.error_response("Time must be in HH:MM format")
            
            # Validate that end time is after start time
            start_time = datetime.strptime(slot['startTime'], '%H:%M')
            end_time = datetime.strptime(slot['endTime'], '%H:%M')
            if end_time <= start_time:
                return resp.error_response("End time must be after start time")
        
        # Update unavailable slots
        if using_single_date:
            result = db.update_unavailable_slots(date, time_slots)
            if result:
                return resp.success_response({
                    "message": f"Unavailable slots for {date} {operation}d successfully",
                    "date": date,
                    "timeSlots": time_slots
                })
            else:
                return resp.error_response(f"Failed to {operation} unavailable slots", 500)
        else:  # using_date_range
            result = db.update_unavailable_slots_range(start_date, end_date, time_slots)
            if result:
                return resp.success_response({
                    "message": f"Unavailable slots for date range {start_date} to {end_date} {operation}d successfully",
                    "startDate": start_date,
                    "endDate": end_date,
                    "timeSlots": time_slots
                })
            else:
                return resp.error_response(f"Failed to {operation} unavailable slots for date range", 500)
    
    else:
        return resp.error_response("Invalid operation. Must be 'get', 'create', or 'update'.")
