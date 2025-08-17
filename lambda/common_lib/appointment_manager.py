"""
Appointment Management Module
Handles appointment creation and update business logic and workflows
"""

import uuid
import time
from decimal import Decimal

import permission_utils as perm
import db_utils as db
import email_utils as email
from notification_manager import notification_manager
from exceptions import BusinessLogicError


class AppointmentManager:
    """Manages appointment-related business logic"""
    
    APPOINTMENTS_LIMIT = 3  # Maximum number of appointments per day
    
    @staticmethod
    def create_appointment(staff_user_email, user_id, appointment_data):
        """
        Complete appointment creation workflow
        
        Args:
            staff_user_email (str): Staff user email (optional)
            user_id (str): User ID
            appointment_data (dict): Appointment data
            
        Returns:
            dict: Success response with appointment ID
            
        Raises:
            BusinessLogicError: If creation fails
        """
        # Validate permissions
        staff_context = perm.PermissionValidator.validate_staff_access(
            staff_user_email, 
            required_roles=['CUSTOMER_SUPPORT'],
            optional=True
        )
        
        user_context = perm.PermissionValidator.validate_user_access(
            user_id, 
            staff_context
        )
        
        effective_user_id = user_context['effective_user_id']
        is_staff_user = bool(staff_context['staff_record'])
        
        # Validate daily limits
        perm.PermissionValidator.validate_daily_limits(
            effective_user_id,
            'appointments',
            AppointmentManager.APPOINTMENTS_LIMIT,
            staff_override=is_staff_user
        )
        
        # Generate unique appointment ID
        appointment_id = str(uuid.uuid4())
        
        # Get pricing
        price = db.get_service_pricing(
            service_id=appointment_data.get('serviceId'),
            plan_id=appointment_data.get('planId')
        )
        if price is None:
            raise BusinessLogicError("Invalid service or plan. Please check the serviceId and planId provided.")
        
        # Build appointment data
        db_appointment_data = db.build_appointment_data(
            appointment_id=appointment_id,
            service_id=appointment_data.get('serviceId'),
            plan_id=appointment_data.get('planId'),
            is_buyer=appointment_data.get('isBuyer', True),
            buyer_data=appointment_data.get('buyerData', {}),
            car_data=appointment_data.get('carData', {}),
            seller_data=appointment_data.get('sellerData', {}),
            notes=appointment_data.get('notes', ''),
            selected_slots=appointment_data.get('selectedSlots', []),
            created_user_id=effective_user_id,
            price=price
        )
        
        # Create appointment in database
        success = db.create_appointment(db_appointment_data)
        if not success:
            raise BusinessLogicError("Failed to create appointment", 500)
        
        # Send notifications
        AppointmentManager._send_creation_notifications(appointment_id, appointment_data, price, effective_user_id)
        
        return {
            "message": "Appointment created successfully",
            "appointmentId": appointment_id
        }
    
    @staticmethod
    def _send_creation_notifications(appointment_id, appointment_data, price, user_id):
        """Send all notifications for appointment creation"""
        try:
            # Email notification to customer
            service_name, plan_name = db.get_service_plan_names(
                appointment_data.get('serviceId'), 
                appointment_data.get('planId')
            )
            
            email_appointment_data = {
                'appointmentId': appointment_id,
                'services': [{
                    'serviceName': service_name,
                    'planName': plan_name,
                }],
                'totalPrice': f"{price:.2f}",
                'selectedSlots': appointment_data.get('selectedSlots', []),
                'vehicleInfo': appointment_data.get('carData', {}),
                'customerData': appointment_data.get('buyerData', {}) if appointment_data.get('isBuyer', True) else appointment_data.get('sellerData', {}),
            }
            
            customer_email = appointment_data.get('buyerData', {}).get('email') if appointment_data.get('isBuyer', True) else appointment_data.get('sellerData', {}).get('email')
            customer_name = appointment_data.get('buyerData', {}).get('name') if appointment_data.get('isBuyer', True) else appointment_data.get('sellerData', {}).get('name')
            
            notification_manager.queue_appointment_created_email(customer_email, customer_name, email_appointment_data)
            
            # Staff WebSocket notifications
            staff_notification_data = {
                "type": "appointment",
                "subtype": "create",
                "success": True,
                "appointmentId": appointment_id,
                "appointmentData": appointment_data
            }
            notification_manager.queue_staff_websocket_notification(staff_notification_data, assigned_to=user_id)
            
            # Firebase push notification to staff
            notification_manager.queue_appointment_firebase_notification(appointment_id, 'create')
            
        except Exception as e:
            print(f"Failed to send appointment creation notifications: {str(e)}")
            # Don't fail the appointment creation if notifications fail


