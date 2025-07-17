from datetime import datetime
import db_utils as db
import response_utils as resp
import request_utils as req

def lambda_handler(event, context):
    date = req.get_query_param(event, 'date') or req.get_body_param(event, 'date')
    operation = req.get_body_param(event, 'operation') or 'get'
    time_slots = req.get_body_param(event, 'timeSlots')
    
    if not date or not operation:
        return resp.error_response("date and operation are required.")
    
    # Validate date format (YYYY-MM-DD)
    try:
        datetime.strptime(date, '%Y-%m-%d')
    except ValueError:
        return resp.error_response("Date must be in YYYY-MM-DD format")
    
    # Handle different operations
    if operation == 'get':
        # Get unavailable slots for the date
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
        
        result = db.update_unavailable_slots(date, time_slots)
        
        if result:
            return resp.success_response({
                "message": f"Unavailable slots for {date} {operation}d successfully",
                "date": date,
                "timeSlots": time_slots
            })
        else:
            return resp.error_response(f"Failed to {operation} unavailable slots", 500)
    
    else:
        return resp.error_response("Invalid operation. Must be 'get', 'create', or 'update'.")
