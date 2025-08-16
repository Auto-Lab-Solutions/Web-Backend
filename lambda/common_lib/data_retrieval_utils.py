"""
Data retrieval utilities for common getter patterns across Lambda functions
Centralizes data fetching logic with proper filtering and access control
"""

import db_utils as db
import permission_utils as perm
import response_utils as resp


class DataRetriever:
    """Handles common data retrieval patterns with access control"""
    
    @staticmethod
    def get_appointments_with_access_control(staff_user_email, user_id=None, appointment_id=None, event=None):
        """
        Get appointments with proper access control and filtering
        
        Args:
            staff_user_email (str): Staff user email (optional)
            user_id (str): User ID for customer access (optional)
            appointment_id (str): Specific appointment ID (optional)
            event (dict): API Gateway event for query parameters
            
        Returns:
            dict: Response data with appointments
            
        Raises:
            PermissionError: If access is denied
        """
        # Validate access
        staff_context = perm.PermissionValidator.validate_staff_access(
            staff_user_email,
            optional=True
        )
        
        if staff_context['staff_record']:
            # Staff user access
            staff_roles = staff_context['staff_roles']
            staff_user_id = staff_context['staff_user_id']
            
            if appointment_id:
                # Get single appointment by ID
                appointment = db.get_appointment(appointment_id)
                if not appointment:
                    raise perm.PermissionError("Appointment not found", 404)
                
                return {"appointment": resp.convert_decimal(appointment)}
            else:
                # Get multiple appointments based on role
                if perm.RoleBasedPermissions.check_permission(staff_roles, 'can_view_all_data'):
                    # ADMIN, CUSTOMER_SUPPORT, CLERK - get all appointments
                    appointments = db.get_all_appointments()
                elif 'MECHANIC' in staff_roles:
                    # MECHANIC - get appointments assigned to them
                    appointments = db.get_appointments_by_assigned_mechanic(staff_user_id)
                else:
                    raise perm.PermissionError("Unauthorized: Invalid staff role", 403)
                
                # Apply query parameter filters if provided
                if event:
                    appointments = DataRetriever._apply_appointment_filters(appointments, event)
                
                return {
                    "appointments": resp.convert_decimal(appointments),
                    "count": len(appointments)
                }
        else:
            # Customer user access
            if not user_id:
                raise perm.PermissionError("userId is required for non-staff users", 400)
            
            user_context = perm.PermissionValidator.validate_user_access(user_id)
            effective_user_id = user_context['effective_user_id']
            
            if appointment_id:
                # Get single appointment by ID - verify ownership
                appointment = db.get_appointment(appointment_id)
                if not appointment:
                    raise perm.PermissionError("Appointment not found", 404)
                
                # Ownership check is commented out in original code
                # perm.PermissionValidator.check_ownership(appointment, effective_user_id)
                
                # Get assigned mechanic details if available
                response_data = {"appointment": resp.convert_decimal(appointment)}
                
                assigned_mechanic_id = appointment.get('assignedMechanicId')
                if assigned_mechanic_id:
                    mechanic_record = db.get_staff_record_by_user_id(assigned_mechanic_id)
                    if mechanic_record:
                        response_data["assignedMechanic"] = {
                            "userName": mechanic_record.get('userName', ''),
                            "userEmail": mechanic_record.get('userEmail', ''),
                            "contactNumber": mechanic_record.get('contactNumber', '')
                        }
                
                return response_data
            else:
                # Get all appointments created by this user
                appointments = db.get_appointments_by_created_user(effective_user_id)
                
                # Apply query parameter filters if provided
                if event:
                    appointments = DataRetriever._apply_appointment_filters(appointments, event)
                
                return {
                    "appointments": resp.convert_decimal(appointments),
                    "count": len(appointments)
                }
    
    @staticmethod
    def get_orders_with_access_control(staff_user_email, user_id=None, order_id=None, event=None):
        """
        Get orders with proper access control and filtering
        
        Args:
            staff_user_email (str): Staff user email (optional)
            user_id (str): User ID for customer access (optional)
            order_id (str): Specific order ID (optional)
            event (dict): API Gateway event for query parameters
            
        Returns:
            dict: Response data with orders
            
        Raises:
            PermissionError: If access is denied
        """
        # Validate access
        staff_context = perm.PermissionValidator.validate_staff_access(
            staff_user_email,
            optional=True
        )
        
        if staff_context['staff_record']:
            # Staff user access
            staff_roles = staff_context['staff_roles']
            
            if order_id:
                # Get single order by ID
                order = db.get_order(order_id)
                if not order:
                    raise perm.PermissionError("Order not found", 404)
                
                return {"order": resp.convert_decimal(order)}
            else:
                # Staff can view all orders
                if perm.RoleBasedPermissions.check_permission(staff_roles, 'can_view_all_data'):
                    orders = db.get_all_orders()
                else:
                    raise perm.PermissionError("Unauthorized: Insufficient permissions", 403)
                
                # Apply query parameter filters if provided
                if event:
                    orders = DataRetriever._apply_order_filters(orders, event)
                
                return {
                    "orders": resp.convert_decimal(orders),
                    "count": len(orders)
                }
        else:
            # Customer user access
            if not user_id:
                raise perm.PermissionError("userId is required for non-staff users", 400)
            
            user_context = perm.PermissionValidator.validate_user_access(user_id)
            effective_user_id = user_context['effective_user_id']
            
            if order_id:
                # Get single order by ID - verify ownership
                order = db.get_order(order_id)
                if not order:
                    raise perm.PermissionError("Order not found", 404)
                
                perm.PermissionValidator.check_ownership(order, effective_user_id)
                
                return {"order": resp.convert_decimal(order)}
            else:
                # Get all orders created by this user
                orders = db.get_orders_by_created_user(effective_user_id)
                
                # Apply query parameter filters if provided
                if event:
                    orders = DataRetriever._apply_order_filters(orders, event)
                
                return {
                    "orders": resp.convert_decimal(orders),
                    "count": len(orders)
                }
    
    @staticmethod
    def _apply_appointment_filters(appointments, event):
        """Apply query parameter filters to appointments"""
        import request_utils as req
        
        # Get filter parameters
        status_filter = req.get_query_param(event, 'status')
        payment_status_filter = req.get_query_param(event, 'paymentStatus')
        date_from = req.get_query_param(event, 'dateFrom')
        date_to = req.get_query_param(event, 'dateTo')
        service_id_filter = req.get_query_param(event, 'serviceId')
        mechanic_id_filter = req.get_query_param(event, 'mechanicId')
        
        filtered_appointments = appointments
        
        # Apply filters
        if status_filter:
            filtered_appointments = [apt for apt in filtered_appointments if apt.get('status') == status_filter]
        
        if payment_status_filter:
            filtered_appointments = [apt for apt in filtered_appointments if apt.get('paymentStatus') == payment_status_filter]
        
        if service_id_filter:
            try:
                service_id = int(service_id_filter)
                filtered_appointments = [apt for apt in filtered_appointments if apt.get('serviceId') == service_id]
            except ValueError:
                pass  # Ignore invalid service ID
        
        if mechanic_id_filter:
            filtered_appointments = [apt for apt in filtered_appointments if apt.get('assignedMechanicId') == mechanic_id_filter]
        
        # Date filtering would require parsing appointment dates
        # Implementation depends on date format in the database
        
        return filtered_appointments
    
    @staticmethod
    def _apply_order_filters(orders, event):
        """Apply query parameter filters to orders"""
        import request_utils as req
        
        # Get filter parameters
        status_filter = req.get_query_param(event, 'status')
        payment_status_filter = req.get_query_param(event, 'paymentStatus')
        date_from = req.get_query_param(event, 'dateFrom')
        date_to = req.get_query_param(event, 'dateTo')
        
        filtered_orders = orders
        
        # Apply filters
        if status_filter:
            filtered_orders = [order for order in filtered_orders if order.get('status') == status_filter]
        
        if payment_status_filter:
            filtered_orders = [order for order in filtered_orders if order.get('paymentStatus') == payment_status_filter]
        
        # Date filtering would require parsing order dates
        # Implementation depends on date format in the database
        
        return filtered_orders


