"""
Appointment Management Module
Handles appointment creation and update business logic and workflows
"""

import uuid
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from decimal import Decimal

import permission_utils as perm
import db_utils as db
import email_utils as email
import s3_utils as s3
import response_utils as resp
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
            # Get customer details for email from appointment data only
            customer_email = None
            customer_name = 'Valued Customer'
            
            # Determine if buyer or seller and get appropriate data
            is_buyer = appointment_data.get('isBuyer', True)
            if is_buyer:
                customer_data = appointment_data.get('buyerData', {})
            else:
                customer_data = appointment_data.get('sellerData', {})
            
            # Get email and name from appointment data only
            customer_email = customer_data.get('email')
            customer_name = customer_data.get('name', 'Valued Customer')
            
            # Send customer email notification if we have an email
            if customer_email:
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
                    'customerData': customer_data,
                    'assignedMechanic': 'Our team'  # Default for new appointments
                }
                
                notification_manager.queue_appointment_created_email(customer_email, customer_name, email_appointment_data)
            else:
                print(f"Warning: No email found in appointment data for appointment {appointment_id}")
            
            # Staff WebSocket notifications - notify all staff, not the customer
            staff_notification_data = {
                "type": "appointment",
                "subtype": "create",
                "success": True,
                "appointmentId": appointment_id,
                "appointmentData": appointment_data
            }
            # Removed: WebSocket notification for appointments (not messaging-related)
            # As per requirements, websocket notifications are only for messaging scenarios
            
            # Firebase push notification to staff
            notification_manager.queue_appointment_firebase_notification(appointment_id, 'create')
            
        except Exception as e:
            print(f"Failed to send appointment creation notifications: {str(e)}")
            # Don't fail the appointment creation if notifications fail


