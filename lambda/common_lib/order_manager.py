"""
Order Management Module
Handles order creation and update business logic and workflows
"""

import uuid
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from decimal import Decimal

import permission_utils as perm
import db_utils as db
import response_utils as resp
import email_utils
from notification_manager import notification_manager
from exceptions import BusinessLogicError


class OrderManager:
    """Manages order-related business logic"""
    
    ORDERS_LIMIT = 5  # Maximum number of orders per day
    
    @staticmethod
    def create_order(staff_user_email, user_id, order_data):
        """
        Complete order creation workflow
        
        Args:
            staff_user_email (str): Staff user email (optional)
            user_id (str): User ID
            order_data (dict): Order data
            
        Returns:
            dict: Success response with order ID
            
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
            'orders',
            OrderManager.ORDERS_LIMIT,
            staff_override=is_staff_user
        )
        
        # Generate unique order ID
        order_id = str(uuid.uuid4())
        
        # Process and validate items, calculate total price
        processed_items, total_price = OrderManager._process_order_items(order_data.get('items', []))
        
        # Build order data
        order_data_db = db.build_order_data(
            order_id=order_id,
            items=processed_items,
            customer_data=order_data.get('customerData', {}),
            car_data=order_data.get('carData', {}),
            notes=order_data.get('notes', ''),
            delivery_location=order_data.get('deliveryLocation', ''),
            created_user_id=effective_user_id,
            total_price=total_price
        )
        
        # Create order in database
        success = db.create_order(order_data_db)
        if not success:
            raise BusinessLogicError("Failed to create order", 500)
        
        # Send notifications
        OrderManager._send_creation_notifications(order_id, order_data, processed_items, total_price, effective_user_id)
        
        return {
            "message": "Order created successfully",
            "orderId": order_id
        }
    
    @staticmethod
    def _process_order_items(items):
        """Process and validate order items, calculate total price"""
        processed_items = []
        total_price = 0
        
        for item in items:
            category_id = item.get('categoryId')
            item_id = item.get('itemId')
            quantity = item.get('quantity', 1)
            
            # Get price by category and item
            item_pricing = db.get_item_pricing(category_id=category_id, item_id=item_id)
            if item_pricing is None:
                raise BusinessLogicError(f"Invalid category or item. Please check categoryId {category_id} and itemId {item_id}")
            
            unitPrice = float(item_pricing)
            item_total = unitPrice * quantity
            total_price += item_total
            
            processed_items.append({
                'categoryId': category_id,
                'itemId': item_id,
                'quantity': quantity,
                'unitPrice': unitPrice,
                'totalPrice': item_total
            })
        
        return processed_items, total_price
    
    @staticmethod
    def _send_creation_notifications(order_id, order_data, processed_items, total_price, user_id):
        """Send all notifications for order creation"""
        try:
            # Get customer details for email from order data only
            customer_email = order_data.get('customerData', {}).get('email')
            customer_name = order_data.get('customerData', {}).get('name', 'Valued Customer')
            
            # Send customer email notification if we have an email
            if customer_email:
                # Prepare items for email with names
                items_for_email = []
                for item in processed_items:
                    category_name, item_name = db.get_category_item_names(item.get('categoryId'), item.get('itemId'))
                    items_for_email.append({
                        'categoryName': category_name,
                        'itemName': item_name,
                        'quantity': item.get('quantity', 1),
                        'unitPrice': f"{item.get('unitPrice', 0):.2f}",
                        'totalPrice': f"{item.get('totalPrice', 0):.2f}"
                    })
                
                email_order_data = {
                    'orderId': order_id,
                    'items': items_for_email,
                    'totalPrice': f"{total_price:.2f}",
                    'customerData': order_data.get('customerData', {}),
                    'vehicleInfo': order_data.get('carData', {}),
                    'deliveryLocation': order_data.get('deliveryLocation', ''),
                    'notes': order_data.get('notes', ''),
                    'assignedMechanic': 'Our team'  # Default for new orders
                }
                
                notification_manager.queue_order_created_email(customer_email, customer_name, email_order_data)
            else:
                print(f"Warning: No email found in order data for order {order_id}")
            
            # Staff WebSocket notifications - notify all staff, not the customer
            staff_notification_data = {
                "type": "order",
                "subtype": "create",
                "success": True,
                "orderId": order_id,
                "orderData": order_data
            }
            # Removed: WebSocket notification for orders (not messaging-related)
            # As per requirements, websocket notifications are only for messaging scenarios
            
            # Firebase push notification to staff
            notification_manager.queue_order_firebase_notification(order_id, 'create')
            
        except Exception as e:
            print(f"Failed to send order creation notifications: {str(e)}")
            # Don't fail the order creation if notifications fail


class OrderUpdateManager:
    """Manages order update business logic"""
    
    CS_TRANSITIONS = {
        'PENDING': ['CANCELLED'],  # SCHEDULED status is set automatically via scheduling scenario
        'SCHEDULED': ['PENDING', 'CANCELLED'],
        'DELIVERED': ['SCHEDULED'],
        'CANCELLED': ['PENDING']  # Cannot go directly to SCHEDULED, must use scheduling scenario
    }
    
    MECHANIC_TRANSITIONS = {
        'SCHEDULED': ['DELIVERED'],
        'DELIVERED': ['SCHEDULED']
    }
    
    @staticmethod
    def update_order(staff_user_email, order_id, update_data):
        """Complete order update workflow"""
        staff_context = perm.PermissionValidator.validate_staff_access(staff_user_email)
        staff_roles = staff_context['staff_roles']
        staff_user_id = staff_context['staff_user_id']
        
        existing_order = db.get_order(order_id)
        if not existing_order:
            raise BusinessLogicError("Order not found", 404)
        
        current_status = existing_order.get('status', '')
        assigned_mechanic_id = existing_order.get('assignedMechanicId', '')
        payment_completed = existing_order.get('paymentStatus', 'pending') == 'paid'
        
        scenario = OrderUpdateManager._determine_scenario(update_data)
        OrderUpdateManager._validate_update_permissions(
            scenario, staff_roles, current_status, staff_user_id, assigned_mechanic_id
        )
        
        processed_data = OrderUpdateManager._process_update_data(
            scenario, update_data, existing_order, staff_roles, 
            staff_user_id, assigned_mechanic_id, payment_completed
        )
        
        processed_data['updatedAt'] = int(datetime.now(ZoneInfo('Australia/Perth')).timestamp())
        
        success = db.update_order(order_id, processed_data)
        if not success:
            raise BusinessLogicError("Failed to update order", 500)
        
        # Update invoice effective date if this is a scheduling update and payment is completed
        if scenario == 'scheduling' and payment_completed and 'scheduledDate' in processed_data:
            scheduled_date = processed_data.get('scheduledDate')
            if scheduled_date:  # Only update if we have a valid scheduled date
                try:
                    import invoice_data_utils
                    invoice_data_utils.update_invoice_effective_date(order_id, 'order', scheduled_date)
                except Exception as e:
                    print(f"Warning: Failed to update invoice effective date for order {order_id}: {str(e)}")
                    # Don't fail the order update if invoice update fails
        
        # Cancel invoices if order is cancelled
        if 'status' in processed_data and processed_data['status'] == 'CANCELLED':
            try:
                OrderUpdateManager._cancel_order_invoices(order_id)
            except Exception as e:
                print(f"Warning: Failed to cancel invoices for cancelled order {order_id}: {str(e)}")
                # Don't fail the order update if invoice cancellation fails
        
        updated_order = db.get_order(order_id)
        OrderUpdateManager._send_update_notifications(
            order_id, scenario, processed_data, updated_order, staff_user_id
        )
        
        return {
            "message": "Order updated successfully",
            "order": resp.convert_decimal(updated_order)
        }
    
    @staticmethod
    def _determine_scenario(update_data):
        if 'status' in update_data:
            return 'status'
        elif 'postNotes' in update_data:
            return 'notes'
        elif 'scheduledDate' in update_data or 'assignedMechanicId' in update_data:
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
        elif scenario == 'notes':
            if not any(role in staff_roles for role in ['MECHANIC', 'CUSTOMER_SUPPORT', 'CLERK']):
                raise BusinessLogicError('Unauthorized: MECHANIC, CUSTOMER_SUPPORT, or CLERK role required', 403)
            if 'MECHANIC' in staff_roles and assigned_mechanic_id != staff_user_id:
                raise BusinessLogicError('Unauthorized: You must be assigned to this order', 403)
    
    @staticmethod
    def _process_update_data(scenario, update_data, existing_order, staff_roles, 
                           staff_user_id, assigned_mechanic_id, payment_completed):
        processed_data = {}
        
        # Handle multiple scenarios in a single update request
        # Process all applicable fields regardless of primary scenario
        
        # Process basic info fields if present
        if any(field in update_data for field in ['items', 'notes', 'deliveryLocation', 'customerData', 'carData']):
            basic_info_data = OrderUpdateManager._process_basic_info(
                update_data, existing_order, payment_completed
            )
            processed_data.update(basic_info_data)
        
        # Process scheduling fields if present
        if any(field in update_data for field in ['scheduledDate', 'assignedMechanicId']):
            scheduling_data = OrderUpdateManager._process_scheduling(update_data)
            processed_data.update(scheduling_data)
        
        # Process status field if present
        if 'status' in update_data:
            new_status = update_data.get('status')
            if not OrderUpdateManager._validate_status_transition(
                existing_order.get('status'), new_status, staff_roles, staff_user_id, assigned_mechanic_id
            ):
                raise BusinessLogicError(f"Invalid status transition", 400)
            processed_data['status'] = new_status
        
        # Process notes fields if present
        if 'postNotes' in update_data:
            notes_data = OrderUpdateManager._process_notes(update_data)
            processed_data.update(notes_data)
        
        return processed_data
    
    @staticmethod
    def _process_basic_info(update_data, existing_order, payment_completed):
        processed = {}
        
        if 'items' in update_data:
            if payment_completed:
                raise BusinessLogicError("Cannot update items after payment is completed", 400)
            processed_items, total_price = OrderManager._process_order_items(update_data['items'])
            processed['items'] = processed_items
            processed['totalPrice'] = Decimal(str(total_price))

        # Handle simple field updates
        for field in ['notes', 'deliveryLocation']:
            if field in update_data:
                processed[field] = update_data[field]
        
        # Handle customerData nested structure
        if 'customerData' in update_data:
            customer_data = update_data['customerData']
            for key, field in [('name', 'customerName'), ('email', 'customerEmail'), ('phoneNumber', 'customerPhone')]:
                if key in customer_data:
                    processed[field] = customer_data[key]
        
        # Handle carData nested structure
        if 'carData' in update_data:
            car_data = update_data['carData']
            for key, field in [('make', 'carMake'), ('model', 'carModel'), ('year', 'carYear')]:
                if key in car_data:
                    processed[field] = str(car_data[key]) if key == 'year' else car_data[key]
        
        return processed
    
    @staticmethod
    def _process_scheduling(update_data):
        processed = {}
        
        if 'scheduledDate' in update_data:
            processed['scheduledDate'] = update_data['scheduledDate']
        
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
    def _process_notes(update_data):
        processed = {}
        
        if 'postNotes' in update_data:
            processed['postNotes'] = update_data['postNotes']
        
        return processed
    
    @staticmethod
    def _validate_status_transition(current_status, new_status, staff_roles, staff_user_id, assigned_mechanic_id):
        if 'CUSTOMER_SUPPORT' in staff_roles and new_status in OrderUpdateManager.CS_TRANSITIONS.get(current_status, []):
            return True
        
        if ('MECHANIC' in staff_roles and 
            assigned_mechanic_id == staff_user_id and 
            new_status in OrderUpdateManager.MECHANIC_TRANSITIONS.get(current_status, [])):
            return True
        
        return False
    
    @staticmethod
    def _send_update_notifications(order_id, scenario, update_data, updated_order, staff_user_id):
        try:
            # Customer email notifications
            customer_email = updated_order.get('customerEmail')
            customer_name = updated_order.get('customerName', 'Valued Customer')
            
            if customer_email:
                # Prepare order data with resolved mechanic name
                email_update_data = dict(updated_order)
                
                # Resolve mechanic name if assigned
                if updated_order.get('assignedMechanicId'):
                    try:
                        mechanic_record = db.get_staff_record_by_user_id(updated_order['assignedMechanicId'])
                        if mechanic_record:
                            email_update_data['assignedMechanic'] = mechanic_record.get('userName', 'Our team')
                        else:
                            email_update_data['assignedMechanic'] = 'Our team'
                    except Exception as e:
                        print(f"Error getting mechanic name: {str(e)}")
                        email_update_data['assignedMechanic'] = 'Our team'
                else:
                    email_update_data['assignedMechanic'] = 'Our team'
                
                # Format total price for email display
                if updated_order.get('totalPrice'):
                    try:
                        total_price_value = float(updated_order.get('totalPrice', 0))
                        email_update_data['totalPrice'] = f"{total_price_value:.2f}"
                    except (ValueError, TypeError):
                        email_update_data['totalPrice'] = "0.00"
                else:
                    email_update_data['totalPrice'] = "0.00"
                
                # Resolve item names and format prices for email display
                if updated_order.get('items'):
                    formatted_items = []
                    for item in updated_order['items']:
                        # Always resolve category and item names for email display
                        category_name, item_name = db.get_category_item_names(
                            item.get('categoryId', 0),
                            item.get('itemId', 0)
                        )
                        formatted_items.append({
                            'categoryName': category_name,
                            'itemName': item_name,
                            'quantity': item.get('quantity', 1),
                            'unitPrice': f"{float(item.get('unitPrice', 0)):.2f}",  # Format price for email display
                            'totalPrice': f"{float(item.get('totalPrice', 0)):.2f}"  # Format total price for email display
                        })
                        # search in update_data['items'] for the record with categoryId and itemId. Then add categoryName and itemName to it. Then replace corresponding record in update_data
                        for index, update_item in enumerate(update_data.get('items', [])):
                            if (update_item.get('categoryId') == item.get('categoryId') and update_item.get('itemId') == item.get('itemId')):
                                update_item['categoryName'] = category_name
                                update_item['itemName'] = item_name
                                del update_item['categoryId'], update_item['itemId']
                                update_data['items'][index] = update_item
                                break
                    email_update_data['items'] = formatted_items
                
                # Replace assignedMechanicId with assignedMechanic name in update_data for email changes
                if 'assignedMechanicId' in update_data:
                    update_data['assignedMechanic'] = email_update_data['assignedMechanic']
                    del update_data['assignedMechanicId']
                
                email_update_data, changes = email_utils.prepare_email_data_and_changes(email_update_data, update_data, 'order')
                
                # Determine if this is a combined scheduling + status update
                has_scheduling_fields = any(field in update_data for field in ['scheduledDate', 'assignedMechanicId'])
                has_status_change = 'status' in update_data
                
                # Intelligent email sending logic to prevent duplicates
                if has_scheduling_fields:
                    # Scheduling update (status is automatically set to SCHEDULED)
                    current_status = updated_order.get('status', 'PENDING')
                    
                    # Determine scheduling context based on whether this is initial scheduling
                    if current_status == 'SCHEDULED':
                        scheduling_message = "Your order has been scheduled"
                    else:
                        scheduling_message = "Your order has been rescheduled"
                    
                    # Create comprehensive changes for scheduling email
                    scheduling_changes = {'Scheduling Update': {'new': scheduling_message}}
                    if changes:
                        # Filter out automatic status change to avoid confusion
                        filtered_changes = {k: v for k, v in changes.items() if k.lower() != 'status'}
                        scheduling_changes.update(filtered_changes)
                    
                    notification_manager.queue_order_updated_email(customer_email, customer_name, email_update_data, scheduling_changes, 'scheduling')
                
                elif has_status_change and not has_scheduling_fields:
                    # Pure status update (non-scheduling related)
                    notification_manager.queue_order_updated_email(customer_email, customer_name, email_update_data, changes, 'status')
                
                elif scenario in ['basic_info', 'notes']:
                    # Other significant updates
                    update_type = 'general' if scenario == 'basic_info' else 'general'
                    notification_manager.queue_order_updated_email(customer_email, customer_name, email_update_data, changes, update_type)
                
                # Note: No email sent for pure notes scenarios unless it's significant
            else:
                print(f"Warning: No email found in order data for order update {order_id}")
        except Exception as e:
            print(f"Failed to queue email notification: {str(e)}")
        
        # Removed: Customer WebSocket notifications for orders (not messaging-related)
        # As per requirements, websocket notifications are only for messaging scenarios
        
        try:
            # Staff WebSocket notifications - notify all staff about order updates
            staff_notification_data = {
                "type": "order",
                "subtype": "update",
                "success": True,
                "orderId": order_id,
                "scenario": scenario,
                "updateData": update_data,
                "updatedBy": staff_user_id,
                "orderData": updated_order
            }
            # Removed: WebSocket notification for orders (not messaging-related)
            # As per requirements, websocket notifications are only for messaging scenarios
            
            # Firebase push notification to staff for significant updates
            if scenario in ['status', 'scheduling']:
                notification_manager.queue_order_firebase_notification(order_id, 'update')
            
        except Exception as e:
            print(f"Failed to send order update notifications: {str(e)}")
            # Don't fail the order update if notifications fail
    
    @staticmethod
    def _cancel_order_invoices(order_id):
        """Cancel invoices associated with a cancelled order by updating their status"""
        try:
            # Get all invoices for this order
            invoices = db.get_invoices_by_reference(order_id, 'order')
            
            if invoices:
                print(f"Found {len(invoices)} invoice(s) for cancelled order {order_id}")
                
                for invoice in invoices:
                    invoice_id = invoice.get('invoiceId')
                    if invoice_id:
                        try:
                            # Check if invoice is already cancelled
                            if invoice.get('status') == 'cancelled':
                                print(f"Invoice {invoice_id} is already cancelled for order {order_id}")
                                continue
                                
                            # Cancel the invoice (updates status to 'cancelled')
                            success = db.cancel_invoice(invoice_id)
                            if success:
                                print(f"Cancelled invoice {invoice_id} for cancelled order {order_id}")
                            else:
                                print(f"Failed to cancel invoice {invoice_id} for cancelled order {order_id}")
                        except Exception as e:
                            print(f"Error cancelling invoice {invoice_id}: {str(e)}")
            else:
                print(f"No invoices found for cancelled order {order_id}")
                
        except Exception as e:
            print(f"Error retrieving invoices for cancelled order {order_id}: {str(e)}")
            raise
