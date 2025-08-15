from datetime import datetime
import db_utils as db
import response_utils as resp
import request_utils as req

def lambda_handler(event, context):
    try:
        staff_user_email = req.get_staff_user_email(event)
        order_id = req.get_path_param(event, 'orderId')
        user_id = req.get_query_param(event, 'userId')

        # Determine if this is a staff user or customer user
        if staff_user_email:
            # Staff user scenarios (1 & 2)
            staff_user_record = db.get_staff_record(staff_user_email)
            if not staff_user_record:
                return resp.error_response(f"No staff record found for email: {staff_user_email}", 404)
            
            staff_roles = staff_user_record.get('roles', [])
            staff_user_id = staff_user_record.get('userId')
            
            if order_id:
                # Get single order by ID
                order = db.get_order(order_id)
                if not order:
                    return resp.error_response("Order not found", 404)
                
                return resp.success_response({
                    "order": resp.convert_decimal(order)
                })
            else:
                # Get multiple orders based on role
                if 'CUSTOMER_SUPPORT' in staff_roles or 'CLERK' in staff_roles:
                    # Scenario 1: CUSTOMER_SUPPORT or CLERK - get all orders
                    orders = db.get_all_orders()
                elif 'MECHANIC' in staff_roles:
                    # Scenario 2: MECHANIC - get orders assigned to them
                    orders = db.get_orders_by_assigned_mechanic(staff_user_id)
                else:
                    return resp.error_response("Unauthorized: Invalid staff role", 403)
                
                # Apply query parameter filters if provided
                orders = apply_query_filters(orders, event)
                
                return resp.success_response({
                    "orders": resp.convert_decimal(orders),
                    "count": len(orders)
                })
        else:
            # Scenario 3: Customer user
            if not user_id:
                return resp.error_response("userId is required for non-staff users")
            
            if order_id:
                # Get single order by ID - verify ownership
                order = db.get_order(order_id)
                if not order:
                    return resp.error_response("Order not found", 404)
                
                # Check if this user created the order
                # if order.get('createdUserId') != user_id:
                #     return resp.error_response("Unauthorized: You can only view orders you created", 403)
                
                # Get assigned mechanic details if available
                mechanic_details = None
                assigned_mechanic_id = order.get('assignedMechanicId')
                if assigned_mechanic_id:
                    mechanic_record = db.get_staff_record_by_user_id(assigned_mechanic_id)
                    if mechanic_record:
                        mechanic_details = {
                            "userName": mechanic_record.get('userName', ''),
                            "userEmail": mechanic_record.get('userEmail', ''),
                            "contactNumber": mechanic_record.get('contactNumber', '')
                        }
                
                response_data = {
                    "order": resp.convert_decimal(order)
                }
                
                # Add mechanic details if available
                if mechanic_details:
                    response_data["assignedMechanic"] = mechanic_details
                
                return resp.success_response(response_data)
            else:
                # Get all orders created by this user
                orders = db.get_orders_by_created_user(user_id)
                
                # Apply query parameter filters if provided
                orders = apply_query_filters(orders, event)
                
                return resp.success_response({
                    "orders": resp.convert_decimal(orders),
                    "count": len(orders)
                })
        
    except Exception as e:
        print(f"Error in get orders lambda: {str(e)}")
        return resp.error_response("Internal server error", 500)


def apply_query_filters(orders, event):
    """Apply query parameter filters to the orders list"""
    if not orders:
        return orders
    
    # Get filter parameters from query string
    status = req.get_query_param(event, 'status')
    start_date = req.get_query_param(event, 'startDate')
    end_date = req.get_query_param(event, 'endDate')
    category_id = req.get_query_param(event, 'categoryId')
    item_id = req.get_query_param(event, 'itemId')
    scheduled_date = req.get_query_param(event, 'scheduledDate')
    
    filtered_orders = orders
    
    # Filter by status
    if status:
        filtered_orders = [
            order for order in filtered_orders 
            if order.get('status', '').upper() == status.upper()
        ]
    
    # Filter by date range
    if start_date:
        if end_date:
            # Filter by date range
            filtered_orders = [
                order for order in filtered_orders 
                if start_date <= order.get('createdDate', '') <= end_date
            ]
        else:
            # Filter by single date
            filtered_orders = [
                order for order in filtered_orders 
                if order.get('createdDate', '') == start_date
            ]
    
    # Filter by category ID
    if category_id:
        try:
            category_id_int = int(category_id)
            filtered_orders = [
                order for order in filtered_orders 
                if any(item.get('categoryId') == category_id_int for item in order.get('items', []))
            ]
        except ValueError:
            pass  # Invalid category ID format, skip filter
    
    # Filter by item ID
    if item_id:
        try:
            item_id_int = int(item_id)
            filtered_orders = [
                order for order in filtered_orders 
                if any(item.get('itemId') == item_id_int for item in order.get('items', []))
            ]
        except ValueError:
            pass  # Invalid item ID format, skip filter
    
    # Filter by handover date
    if scheduled_date:
        filtered_orders = [
            order for order in filtered_orders 
            if order.get('scheduledDate', '') == scheduled_date
        ]
    
    return filtered_orders
