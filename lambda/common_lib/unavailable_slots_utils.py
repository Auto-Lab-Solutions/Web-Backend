"""
Unavailable Slots Manager for API operations

This module provides managers for unavailable slots operations,
including reading and updating slot availability.
"""

from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

import db_utils as db
import request_utils as req
from exceptions import BusinessLogicError
from data_access_utils import DataAccessManager


def parse_time_slot(slot_str):
    """Parse a time slot string into start and end time objects"""
    try:
        start_str, end_str = slot_str.split('-')
        start_time = datetime.strptime(start_str, '%H:%M').time()
        end_time = datetime.strptime(end_str, '%H:%M').time()
        return start_time, end_time
    except ValueError:
        raise ValueError(f"Invalid time slot format: {slot_str}")


def format_time_slot(start_time, end_time):
    """Format start and end time objects into a time slot string"""
    return f"{start_time.strftime('%H:%M')}-{end_time.strftime('%H:%M')}"


def time_slots_overlap(slot1_start, slot1_end, slot2_start, slot2_end):
    """Check if two time slots overlap or are adjacent"""
    # Convert to minutes for easier comparison
    slot1_start_min = slot1_start.hour * 60 + slot1_start.minute
    slot1_end_min = slot1_end.hour * 60 + slot1_end.minute
    slot2_start_min = slot2_start.hour * 60 + slot2_start.minute
    slot2_end_min = slot2_end.hour * 60 + slot2_end.minute
    
    # Check if they overlap or are adjacent (touching)
    return not (slot1_end_min < slot2_start_min or slot2_end_min < slot1_start_min)

    # # Only count as overlap if there is a true intersection (not just touching)
    # # i.e., [a, b) and [c, d) overlap iff a < d and c < b
    # return slot1_start_min < slot2_end_min and slot2_start_min < slot1_end_min


def merge_time_slots(slots):
    """Merge overlapping or adjacent time slots"""
    if not slots:
        return []
    
    # Parse all slots into (start_time, end_time) tuples
    parsed_slots = []
    for slot in slots:
        try:
            start_time, end_time = parse_time_slot(slot)
            parsed_slots.append((start_time, end_time))
        except ValueError as e:
            print(f"Warning: Skipping invalid slot {slot}: {e}")
            continue
    
    if not parsed_slots:
        return []
    
    # Sort by start time
    parsed_slots.sort(key=lambda x: (x[0].hour, x[0].minute))
    
    merged = []
    current_start, current_end = parsed_slots[0]
    
    for start_time, end_time in parsed_slots[1:]:
        if time_slots_overlap(current_start, current_end, start_time, end_time):
            # Merge overlapping or adjacent slots
            current_end = max(current_end, end_time, key=lambda t: t.hour * 60 + t.minute)
        else:
            # No overlap, add current slot and start new one
            merged.append(format_time_slot(current_start, current_end))
            current_start, current_end = start_time, end_time
    
    # Add the last slot
    merged.append(format_time_slot(current_start, current_end))
    
    return merged


