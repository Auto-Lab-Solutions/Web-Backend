import json
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import response_utils as resp
import request_utils as req
import permission_utils as perm
import business_logic_utils as biz
import db_utils as db

@perm.handle_permission_error
@biz.handle_business_logic_error
def lambda_handler(event, context):
    """
    Invoice Status Management API - Admin Only
    
    Supports both cancelling and reactivating invoices. Only admins can perform
    these operations as they affect financial records and analytics data. 
    Invoices are not physically deleted but their status is updated for audit purposes.
    
    Actions supported:
    - cancel: Mark invoice as cancelled
    - reactivate: Mark cancelled invoice as generated (active)
    """
    try:
        # Validate staff permissions - only ADMIN can manage invoice status
        staff_user_email = req.get_staff_user_email(event)
        staff_context = perm.PermissionValidator.validate_staff_access(
            staff_user_email,
            required_roles=['ADMIN']
        )
        
        # Parse the request
        path_parameters = event.get('pathParameters', {}) or {}
        
        # Parse request body for action and invoice_id parameters
        action = req.get_body_param(event, 'action', 'cancel').lower()  # Default to cancel for backward compatibility
        invoice_id = req.get_body_param(event, 'invoice_id')
        
        # Validate action
        if action not in ['cancel', 'reactivate']:
            raise biz.BusinessLogicError("Action must be either 'cancel' or 'reactivate'", 400)

        # Get invoice ID from request body (new approach) or fall back to path parameters (backward compatibility)
        if not invoice_id:
            invoice_id = path_parameters.get('invoice_id')
        
        if not invoice_id:
            raise biz.BusinessLogicError("Invoice ID is required in request body", 400)
        
        # Validate invoice ID format (basic validation)
        if not invoice_id.strip():
            raise biz.BusinessLogicError("Invoice ID cannot be empty", 400)
        
        # Check if invoice exists before attempting status change
        existing_invoice = db.get_invoice_by_id(invoice_id)
        if not existing_invoice:
            raise biz.BusinessLogicError(f"Invoice with ID '{invoice_id}' not found", 404)
        
        current_status = existing_invoice.get('status', 'generated')
        
        # Validate status transition
        if action == 'cancel':
            if current_status == 'cancelled':
                raise biz.BusinessLogicError(f"Invoice '{invoice_id}' is already cancelled", 400)
        elif action == 'reactivate':
            if current_status != 'cancelled':
                raise biz.BusinessLogicError(f"Invoice '{invoice_id}' is not cancelled and cannot be reactivated. Current status: {current_status}", 400)
        
        # Capture invoice details for logging and response
        invoice_details = {
            'invoiceId': existing_invoice.get('invoiceId'),
            'referenceNumber': existing_invoice.get('referenceNumber'),
            'referenceType': existing_invoice.get('referenceType'),
            'createdAt': existing_invoice.get('createdAt'),
            'status': current_status,
            'fileUrl': existing_invoice.get('fileUrl'),
            'format': existing_invoice.get('format')
        }
        
        # Perform the status change
        if action == 'cancel':
            operation_success = db.cancel_invoice(invoice_id)
            new_status = 'cancelled'
            action_verb = 'cancelled'
            
            # When cancelling invoice, update payment status of related appointment/order
            if operation_success:
                try:
                    reference_number = invoice_details.get('referenceNumber')
                    reference_type = invoice_details.get('referenceType')
                    
                    if reference_number and reference_type in ['appointment', 'order']:
                        # Check if this was the active invoice for this reference
                        remaining_active_invoices = db.has_active_invoices(reference_number, reference_type)
                        
                        if not remaining_active_invoices:
                            # No more active invoices, update payment status to cancelled
                            update_data = {
                                'paymentStatus': 'cancelled',
                                'updatedAt': int(datetime.now(ZoneInfo('Australia/Perth')).timestamp())
                            }
                            
                            if reference_type == 'appointment':
                                update_success = db.update_appointment(reference_number, update_data)
                                print(f"Updated appointment {reference_number} payment status to cancelled: {update_success}")
                            else:  # order
                                update_success = db.update_order(reference_number, update_data)
                                print(f"Updated order {reference_number} payment status to cancelled: {update_success}")
                            
                            if update_success:
                                print(f"AUDIT: {reference_type.title()} {reference_number} payment status updated to 'cancelled' due to invoice {invoice_id} cancellation")
                            else:
                                print(f"WARNING: Failed to update {reference_type} {reference_number} payment status after invoice cancellation")
                        else:
                            print(f"INFO: {reference_type.title()} {reference_number} still has active invoices, payment status not changed")
                    else:
                        print(f"INFO: Invoice {invoice_id} not linked to appointment/order, no payment status update needed")
                        
                except Exception as e:
                    print(f"ERROR: Failed to update {reference_type} payment status after invoice cancellation: {str(e)}")
                    # Don't fail the invoice cancellation if reference update fails
            
        else:  # reactivate
            operation_success = db.reactivate_invoice(invoice_id)
            new_status = 'generated'
            action_verb = 'reactivated'
            
            # When reactivating invoice, update payment status of related appointment/order back to paid
            if operation_success:
                try:
                    reference_number = invoice_details.get('referenceNumber')
                    reference_type = invoice_details.get('referenceType')
                    
                    if reference_number and reference_type in ['appointment', 'order']:
                        # Get the current record to check payment status
                        if reference_type == 'appointment':
                            current_record = db.get_appointment(reference_number)
                        else:  # order
                            current_record = db.get_order(reference_number)
                        
                        if current_record and current_record.get('paymentStatus') == 'cancelled':
                            # Update payment status back to paid since we have an active invoice
                            update_data = {
                                'paymentStatus': 'paid',
                                'updatedAt': int(datetime.now(ZoneInfo('Australia/Perth')).timestamp())
                            }
                            
                            if reference_type == 'appointment':
                                update_success = db.update_appointment(reference_number, update_data)
                                print(f"Updated appointment {reference_number} payment status to paid: {update_success}")
                            else:  # order
                                update_success = db.update_order(reference_number, update_data)
                                print(f"Updated order {reference_number} payment status to paid: {update_success}")
                            
                            if update_success:
                                print(f"AUDIT: {reference_type.title()} {reference_number} payment status updated to 'paid' due to invoice {invoice_id} reactivation")
                            else:
                                print(f"WARNING: Failed to update {reference_type} {reference_number} payment status after invoice reactivation")
                        else:
                            current_payment_status = current_record.get('paymentStatus', 'unknown') if current_record else 'record_not_found'
                            print(f"INFO: {reference_type.title()} {reference_number} payment status is '{current_payment_status}', no update needed")
                    else:
                        print(f"INFO: Invoice {invoice_id} not linked to appointment/order, no payment status update needed")
                        
                except Exception as e:
                    print(f"ERROR: Failed to update {reference_type} payment status after invoice reactivation: {str(e)}")
                    # Don't fail the invoice reactivation if reference update fails
        
        if not operation_success:
            raise biz.BusinessLogicError(f"Failed to {action} invoice '{invoice_id}'. Please try again.", 500)
        
        # Send email notification after successful operation
        try:
            # Get updated invoice data to extract customer information
            updated_invoice = db.get_invoice_by_id(invoice_id)
            
            if updated_invoice:
                # Extract customer information from invoice record
                # Try metadata first, then analyticsData as fallback
                customer_email = None
                customer_name = None
                amount = '0.00'
                payment_method = 'Payment'
                
                # Check metadata for customer info
                metadata = updated_invoice.get('metadata', {})
                if metadata:
                    customer_email = metadata.get('userEmail')
                    customer_name = metadata.get('userName', 'Valued Customer')
                    amount = str(metadata.get('totalAmount', '0.00'))
                    payment_method = metadata.get('paymentMethod', 'Payment')
                
                # Fallback to analyticsData if metadata doesn't have customer info
                if not customer_email:
                    analytics_data = updated_invoice.get('analyticsData', {})
                    operation_data = analytics_data.get('operation_data', {})
                    customer_email = operation_data.get('customerId')
                    payment_details = operation_data.get('paymentDetails', {})
                    amount = payment_details.get('amount', '0.00')
                    payment_method = payment_details.get('payment_method', 'Payment')
                    # Customer name not available in analyticsData, use default
                    customer_name = customer_name or 'Valued Customer'
                
                if customer_email:
                    # Import notification manager functions
                    import notification_manager
                    
                    # Prepare payment data for email using invoice data
                    payment_data = {
                        'referenceNumber': updated_invoice.get('referenceNumber', invoice_id),
                        'amount': amount,
                        'paymentMethod': payment_method,
                        'invoiceId': invoice_id,
                        'referenceType': updated_invoice.get('referenceType', 'manual')
                    }
                    
                    if action == 'cancel':
                        payment_data.update({
                            'cancellationDate': datetime.now(ZoneInfo('Australia/Perth')).strftime('%d/%m/%Y'),
                            'cancellationReason': 'Invoice was cancelled by staff',
                            'cancelledInvoiceId': invoice_id
                        })
                        notification_manager.queue_payment_cancellation_email(customer_email, customer_name, payment_data)
                        print(f"Payment cancellation email queued for {customer_email} (invoice type: {payment_data['referenceType']})")
                    
                    else:  # reactivate
                        payment_data.update({
                            'reactivationDate': datetime.now(ZoneInfo('Australia/Perth')).strftime('%d/%m/%Y'),
                            'reactivationReason': 'Invoice was reactivated by staff',
                            'reactivatedInvoiceId': invoice_id
                        })
                        notification_manager.queue_payment_reactivation_email(customer_email, customer_name, payment_data)
                        print(f"Payment reactivation email queued for {customer_email} (invoice type: {payment_data['referenceType']})")
                else:
                    print(f"Warning: No customer email found in invoice {invoice_id}, skipping email notification")
            else:
                print(f"Warning: Could not retrieve updated invoice {invoice_id}, skipping email notification")
                
        except Exception as e:
            print(f"Warning: Failed to send email notification for invoice {action}: {str(e)}")
            # Don't fail the invoice operation if email fails
        
        # Log the status change for audit purposes
        staff_user_id = staff_context.get('staff_user_id', 'unknown')
        staff_user_name = staff_context.get('staff_record', {}).get('userName', 'Unknown Admin')
        
        print(f"AUDIT: Invoice {invoice_id} {action_verb} by admin {staff_user_name} (ID: {staff_user_id}) - "
              f"Reference: {invoice_details.get('referenceNumber')} ({invoice_details.get('referenceType')}), "
              f"Previous Status: {current_status}, New Status: {new_status}")
        
        # Prepare success response
        response_data = {
            "message": f"Invoice {action_verb} successfully",
            "invoice": {
                "invoiceId": invoice_id,
                "referenceNumber": invoice_details.get('referenceNumber'),
                "referenceType": invoice_details.get('referenceType'),
                "createdAt": invoice_details.get('createdAt'),
                "fileUrl": invoice_details.get('fileUrl'),
                "format": invoice_details.get('format'),
                "previousStatus": current_status,
                "newStatus": new_status
            },
            "performedBy": {
                "staffId": staff_user_id,
                "staffName": staff_user_name,
                "actionPerformedAt": int(datetime.now(ZoneInfo('Australia/Perth')).timestamp()),
                "action": action
            }
        }
        
        # Add information about related appointment/order updates if applicable
        reference_number = invoice_details.get('referenceNumber')
        reference_type = invoice_details.get('referenceType')
        if reference_number and reference_type in ['appointment', 'order']:
            response_data["relatedRecordUpdate"] = {
                "referenceNumber": reference_number,
                "referenceType": reference_type,
                "paymentStatusUpdated": True if operation_success else False
            }
        
        return resp.success_response(response_data)
        
    except Exception as e:
        print(f"Error in api-cancel-invoice lambda_handler: {str(e)}")
        # Re-raise known business logic errors
        if isinstance(e, biz.BusinessLogicError):
            raise
        # Handle unexpected errors
        return resp.error_response(f"Internal server error: {str(e)}", 500)