class StaffDataRetriever:
    """Handles staff-specific data retrieval patterns"""
    
    @staticmethod
    def get_connections_with_access_control(staff_user_email):
        """
        Get WebSocket connections with proper staff access control
        
        Args:
            staff_user_email (str): Staff user email
            
        Returns:
            dict: Response data with connections
            
        Raises:
            PermissionError: If access is denied
        """
        # Validate staff access
        staff_context = perm.PermissionValidator.validate_staff_access(
            staff_user_email,
            required_roles=['CUSTOMER_SUPPORT', 'CLERK']
        )
        
        # Get all connections
        connections = db.get_all_active_connections()
        
        return {
            "connections": resp.convert_decimal(connections),
            "count": len(connections)
        }
    
    @staticmethod
    def get_last_messages_with_access_control(staff_user_email):
        """
        Get last messages with proper staff access control
        
        Args:
            staff_user_email (str): Staff user email
            
        Returns:
            dict: Response data with last messages
            
        Raises:
            PermissionError: If access is denied
        """
        # Validate staff access
        staff_context = perm.PermissionValidator.validate_staff_access(
            staff_user_email,
            required_roles=['CUSTOMER_SUPPORT', 'CLERK']
        )
        
        staff_user_id = staff_context['staff_user_id']
        
        # Get messages and extract latest by conversation
        latest_messages = StaffDataRetriever._get_latest_messages_by_user(staff_user_id)
        
        return {
            "messages": resp.convert_decimal(latest_messages)
        }
    
    @staticmethod
    def _get_latest_messages_by_user(user_id):
        """Get latest messages by user for all conversations"""
        sender_messages = db.get_messages_by_index(
            index_name='senderId-index', 
            key_name='senderId', 
            key_value=user_id
        )
        receiver_messages = db.get_messages_by_index(
            index_name='receiverId-index', 
            key_name='receiverId', 
            key_value=user_id
        )
        staff_unassigned_messages = db.get_messages_by_index(
            index_name='receiverId-index', 
            key_name='receiverId', 
            key_value='ALL'
        )
        
        all_messages = sender_messages + receiver_messages + staff_unassigned_messages
        
        return StaffDataRetriever._extract_latest_messages_by_conversation(user_id, all_messages)
    
    @staticmethod
    def _extract_latest_messages_by_conversation(user_id, messages):
        """Extract latest message for each conversation"""
        latest_by_user = {}
        
        for message in messages:
            sender_id = message['senderId']
            receiver_id = message['receiverId']
            created_at = int(message['createdAt'])
            
            other_user = receiver_id if sender_id == user_id else sender_id
            
            if (other_user not in latest_by_user or
                    created_at > int(latest_by_user[other_user]['createdAt'])):
                latest_by_user[other_user] = message
        
        # Sort by creation time, newest first
        latest_messages = list(latest_by_user.values())
        return sorted(latest_messages, key=lambda x: int(x['createdAt']), reverse=True)


def handle_data_retrieval_error(func):
    """
    Decorator to handle data retrieval errors and convert to proper responses
    """
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except perm.PermissionError as e:
            return resp.error_response(e.message, e.status_code)
        except Exception as e:
            print(f"Unexpected error in {func.__name__}: {str(e)}")
            return resp.error_response("Internal server error", 500)
    
    return wrapper