class AppointmentUpdateManager:
    """Manages appointment update business logic"""
    
    CS_TRANSITIONS = {
        'PENDING': ['CANCELLED'],  # SCHEDULED status is set automatically via scheduling scenario
        'SCHEDULED': ['PENDING', 'CANCELLED'],
        'ONGOING': ['SCHEDULED', 'CANCELLED'],
        'CANCELLED': ['PENDING']  # Cannot go directly to SCHEDULED, must use scheduling scenario
    }
    
    MECHANIC_TRANSITIONS = {
        'SCHEDULED': ['ONGOING', 'COMPLETED'],
        'ONGOING': ['COMPLETED', 'SCHEDULED'],
        'COMPLETED': ['ONGOING', 'SCHEDULED']
    }
    
    @staticmethod
    def update_appointment(staff_user_email, appointment_id, update_data):
        """Complete appointment update workflow"""
        staff_context = perm.PermissionValidator.validate_staff_access(staff_user_email)
        staff_roles = staff_context['staff_roles']
        staff_user_id = staff_context['staff_user_id']
        
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
        
        processed_data['updatedAt'] = int(datetime.now(ZoneInfo('Australia/Perth')).timestamp())
        
        success = db.update_appointment(appointment_id, processed_data)
        if not success:
            raise BusinessLogicError("Failed to update appointment", 500)
        
        # Update invoice effective date if this is a scheduling update and payment is completed
        if scenario == 'scheduling' and payment_completed and 'scheduledDate' in processed_data:
            scheduled_date = processed_data.get('scheduledDate')
            if scheduled_date:  # Only update if we have a valid scheduled date
                try:
                    import invoice_data_utils
                    invoice_data_utils.update_invoice_effective_date(appointment_id, 'appointment', scheduled_date)
                except Exception as e:
                    print(f"Warning: Failed to update invoice effective date for appointment {appointment_id}: {str(e)}")
                    # Don't fail the appointment update if invoice update fails
        
        # Cancel invoices if appointment is cancelled
        if 'status' in processed_data and processed_data['status'] == 'CANCELLED':
            try:
                AppointmentUpdateManager._cancel_appointment_invoices(appointment_id)
            except Exception as e:
                print(f"Warning: Failed to cancel invoices for cancelled appointment {appointment_id}: {str(e)}")
                # Don't fail the appointment update if invoice cancellation fails
        
        updated_appointment = db.get_appointment(appointment_id)
        AppointmentUpdateManager._send_update_notifications(
            appointment_id, scenario, update_data, updated_appointment
        )
        
        return {
            "message": "Appointment updated successfully",
            "appointment": resp.convert_decimal(updated_appointment)
        }
    
    @staticmethod
    def _determine_scenario(update_data):
        if 'status' in update_data:
            return 'status'
        elif 'reportApproval' in update_data:
            return 'report_approval'
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
        elif scenario == 'report_approval':
            if 'ADMIN' not in staff_roles:
                raise BusinessLogicError('Unauthorized: ADMIN role required for report approval', 403)
            if current_status != 'COMPLETED':
                raise BusinessLogicError(f'Cannot approve reports when status is {current_status}', 400)
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
        
        # Handle multiple scenarios in a single update request
        # Process all applicable fields regardless of primary scenario
        
        # Process basic info fields if present
        if any(field in update_data for field in ['serviceId', 'planId', 'isBuyer', 'notes', 'buyerData', 'carData', 'sellerData']):
            basic_info_data = AppointmentUpdateManager._process_basic_info(
                update_data, existing_appointment, payment_completed
            )
            processed_data.update(basic_info_data)
        
        # Process scheduling fields if present
        if any(field in update_data for field in ['scheduledTimeSlot', 'assignedMechanicId']):
            scheduling_data = AppointmentUpdateManager._process_scheduling(update_data)
            processed_data.update(scheduling_data)
        
        # Process status field if present
        if 'status' in update_data:
            new_status = update_data.get('status')
            if not AppointmentUpdateManager._validate_status_transition(
                existing_appointment.get('status'), new_status, staff_roles, staff_user_id, assigned_mechanic_id
            ):
                raise BusinessLogicError(f"Invalid status transition", 400)
            processed_data['status'] = new_status
        
        # Process report approval if present
        if 'reportApproval' in update_data:
            report_approval_data = AppointmentUpdateManager._process_report_approval(
                update_data, existing_appointment, staff_user_id
            )
            processed_data.update(report_approval_data)
        
        # Process reports fields if present
        if any(field in update_data for field in ['reports', 'postNotes']):
            reports_data = AppointmentUpdateManager._process_reports(update_data, existing_appointment)
            processed_data.update(reports_data)
        
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
        
        # Automatically set status to SCHEDULED when making scheduling updates
        # This prevents the need for separate scheduling + status API calls
        if processed:  # Only set status if we actually have scheduling data
            processed['status'] = 'SCHEDULED'
        
        return processed
    
    @staticmethod
    def _process_reports(update_data, existing_appointment=None):
        processed = {}
        
        if 'postNotes' in update_data:
            processed['postNotes'] = update_data['postNotes']
        
        if 'reports' in update_data:
            reports = update_data['reports']
            if isinstance(reports, list):
                # Get existing reports to preserve review state
                existing_reports = existing_appointment.get('reports', []) if existing_appointment else []
                
                # Create a map of existing reports by S3 key for quick lookup
                existing_reports_map = {}
                for existing_report in existing_reports:
                    s3_key = existing_report.get('s3Key') or existing_report.get('fileKey')
                    if s3_key:
                        existing_reports_map[s3_key] = existing_report
                
                # Process each report, preserving review state if it exists
                for i, report in enumerate(reports):
                    # Check for S3 key - handle both 's3Key' and 'fileKey' for backward compatibility
                    s3_key = report.get('s3Key') or report.get('fileKey')
                    if not s3_key:
                        raise BusinessLogicError(f"Report at index {i} is missing S3 key (s3Key or fileKey). Report data: {report}")
                    
                    # Normalize the field name to 's3Key' for consistency
                    if 'fileKey' in report and 's3Key' not in report:
                        report['s3Key'] = report['fileKey']
                    
                    if not report.get('fileName'):
                        raise BusinessLogicError(f"Report at index {i} is missing fileName. Report data: {report}")
                    if not report.get('uploadedBy'):
                        raise BusinessLogicError(f"Report at index {i} is missing uploadedBy. Report data: {report}")
                    
                    # Allow reportNotes field for uploader notes to reviewer
                    if 'reportNotes' in report:
                        # Validate that reportNotes is a string if provided
                        if not isinstance(report['reportNotes'], str):
                            raise BusinessLogicError(f"Report at index {i} has invalid reportNotes. Must be a string.")
                    
                    # CRITICAL: Preserve review state from existing report if it exists
                    existing_report = existing_reports_map.get(s3_key)
                    if existing_report and existing_report.get('reviewed', False):
                        # Preserve all review-related fields from existing report
                        review_fields = ['reviewed', 'approved', 'reviewedAt', 'reviewedBy', 'reviewNotes']
                        for field in review_fields:
                            if field in existing_report:
                                report[field] = existing_report[field]
                        print(f"Preserved review state for report {i} with S3 key: {s3_key}")
                    
                    # IMPORTANT: Preserve existing fileUrl if it exists and is valid CloudFront URL
                    # Only regenerate if fileUrl is missing or appears to be old S3 format
                    existing_file_url = report.get('fileUrl', '')
                    if not existing_file_url or not existing_file_url.startswith('https://') or '.s3.amazonaws.com' in existing_file_url:
                        # Generate new CloudFront URL if fileUrl is missing or is old S3 format
                        try:
                            import s3_utils as s3
                            new_file_url = s3.generate_public_url(file_key=s3_key)
                            report['fileUrl'] = new_file_url
                            print(f"Regenerated fileUrl for report {i}: {new_file_url}")
                        except Exception as e:
                            print(f"Warning: Could not regenerate fileUrl for report {i}: {str(e)}")
                            # Keep existing fileUrl if regeneration fails
                    else:
                        print(f"Preserving existing valid fileUrl for report {i}: {existing_file_url}")
                
                processed['reports'] = reports
        
        return processed
    
    @staticmethod
    def _process_report_approval(update_data, existing_appointment, staff_user_id):
        """Process report approval/rejection"""
        processed = {}
        
        report_approval = update_data.get('reportApproval', {})
        report_s3_key = report_approval.get('reportS3Key')
        action = report_approval.get('action')  # 'approve' or 'reject'
        notes = report_approval.get('notes', '')
        
        if not report_s3_key:
            raise BusinessLogicError("reportS3Key is required for report approval")
        
        # Trim whitespace and validate the S3 key format
        report_s3_key = report_s3_key.strip()
        if not report_s3_key.startswith('reports/'):
            raise BusinessLogicError(f"Invalid S3 key format. Expected to start with 'reports/', got: {report_s3_key}")
        
        if action not in ['approve', 'reject']:
            raise BusinessLogicError("action must be 'approve' or 'reject'")        # Find the report in the existing appointment
        reports = existing_appointment.get('reports', [])
        target_report = None
        report_index = None
        
        # First pass: exact match - check both s3Key and fileKey for backward compatibility
        for i, report in enumerate(reports):
            report_key = report.get('s3Key') or report.get('fileKey')
            if report_key == report_s3_key:
                target_report = report
                report_index = i
                break
        
        # Second pass: case-insensitive match (for debugging purposes)
        if not target_report:
            for i, report in enumerate(reports):
                report_key = report.get('s3Key') or report.get('fileKey')
                if report_key and report_key.lower() == report_s3_key.lower():
                    print(f"Warning: Found case-insensitive match for S3 key. "
                          f"Requested: '{report_s3_key}', Found: '{report_key}'")
                    # Don't use this match, but log it for debugging
        
        if not target_report:
            # Provide more detailed error information for debugging
            available_s3_keys = []
            for report in reports:
                s3_key = report.get('s3Key') or report.get('fileKey') or 'NO_S3_KEY'
                available_s3_keys.append(s3_key)
            
            # Check if any reports have missing S3 keys (check both field names)
            missing_s3_key_reports = []
            for i, report in enumerate(reports):
                if not (report.get('s3Key') or report.get('fileKey')):
                    missing_s3_key_reports.append(i)
            
            error_msg = (
                f"Report with S3 key '{report_s3_key}' not found. "
                f"Available reports in appointment: {len(reports)} total. "
                f"Available S3 keys: {available_s3_keys}"
            )
            
            if missing_s3_key_reports:
                error_msg += (
                    f". WARNING: Found {len(missing_s3_key_reports)} report(s) with missing S3 keys at indexes: {missing_s3_key_reports}. "
                    f"This indicates a data integrity issue - reports exist but S3 keys are missing. "
                    f"To fix this, you need to either: 1) Re-upload the report, or 2) Manually update the database record with the correct S3 key if the file exists in S3."
                )
            
            raise BusinessLogicError(error_msg)
        
        if target_report.get('reviewed', False):
            raise BusinessLogicError("Report has already been reviewed")
        
        # Update the report with approval information
        updated_report = target_report.copy()
        updated_report['reviewed'] = True
        updated_report['approved'] = (action == 'approve')
        updated_report['reviewedBy'] = staff_user_id
        updated_report['reviewedAt'] = int(datetime.now(ZoneInfo('Australia/Perth')).timestamp())
        
        if notes:
            updated_report['reviewNotes'] = notes
        
        # Update the reports array
        updated_reports = reports.copy()
        updated_reports[report_index] = updated_report
        processed['reports'] = updated_reports
        
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
    def _cancel_appointment_invoices(appointment_id):
        """Cancel invoices associated with a cancelled appointment by updating their status"""
        try:
            # Get all invoices for this appointment
            invoices = db.get_invoices_by_reference(appointment_id, 'appointment')
            
            if invoices:
                print(f"Found {len(invoices)} invoice(s) for cancelled appointment {appointment_id}")
                
                for invoice in invoices:
                    invoice_id = invoice.get('invoiceId')
                    if invoice_id:
                        try:
                            # Check if invoice is already cancelled
                            if invoice.get('status') == 'cancelled':
                                print(f"Invoice {invoice_id} is already cancelled for appointment {appointment_id}")
                                continue
                                
                            # Cancel the invoice (updates status to 'cancelled')
                            success = db.cancel_invoice(invoice_id)
                            if success:
                                print(f"Cancelled invoice {invoice_id} for cancelled appointment {appointment_id}")
                            else:
                                print(f"Failed to cancel invoice {invoice_id} for cancelled appointment {appointment_id}")
                        except Exception as e:
                            print(f"Error cancelling invoice {invoice_id}: {str(e)}")
            else:
                print(f"No invoices found for cancelled appointment {appointment_id}")
                
        except Exception as e:
            print(f"Error retrieving invoices for cancelled appointment {appointment_id}: {str(e)}")
            raise
    
    @staticmethod
    def _send_update_notifications(appointment_id, scenario, update_data, updated_appointment):
        try:
            # Customer email notifications
            is_buyer = updated_appointment.get('isBuyer', True)
            customer_email = updated_appointment.get('buyerEmail' if is_buyer else 'sellerEmail')
            customer_name = updated_appointment.get('buyerName' if is_buyer else 'sellerName', 'Valued Customer')
            
            if customer_email:
                # Prepare appointment data with resolved mechanic name
                email_appointment_data = dict(updated_appointment)
                
                # Resolve mechanic name if assigned
                if updated_appointment.get('assignedMechanicId'):
                    try:
                        mechanic_record = db.get_staff_record_by_user_id(updated_appointment['assignedMechanicId'])
                        if mechanic_record:
                            email_appointment_data['assignedMechanic'] = mechanic_record.get('userName', 'Our team')
                        else:
                            email_appointment_data['assignedMechanic'] = 'Our team'
                    except Exception as e:
                        print(f"Error getting mechanic name: {str(e)}")
                        email_appointment_data['assignedMechanic'] = 'Our team'
                else:
                    email_appointment_data['assignedMechanic'] = 'Our team'
                
                # Format price for email display
                if updated_appointment.get('price'):
                    try:
                        price_value = float(updated_appointment.get('price', 0))
                        email_appointment_data['totalPrice'] = f"{price_value:.2f}"
                        email_appointment_data['price'] = f"{price_value:.2f}"  # Keep for backward compatibility
                    except (ValueError, TypeError):
                        email_appointment_data['totalPrice'] = "0.00"
                        email_appointment_data['price'] = "0.00"
                else:
                    email_appointment_data['totalPrice'] = "0.00"
                    email_appointment_data['price'] = "0.00"
                
                # Resolve service and plan names if available
                if updated_appointment.get('serviceId') and updated_appointment.get('planId'):
                    try:
                        service_name, plan_name = db.get_service_plan_names(
                            updated_appointment['serviceId'], 
                            updated_appointment['planId']
                        )
                        email_appointment_data['serviceName'] = service_name
                        email_appointment_data['planName'] = plan_name
                    except Exception as e:
                        print(f"Error getting service/plan names: {str(e)}")
                
                # Replace assignedMechanicId with assignedMechanic name in update_data for email changes
                if 'assignedMechanicId' in update_data:
                    update_data['assignedMechanic'] = email_appointment_data['assignedMechanic']
                    del update_data['assignedMechanicId']

                email_appointment_data, changes = email.prepare_email_data_and_changes(
                    email_appointment_data, update_data, 'appointment'
                )
                
                # Determine if this is a scheduling operation that should send an email
                has_scheduling_changes = any(key in update_data for key in ['scheduledTimeSlot', 'assignedMechanicId'])
                has_status_change = 'status' in update_data
                
                # Intelligent email sending logic to prevent duplicates
                if has_scheduling_changes:
                    # Scheduling update (status is automatically set to SCHEDULED)
                    existing_slot = updated_appointment.get('scheduledTimeSlot')
                    is_initial_scheduling = not existing_slot or not existing_slot.get('date')
                    
                    # Create scheduling context for email
                    scheduling_context = "scheduled" if is_initial_scheduling else "rescheduled"
                    scheduling_changes = {'Scheduling Update': {'new': f'Appointment {scheduling_context}'}}
                    
                    # Filter out automatic status change to avoid confusion
                    if changes:
                        filtered_changes = {k: v for k, v in changes.items() if k.lower() != 'status'}
                        scheduling_changes.update(filtered_changes)
                    
                    notification_manager.queue_appointment_updated_email(
                        customer_email, customer_name, email_appointment_data, scheduling_changes, 'scheduling'
                    )
                elif scenario == 'report_approval':
                    # Send report ready email only when admin approves a report
                    report_approval = update_data.get('reportApproval', {})
                    action = report_approval.get('action', '')
                    
                    if action == 'approve':
                        # Find the approved report details
                        report_s3_key = report_approval.get('reportS3Key', '')
                        approved_report = None
                        
                        # Find the specific report that was approved
                        for report in updated_appointment.get('reports', []):
                            report_key = report.get('s3Key') or report.get('fileKey')
                            if report_key == report_s3_key:
                                approved_report = report
                                break
                        
                        # Add report information to the email data
                        # Get the S3 key for URL generation
                        s3_key = approved_report.get('s3Key') or approved_report.get('fileKey', '') if approved_report else ''
                        
                        # Use existing fileUrl if available and valid, otherwise generate new one
                        report_url = ''
                        if approved_report and approved_report.get('fileUrl'):
                            existing_file_url = approved_report.get('fileUrl')
                            # Check if existing fileUrl is valid CloudFront URL (not old S3 format)
                            if existing_file_url.startswith('https://') and '.s3.amazonaws.com' not in existing_file_url:
                                report_url = existing_file_url
                                print(f"Using existing valid fileUrl for approved report: {report_url}")
                            else:
                                print(f"Existing fileUrl appears to be old S3 format, regenerating: {existing_file_url}")
                                if s3_key:
                                    report_url = s3.generate_public_url(file_key=s3_key)
                        elif s3_key:
                            # Generate proper CloudFront URL for the report
                            report_url = s3.generate_public_url(file_key=s3_key)
                        
                        email_appointment_data['approvedReport'] = {
                            'fileName': approved_report.get('fileName', 'Inspection Report') if approved_report else 'Inspection Report',
                            'fileUrl': report_url,  # Use the generated CloudFront URL
                            's3Key': s3_key,
                            'fileSize': approved_report.get('fileSize', 0) if approved_report else 0,
                            'approvedAt': approved_report.get('reviewedAt') if approved_report else int(datetime.now(ZoneInfo('Australia/Perth')).timestamp())
                        }
                        
                        notification_manager.queue_report_ready_email(
                            customer_email, customer_name, email_appointment_data, report_url
                        )
                    # Note: No email is sent for report rejection - internal process only
                elif has_status_change and not has_scheduling_changes:
                    # Send status email only if there are no scheduling changes (non-scheduling related status change)
                    notification_manager.queue_appointment_updated_email(customer_email, customer_name, email_appointment_data, changes, 'status')
                elif scenario == 'basic_info':
                    # Send general email for basic info updates
                    notification_manager.queue_appointment_updated_email(customer_email, customer_name, email_appointment_data, changes, 'general')
                # Note: If both scheduling and status change, only scheduling email is sent with full context
            else:
                print(f"Warning: No email found for customer notification for appointment update {appointment_id}")
        except Exception as e:
            print(f"Failed to queue email notification: {str(e)}")
        
        # Removed: Customer WebSocket notifications for appointments (not messaging-related)
        # As per requirements, websocket notifications are only for messaging scenarios
        
        try:
            # Staff WebSocket notifications - notify all staff about appointment updates
            staff_notification_data = {
                "type": "appointment",
                "subtype": "update",
                "success": True,
                "appointmentId": appointment_id,
                "scenario": scenario,
                "updateData": update_data,
                "appointmentData": updated_appointment
            }
            # Removed: WebSocket notification for appointments (not messaging-related)
            # As per requirements, websocket notifications are only for messaging scenarios

            # Firebase push notification to staff for significant updates
            if scenario in ['status', 'scheduling', 'reports', 'report_approval']:
                notification_manager.queue_appointment_firebase_notification(appointment_id, 'update')
            
        except Exception as e:
            print(f"Failed to send staff notifications: {str(e)}")
            # Don't fail the appointment update if notifications fail