class AppointmentUpdateManager:
    """Manages appointment update business logic"""
    
    CS_TRANSITIONS = {
        'PENDING': ['SCHEDULED', 'CANCELLED'],
        'SCHEDULED': ['PENDING', 'CANCELLED'],
        'ONGOING': ['SCHEDULED', 'CANCELLED'],
        'CANCELLED': ['PENDING', 'SCHEDULED']
    }
    
    MECHANIC_TRANSITIONS = {
        'SCHEDULED': ['ONGOING'],
        'ONGOING': ['COMPLETED', 'SCHEDULED'],
        'COMPLETED': ['ONGOING']
    }
    
    @staticmethod
    def update_appointment(staff_user_email, appointment_id, update_data):
        """Complete appointment update workflow"""
        staff_context = perm.PermissionValidator.validate_staff_access(staff_user_email)
        staff_roles = staff_context['roles']
        staff_user_id = staff_context['user_id']
        
        existing_appointment = db.get_appointment(appointment_id)
        if not existing_appointment:
            raise BusinessLogicError("Appointment not found", 404)
        
        current_status = existing_appointment.get('status', '')
        assigned_mechanic_id = existing_appointment.get('assignedMechanicId', '')
        payment_completed = existing_appointment.get('paymentStatus', 'pending') == 'paid'
        
        scenario = AppointmentUpdateManager._determine_scenario(update_data)
        AppointmentUpdateManager._validate_update_permissions(
            scenario, staff_roles, current_status, staff_user_id, assigned_mechanic_id
        )
        
        processed_data = AppointmentUpdateManager._process_update_data(
            scenario, update_data, existing_appointment, staff_roles, 
            staff_user_id, assigned_mechanic_id, payment_completed
        )
        
        processed_data['updatedAt'] = int(time.time())
        
        success = db.update_appointment(appointment_id, processed_data)
        if not success:
            raise BusinessLogicError("Failed to update appointment", 500)
        
        updated_appointment = db.get_appointment(appointment_id)
        AppointmentUpdateManager._send_update_notifications(
            appointment_id, scenario, processed_data, updated_appointment
        )
        
        return {
            "message": "Appointment updated successfully",
            "appointment": updated_appointment
        }
    
    @staticmethod
    def _determine_scenario(update_data):
        if 'status' in update_data:
            return 'status'
        elif 'reports' in update_data or 'postNotes' in update_data:
            return 'reports'
        elif 'scheduledTimeSlot' in update_data or 'assignedMechanicId' in update_data:
            return 'scheduling'
        else:
            return 'basic_info'
    
    @staticmethod
    def _validate_update_permissions(scenario, staff_roles, current_status, staff_user_id, assigned_mechanic_id):
        if scenario == 'basic_info':
            if 'CUSTOMER_SUPPORT' not in staff_roles:
                raise BusinessLogicError('Unauthorized: CUSTOMER_SUPPORT role required', 403)
            if current_status not in ['PENDING', 'SCHEDULED', 'ONGOING']:
                raise BusinessLogicError(f'Cannot update basic info when status is {current_status}', 400)
        elif scenario == 'scheduling':
            if 'CUSTOMER_SUPPORT' not in staff_roles:
                raise BusinessLogicError('Unauthorized: CUSTOMER_SUPPORT role required', 403)
            if current_status not in ['PENDING', 'SCHEDULED']:
                raise BusinessLogicError(f'Cannot update scheduling when status is {current_status}', 400)
        elif scenario == 'reports':
            if not any(role in staff_roles for role in ['MECHANIC', 'CUSTOMER_SUPPORT', 'CLERK']):
                raise BusinessLogicError('Unauthorized: MECHANIC, CUSTOMER_SUPPORT, or CLERK role required', 403)
            if 'MECHANIC' in staff_roles and assigned_mechanic_id != staff_user_id:
                raise BusinessLogicError('Unauthorized: You must be assigned to this appointment', 403)
            if current_status != 'COMPLETED':
                raise BusinessLogicError(f'Cannot update reports when status is {current_status}', 400)
    
    @staticmethod
    def _process_update_data(scenario, update_data, existing_appointment, staff_roles, 
                           staff_user_id, assigned_mechanic_id, payment_completed):
        processed_data = {}
        
        if scenario == 'basic_info':
            processed_data = AppointmentUpdateManager._process_basic_info(
                update_data, existing_appointment, payment_completed
            )
        elif scenario == 'scheduling':
            processed_data = AppointmentUpdateManager._process_scheduling(update_data)
        elif scenario == 'status':
            new_status = update_data.get('status')
            if not AppointmentUpdateManager._validate_status_transition(
                existing_appointment.get('status'), new_status, staff_roles, staff_user_id, assigned_mechanic_id
            ):
                raise BusinessLogicError(f"Invalid status transition", 400)
            processed_data['status'] = new_status
        elif scenario == 'reports':
            processed_data = AppointmentUpdateManager._process_reports(update_data)
        
        return processed_data
    
    @staticmethod
    def _process_basic_info(update_data, existing_appointment, payment_completed):
        processed = {}
        
        if 'serviceId' in update_data:
            if payment_completed:
                raise BusinessLogicError("Cannot update serviceId after payment is completed", 400)
            processed['serviceId'] = update_data['serviceId']
            plan_id = update_data.get('planId', existing_appointment.get('planId'))
            price = db.get_service_pricing(update_data['serviceId'], plan_id)
            if price is None:
                raise BusinessLogicError("Invalid service or plan")
            processed['price'] = price
        
        if 'planId' in update_data:
            if payment_completed:
                raise BusinessLogicError("Cannot update planId after payment is completed", 400)
            processed['planId'] = update_data['planId']
            service_id = update_data.get('serviceId', existing_appointment.get('serviceId'))
            price = db.get_service_pricing(service_id, update_data['planId'])
            if price is None:
                raise BusinessLogicError("Invalid service or plan")
            processed['price'] = price
        
        for field in ['isBuyer', 'notes']:
            if field in update_data:
                processed[field] = update_data[field]
        
        if 'buyerData' in update_data:
            buyer_data = update_data['buyerData']
            for key, field in [('name', 'buyerName'), ('email', 'buyerEmail'), ('phoneNumber', 'buyerPhone')]:
                if key in buyer_data:
                    processed[field] = buyer_data[key]
        
        if 'carData' in update_data:
            car_data = update_data['carData']
            for key, field in [('make', 'carMake'), ('model', 'carModel'), ('year', 'carYear'), ('location', 'carLocation')]:
                if key in car_data:
                    processed[field] = str(car_data[key]) if key == 'year' else car_data[key]
        
        if 'sellerData' in update_data:
            seller_data = update_data['sellerData']
            for key, field in [('name', 'sellerName'), ('email', 'sellerEmail'), ('phoneNumber', 'sellerPhone')]:
                if key in seller_data:
                    processed[field] = seller_data[key]
        
        return processed
    
    @staticmethod
    def _process_scheduling(update_data):
        processed = {}
        
        if 'scheduledTimeSlot' in update_data:
            scheduled_slot = update_data['scheduledTimeSlot']
            if isinstance(scheduled_slot, dict) and scheduled_slot:
                processed['scheduledTimeSlot'] = {
                    'date': scheduled_slot.get('date', ''),
                    'start': scheduled_slot.get('start', ''),
                    'end': scheduled_slot.get('end', '')
                }
                processed['scheduledDate'] = scheduled_slot.get('date', '')
            else:
                processed['scheduledTimeSlot'] = {}
                processed['scheduledDate'] = ''
        
        if 'assignedMechanicId' in update_data:
            mechanic_id = update_data['assignedMechanicId']
            if mechanic_id:
                mechanic_record = db.get_staff_record_by_user_id(mechanic_id)
                if not mechanic_record or 'MECHANIC' not in mechanic_record.get('roles', []):
                    raise BusinessLogicError("Invalid mechanic ID")
            processed['assignedMechanicId'] = mechanic_id
        
        return processed
    
    @staticmethod
    def _process_reports(update_data):
        processed = {}
        
        if 'postNotes' in update_data:
            processed['postNotes'] = update_data['postNotes']
        
        if 'reports' in update_data:
            reports = update_data['reports']
            if isinstance(reports, list):
                processed['reports'] = reports
        
        return processed
    
    @staticmethod
    def _validate_status_transition(current_status, new_status, staff_roles, staff_user_id, assigned_mechanic_id):
        if 'CUSTOMER_SUPPORT' in staff_roles and new_status in AppointmentUpdateManager.CS_TRANSITIONS.get(current_status, []):
            return True
        
        if ('MECHANIC' in staff_roles and 
            assigned_mechanic_id == staff_user_id and 
            new_status in AppointmentUpdateManager.MECHANIC_TRANSITIONS.get(current_status, [])):
            return True
        
        return False
    
    @staticmethod
    def _send_update_notifications(appointment_id, scenario, update_data, updated_appointment):
        try:
            customer_user_id = updated_appointment.get('createdUserId')
            if customer_user_id:
                notification_manager.queue_appointment_websocket_notification(appointment_id, scenario, update_data, customer_user_id)
        except Exception as e:
            print(f"Failed to queue WebSocket notification: {str(e)}")
        
        try:
            is_buyer = updated_appointment.get('isBuyer', True)
            customer_email = updated_appointment.get('buyerEmail' if is_buyer else 'sellerEmail')
            customer_name = updated_appointment.get('buyerName' if is_buyer else 'sellerName', 'Valued Customer')
            
            if customer_email:
                email_appointment_data, changes = email.prepare_email_data_and_changes(
                    updated_appointment, update_data, 'appointment'
                )
                
                if 'reportUrl' in update_data and update_data.get('reportUrl'):
                    notification_manager.queue_report_ready_email(
                        customer_email, customer_name, email_appointment_data, update_data.get('reportUrl')
                    )
                elif scenario == 'status':
                    notification_manager.queue_appointment_updated_email(customer_email, customer_name, email_appointment_data, changes, 'status')
                else:
                    notification_manager.queue_appointment_updated_email(customer_email, customer_name, email_appointment_data, changes, 'general')
        except Exception as e:
            print(f"Failed to queue email notification: {str(e)}")
