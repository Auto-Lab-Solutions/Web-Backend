"""
Payment Management Module
Handles payment confirmation and processing workflows
"""

import time
from datetime import datetime
from zoneinfo import ZoneInfo
from decimal import Decimal

import permission_utils as perm
import db_utils as db
from notification_manager import queue_payment_firebase_notification, invoice_manager
import wsgw_utils as wsgw
from exceptions import BusinessLogicError


class PaymentManager:
    """Manages payment-related business logic"""
    
    @staticmethod
    def confirm_manual_payment(reference_number, payment_type, payment_method, staff_user_id):
        """
        Confirm manual payment for appointment or order
        
        Args:
            reference_number (str): Appointment or order ID
            payment_type (str): 'appointment' or 'order'
            payment_method (str): 'cash', 'bank_transfer', or 'card'
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
            'paymentConfirmedAt': int(datetime.now(ZoneInfo('Australia/Perth')).timestamp())
        }
        
        # Update record
        if payment_type == 'appointment':
            success = db.update_appointment(reference_number, update_data)
        else:
            success = db.update_order(reference_number, update_data)
        
        if not success:
            raise BusinessLogicError(f"Failed to update {payment_type} payment status", 500)
        
        # Generate payment identifier that matches the invoice generation pattern
        # Format: {payment_method}_{reference_number}_{timestamp} to match notification_manager expectations
        payment_identifier = f"{payment_method}_{reference_number}_{int(datetime.now(ZoneInfo('Australia/Perth')).timestamp())}"
        
        # Queue invoice generation asynchronously (similar to Stripe payments)
        try:
            # Get updated record to pass to invoice generation
            if payment_type == 'appointment':
                updated_record = db.get_appointment(reference_number)
            else:
                updated_record = db.get_order(reference_number)
            
            if updated_record and updated_record.get('paymentStatus') == 'paid':
                invoice_manager.queue_invoice_generation(updated_record, payment_type, payment_identifier)
                print(f"Invoice generation queued for {payment_type} {reference_number}")
        except Exception as e:
            print(f"Error queuing invoice generation: {str(e)}")
            # Don't fail the payment confirmation if invoice generation fails
        
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
            'paymentRevertedAt': int(datetime.now(ZoneInfo('Australia/Perth')).timestamp())
        }
        
        # Update record
        if payment_type == 'appointment':
            success = db.update_appointment(reference_number, update_data)
        else:
            success = db.update_order(reference_number, update_data)
        
        if not success:
            raise BusinessLogicError(f"Failed to revert {payment_type} payment status", 500)
        
        # Cancel associated invoices when payment is reverted
        cancelled_invoices = []
        try:
            invoices = db.get_invoices_by_reference(reference_number, payment_type)
            cancelled_invoice_count = 0
            for invoice in invoices:
                # Only cancel active invoices (not already cancelled)
                if invoice.get('status') != 'cancelled':
                    success = db.cancel_invoice(invoice.get('invoiceId'))
                    if success:
                        cancelled_invoice_count += 1
                        cancelled_invoices.append(invoice.get('invoiceId'))
                        print(f"Cancelled invoice {invoice.get('invoiceId')} for reverted {payment_type} payment {reference_number}")
                    else:
                        print(f"Failed to cancel invoice {invoice.get('invoiceId')} for reverted {payment_type} payment {reference_number}")
            
            if cancelled_invoice_count > 0:
                print(f"Cancelled {cancelled_invoice_count} invoices for reverted {payment_type} payment {reference_number}")
        except Exception as e:
            print(f"Error cancelling invoices for reverted {payment_type} payment {reference_number}: {str(e)}")
            # Don't fail the payment reversion if invoice cancellation fails
        
        # Send payment cancellation email notification
        try:
            PaymentManager._send_payment_cancellation_notifications(
                existing_record, payment_type, reference_number, cancelled_invoices
            )
        except Exception as e:
            print(f"Error sending payment cancellation notifications: {str(e)}")
            # Don't fail the payment reversion if email notification fails
        
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
            
            # Get customer user ID for WebSocket notifications
            customer_user_id = record.get('createdUserId')
            
            # Get customer information from record (following the same pattern as notification_manager)
            customer_email = None
            customer_name = None
            
            if record_type == 'order':
                # For orders, get customer data directly from the record
                customer_email = record.get('customerEmail')
                customer_name = record.get('customerName', 'Valued Customer')
            else:  # appointment
                # For appointments, check if it's a buyer or seller
                is_buyer = record.get('isBuyer', True)
                if is_buyer:
                    customer_email = record.get('buyerEmail')
                    customer_name = record.get('buyerName', 'Valued Customer')
                else:
                    customer_email = record.get('sellerEmail')
                    customer_name = record.get('sellerName', 'Valued Customer')
            
            # Removed: WebSocket notifications for payments (not messaging-related)
            # As per requirements, websocket notifications are only for messaging scenarios
            
            # Queue Firebase push notification
            queue_payment_firebase_notification(record.get(f'{record_type}Id'), 'cash_payment_confirmed')
            
            # Note: Payment confirmation email will be sent by the invoice generation process
            # The invoice generation queued earlier will handle sending the email with the invoice attached
            # This ensures customers receive a single email with both payment confirmation and invoice
            
        except Exception as e:
            print(f"Failed to send payment confirmation notifications: {str(e)}")

    @staticmethod
    def _send_payment_cancellation_notifications(record, record_type, reference_id, cancelled_invoices=None):
        """Send notifications for payment cancellation"""
        try:
            from notification_manager import queue_payment_cancellation_email
            import wsgw_utils as wsgw
            
            wsgw_client = wsgw.get_apigateway_client()
            
            # Get customer user ID for WebSocket notifications
            customer_user_id = record.get('createdUserId')
            
            # Get customer information from record
            customer_email = None
            customer_name = None
            
            if record_type == 'order':
                # For orders, get customer data directly from the record
                customer_email = record.get('customerEmail')
                customer_name = record.get('customerName', 'Valued Customer')
            else:  # appointment
                # For appointments, check if it's a buyer or seller
                is_buyer = record.get('isBuyer', True)
                if is_buyer:
                    customer_email = record.get('buyerEmail')
                    customer_name = record.get('buyerName', 'Valued Customer')
                else:
                    customer_email = record.get('sellerEmail')
                    customer_name = record.get('sellerName', 'Valued Customer')
            
            # Removed: WebSocket notifications for payments (not messaging-related)
            # As per requirements, websocket notifications are only for messaging scenarios
            
            # Send email notification if customer email is available
            if customer_email and customer_name:
                # Prepare payment data for email
                payment_data = {
                    'referenceNumber': reference_id,
                    'amount': record.get('totalPrice', record.get('price', '0.00')),
                    'paymentMethod': record.get('paymentMethod', 'Payment'),
                    'cancellationDate': datetime.now(ZoneInfo('Australia/Perth')).strftime('%d/%m/%Y'),
                    'cancellationReason': 'Payment was cancelled by staff'
                }
                
                # Add cancelled invoice ID if available
                if cancelled_invoices and len(cancelled_invoices) > 0:
                    # Use the first cancelled invoice ID
                    payment_data['cancelledInvoiceId'] = cancelled_invoices[0]
                
                # Queue cancellation email
                queue_payment_cancellation_email(customer_email, customer_name, payment_data)
                print(f"Payment cancellation email queued for {customer_email}")
            else:
                print(f"Warning: No customer email found for {record_type} {reference_id}, skipping email notification")
            
        except Exception as e:
            print(f"Failed to send payment cancellation notifications: {str(e)}")
