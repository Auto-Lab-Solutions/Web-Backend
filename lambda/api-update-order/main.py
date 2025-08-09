from datetime import datetime
import time
import db_utils as db
import response_utils as resp
import request_utils as req
import wsgw_utils as wsgw
import email_utils as email
import notification_utils as notify

wsgw_client = wsgw.get_apigateway_client()

def lambda_handler(event, context):
    try:
        # Get staff user information
        staff_user_email = req.get_staff_user_email(event)
        if not staff_user_email:
            return resp.error_response("Unauthorized: Staff authentication required", 401)
            
        staff_user_record = db.get_staff_record(staff_user_email)
        if not staff_user_record:
            return resp.error_response(f"No staff record found for email: {staff_user_email}", 404)
        
        # Convert decimals to handle DynamoDB Decimal objects
        staff_user_record = resp.convert_decimal(staff_user_record)
        
        staff_roles = staff_user_record.get('roles', [])
        staff_user_id = staff_user_record.get('userId')
        
        # Get order ID from path parameters
        order_id = req.get_path_param(event, 'orderId')
        if not order_id:
            return resp.error_response("orderId is required in path")
        
        # Get existing order
        existing_order = db.get_order(order_id)
        if not existing_order:
            return resp.error_response("Order not found", 404)
        
        # Convert decimals to handle DynamoDB Decimal objects
        existing_order = resp.convert_decimal(existing_order)
        
        current_status = existing_order.get('status', '')
        assigned_mechanic_id = existing_order.get('assignedMechanicId', '')
        payment_completed = existing_order.get('paymentStatus', 'pending') == 'paid'
        
        # Get request body
        body = req.get_body(event)
        if not body:
            return resp.error_response("Request body is required")
        
        # Determine update scenario and validate permissions
        update_data = {}
        scenario = determine_update_scenario(body)
        
        # Validate permissions based on scenario
        permission_result = validate_permissions(scenario, staff_roles, current_status, staff_user_id, assigned_mechanic_id, payment_completed)
        if not permission_result['allowed']:
            return resp.error_response(permission_result['message'], 403)
        
        # Process updates based on scenario
        if scenario == 'basic_info':
            # Scenario 1: Update basic order info
            update_data = process_basic_info_updates(body, existing_order)
            
        elif scenario == 'scheduling':
            # Scenario 2: Update scheduling information
            update_data = process_scheduling_updates(body, existing_order)
            
        elif scenario == 'status':
            # Scenario 3: Update status
            new_status = body.get('status')
            if not validate_status_transition(current_status, new_status, staff_roles, staff_user_id, assigned_mechanic_id):
                return resp.error_response(f"Invalid status transition from {current_status} to {new_status}")
            if current_status == 'PENDING' and new_status == 'SCHEDULED' and not (existing_order.get('scheduledDate') and existing_order.get('assignedMechanicId')):
                return resp.error_response("Cannot schedule appointment without a scheduled date and assigned mechanic")
            update_data['status'] = new_status
            
        elif scenario == 'notes':
            # Scenario 4: Update post notes
            update_data = process_notes_updates(body, existing_order)
        
        # Add updated timestamp
        update_data['updatedAt'] = int(time.time())
        
        if not update_data:
            return resp.error_response("No valid update data provided")
        
        # Update order in database
        success = db.update_order(order_id, update_data)
        if not success:
            return resp.error_response("Failed to update order", 500)
        
        # Get updated order for response
        updated_order = db.get_order(order_id)
        updated_order = resp.convert_decimal(updated_order)
        
        # Send notifications to relevant users
        send_update_notifications(order_id, scenario, update_data, updated_order, staff_user_id)
        
        return resp.success_response({
            "message": "Order updated successfully",
            "order": updated_order
        })
        
    except Exception as e:
        print(f"Error in update order lambda: {str(e)}")
        return resp.error_response("Internal server error", 500)


def determine_update_scenario(body):
    """Determine which update scenario this request falls under"""
    if 'status' in body:
        return 'status'
    elif 'postNotes' in body:
        return 'notes'
    elif 'scheduledDate' in body or 'assignedMechanicId' in body:
        return 'scheduling'
    else:
        return 'basic_info'