def subtract_time_slots(existing_slots, slots_to_remove):
    """Remove time slots from existing slots, handling partial overlaps"""
    if not existing_slots:
        return []
    
    if not slots_to_remove:
        return existing_slots
    
    # Parse existing slots
    existing_parsed = []
    for slot in existing_slots:
        try:
            start_time, end_time = parse_time_slot(slot)
            existing_parsed.append((start_time, end_time))
        except ValueError as e:
            print(f"Warning: Skipping invalid existing slot {slot}: {e}")
            continue
    
    # Parse slots to remove
    remove_parsed = []
    for slot in slots_to_remove:
        try:
            start_time, end_time = parse_time_slot(slot)
            remove_parsed.append((start_time, end_time))
        except ValueError as e:
            print(f"Warning: Skipping invalid remove slot {slot}: {e}")
            continue
    
    result = []
    
    for existing_start, existing_end in existing_parsed:
        current_segments = [(existing_start, existing_end)]
        
        # For each slot to remove, check if it affects current segments
        for remove_start, remove_end in remove_parsed:
            new_segments = []
            
            for seg_start, seg_end in current_segments:
                # Convert to minutes for easier comparison
                seg_start_min = seg_start.hour * 60 + seg_start.minute
                seg_end_min = seg_end.hour * 60 + seg_end.minute
                remove_start_min = remove_start.hour * 60 + remove_start.minute
                remove_end_min = remove_end.hour * 60 + remove_end.minute
                
                # Check if remove slot overlaps with current segment
                if remove_end_min <= seg_start_min or remove_start_min >= seg_end_min:
                    # No overlap, keep segment as is
                    new_segments.append((seg_start, seg_end))
                else:
                    # There's overlap, split the segment
                    # Add part before the remove slot (if any)
                    if seg_start_min < remove_start_min:
                        before_end_min = remove_start_min
                        before_end = time(before_end_min // 60, before_end_min % 60)
                        new_segments.append((seg_start, before_end))
                    
                    # Add part after the remove slot (if any)
                    if seg_end_min > remove_end_min:
                        after_start_min = remove_end_min
                        after_start = time(after_start_min // 60, after_start_min % 60)
                        new_segments.append((after_start, seg_end))
            
            current_segments = new_segments
        
        # Add remaining segments to result
        for seg_start, seg_end in current_segments:
            result.append(format_time_slot(seg_start, seg_end))
    
    return result


class UnavailableSlotManager(DataAccessManager):
    """Manager for unavailable slots operations"""
    
    def __init__(self):
        super().__init__()
        self.admin_roles = ['ADMIN']
    
    def get_unavailable_slots(self, event):
        """
        Get unavailable slots for date or date range, or check specific timeslot availability
        
        Args:
            event: Lambda event with query parameters
            
        Returns:
            dict: Unavailable slots data or timeslot availability check result
        """
        # Get parameters - support both single date and date range
        date = req.get_query_param(event, 'date')
        start_date = req.get_query_param(event, 'startDate')
        end_date = req.get_query_param(event, 'endDate')
        check_slot = req.get_query_param(event, 'checkSlot')  # New parameter for customer availability check
        
        # Validate parameters
        using_date_range = start_date and end_date
        using_single_date = date
        using_check_slot = check_slot
        
        if not (using_date_range or using_single_date):
            raise BusinessLogicError(
                "Either 'date' or both 'startDate' and 'endDate' parameters are required", 400
            )
        
        if using_date_range and using_single_date:
            raise BusinessLogicError(
                "Cannot specify both single 'date' and date range ('startDate'/'endDate'). Use one or the other.", 400
            )
        
        # Handle customer timeslot availability check
        if using_check_slot:
            if not using_single_date:
                raise BusinessLogicError(
                    "Parameter 'checkSlot' can only be used with single 'date' parameter, not with date ranges", 400
                )
            
            # Perform availability check for the specific timeslot
            availability_result = self.check_timeslot_availability(date, check_slot)
            
            # Also include full unavailable slots data for reference
            full_data = self._get_unavailable_slots_single_date(date)
            
            return {
                'availabilityCheck': availability_result,
                'fullUnavailableSlots': full_data
            }
        
        # Handle existing functionality (unchanged)
        if using_single_date:
            return self._get_unavailable_slots_single_date(date)
        else:
            return self._get_unavailable_slots_date_range(start_date, end_date)
    
    def _get_unavailable_slots_single_date(self, date):
        """Get unavailable slots for a single date"""
        # Validate date format
        self.validate_date_parameter(date, 'date')
        
        # Get manually unavailable slots
        unavailable_slots_record = db.get_unavailable_slots(date)
        manually_unavailable_slots = []
        
        if unavailable_slots_record and 'timeSlots' in unavailable_slots_record:
            raw_time_slots = unavailable_slots_record['timeSlots']
            
            # Convert time slots to consistent format
            for slot in raw_time_slots:
                try:
                    if isinstance(slot, str):
                        # Already in "HH:MM-HH:MM" format
                        manually_unavailable_slots.append(slot)
                    elif isinstance(slot, dict):
                        # Convert from object format
                        if 'startTime' in slot and 'endTime' in slot:
                            time_slot = f"{slot['startTime']}-{slot['endTime']}"
                            manually_unavailable_slots.append(time_slot)
                        elif 'start' in slot and 'end' in slot:
                            time_slot = f"{slot['start']}-{slot['end']}"
                            manually_unavailable_slots.append(time_slot)
                        else:
                            print(f"Warning: Unknown manually set slot format: {slot}")
                except Exception as e:
                    print(f"Warning: Error processing manually unavailable slot {slot}: {str(e)}")

        # Get scheduled appointment slots
        scheduled_slots = self._get_scheduled_appointment_slots(date)

        # Merge both lists
        all_unavailable_slots = self._merge_unavailable_slots(manually_unavailable_slots, scheduled_slots)

        return {
            'date': date,
            'unavailableSlots': all_unavailable_slots,
            'manuallyUnavailableSlots': manually_unavailable_slots,
            'scheduledSlots': scheduled_slots
        }
    
    def _get_unavailable_slots_date_range(self, start_date, end_date):
        """Get unavailable slots for a date range"""
        # Validate date range
        start_dt, end_dt = self.validate_date_range(start_date, end_date)
        
        # Process each date in range
        result = {}
        current_date = start_dt
        
        while current_date <= end_dt:
            date_str = current_date.strftime('%Y-%m-%d')
            result[date_str] = self._get_unavailable_slots_single_date(date_str)
            current_date += timedelta(days=1)
        
        return {
            'dateRange': {
                'startDate': start_date,
                'endDate': end_date
            },
            'unavailableSlotsByDate': result
        }
    
    def _get_scheduled_appointment_slots(self, date):
        """Get time slots that are scheduled for appointments on the given date"""
        try:
            scheduled_slots = []
            
            # Get appointments scheduled for this specific date
            scheduled_appointments = db.get_appointments_by_scheduled_date(date)

            for appointment in scheduled_appointments:
                try:
                    # Check if appointment is confirmed or pending (not cancelled or completed)
                    status = appointment.get('status', '').upper() 
                    appointment_id = appointment.get('appointmentId', 'unknown')
                    
                    if status not in ['CANCELLED', 'COMPLETED']:
                        scheduled_time_slot = appointment.get('scheduledTimeSlot')
                        if scheduled_time_slot and isinstance(scheduled_time_slot, dict):
                            start_time = scheduled_time_slot.get('start')
                            end_time = scheduled_time_slot.get('end')
                            if start_time and end_time:
                                time_slot = f"{start_time}-{end_time}"
                                scheduled_slots.append({
                                    'timeSlot': time_slot,
                                    'reason': 'scheduled_appointment',
                                    'appointmentId': appointment_id,
                                    'status': status
                                })
                            else:
                                print(f"Warning: Missing start/end time in scheduledTimeSlot for appointment {appointment_id}")
                        else:
                            print(f"Info: No scheduledTimeSlot for appointment {appointment_id} (status: {status})")
                            
                except Exception as e:
                    print(f"Warning: Error processing scheduled appointment {appointment.get('appointmentId', 'unknown')}: {str(e)}")

            # Get pending appointments with paid status
            pending_appointments = db.get_appointments_by_status('PENDING')
            
            for appointment in pending_appointments:
                try:
                    appointment_id = appointment.get('appointmentId', 'unknown')
                    payment_status = appointment.get('paymentStatus', 'unknown')
                    
                    if appointment.get('paymentStatus') == 'paid':
                        status = appointment.get('status', '').upper()
                        selected_time_slots = appointment.get('selectedSlots')
                        
                        if selected_time_slots and isinstance(selected_time_slots, list):
                            for slot in selected_time_slots:
                                try:
                                    if isinstance(slot, dict):
                                        slot_date = slot.get('date')
                                        slot_priority = slot.get('priority')
                                        
                                        if slot_date == date and slot_priority and int(slot_priority) == 1:
                                            start_time = slot.get('start')
                                            end_time = slot.get('end')
                                            if start_time and end_time:
                                                time_slot = f"{start_time}-{end_time}"
                                                scheduled_slots.append({
                                                    'timeSlot': time_slot,
                                                    'reason': 'pending_appointment',
                                                    'appointmentId': appointment_id,
                                                    'status': status
                                                })
                                            else:
                                                print(f"Warning: Missing start/end time in selected slot for appointment {appointment_id}")
                                    else:
                                        print(f"Warning: Invalid slot format in selectedSlots for appointment {appointment_id}")
                                except Exception as e:
                                    print(f"Warning: Error processing slot for appointment {appointment_id}: {str(e)}")
                        else:
                            print(f"Info: No valid selectedSlots for paid pending appointment {appointment_id}")
                            
                except Exception as e:
                    print(f"Warning: Error processing pending appointment {appointment.get('appointmentId', 'unknown')}: {str(e)}")

            return scheduled_slots
            
        except Exception as e:
            print(f"Error getting scheduled appointments for {date}: {str(e)}")
            import traceback
            traceback.print_exc()
            return []
    
    def _merge_unavailable_slots(self, manually_unavailable, scheduled_slots):
        """Merge manually unavailable slots and scheduled appointment slots"""
        all_slots = []
        
        # Add manually unavailable slots (these are now always strings)
        for slot in manually_unavailable:
            if isinstance(slot, str):
                all_slots.append({
                    'timeSlot': slot,
                    'reason': 'manually_set'
                })
            elif isinstance(slot, dict):
                # Handle legacy format if it still exists
                if 'timeSlot' in slot:
                    slot_copy = slot.copy()
                    if 'reason' not in slot_copy:
                        slot_copy['reason'] = 'manually_set'
                    all_slots.append(slot_copy)
                else:
                    # Convert old format
                    time_slot = None
                    if 'startTime' in slot and 'endTime' in slot:
                        time_slot = f"{slot['startTime']}-{slot['endTime']}"
                    elif 'start' in slot and 'end' in slot:
                        time_slot = f"{slot['start']}-{slot['end']}"
                    
                    if time_slot:
                        all_slots.append({
                            'timeSlot': time_slot,
                            'reason': 'manually_set'
                        })
        
        # Add scheduled slots (these are always dictionaries with timeSlot key)
        all_slots.extend(scheduled_slots)
        
        # Remove duplicates while preserving order
        seen_slots = set()
        unique_slots = []
        
        for slot in all_slots:
            # All slots should now be dictionaries with timeSlot key
            time_slot = slot.get('timeSlot') if isinstance(slot, dict) else str(slot)
            if time_slot and time_slot not in seen_slots:
                seen_slots.add(time_slot)
                unique_slots.append(slot)
        
        return unique_slots
    
    def check_timeslot_availability(self, date, timeslot):
        """
        Check if a specific timeslot is available on a given date
        
        Args:
            date (str): Date in YYYY-MM-DD format
            timeslot (str): Timeslot in HH:MM-HH:MM format
            
        Returns:
            dict: Availability information with appointmentsCount and blocked status
        """
        # Validate inputs
        self.validate_date_parameter(date, 'date')
        
        try:
            check_start, check_end = parse_time_slot(timeslot)
        except ValueError as e:
            raise BusinessLogicError(f"Invalid timeslot format: {str(e)}", 400)
        
        # Get manually unavailable slots
        unavailable_slots_record = db.get_unavailable_slots(date)
        manually_unavailable_slots = []
        
        if unavailable_slots_record and 'timeSlots' in unavailable_slots_record:
            raw_time_slots = unavailable_slots_record['timeSlots']
            
            # Convert time slots to consistent format
            for slot in raw_time_slots:
                try:
                    if isinstance(slot, str):
                        # Already in "HH:MM-HH:MM" format
                        manually_unavailable_slots.append(slot)
                    elif isinstance(slot, dict):
                        # Convert from object format
                        if 'startTime' in slot and 'endTime' in slot:
                            time_slot = f"{slot['startTime']}-{slot['endTime']}"
                            manually_unavailable_slots.append(time_slot)
                        elif 'start' in slot and 'end' in slot:
                            time_slot = f"{slot['start']}-{slot['end']}"
                            manually_unavailable_slots.append(time_slot)
                        else:
                            print(f"Warning: Unknown manually set slot format: {slot}")
                except Exception as e:
                    print(f"Warning: Error processing manually unavailable slot {slot}: {str(e)}")

        # Check if requested timeslot overlaps with manually blocked slots
        blocked = False
        for slot_str in manually_unavailable_slots:
            try:
                manual_start, manual_end = parse_time_slot(slot_str)
                if time_slots_overlap(check_start, check_end, manual_start, manual_end):
                    blocked = True
                    break
            except ValueError as e:
                print(f"Warning: Invalid manually unavailable slot format {slot_str}: {e}")
                continue

        # Count appointments that overlap with requested timeslot
        appointments_count = 0
        
        # Get scheduled appointment slots (confirmed appointments)
        scheduled_appointments = db.get_appointments_by_scheduled_date(date)
        for appointment in scheduled_appointments:
            try:
                # Check if appointment is confirmed or pending (not cancelled or completed)
                status = appointment.get('status', '').upper() 
                
                if status not in ['CANCELLED', 'COMPLETED']:
                    scheduled_time_slot = appointment.get('scheduledTimeSlot')
                    if scheduled_time_slot and isinstance(scheduled_time_slot, dict):
                        start_time = scheduled_time_slot.get('start')
                        end_time = scheduled_time_slot.get('end')
                        if start_time and end_time:
                            try:
                                appt_start, appt_end = parse_time_slot(f"{start_time}-{end_time}")
                                if time_slots_overlap(check_start, check_end, appt_start, appt_end):
                                    appointments_count += 1
                            except ValueError as e:
                                print(f"Warning: Invalid scheduled appointment slot format {start_time}-{end_time}: {e}")
                        
            except Exception as e:
                print(f"Warning: Error processing scheduled appointment {appointment.get('appointmentId', 'unknown')}: {str(e)}")

        # Get pending appointments with paid status (priority 1 slots)
        pending_appointments = db.get_appointments_by_status('PENDING')
        for appointment in pending_appointments:
            try:
                appointment_id = appointment.get('appointmentId', 'unknown')
                payment_status = appointment.get('paymentStatus', 'unknown')
                
                if appointment.get('paymentStatus') == 'paid':
                    selected_time_slots = appointment.get('selectedSlots')
                    
                    if selected_time_slots and isinstance(selected_time_slots, list):
                        for slot in selected_time_slots:
                            try:
                                if isinstance(slot, dict):
                                    slot_date = slot.get('date')
                                    slot_priority = slot.get('priority')
                                    
                                    if slot_date == date and slot_priority and int(slot_priority) == 1:
                                        start_time = slot.get('start')
                                        end_time = slot.get('end')
                                        if start_time and end_time:
                                            try:
                                                pending_start, pending_end = parse_time_slot(f"{start_time}-{end_time}")
                                                if time_slots_overlap(check_start, check_end, pending_start, pending_end):
                                                    appointments_count += 1
                                            except ValueError as e:
                                                print(f"Warning: Invalid pending appointment slot format {start_time}-{end_time}: {e}")
                                        
                            except Exception as e:
                                print(f"Warning: Error processing slot for appointment {appointment_id}: {str(e)}")
                        
            except Exception as e:
                print(f"Warning: Error processing pending appointment {appointment.get('appointmentId', 'unknown')}: {str(e)}")
        
        return {
            'date': date,
            'requestedSlot': timeslot,
            'appointmentsCount': appointments_count,
            'blocked': blocked
        }
    
    def update_unavailable_slots(self, event, staff_context):
        """
        Update unavailable slots with admin authorization
        
        Args:
            event: Lambda event with parameters
            staff_context: Staff context from authentication
            
        Returns:
            dict: Update result
        """
        # Validate admin permission
        if not any(role in staff_context['staff_roles'] for role in self.admin_roles):
            raise BusinessLogicError("Unauthorized: ADMIN role required", 403)
        
        # Get parameters from query parameters or body
        date = req.get_query_param(event, 'date') or req.get_body_param(event, 'date')
        start_date = req.get_query_param(event, 'startDate') or req.get_body_param(event, 'startDate')
        end_date = req.get_query_param(event, 'endDate') or req.get_body_param(event, 'endDate')
        operation = req.get_body_param(event, 'operation') or 'get'
        time_slots = req.get_body_param(event, 'timeSlots')
        
        # Validate parameters
        using_date_range = start_date and end_date
        using_single_date = date
        
        if not (using_date_range or using_single_date) or not operation:
            raise BusinessLogicError(
                "Either 'date' or both 'startDate' and 'endDate' are required, along with 'operation'", 400
            )
        
        if using_date_range and using_single_date:
            raise BusinessLogicError(
                "Cannot specify both single 'date' and date range ('startDate'/'endDate'). Use one or the other.", 400
            )
        
        if using_single_date:
            return self._update_unavailable_slots_single_date(date, operation, time_slots, staff_context)
        else:
            return self._update_unavailable_slots_date_range(
                start_date, end_date, operation, time_slots, staff_context
            )
    
    def _update_unavailable_slots_single_date(self, date, operation, time_slots, staff_context):
        """Update unavailable slots for a single date"""
        # Validate date
        self.validate_date_parameter(date, 'date')
        
        if operation == 'get':
            return self._get_unavailable_slots_single_date(date)
        
        elif operation in ['set', 'add', 'remove']:
            if not time_slots:
                raise BusinessLogicError("timeSlots parameter is required for set/add/remove operations", 400)
            
            if not isinstance(time_slots, list):
                raise BusinessLogicError("timeSlots must be an array", 400)
            
            # Get current slots
            current_record = db.get_unavailable_slots(date)
            raw_current_slots = current_record.get('timeSlots', []) if current_record else []
            
            # Convert current slots to consistent string format
            current_slots = []
            for slot in raw_current_slots:
                try:
                    if isinstance(slot, str):
                        current_slots.append(slot)
                    elif isinstance(slot, dict):
                        if 'startTime' in slot and 'endTime' in slot:
                            time_slot = f"{slot['startTime']}-{slot['endTime']}"
                            current_slots.append(time_slot)
                        elif 'start' in slot and 'end' in slot:
                            time_slot = f"{slot['start']}-{slot['end']}"
                            current_slots.append(time_slot)
                        else:
                            print(f"Warning: Unknown current slot format: {slot}")
                    else:
                        print(f"Warning: Unexpected slot type {type(slot)}: {slot}")
                except Exception as e:
                    print(f"Warning: Error processing current slot {slot}: {str(e)}")
            
            # Convert input time_slots to consistent string format
            normalized_time_slots = []
            for slot in time_slots:
                try:
                    if isinstance(slot, str):
                        normalized_time_slots.append(slot)
                    elif isinstance(slot, dict):
                        if 'startTime' in slot and 'endTime' in slot:
                            time_slot = f"{slot['startTime']}-{slot['endTime']}"
                            normalized_time_slots.append(time_slot)
                        elif 'start' in slot and 'end' in slot:
                            time_slot = f"{slot['start']}-{slot['end']}"
                            normalized_time_slots.append(time_slot)
                        else:
                            print(f"Warning: Unknown input slot format: {slot}")
                    else:
                        print(f"Warning: Unexpected input slot type {type(slot)}: {slot}")
                except Exception as e:
                    print(f"Warning: Error processing input slot {slot}: {str(e)}")
            
            # Apply operation with smart slot handling
            if operation == 'set':
                # For set operation, just use the new slots (after merging)
                new_slots = merge_time_slots(normalized_time_slots)
            elif operation == 'add':
                # For add operation, merge existing and new slots
                all_slots = current_slots + normalized_time_slots
                new_slots = merge_time_slots(all_slots)
            elif operation == 'remove':
                # For remove operation, subtract slots from existing ones
                new_slots = subtract_time_slots(current_slots, normalized_time_slots)
            
            # Update database
            staff_user_id = staff_context['staff_user_id']
            result = db.update_unavailable_slots(date, new_slots, staff_user_id)
            
            return {
                'date': date,
                'operation': operation,
                'previousSlots': current_slots,
                'newSlots': new_slots,
                'updatedBy': staff_user_id,
                'timestamp': datetime.now(ZoneInfo('Australia/Perth')).isoformat()
            }
        
        else:
            raise BusinessLogicError(f"Invalid operation: {operation}. Must be 'get', 'set', 'add', or 'remove'", 400)
    
    def _update_unavailable_slots_date_range(self, start_date, end_date, operation, time_slots, staff_context):
        """Update unavailable slots for a date range"""
        # Validate date range - note: this returns timestamps, not datetime objects
        start_timestamp, end_timestamp = self.validate_date_range(start_date, end_date)
        
        # Convert timestamps back to datetime objects for iteration
        start_dt = datetime.fromtimestamp(start_timestamp, ZoneInfo('Australia/Perth'))
        end_dt = datetime.fromtimestamp(end_timestamp, ZoneInfo('Australia/Perth'))
        
        if operation == 'get':
            return self._get_unavailable_slots_date_range(start_date, end_date)
        
        elif operation in ['set', 'add', 'remove']:
            if not time_slots:
                raise BusinessLogicError("timeSlots parameter is required for set/add/remove operations", 400)
            
            # Apply operation to each date in range
            results = {}
            current_date = start_dt
            
            while current_date <= end_dt:
                date_str = current_date.strftime('%Y-%m-%d')
                try:
                    result = self._update_unavailable_slots_single_date(
                        date_str, operation, time_slots, staff_context
                    )
                    results[date_str] = result
                except Exception as e:
                    results[date_str] = {
                        'error': str(e),
                        'date': date_str
                    }
                current_date += timedelta(days=1)
            
            return {
                'dateRange': {
                    'startDate': start_date,
                    'endDate': end_date
                },
                'operation': operation,
                'results': results,
                'updatedBy': staff_context['staff_user_id'],
                'timestamp': datetime.now(ZoneInfo('Australia/Perth')).isoformat()
            }
        
        else:
            raise BusinessLogicError(f"Invalid operation: {operation}. Must be 'get', 'set', 'add', or 'remove'", 400)


def get_unavailable_slot_manager():
    """Factory function to get UnavailableSlotManager instance"""
    return UnavailableSlotManager()
