from datetime import datetime
import uuid
import db_utils as db
import response_utils as resp
import request_utils as req
import wsgw_utils as wsgw
import email_utils as email
import notification_utils as notify

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
        valid, msg = req.validate_order_data(order_data, staff_user=bool(staff_user_email))
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

        # Process and validate items, calculate total price
        processed_items = []
        total_price = 0
        
        for item in order_data.get('items', []):
            category_id = item.get('categoryId')
            item_id = item.get('itemId')
            quantity = item.get('quantity', 1)
            
            # Get price by category and item
            item_pricing = db.get_item_pricing(category_id=category_id, item_id=item_id)
            if item_pricing is None:
                return resp.error_response(f"Invalid category or item. Please check categoryId {category_id} and itemId {item_id}")

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

        # Build order data
        order_data_db = db.build_order_data(
            order_id=order_id,
            items=processed_items,
            customer_data=order_data.get('customerData', {}),
            car_data=order_data.get('carData', {}),
            notes=order_data.get('notes', ''),
            delivery_location=order_data.get('deliveryLocation', ''),
            created_user_id=user_id,
            total_price=total_price
        )

        # Create order in database
        success = db.create_order(order_data_db)
        if not success:
            return resp.error_response("Failed to create order", 500)

        # Queue staff WebSocket notifications
        try:
            staff_notification_data = {
                "type": "order",
                "subtype": "create",
                "success": True,
                "orderId": order_id,
                "orderData": resp.convert_decimal(order_data_db)
            }
            notify.queue_staff_websocket_notification(staff_notification_data, assigned_to=user_id)
        except Exception as e:
            print(f"Failed to queue staff WebSocket notification: {str(e)}")

        # Queue Firebase push notification to staff
        try:
            notify.queue_order_firebase_notification(order_id, 'create')
        except Exception as e:
            print(f"Failed to queue Firebase notification: {str(e)}")

        # Queue email notification to customer
        try:
            # Get customer details
            user_record = db.get_user_record(user_id)
            if user_record and user_record.get('email'):
                customer_email = user_record.get('email')
                customer_name = user_record.get('name', 'Valued Customer')
                
                # Prepare order data for email
                email_order_data = {
                    'orderId': order_id,
                    'services': order_data.get('services', []),
                    'items': [
                        {
                            'name': item.get('name', f"Item {item.get('itemId', 'Unknown')}"),
                            'quantity': item.get('quantity', 1),
                            'price': f"{item.get('price', 0):.2f}"
                        } for item in processed_items
                    ],
                    'vehicleInfo': order_data.get('carData', {}),
                    'totalAmount': f"{total_price:.2f}",
                    'status': 'Processing',
                    'customerData': order_data.get('customerData', {})
                }
                
                # Queue order created email
                notify.queue_order_created_email(customer_email, customer_name, email_order_data)
                
        except Exception as e:
            print(f"Failed to queue order creation email: {str(e)}")
            # Don't fail the order creation if email queueing fails

        # Return success response
        return resp.success_response({
            "message": "Order created successfully",
            "orderId": order_id,
            "totalPrice": total_price,
            "itemCount": len(processed_items)
        })
        
    except Exception as e:
        print(f"Error in create order lambda: {str(e)}")
        return resp.error_response("Internal server error", 500)
