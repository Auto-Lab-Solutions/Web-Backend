"""
Payment Management Module
Handles payment confirmation and processing workflows
"""

import time
from decimal import Decimal

import permission_utils as perm
import data_retrieval_utils as db
from notification_manager import notification_manager
import wsgw_utils as wsgw
from exceptions import BusinessLogicError


class PaymentManager:
    """Manages payment-related business logic"""
    
    @staticmethod
    def confirm_cash_payment(staff_user_email, payment_id, amount):
        """
        Confirm cash payment workflow
        
        Args:
            staff_user_email (str): Staff user email
            payment_id (str): Payment ID
            amount (float): Payment amount
            
        Returns:
            dict: Success response
            
        Raises:
            BusinessLogicError: If confirmation fails
        """
        # Validate permissions
        staff_context = perm.PermissionValidator.validate_staff_access(
            staff_user_email,
            required_roles=['ADMIN']
        )
        
        # Get payment record
        payment_record = db.get_payment_record(payment_id)
        if not payment_record:
            raise BusinessLogicError("Payment not found", 404)
        
        if payment_record.get('status') == 'paid':
            raise BusinessLogicError("Payment already confirmed", 400)
        
        # Update payment status
        update_data = {
            'status': 'paid',
            'paymentMethod': 'cash',
            'confirmedBy': staff_context['staff_user_id'],
            'confirmedAt': int(time.time()),
            'amount': Decimal(str(amount))
        }
        
        success = db.update_payment(payment_id, update_data)
        if not success:
            raise BusinessLogicError("Failed to confirm payment", 500)
        
        # Update related appointment/order status
        PaymentManager._update_related_resource_status(payment_record)
        
        return {
            "message": "Cash payment confirmed successfully",
            "paymentId": payment_id
        }
    
    @staticmethod
    def confirm_manual_payment(reference_number, payment_type, payment_method, staff_user_id):
        """
        Confirm manual payment for appointment or order
        
        Args:
            reference_number (str): Appointment or order ID
            payment_type (str): 'appointment' or 'order'
            payment_method (str): 'cash' or 'bank_transfer'
            staff_user_id (str): Staff user ID
            
        Returns:
            dict: Success response
            
        Raises:
            BusinessLogicError: If confirmation fails
        """
        # Get the existing record
        if payment_type == 'appointment':
            existing_record = db.get_appointment(reference_number)
            if not existing_record:
                raise BusinessLogicError("Appointment not found", 404)
        else:  # order
            existing_record = db.get_order(reference_number)
            if not existing_record:
                raise BusinessLogicError("Order not found", 404)
        
        # Check if payment is already confirmed
        if existing_record.get('paymentStatus') == 'paid':
            raise BusinessLogicError("Payment already confirmed for this record", 400)
        
        # Check if record is cancelled
        if existing_record.get('status') == 'CANCELLED':
            raise BusinessLogicError(f"Cannot confirm payment for cancelled {payment_type}", 400)
        
        # Update payment status
        update_data = {
            'paymentStatus': 'paid',
            'paymentMethod': payment_method,
            'paymentConfirmedBy': staff_user_id,
            'paymentConfirmedAt': int(time.time())
        }
        
        # Update record
        if payment_type == 'appointment':
            success = db.update_appointment(reference_number, update_data)
        else:
            success = db.update_order(reference_number, update_data)
        
        if not success:
            raise BusinessLogicError(f"Failed to update {payment_type} payment status", 500)
        
        # Send notifications
        PaymentManager._send_payment_confirmation_notifications(
            existing_record, payment_type, payment_method, reference_number
        )
        
        return {
            "message": f"{payment_method.replace('_', ' ').title()} payment confirmed successfully",
            "referenceNumber": reference_number,
            "type": payment_type,
            "paymentMethod": payment_method,
            "paymentStatus": "paid"
        }
    
    @staticmethod
    def revert_payment_confirmation(reference_number, payment_type, staff_user_id):
        """
        Revert payment confirmation for appointment or order
        
        Args:
            reference_number (str): Appointment or order ID
            payment_type (str): 'appointment' or 'order'
            staff_user_id (str): Staff user ID
            
        Returns:
            dict: Success response
            
        Raises:
            BusinessLogicError: If reversion fails
        """
        # Get the existing record
        if payment_type == 'appointment':
            existing_record = db.get_appointment(reference_number)
            if not existing_record:
                raise BusinessLogicError("Appointment not found", 404)
        else:  # order
            existing_record = db.get_order(reference_number)
            if not existing_record:
                raise BusinessLogicError("Order not found", 404)
        
        # Check if payment can be reverted
        if existing_record.get('paymentStatus') != 'paid':
            raise BusinessLogicError("Payment is not confirmed, cannot revert", 400)
        
        # Update payment status
        update_data = {
            'paymentStatus': 'pending',
            'paymentMethod': None,
            'paymentConfirmedBy': None,
            'paymentConfirmedAt': None,
            'paymentRevertedBy': staff_user_id,
            'paymentRevertedAt': int(time.time())
        }
        
        # Update record
        if payment_type == 'appointment':
            success = db.update_appointment(reference_number, update_data)
        else:
            success = db.update_order(reference_number, update_data)
        
        if not success:
            raise BusinessLogicError(f"Failed to revert {payment_type} payment status", 500)
        
        return {
            "message": "Payment confirmation reverted successfully",
            "referenceNumber": reference_number,
            "type": payment_type,
            "paymentStatus": "pending"
        }
    
    @staticmethod
    def _send_payment_confirmation_notifications(record, record_type, payment_method, reference_id):
        """Send notifications for payment confirmation"""
        try:
            wsgw_client = wsgw.get_apigateway_client()
            
            # Get customer user ID
            customer_user_id = record.get('createdUserId')
            
            # Send WebSocket notification to customer if connected
            if customer_user_id:
                customer_connection = db.get_connection_by_user_id(customer_user_id)
                if customer_connection:
                    wsgw.send_notification(wsgw_client, customer_connection.get('connectionId'), {
                        "type": "payment",
                        "subtype": "confirmed",
                        "success": True,
                        "referenceId": reference_id,
                        "referenceType": record_type,
                        "paymentMethod": payment_method,
                        "message": f"Your {record_type} payment has been confirmed"
                    })
            
            # Send WebSocket notifications to all connected staff
            staff_connections = db.get_all_staff_connections()
            for connection in staff_connections:
                wsgw.send_notification(wsgw_client, connection.get('connectionId'), {
                    "type": "payment",
                    "subtype": "confirmed",
                    "success": True,
                    "referenceId": reference_id,
                    "referenceType": record_type,
                    "paymentMethod": payment_method,
                    "message": f"{record_type.title()} payment confirmed"
                })
            
            # Queue Firebase push notification
            notification_manager.queue_payment_firebase_notification(record.get(f'{record_type}Id'), 'cash_payment_confirmed')
            
        except Exception as e:
            print(f"Failed to send payment confirmation notifications: {str(e)}")
    
    @staticmethod
    def _update_related_resource_status(payment_record):
        """Update appointment or order status after payment confirmation"""
        try:
            appointment_id = payment_record.get('appointmentId')
            order_id = payment_record.get('orderId')
            
            if appointment_id:
                db.update_appointment(appointment_id, {'paymentStatus': 'paid'})
            elif order_id:
                db.update_order(order_id, {'paymentStatus': 'paid'})
                
        except Exception as e:
            print(f"Failed to update related resource status: {str(e)}")
