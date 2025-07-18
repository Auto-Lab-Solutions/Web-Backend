from datetime import datetime
import uuid
import db_utils as db
import response_utils as resp
import request_utils as req
import wsgw_utils as wsgw

PERMITTED_ROLE = 'CUSTOMER_SUPPORT'

ORDERS_LIMIT = 5  # Maximum number of orders per day
wsgw_client = wsgw.get_apigateway_client()

def lambda_handler(event, context):
    try:
        staff_user_email = req.get_staff_user_email(event)
        user_id = req.get_body_param(event, 'userId')
        order_data = req.get_body_param(event, 'orderData')

        if staff_user_email:
            staff_user_record = db.get_staff_record(staff_user_email)
            if not staff_user_record:
                return resp.error_response(f"No staff record found for email: {staff_user_email}")
            staff_roles = staff_user_record.get('roles', [])
            if PERMITTED_ROLE not in staff_roles:
                return resp.error_response("Unauthorized: CUSTOMER_SUPPORT role required")
            user_id = staff_user_record.get('userId')
        else:
            if not user_id:
                return resp.error_response("userId is required for non-staff users")
            user_record = db.get_user_record(user_id)
            if not user_record:
                return resp.error_response(f"No user record found for userId: {user_id}")

        # Validate order data
        valid, msg = validate_order_data(order_data, staff_user=bool(staff_user_email))
        if not valid:
            return resp.error_response(msg)
        
        # Check if the user has reached the order limit for today
        if not staff_user_email:
            today = datetime.now().date()
            order_count = db.get_daily_unpaid_orders_count(user_id, today)
            if order_count >= ORDERS_LIMIT:
                return resp.error_response("Order limit reached for today")

        # Generate unique order ID
        order_id = str(uuid.uuid4())

        # Get price by category and item
        item_pricing = db.get_item_pricing(
            category_id=order_data.get('categoryId'),
            item_id=order_data.get('itemId')
        )
        if not item_pricing:
            return resp.error_response("Invalid category or item. Please check the categoryId and itemId provided")

        price = item_pricing.get('price', 0)
        quantity = order_data.get('quantity', 1)

        # Build order data
        order_data_db = db.build_order_data(
            order_id=order_id,
            category_id=order_data.get('categoryId'),
            item_id=order_data.get('itemId'),
            quantity=quantity,
            customer_data=order_data.get('customerData', {}),
            car_data=order_data.get('carData', {}),
            notes=order_data.get('notes', ''),
            created_user_id=user_id,
            price=price
        )

        # Create order in database
        success = db.create_order(order_data_db)
        if not success:
            return resp.error_response("Failed to create order", 500)

        # Send notifications to staff users
        staff_connections = db.get_assigned_or_all_staff_connections(assigned_to=user_id)
        notification_data = {
            "type": "order",
            "subtype": "create",
            "success": True,
            "orderId": order_id,
            "orderData": resp.convert_decimal(order_data_db)
        }

        for staff in staff_connections:
            wsgw.send_notification(wsgw_client, staff.get('connectionId'), notification_data)

        # Return success response
        return resp.success_response({
            "message": "Order created successfully",
            "orderId": order_id,
            "totalPrice": price * quantity
        })
        
    except Exception as e:
        print(f"Error in create order lambda: {str(e)}")
        return resp.error_response("Internal server error", 500)


def validate_order_data(order_data, staff_user=False):
    """Validate order data"""
    if not order_data:
        return False, "Order data is required"
    
    # Required fields
    required_fields = ['categoryId', 'itemId', 'quantity', 'customerData', 'carData']
    for field in required_fields:
        if field not in order_data:
            return False, f"{field} is required"
    
    # Validate category and item IDs
    try:
        category_id = int(order_data['categoryId'])
        item_id = int(order_data['itemId'])
        quantity = int(order_data['quantity'])
        
        if category_id <= 0 or item_id <= 0 or quantity <= 0:
            return False, "categoryId, itemId, and quantity must be positive integers"
            
    except (ValueError, TypeError):
        return False, "categoryId, itemId, and quantity must be valid integers"
    
    # Validate customer data
    customer_data = order_data.get('customerData', {})
    if not isinstance(customer_data, dict):
        return False, "customerData must be an object"
    
    required_customer_fields = ['name', 'email', 'phoneNumber']
    for field in required_customer_fields:
        if field not in customer_data or not customer_data[field]:
            return False, f"customerData.{field} is required"
    
    # Validate email format
    email = customer_data.get('email', '')
    if '@' not in email or '.' not in email:
        return False, "Invalid email format"
    
    # Validate car data
    car_data = order_data.get('carData', {})
    if not isinstance(car_data, dict):
        return False, "carData must be an object"
    
    required_car_fields = ['make', 'model', 'year']
    for field in required_car_fields:
        if field not in car_data or not car_data[field]:
            return False, f"carData.{field} is required"
    
    # Validate car year
    try:
        year = int(car_data.get('year', 0))
        current_year = datetime.now().year
        if year < 1900 or year > current_year + 1:
            return False, f"Car year must be between 1900 and {current_year + 1}"
    except (ValueError, TypeError):
        return False, "Car year must be a valid integer"
    
    # Validate quantity limits
    if quantity > 100:
        return False, "Maximum quantity per order is 100"

    return True, "Valid"