def validate_permissions(scenario, staff_roles, current_status, staff_user_id, assigned_mechanic_id, payment_completed):
    """Validate if the user has permission for this update scenario"""
    
    if scenario == 'basic_info':
        # Scenario 1: Basic info updates
        if 'CUSTOMER_SUPPORT' not in staff_roles:
            return {'allowed': False, 'message': 'Unauthorized: CUSTOMER_SUPPORT role required'}
        if current_status not in ['PENDING', 'SCHEDULED']:
            return {'allowed': False, 'message': f'Cannot update basic info when status is {current_status}'}
        if payment_completed:
            return {'allowed': False, 'message': 'Cannot update basic info when payment is completed'}
            
    elif scenario == 'scheduling':
        # Scenario 2: Scheduling updates
        if 'CUSTOMER_SUPPORT' not in staff_roles:
            return {'allowed': False, 'message': 'Unauthorized: CUSTOMER_SUPPORT role required'}
        if current_status not in ['PENDING', 'SCHEDULED']:
            return {'allowed': False, 'message': f'Cannot update scheduling when status is {current_status}'}
            
    elif scenario == 'status':
        # Scenario 3: Status updates - validation done in validate_status_transition
        pass
        
    elif scenario == 'notes':
        # Scenario 4: Post notes
        if 'MECHANIC' not in staff_roles and 'CUSTOMER_SUPPORT' not in staff_roles:
            return {'allowed': False, 'message': 'Unauthorized: MECHANIC role required'}
        if current_status not in ['DELIVERED']:
            return {'allowed': False, 'message': f'Cannot update notes when status is {current_status}'}
        if assigned_mechanic_id != staff_user_id and 'CUSTOMER_SUPPORT' not in staff_roles:
            return {'allowed': False, 'message': 'Unauthorized: You must be assigned to this order'}
    
    return {'allowed': True, 'message': ''}


def validate_status_transition(current_status, new_status, staff_roles, staff_user_id, assigned_mechanic_id):
    """Validate if the status transition is allowed"""
    
    # Customer Support allowed transitions
    cs_transitions = {
        'PENDING': ['SCHEDULED', 'CANCELLED'],
        'SCHEDULED': ['PENDING', 'CANCELLED'],
        'CANCELLED': ['PENDING', 'SCHEDULED'],
        'DELIVERED': ['SCHEDULED']
    }
    
    # Mechanic allowed transitions (must be assigned)
    mechanic_transitions = {
        'SCHEDULED': ['DELIVERED'],
        'DELIVERED': ['SCHEDULED']
    }
    
    if 'CUSTOMER_SUPPORT' in staff_roles and new_status in cs_transitions.get(current_status, []):
        return True
    
    if ('MECHANIC' in staff_roles and 
        assigned_mechanic_id == staff_user_id and 
        new_status in mechanic_transitions.get(current_status, [])):
        return True
    
    return False


def process_basic_info_updates(body, existing_order):
    """Process basic order information updates"""
    update_data = {}
    
    # Items updates
    if 'items' in body:
        items = body['items']
        if not isinstance(items, list) or len(items) == 0:
            raise ValueError("items must be a non-empty array")
        
        if len(items) > 10:
            raise ValueError("Maximum 10 items allowed per order")

        # Validate and process each item
        processed_items = []
        total_price = 0
        
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"Item {i+1} must be an object")
            
            # Required item fields
            required_fields = ['categoryId', 'itemId', 'quantity']
            for field in required_fields:
                if field not in item:
                    raise ValueError(f"Item {i+1}: {field} is required")
            
            try:
                category_id = int(item['categoryId'])
                item_id = int(item['itemId'])
                quantity = int(item['quantity'])
                
                if category_id <= 0 or item_id <= 0 or quantity <= 0:
                    raise ValueError(f"Item {i+1}: categoryId, itemId, and quantity must be positive integers")
                
                if quantity > 30:
                    raise ValueError(f"Item {i+1}: Maximum quantity per item is 30")

                # Get item pricing
                item_pricing = db.get_item_pricing(category_id, item_id)
                if not item_pricing:
                    raise ValueError(f"Item {i+1}: Invalid category or item. Please check categoryId {category_id} and itemId {item_id}")
                
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
                
            except (ValueError, TypeError) as e:
                if "Invalid category or item" in str(e):
                    raise e
                raise ValueError(f"Item {i+1}: categoryId, itemId, and quantity must be valid integers")
        
        # Convert to DynamoDB format
        items_list = []
        for item in processed_items:
            item_data = {
                'M': {
                    'categoryId': {'N': str(item['categoryId'])},
                    'itemId': {'N': str(item['itemId'])},
                    'quantity': {'N': str(item['quantity'])},
                    'price': {'N': str(item['price'])},
                    'totalPrice': {'N': str(item['totalPrice'])}
                }
            }
            items_list.append(item_data)
        
        update_data['items'] = {'L': items_list}
        update_data['totalPrice'] = total_price
    
    # Customer data updates
    if 'customerData' in body:
        customer_data = body['customerData']
        if 'name' in customer_data:
            update_data['customerName'] = customer_data['name']
        if 'email' in customer_data:
            update_data['customerEmail'] = customer_data['email']
        if 'phoneNumber' in customer_data:
            update_data['customerPhone'] = customer_data['phoneNumber']
    
    # Car data updates
    if 'carData' in body:
        car_data = body['carData']
        if 'make' in car_data:
            update_data['carMake'] = car_data['make']
        if 'model' in car_data:
            update_data['carModel'] = car_data['model']
        if 'year' in car_data:
            update_data['carYear'] = str(car_data['year'])
    
    # Notes update
    if 'notes' in body:
        update_data['notes'] = body['notes']
    
    # Delivery location update
    if 'deliveryLocation' in body:
        update_data['deliveryLocation'] = body['deliveryLocation']
    
    return update_data


