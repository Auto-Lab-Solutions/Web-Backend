from datetime import datetime
import db_utils as db
import response_utils as resp
import request_utils as req

def lambda_handler(event, context):
    try:
        # Get date parameter - required
        date = req.get_query_param(event, 'date')
        
        if not date:
            return resp.error_response("date parameter is required")
        
        # Validate date format (YYYY-MM-DD)
        try:
            datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            return resp.error_response("Date must be in YYYY-MM-DD format")
        
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
