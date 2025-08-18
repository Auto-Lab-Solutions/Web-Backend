"""
Unavailable Slots Manager for API operations

This module provides managers for unavailable slots operations,
including reading and updating slot availability.
"""

from datetime import datetime, timedelta

import db_utils as db
import request_utils as req
from exceptions import BusinessLogicError
from data_access_utils import DataAccessManager


class UnavailableSlotManager(DataAccessManager):
    """Manager for unavailable slots operations"""
    
    def __init__(self):
        super().__init__()
        self.admin_roles = ['ADMIN']
    
    def get_unavailable_slots(self, event):
        """
        Get unavailable slots for date or date range
        
        Args:
            event: Lambda event with query parameters
            
        Returns:
            dict: Unavailable slots data
        """
        # Get parameters - support both single date and date range
        date = req.get_query_param(event, 'date')
        start_date = req.get_query_param(event, 'startDate')
        end_date = req.get_query_param(event, 'endDate')
        
        # Validate parameters
        using_date_range = start_date and end_date
        using_single_date = date
        
        if not (using_date_range or using_single_date):
            raise BusinessLogicError(
                "Either 'date' or both 'startDate' and 'endDate' parameters are required", 400
            )
        
        if using_date_range and using_single_date:
            raise BusinessLogicError(
                "Cannot specify both single 'date' and date range ('startDate'/'endDate'). Use one or the other.", 400
            )
        
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
            manually_unavailable_slots = unavailable_slots_record['timeSlots']
        
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
            appointments = db.get_appointments_by_date(date)
            scheduled_slots = []
            
            for appointment in appointments:
                # Check if appointment is confirmed or pending (not cancelled)
                status = appointment.get('status', '').upper()
                if status not in ['CANCELLED', 'COMPLETED']:
                    time_slot = appointment.get('timeSlot')
                    if time_slot:
                        scheduled_slots.append({
                            'timeSlot': time_slot,
                            'reason': 'scheduled_appointment',
                            'appointmentId': appointment.get('appointmentId'),
                            'status': status
                        })
            
            return scheduled_slots
        except Exception as e:
            print(f"Error getting scheduled appointments for {date}: {str(e)}")
            return []
    
    def _merge_unavailable_slots(self, manually_unavailable, scheduled_slots):
        """Merge manually unavailable slots and scheduled appointment slots"""
        all_slots = []
        
        # Add manually unavailable slots
        for slot in manually_unavailable:
            if isinstance(slot, str):
                all_slots.append({
                    'timeSlot': slot,
                    'reason': 'manually_set'
                })
            elif isinstance(slot, dict):
                slot_copy = slot.copy()
                if 'reason' not in slot_copy:
                    slot_copy['reason'] = 'manually_set'
                all_slots.append(slot_copy)
        
        # Add scheduled slots
        all_slots.extend(scheduled_slots)
        
        # Remove duplicates while preserving order
        seen_slots = set()
        unique_slots = []
        
        for slot in all_slots:
            time_slot = slot.get('timeSlot') if isinstance(slot, dict) else slot
            if time_slot not in seen_slots:
                seen_slots.add(time_slot)
                unique_slots.append(slot)
        
        return unique_slots
    
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
            current_slots = current_record.get('timeSlots', []) if current_record else []
            
            # Apply operation
            if operation == 'set':
                new_slots = time_slots
            elif operation == 'add':
                new_slots = list(set(current_slots + time_slots))  # Remove duplicates
            elif operation == 'remove':
                new_slots = [slot for slot in current_slots if slot not in time_slots]
            
            # Update database
            staff_user_id = staff_context['staff_user_id']
            result = db.update_unavailable_slots(date, new_slots, staff_user_id)
            
            return {
                'date': date,
                'operation': operation,
                'previousSlots': current_slots,
                'newSlots': new_slots,
                'updatedBy': staff_user_id,
                'timestamp': datetime.utcnow().isoformat()
            }
        
        else:
            raise BusinessLogicError(f"Invalid operation: {operation}. Must be 'get', 'set', 'add', or 'remove'", 400)
    
    def _update_unavailable_slots_date_range(self, start_date, end_date, operation, time_slots, staff_context):
        """Update unavailable slots for a date range"""
        # Validate date range
        start_dt, end_dt = self.validate_date_range(start_date, end_date)
        
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
                'timestamp': datetime.utcnow().isoformat()
            }
        
        else:
            raise BusinessLogicError(f"Invalid operation: {operation}. Must be 'get', 'set', 'add', or 'remove'", 400)


def get_unavailable_slot_manager():
    """Factory function to get UnavailableSlotManager instance"""
    return UnavailableSlotManager()