def process_scheduling_updates(body, existing_order):
    """Process scheduling-related updates"""
    update_data = {}
    
    if 'scheduledDate' in body:
        scheduled_date = body['scheduledDate']
        # Validate date format
        try:
            datetime.strptime(scheduled_date, '%Y-%m-%d')
        except ValueError:
            raise ValueError("Scheduled date must be in YYYY-MM-DD format")
        update_data['scheduledDate'] = scheduled_date
    
    if 'assignedMechanicId' in body:
        mechanic_id = body['assignedMechanicId']
        # Validate mechanic exists if not empty
        if mechanic_id:
            mechanic_record = db.get_staff_record_by_user_id(mechanic_id)
            if mechanic_record:
                mechanic_record = resp.convert_decimal(mechanic_record)
            if not mechanic_record or 'MECHANIC' not in mechanic_record.get('roles', []):
                raise ValueError("Invalid mechanic ID")
        update_data['assignedMechanicId'] = mechanic_id
    
    return update_data


def process_notes_updates(body, existing_order):
    """Process post notes updates"""
    update_data = {}
    
    if 'postNotes' in body:
        update_data['postNotes'] = body['postNotes']
    
    return update_data


def send_update_notifications(order_id, scenario, update_data, updated_order, staff_user_id):
    """Send notifications to created user about the order update"""
    # Queue WebSocket notification for customer
    try:
        customer_user_id = updated_order.get('createdUserId')
        if customer_user_id:
            notify.queue_order_websocket_notification(order_id, scenario, update_data, customer_user_id)
    except Exception as e:
        print(f"Failed to queue customer WebSocket notification: {str(e)}")
    
    # Queue email notification to customer
    try:
        customer_user_id = updated_order.get('createdUserId')
        if customer_user_id:
            user_record = db.get_user_record(customer_user_id)
            if user_record and user_record.get('email'):
                customer_email = user_record.get('email')
                customer_name = user_record.get('name', 'Valued Customer')
                
                # Format order data for email
                email_order_data = format_order_data_for_email(updated_order)
                
                # Handle special case for report ready notification
                if 'reportUrl' in update_data and update_data.get('reportUrl'):
                    notify.queue_report_ready_email(
                        customer_email, 
                        customer_name, 
                        email_order_data, 
                        update_data.get('reportUrl')
                    )
                    return  # Exit early for report updates
                
                # Send appropriate email based on scenario
                if scenario == 'MECHANIC_ASSIGNMENT' and 'scheduledDate' in update_data:
                    # Order scheduled with mechanic
                    notify.queue_order_scheduled_email(customer_email, customer_name, email_order_data)
                elif any(key in update_data for key in ['assignedMechanic', 'scheduledDate', 'timeSlot', 'status']):
                    # General order update
                    notify.queue_order_updated_email(customer_email, customer_name, email_order_data)
                    
    except Exception as e:
        print(f"Failed to queue email notification: {str(e)}")
        # Don't fail the update if notification queueing fails
    
    # Queue Firebase push notification to staff
    try:
        # Determine which staff should be notified
        assigned_mechanic_id = updated_order.get('assignedMechanicId')
        staff_to_notify = []
        
        # Always notify customer support staff for most updates
        if scenario in ['basic_info', 'scheduling', 'status']:
            # For general updates, notify all customer support
            notify.queue_order_firebase_notification(order_id, scenario)
        
        # For mechanic-specific updates, notify the assigned mechanic
        if scenario == 'notes' and assigned_mechanic_id:
            # Notify the assigned mechanic about note updates
            notify.queue_order_firebase_notification(order_id, scenario, [assigned_mechanic_id])
        
        # For status changes, notify relevant staff based on new status
        if scenario == 'status':
            new_status = update_data.get('status')
            if new_status == 'SCHEDULED' and assigned_mechanic_id:
                # Notify assigned mechanic when order is scheduled
                notify.queue_order_firebase_notification(order_id, scenario, [assigned_mechanic_id])
            elif new_status == 'DELIVERED':
                # Notify customer support when order is delivered
                notify.queue_order_firebase_notification(order_id, scenario)
                
    except Exception as e:
        print(f"Failed to queue Firebase notification: {str(e)}")
        # Don't fail the update if notification queueing fails


