"""
Order Management Module
Handles order creation and update business logic and workflows
"""

import uuid
import time
from decimal import Decimal

import permission_utils as perm
import db_utils as db
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
            
            price = float(item_pricing)
            item_total = price * quantity
            total_price += item_total
            
            processed_items.append({
                'categoryId': category_id,
                'itemId': item_id,
                'quantity': quantity,
                'price': price,
                'totalPrice': item_total
            })
        
        return processed_items, total_price
    
    @staticmethod
    def _send_creation_notifications(order_id, order_data, processed_items, total_price, user_id):
        """Send all notifications for order creation"""
        try:
            # Get customer details for email
            user_record = db.get_user_record(user_id)
            if user_record and user_record.get('email'):
                customer_email = user_record.get('email')
                customer_name = user_record.get('name', 'Valued Customer')
                
                # Prepare items for email with names
                items_for_email = []
                for item in processed_items:
                    try:
                        category_name, item_name = db.get_category_item_names(item.get('categoryId'), item.get('itemId'))
                        items_for_email.append({
                            'categoryName': category_name,
                            'itemName': item_name,
                            'quantity': item.get('quantity', 1),
                            'price': f"{item.get('price', 0):.2f}"
                        })
                    except Exception as e:
                        print(f"Failed to get category/item names: {str(e)}")
                        # Fallback to IDs if name lookup fails
                        items_for_email.append({
                            'categoryName': f"Category {item.get('categoryId')}",
                            'itemName': f"Item {item.get('itemId')}",
                            'quantity': item.get('quantity', 1),
                            'price': f"{item.get('price', 0):.2f}"
                        })
                
                email_order_data = {
                    'orderId': order_id,
                    'items': items_for_email,
                    'totalPrice': f"{total_price:.2f}",
                    'customerData': order_data.get('customerData', {}),
                    'vehicleInfo': order_data.get('carData', {}),
                    'deliveryLocation': order_data.get('deliveryLocation', ''),
                    'notes': order_data.get('notes', '')
                }
                
                notification_manager.queue_order_created_email(customer_email, customer_name, email_order_data)
            
            # Staff WebSocket notifications
            staff_notification_data = {
                "type": "order",
                "subtype": "create",
                "success": True,
                "orderId": order_id,
                "orderData": order_data
            }
            notification_manager.queue_staff_websocket_notification(staff_notification_data, assigned_to=user_id)
            
            # Firebase push notification to staff
            notification_manager.queue_order_firebase_notification(order_id, 'create')
            
        except Exception as e:
            print(f"Failed to send order creation notifications: {str(e)}")
            # Don't fail the order creation if notifications fail


class OrderUpdateManager:
    """Manages order update business logic"""
    
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
    def update_order(staff_user_email, order_id, update_data):
        """Complete order update workflow"""
        staff_context = perm.PermissionValidator.validate_staff_access(staff_user_email)
        staff_roles = staff_context['roles']
        staff_user_id = staff_context['user_id']
        
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
        
        processed_data['updatedAt'] = int(time.time())
        
        success = db.update_order(order_id, processed_data)
        if not success:
            raise BusinessLogicError("Failed to update order", 500)
        
        updated_order = db.get_order(order_id)
        OrderUpdateManager._send_update_notifications(
            order_id, scenario, processed_data, updated_order, staff_user_id
        )
        
        return {
            "message": "Order updated successfully",
            "order": updated_order
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
        
        if scenario == 'basic_info':
            processed_data = OrderUpdateManager._process_basic_info(
                update_data, existing_order, payment_completed
            )
        elif scenario == 'scheduling':
            processed_data = OrderUpdateManager._process_scheduling(update_data)
        elif scenario == 'status':
            new_status = update_data.get('status')
            if not OrderUpdateManager._validate_status_transition(
                existing_order.get('status'), new_status, staff_roles, staff_user_id, assigned_mechanic_id
            ):
                raise BusinessLogicError(f"Invalid status transition", 400)
            processed_data['status'] = new_status
        elif scenario == 'notes':
            processed_data = OrderUpdateManager._process_notes(update_data)
        
        return processed_data
    
    @staticmethod
    def _process_basic_info(update_data, existing_order, payment_completed):
        processed = {}
        
        if 'items' in update_data:
            if payment_completed:
                raise BusinessLogicError("Cannot update items after payment is completed", 400)
            items = update_data['items']
            if isinstance(items, list):
                total_price = 0
                for item in items:
                    category_id = item.get('categoryId')
                    item_id = item.get('itemId')
                    quantity = item.get('quantity', 1)
                    
                    item_pricing = db.get_item_pricing(category_id=category_id, item_id=item_id)
                    if item_pricing is None:
                        raise BusinessLogicError(f"Invalid category or item. Please check categoryId {category_id} and itemId {item_id}")
                    
                    price = float(item_pricing)
                    total_price += price * quantity
                
                processed['items'] = items
                processed['totalPrice'] = Decimal(str(total_price))
        
        for field in ['notes', 'deliveryLocation']:
            if field in update_data:
                processed[field] = update_data[field]
        
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
            customer_user_id = updated_order.get('createdUserId')
            if customer_user_id:
                notification_manager.queue_order_websocket_notification(order_id, scenario, update_data, customer_user_id)
        except Exception as e:
            print(f"Failed to queue WebSocket notification: {str(e)}")
