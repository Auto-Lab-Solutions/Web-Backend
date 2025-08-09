from datetime import datetime, timedelta
import db_utils as db
import response_utils as resp
import request_utils as req

def lambda_handler(event, context):
    try:
        # Get parameters - support both single date and date range
        date = req.get_query_param(event, 'date')
        start_date = req.get_query_param(event, 'startDate')
        end_date = req.get_query_param(event, 'endDate')
        
        # Check if using date range or single date
        using_date_range = start_date and end_date
        using_single_date = date
        
        if not (using_date_range or using_single_date):
            return resp.error_response("Either 'date' or both 'startDate' and 'endDate' parameters are required")
        
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
        
        if using_single_date:
            # Original single date logic
            # 1. Get unavailable slots from UNAVAILABLE_SLOTS_TABLE
            unavailable_slots_record = db.get_unavailable_slots(date)
            manually_unavailable_slots = []
            
            if unavailable_slots_record and 'timeSlots' in unavailable_slots_record:
                manually_unavailable_slots = unavailable_slots_record['timeSlots']
            
            # 2. Get scheduled time slots from APPOINTMENTS_TABLE
            scheduled_slots = get_scheduled_appointment_slots(date)
            
            # 3. Merge both lists to get all unavailable slots
            all_unavailable_slots = merge_unavailable_slots(manually_unavailable_slots, scheduled_slots)
            
            return resp.success_response({
                "date": date,
                "unavailableSlots": all_unavailable_slots,
                "totalUnavailableSlots": len(all_unavailable_slots)
            })
        else:
            # Date range logic
            unavailable_slots_by_date = {}
            current_date = start_dt
            
            while current_date <= end_dt:
                date_str = current_date.strftime('%Y-%m-%d')
                
                # 1. Get unavailable slots from UNAVAILABLE_SLOTS_TABLE
                unavailable_slots_record = db.get_unavailable_slots(date_str)
                manually_unavailable_slots = []
                
                if unavailable_slots_record and 'timeSlots' in unavailable_slots_record:
                    manually_unavailable_slots = unavailable_slots_record['timeSlots']
                
                # 2. Get scheduled time slots from APPOINTMENTS_TABLE
                scheduled_slots = get_scheduled_appointment_slots(date_str)
                
                # 3. Merge both lists to get all unavailable slots
                all_unavailable_slots = merge_unavailable_slots(manually_unavailable_slots, scheduled_slots)
                
                unavailable_slots_by_date[date_str] = {
                    "unavailableSlots": all_unavailable_slots,
                    "totalUnavailableSlots": len(all_unavailable_slots)
                }
                
                current_date += timedelta(days=1)
            
            return resp.success_response({
                "startDate": start_date,
                "endDate": end_date,
                "unavailableSlotsByDate": unavailable_slots_by_date
            })
        
    except Exception as e:
        print(f"Error in get unavailable slots lambda: {str(e)}")
        return resp.error_response("Internal server error", 500)


def get_scheduled_appointment_slots(date):
    """Get all scheduled appointment time slots for a specific date using index"""
    try:
        # Use index to query appointments by scheduled date for better performance
        scheduled_appointments = db.get_appointments_by_scheduled_date(date)
        scheduled_slots = []
        
        for appointment in scheduled_appointments:
            # Check if appointment is in a scheduled state and has a scheduled time slot
            if (appointment.get('status') in ['SCHEDULED', 'ONGOING', 'COMPLETED'] and 
                appointment.get('scheduledTimeSlot')):
                
                scheduled_slot = appointment.get('scheduledTimeSlot')
                
                slot_info = {
                    'startTime': scheduled_slot.get('start', ''),
                    'endTime': scheduled_slot.get('end', ''),
                    'status': appointment.get('status'),
                    'serviceId': appointment.get('serviceId'),
                    'planId': appointment.get('planId')
                }
                scheduled_slots.append(slot_info)
        
        return scheduled_slots
        
    except Exception as e:
        print(f"Error getting scheduled appointment slots: {str(e)}")
        return []


def merge_unavailable_slots(manually_unavailable, scheduled_slots):
    """Merge manually blocked slots and scheduled appointment slots"""
    all_slots = []
    
    # Add manually unavailable slots
    for slot in manually_unavailable:
        slot_info = {
            'startTime': slot.get('startTime', ''),
            'endTime': slot.get('endTime', ''),
            'type': 'manual',
            'reason': 'Manually blocked'
        }
        all_slots.append(slot_info)
    
    # Add scheduled appointment slots
    for slot in scheduled_slots:
        slot_info = {
            'startTime': slot.get('startTime', ''),
            'endTime': slot.get('endTime', ''),
            'status': slot.get('status', ''),
            'serviceId': slot.get('serviceId', ''),
            'planId': slot.get('planId', ''),
            'type': 'appointment',
            'reason': 'Scheduled appointment'
        }
        all_slots.append(slot_info)
    
    # Sort slots by start time
    all_slots.sort(key=lambda x: x.get('startTime', ''))
    
    return all_slots
