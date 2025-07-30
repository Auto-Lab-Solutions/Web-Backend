from datetime import datetime
import time
import db_utils as db
import response_utils as resp
import request_utils as req
import wsgw_utils as wsgw

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
    notification_data = {
        "type": "order",
        "subtype": "update",
        "scenario": scenario,
        "orderId": order_id,
        "changes": list(update_data.keys())
    }
    
    # Get connections of customer user and send notification
    customer_user_connection = db.get_connection_by_user_id(updated_order.get('createdUserId'))
    if customer_user_connection:
        customer_user_connection = resp.convert_decimal(customer_user_connection)
        wsgw.send_notification(
            wsgw_client,
            customer_user_connection.get('connectionId'),
            notification_data
        )