def format_order_data_for_email(order_data):
    """Format order data for email notifications"""
    # Get service and plan names if available
    services = []
    service_id = order_data.get('serviceId')
    plan_id = order_data.get('planId')
    
    if service_id and plan_id:
        try:
            service_plan_names = db.get_service_plan_names(service_id, plan_id)
            if service_plan_names:
                service_name, plan_name = service_plan_names
                services.append({
                    'serviceName': service_name,
                    'planName': plan_name,
                })
        except Exception as e:
            print(f"Error getting service plan names: {str(e)}")
    
    # Format items from database format
    items = []
    order_items = order_data.get('items', [])
    if isinstance(order_items, list):
        for item in order_items:
            # Handle the case where items might be in DynamoDB format or already deserialized
            if isinstance(item, dict) and 'M' in item:
                # DynamoDB format
                item_data = item['M']
                items.append({
                    'name': f"Item {item_data.get('itemId', {}).get('N', 'Unknown')}",
                    'quantity': int(item_data.get('quantity', {}).get('N', 1)),
                    'price': f"{float(item_data.get('price', {}).get('N', 0)):.2f}"
                })
            else:
                # Already deserialized
                items.append({
                    'name': item.get('name', f"Item {item.get('itemId', 'Unknown')}"),
                    'quantity': item.get('quantity', 1),
                    'price': f"{item.get('price', 0):.2f}"
                })
    
    # Format vehicle info from database fields
    vehicle_info = {
        'make': order_data.get('carMake', 'N/A'),
        'model': order_data.get('carModel', 'N/A'),
        'year': order_data.get('carYear', 'N/A')
    }
    
    # Format scheduled time slot for display
    scheduled_slot = order_data.get('scheduledTimeSlot', {})
    time_slot = "TBD"
    if scheduled_slot and isinstance(scheduled_slot, dict):
        start = scheduled_slot.get('start', '')
        end = scheduled_slot.get('end', '')
        if start and end:
            time_slot = f"{start} - {end}"
    
    # Get mechanic name if assigned
    assigned_mechanic = "Our team"
    assigned_mechanic_id = order_data.get('assignedMechanicId')
    if assigned_mechanic_id:
        try:
            mechanic_record = db.get_staff_record_by_user_id(assigned_mechanic_id)
            if mechanic_record:
                assigned_mechanic = mechanic_record.get('name', 'Our team')
        except Exception as e:
            print(f"Error getting mechanic name: {str(e)}")
    
    # Format customer data
    customer_data = {
        'phoneNumber': order_data.get('customerPhone', 'N/A')
    }
    
    return {
        'orderId': order_data.get('orderId'),
        'services': services,
        'items': items,
        'vehicleInfo': vehicle_info,
        'totalAmount': f"{order_data.get('totalPrice', 0):.2f}",
        'status': order_data.get('status', 'Processing'),
        'customerData': customer_data,
        'scheduledDate': order_data.get('scheduledDate'),
        'timeSlot': time_slot,
        'assignedMechanic': assigned_mechanic,
        'estimatedDuration': order_data.get('estimatedDuration', 'TBD'),
        'reportType': order_data.get('reportType')
    }
