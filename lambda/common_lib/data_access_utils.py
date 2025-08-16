"""
Data Access Manager for API operations

This module provides managers for common data access patterns used across
API Lambda functions, including analytics, inquiries, prices, users, etc.
"""

import sys
import os
from datetime import datetime, timedelta
from collections import defaultdict, Counter

# Add common_lib to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'common_lib'))

import db_utils as db
import request_utils as req
from exceptions import BusinessLogicError


class DataAccessManager:
    """Base manager for common data access patterns"""
    
    def __init__(self):
        pass
    
    def validate_staff_authentication(self, event, required_roles=None):
        """
        Validate staff authentication and return staff context
        
        Args:
            event: Lambda event
            required_roles: List of required roles (optional)
            
        Returns:
            dict: Staff context with user info and roles
            
        Raises:
            BusinessLogicError: If authentication fails
        """
        staff_user_email = req.get_staff_user_email(event)
        if not staff_user_email:
            raise BusinessLogicError("Unauthorized: Staff authentication required", 401)
        
        staff_user_record = db.get_staff_record(staff_user_email)
        if not staff_user_record:
            raise BusinessLogicError(f"No staff record found for email: {staff_user_email}", 404)
        
        staff_roles = staff_user_record.get('roles', [])
        staff_user_id = staff_user_record.get('userId')
        
        # Check role requirements if specified
        if required_roles:
            if not any(role in staff_roles for role in required_roles):
                required_roles_str = ', '.join(required_roles)
                raise BusinessLogicError(f"Unauthorized: {required_roles_str} role required", 403)
        
        return {
            'staff_user_email': staff_user_email,
            'staff_user_id': staff_user_id,
            'staff_roles': staff_roles,
            'staff_record': staff_user_record
        }
    
    def validate_shared_key_authentication(self, event, required_shared_key):
        """
        Validate shared key authentication
        
        Args:
            event: Lambda event
            required_shared_key: Expected shared key value
            
        Returns:
            str: Email from request
            
        Raises:
            BusinessLogicError: If authentication fails
        """
        email = req.get_query_param(event, 'email')
        shared_key = req.get_header(event, 'shared-api-key')
        
        if not email or not shared_key:
            raise BusinessLogicError("Email and sharedKey are required", 400)
        
        if shared_key != required_shared_key:
            raise BusinessLogicError("Invalid sharedKey provided", 401)
        
        return email
    
    def validate_date_parameter(self, date_str, param_name='date'):
        """
        Validate date parameter in YYYY-MM-DD format
        
        Args:
            date_str: Date string to validate
            param_name: Parameter name for error messages
            
        Returns:
            datetime: Parsed datetime object
            
        Raises:
            BusinessLogicError: If date format is invalid
        """
        if not date_str:
            raise BusinessLogicError(f"{param_name} parameter is required", 400)
        
        try:
            return datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            raise BusinessLogicError(f"{param_name} must be in YYYY-MM-DD format", 400)
    
    def validate_date_range(self, start_date_str, end_date_str, max_days=None):
        """
        Validate date range parameters
        
        Args:
            start_date_str: Start date string
            end_date_str: End date string
            max_days: Maximum allowed range in days (optional)
            
        Returns:
            tuple: (start_datetime, end_datetime)
            
        Raises:
            BusinessLogicError: If date range is invalid
        """
        start_dt = self.validate_date_parameter(start_date_str, 'startDate')
        end_dt = self.validate_date_parameter(end_date_str, 'endDate')
        
        if end_dt < start_dt:
            raise BusinessLogicError("End date must be on or after start date", 400)
        
        if max_days:
            range_days = (end_dt - start_dt).days
            if range_days > max_days:
                raise BusinessLogicError(f"Date range cannot exceed {max_days} days", 400)
        
        return start_dt, end_dt
    
    def validate_timestamp_range(self, start_timestamp_str, end_timestamp_str, max_seconds=None):
        """
        Validate timestamp range parameters
        
        Args:
            start_timestamp_str: Start timestamp string
            end_timestamp_str: End timestamp string
            max_seconds: Maximum allowed range in seconds (optional)
            
        Returns:
            tuple: (start_timestamp, end_timestamp)
            
        Raises:
            BusinessLogicError: If timestamp range is invalid
        """
        if not start_timestamp_str or not end_timestamp_str:
            raise BusinessLogicError("start_date and end_date parameters are required (timestamps)", 400)
        
        try:
            start_timestamp = int(start_timestamp_str)
            end_timestamp = int(end_timestamp_str)
        except ValueError:
            raise BusinessLogicError("start_date and end_date must be valid timestamps", 400)
        
        if end_timestamp <= start_timestamp:
            raise BusinessLogicError("end_date must be greater than start_date", 400)
        
        if max_seconds:
            range_seconds = end_timestamp - start_timestamp
            if range_seconds > max_seconds:
                max_days = max_seconds // (24 * 60 * 60)
                raise BusinessLogicError(f"Date range cannot exceed {max_days} days", 400)
        
        return start_timestamp, end_timestamp


class AnalyticsManager(DataAccessManager):
    """Manager for analytics data operations"""
    
    def __init__(self):
        super().__init__()
        self.allowed_roles = ['CUSTOMER_SUPPORT', 'CLERK', 'ADMIN', 'MANAGER']
        self.query_handlers = {
            # Orders analytics
            'orders_by_category': self.get_orders_by_category,
            'orders_by_item': self.get_orders_by_item,
            'orders_by_status': self.get_orders_by_status,
            'orders_by_mechanic': self.get_orders_by_mechanic,
            'daily_orders': self.get_daily_orders,
            'monthly_orders': self.get_monthly_orders,
            'orders_revenue': self.get_orders_revenue,
            
            # Appointments analytics
            'appointments_by_service': self.get_appointments_by_service,
            'appointments_by_plan': self.get_appointments_by_plan,
            'appointments_by_status': self.get_appointments_by_status,
            'appointments_by_mechanic': self.get_appointments_by_mechanic_analytics,
            'daily_appointments': self.get_daily_appointments,
            'monthly_appointments': self.get_monthly_appointments,
            'appointments_revenue': self.get_appointments_revenue,
            
            # Combined analytics
            'daily_income': self.get_daily_income,
            'monthly_income': self.get_monthly_income,
            'yearly_income': self.get_yearly_income,
            'revenue_breakdown': self.get_revenue_breakdown,
            
            # Staff analytics
            'staff_performance': self.get_staff_performance,
            'mechanic_workload': self.get_mechanic_workload,
            
            # Customer analytics
            'customer_activity': self.get_customer_activity,
            'top_customers': self.get_top_customers,
            
            # Trend analytics
            'daily_trends': self.get_daily_trends,
            'monthly_trends': self.get_monthly_trends,
            'service_popularity': self.get_service_popularity,
            'item_popularity': self.get_item_popularity,
            
            # Summary analytics
            'dashboard_summary': self.get_dashboard_summary,
            'financial_summary': self.get_financial_summary,
        }
    
    def validate_analytics_access(self, event):
        """Validate staff has analytics access"""
        return self.validate_staff_authentication(event, self.allowed_roles)
    
    def route_analytics_query(self, query_type, parameters, user_context):
        """
        Route analytics query to appropriate handler
        
        Args:
            query_type: Type of analytics query
            parameters: Query parameters
            user_context: User context from authentication
            
        Returns:
            dict: Query results
        """
        handler = self.query_handlers.get(query_type)
        if not handler:
            raise BusinessLogicError(f"Unsupported query type: {query_type}", 400)
        
        return handler(parameters, user_context)
    
    # ==================== UTILITY METHODS ====================
    
    def filter_by_date_range(self, item, start_date=None, end_date=None):
        """Filter items by date range"""
        if not start_date and not end_date:
            return True
        
        item_date = item.get('createdDate', '')
        if not item_date:
            return False
        
        if start_date and item_date < start_date:
            return False
        
        if end_date and item_date > end_date:
            return False
        
        return True
    
    # ==================== ORDERS ANALYTICS ====================
    
    def get_orders_by_category(self, parameters, user_context):
        """Get orders grouped by category"""
        from collections import defaultdict
        
        start_date = parameters.get('startDate')
        end_date = parameters.get('endDate')
        
        orders = db.get_all_orders()
        category_data = defaultdict(lambda: {'count': 0, 'revenue': 0, 'items': []})
        
        for order in orders:
            if self.filter_by_date_range(order, start_date, end_date):
                category_id = order.get('categoryId', 0)
                category_key = f"Category {category_id}"
                
                category_data[category_key]['count'] += 1
                category_data[category_key]['revenue'] += float(order.get('totalPrice', 0))
                category_data[category_key]['items'].append({
                    'orderId': order.get('orderId'),
                    'itemId': order.get('itemId'),
                    'quantity': order.get('quantity'),
                    'price': float(order.get('totalPrice', 0)),
                    'status': order.get('status'),
                    'createdDate': order.get('createdDate')
                })
        
        return dict(category_data)
    
    def get_orders_by_item(self, parameters, user_context):
        """Get orders grouped by item"""
        from collections import defaultdict
        
        start_date = parameters.get('startDate')
        end_date = parameters.get('endDate')
        category_id = parameters.get('categoryId')
        
        orders = db.get_all_orders()
        item_data = defaultdict(lambda: {'count': 0, 'revenue': 0, 'totalQuantity': 0})
        
        for order in orders:
            if self.filter_by_date_range(order, start_date, end_date):
                if category_id and order.get('categoryId') != category_id:
                    continue
                    
                item_id = order.get('itemId', 0)
                item_key = f"Item {item_id}"
                
                item_data[item_key]['count'] += 1
                item_data[item_key]['revenue'] += float(order.get('totalPrice', 0))
                item_data[item_key]['totalQuantity'] += order.get('quantity', 0)
        
        return dict(item_data)
    
    def get_orders_by_status(self, parameters, user_context):
        """Get orders grouped by status"""
        from collections import defaultdict
        
        start_date = parameters.get('startDate')
        end_date = parameters.get('endDate')
        
        orders = db.get_all_orders()
        status_data = defaultdict(lambda: {'count': 0, 'revenue': 0})
        
        for order in orders:
            if self.filter_by_date_range(order, start_date, end_date):
                status = order.get('status', 'UNKNOWN')
                status_data[status]['count'] += 1
                status_data[status]['revenue'] += float(order.get('totalPrice', 0))
        
        return dict(status_data)
    
    def get_orders_by_mechanic(self, parameters, user_context):
        """Get orders grouped by assigned mechanic"""
        from collections import defaultdict
        
        start_date = parameters.get('startDate')
        end_date = parameters.get('endDate')
        
        orders = db.get_all_orders()
        mechanic_data = defaultdict(lambda: {'count': 0, 'revenue': 0, 'orders': []})
        
        for order in orders:
            if self.filter_by_date_range(order, start_date, end_date):
                mechanic_id = order.get('assignedMechanicId', 'Unassigned')
                
                mechanic_data[mechanic_id]['count'] += 1
                mechanic_data[mechanic_id]['revenue'] += float(order.get('totalPrice', 0))
                mechanic_data[mechanic_id]['orders'].append({
                    'orderId': order.get('orderId'),
                    'status': order.get('status'),
                    'createdDate': order.get('createdDate'),
                    'price': float(order.get('totalPrice', 0))
                })
        
        return dict(mechanic_data)
    
    def get_daily_orders(self, parameters, user_context):
        """Get daily orders count and revenue"""
        from collections import defaultdict
        from datetime import datetime
        
        start_date = parameters.get('startDate')
        end_date = parameters.get('endDate', datetime.now().strftime('%Y-%m-%d'))
        
        orders = db.get_all_orders()
        daily_data = defaultdict(lambda: {'count': 0, 'revenue': 0, 'paid': 0, 'unpaid': 0})
        
        for order in orders:
            if self.filter_by_date_range(order, start_date, end_date):
                date = order.get('createdDate', '')
                if date:
                    daily_data[date]['count'] += 1
                    daily_data[date]['revenue'] += float(order.get('totalPrice', 0))
                    
                    if order.get('paymentStatus', 'pending') == 'paid':
                        daily_data[date]['paid'] += 1
                    else:
                        daily_data[date]['unpaid'] += 1
        
        return dict(daily_data)
    
    def get_monthly_orders(self, parameters, user_context):
        """Get monthly orders count and revenue"""
        from collections import defaultdict
        from datetime import datetime
        
        year = parameters.get('year', datetime.now().year)
        
        orders = db.get_all_orders()
        monthly_data = defaultdict(lambda: {'count': 0, 'revenue': 0, 'paid': 0, 'unpaid': 0})
        
        for order in orders:
            created_date = order.get('createdDate', '')
            if created_date and created_date.startswith(str(year)):
                month = created_date[:7]  # YYYY-MM format
                
                monthly_data[month]['count'] += 1
                monthly_data[month]['revenue'] += float(order.get('totalPrice', 0))
                
                if order.get('paymentStatus', 'pending') == 'paid':
                    monthly_data[month]['paid'] += 1
                else:
                    monthly_data[month]['unpaid'] += 1
        
        return dict(monthly_data)
    
    def get_orders_revenue(self, parameters, user_context):
        """Get detailed orders revenue analysis"""
        from collections import defaultdict
        
        start_date = parameters.get('startDate')
        end_date = parameters.get('endDate')
        
        orders = db.get_all_orders()
        
        total_revenue = 0
        paid_revenue = 0
        unpaid_revenue = 0
        orders_count = 0
        
        revenue_by_status = defaultdict(float)
        revenue_by_category = defaultdict(float)
        
        for order in orders:
            if self.filter_by_date_range(order, start_date, end_date):
                revenue = float(order.get('totalPrice', 0))
                total_revenue += revenue
                orders_count += 1
                
                if order.get('paymentStatus', 'pending') == 'paid':
                    paid_revenue += revenue
                else:
                    unpaid_revenue += revenue
                
                status = order.get('status', 'UNKNOWN')
                revenue_by_status[status] += revenue
                
                category_id = order.get('categoryId', 0)
                revenue_by_category[f"Category {category_id}"] += revenue
        
        return {
            'totalRevenue': total_revenue,
            'paidRevenue': paid_revenue,
            'unpaidRevenue': unpaid_revenue,
            'ordersCount': orders_count,
            'averageOrderValue': total_revenue / orders_count if orders_count > 0 else 0,
            'revenueByStatus': dict(revenue_by_status),
            'revenueByCategory': dict(revenue_by_category)
        }
    
    # ==================== APPOINTMENTS ANALYTICS ====================
    
    def get_appointments_by_service(self, parameters, user_context):
        """Get appointments grouped by service"""
        from collections import defaultdict
        
        start_date = parameters.get('startDate')
        end_date = parameters.get('endDate')
        
        appointments = db.get_all_appointments()
        service_data = defaultdict(lambda: {'count': 0, 'revenue': 0, 'appointments': []})
        
        for appointment in appointments:
            if self.filter_by_date_range(appointment, start_date, end_date):
                service_id = appointment.get('serviceId', 0)
                service_key = f"Service {service_id}"
                
                service_data[service_key]['count'] += 1
                service_data[service_key]['revenue'] += float(appointment.get('price', 0))
                service_data[service_key]['appointments'].append({
                    'appointmentId': appointment.get('appointmentId'),
                    'status': appointment.get('status'),
                    'scheduledDate': appointment.get('scheduledDate'),
                    'price': float(appointment.get('price', 0))
                })
        
        return dict(service_data)
    
    def get_appointments_by_plan(self, parameters, user_context):
        """Get appointments grouped by plan"""
        from collections import defaultdict
        
        start_date = parameters.get('startDate')
        end_date = parameters.get('endDate')
        service_id = parameters.get('serviceId')
        
        appointments = db.get_all_appointments()
        plan_data = defaultdict(lambda: {'count': 0, 'revenue': 0})
        
        for appointment in appointments:
            if self.filter_by_date_range(appointment, start_date, end_date):
                if service_id and appointment.get('serviceId') != service_id:
                    continue
                    
                plan_id = appointment.get('planId', 0)
                plan_key = f"Plan {plan_id}"
                
                plan_data[plan_key]['count'] += 1
                plan_data[plan_key]['revenue'] += float(appointment.get('price', 0))
        
        return dict(plan_data)
    
    def get_appointments_by_status(self, parameters, user_context):
        """Get appointments grouped by status"""
        from collections import defaultdict
        
        start_date = parameters.get('startDate')
        end_date = parameters.get('endDate')
        
        appointments = db.get_all_appointments()
        status_data = defaultdict(lambda: {'count': 0, 'revenue': 0})
        
        for appointment in appointments:
            if self.filter_by_date_range(appointment, start_date, end_date):
                status = appointment.get('status', 'UNKNOWN')
                status_data[status]['count'] += 1
                status_data[status]['revenue'] += float(appointment.get('price', 0))
        
        return dict(status_data)
    
    def get_appointments_by_mechanic_analytics(self, parameters, user_context):
        """Get appointments grouped by assigned mechanic"""
        from collections import defaultdict
        
        start_date = parameters.get('startDate')
        end_date = parameters.get('endDate')
        
        appointments = db.get_all_appointments()
        mechanic_data = defaultdict(lambda: {'count': 0, 'revenue': 0, 'appointments': []})
        
        for appointment in appointments:
            if self.filter_by_date_range(appointment, start_date, end_date):
                mechanic_id = appointment.get('assignedMechanicId', 'Unassigned')
                
                mechanic_data[mechanic_id]['count'] += 1
                mechanic_data[mechanic_id]['revenue'] += float(appointment.get('price', 0))
                mechanic_data[mechanic_id]['appointments'].append({
                    'appointmentId': appointment.get('appointmentId'),
                    'status': appointment.get('status'),
                    'scheduledDate': appointment.get('scheduledDate'),
                    'price': float(appointment.get('price', 0))
                })
        
        return dict(mechanic_data)
    
    def get_daily_appointments(self, parameters, user_context):
        """Get daily appointments count and revenue"""
        from collections import defaultdict
        from datetime import datetime
        
        start_date = parameters.get('startDate')
        end_date = parameters.get('endDate', datetime.now().strftime('%Y-%m-%d'))
        
        appointments = db.get_all_appointments()
        daily_data = defaultdict(lambda: {'count': 0, 'revenue': 0, 'paid': 0, 'unpaid': 0})
        
        for appointment in appointments:
            if self.filter_by_date_range(appointment, start_date, end_date):
                date = appointment.get('createdDate', '')
                if date:
                    daily_data[date]['count'] += 1
                    daily_data[date]['revenue'] += float(appointment.get('price', 0))
                    
                    if appointment.get('paymentStatus', 'paid') == 'paid':
                        daily_data[date]['paid'] += 1
                    else:
                        daily_data[date]['unpaid'] += 1
        
        return dict(daily_data)
    
    def get_monthly_appointments(self, parameters, user_context):
        """Get monthly appointments count and revenue"""
        from collections import defaultdict
        from datetime import datetime
        
        year = parameters.get('year', datetime.now().year)
        
        appointments = db.get_all_appointments()
        monthly_data = defaultdict(lambda: {'count': 0, 'revenue': 0, 'paid': 0, 'unpaid': 0})
        
        for appointment in appointments:
            created_date = appointment.get('createdDate', '')
            if created_date and created_date.startswith(str(year)):
                month = created_date[:7]  # YYYY-MM format
                
                monthly_data[month]['count'] += 1
                monthly_data[month]['revenue'] += float(appointment.get('price', 0))
                
                if appointment.get('paymentStatus', 'pending') == 'paid':
                    monthly_data[month]['paid'] += 1
                else:
                    monthly_data[month]['unpaid'] += 1
        
        return dict(monthly_data)
    
    def get_appointments_revenue(self, parameters, user_context):
        """Get detailed appointments revenue analysis"""
        from collections import defaultdict
        
        start_date = parameters.get('startDate')
        end_date = parameters.get('endDate')
        
        appointments = db.get_all_appointments()
        
        total_revenue = 0
        paid_revenue = 0
        unpaid_revenue = 0
        appointments_count = 0
        
        revenue_by_status = defaultdict(float)
        revenue_by_service = defaultdict(float)
        
        for appointment in appointments:
            if self.filter_by_date_range(appointment, start_date, end_date):
                revenue = float(appointment.get('price', 0))
                total_revenue += revenue
                appointments_count += 1
                
                if appointment.get('paymentStatus', 'pending') == 'paid':
                    paid_revenue += revenue
                else:
                    unpaid_revenue += revenue
                
                status = appointment.get('status', 'UNKNOWN')
                revenue_by_status[status] += revenue
                
                service_id = appointment.get('serviceId', 0)
                revenue_by_service[f"Service {service_id}"] += revenue
        
        return {
            'totalRevenue': total_revenue,
            'paidRevenue': paid_revenue,
            'unpaidRevenue': unpaid_revenue,
            'appointmentsCount': appointments_count,
            'averageAppointmentValue': total_revenue / appointments_count if appointments_count > 0 else 0,
            'revenueByStatus': dict(revenue_by_status),
            'revenueByService': dict(revenue_by_service)
        }
    


class InquiryManager(DataAccessManager):
    """Manager for inquiry data operations"""
    
    def get_inquiry_by_id(self, inquiry_id):
        """Get single inquiry by ID"""
        if not inquiry_id:
            raise BusinessLogicError("Inquiry ID is required", 400)
        
        inquiry = db.get_inquiry(inquiry_id)
        if not inquiry:
            raise BusinessLogicError("Inquiry not found", 404)
        
        return inquiry
    
    def get_all_inquiries_with_filters(self, event):
        """Get all inquiries with optional filters"""
        inquiries = db.get_all_inquiries()
        
        # Apply query parameter filters (implementation would be moved from original function)
        inquiries = self._apply_inquiry_filters(inquiries, event)
        
        # Sort by creation date (newest first)
        inquiries.sort(key=lambda x: x.get('createdAt', 0), reverse=True)
        
        return inquiries
    
    def _apply_inquiry_filters(self, inquiries, event):
        """Apply query parameter filters to inquiries"""
        if not inquiries:
            return inquiries
        
        # Get filter parameters from query string
        status = req.get_query_param(event, 'status')
        start_date = req.get_query_param(event, 'startDate')
        end_date = req.get_query_param(event, 'endDate')
        user_id = req.get_query_param(event, 'userId')
        
        filtered_inquiries = inquiries
        
        # Filter by status
        if status:
            filtered_inquiries = [
                inquiry for inquiry in filtered_inquiries 
                if inquiry.get('status', '').upper() == status.upper()
            ]
        
        # Filter by userId
        if user_id:
            filtered_inquiries = [
                inquiry for inquiry in filtered_inquiries 
                if inquiry.get('userId', '') == user_id
            ]
        
        # Filter by date range
        if start_date:
            if end_date:
                # Filter by date range
                filtered_inquiries = [
                    inquiry for inquiry in filtered_inquiries 
                    if start_date <= inquiry.get('createdDate', '') <= end_date
                ]
            else:
                # Filter from start date onwards
                filtered_inquiries = [
                    inquiry for inquiry in filtered_inquiries 
                    if inquiry.get('createdDate', '') >= start_date
                ]
        elif end_date:
            # Filter up to end date
            filtered_inquiries = [
                inquiry for inquiry in filtered_inquiries 
                if inquiry.get('createdDate', '') <= end_date
            ]
        
        return filtered_inquiries


class InvoiceManager(DataAccessManager):
    """Manager for invoice data operations"""
    
    def get_invoices_by_date_range(self, start_date_str, end_date_str, limit_str='2000'):
        """
        Get invoices within date range
        
        Args:
            start_date_str: Start timestamp string
            end_date_str: End timestamp string  
            limit_str: Limit parameter string
            
        Returns:
            list: Invoices within date range
        """
        # Validate timestamp range (max 90 days)
        max_range = 90 * 24 * 60 * 60  # 90 days in seconds
        start_timestamp, end_timestamp = self.validate_timestamp_range(
            start_date_str, end_date_str, max_range
        )
        
        # Validate limit
        try:
            limit = int(limit_str)
        except (ValueError, TypeError):
            limit = 2000
        
        # Get invoices from database
        invoices = db.get_invoices_by_date_range(start_timestamp, end_timestamp, limit)
        return invoices


class PriceManager(DataAccessManager):
    """Manager for price data operations"""
    
    def get_all_prices(self):
        """Get all item and service prices"""
        item_prices = db.get_all_item_prices()
        service_prices = db.get_all_service_prices()
        
        return {
            'item_prices': item_prices,
            'service_prices': service_prices,
            'timestamp': datetime.utcnow().isoformat()
        }


class UserManager(DataAccessManager):
    """Manager for user data operations"""
    
    def get_all_users(self):
        """Get all customer and staff users"""
        customer_users = db.get_all_users()
        staff_users = db.get_all_staff_records()
        
        return {
            'customer_users': customer_users,
            'staff_users': staff_users
        }


class MessageManager(DataAccessManager):
    """Manager for message data operations"""
    
    def get_user_messages(self, client_id):
        """
        Get all messages for a user
        
        Args:
            client_id: User ID to get messages for
            
        Returns:
            list: Sorted messages for the user
        """
        if not client_id:
            raise BusinessLogicError("clientId is required", 400)
        
        # Validate client is not staff
        if db.get_staff_record(client_id):
            raise BusinessLogicError("Cannot retrieve messages for staff userId", 400)
        
        # Validate user exists
        if not db.get_user_record(client_id):
            raise BusinessLogicError(f"User with userId {client_id} does not exist", 404)
        
        # Get messages where user is sender or receiver
        sender_messages = db.get_messages_by_index(
            index_name='senderId-index', 
            key_name='senderId', 
            key_value=client_id
        )
        receiver_messages = db.get_messages_by_index(
            index_name='receiverId-index', 
            key_name='receiverId', 
            key_value=client_id
        )
        
        all_messages = sender_messages + receiver_messages
        
        # Sort by creation date (newest first)
        sorted_messages = sorted(
            all_messages, 
            key=lambda x: int(x.get('createdAt', 0)), 
            reverse=True
        )
        
        return sorted_messages


class StaffRoleManager(DataAccessManager):
    """Manager for staff role operations"""
    
    def get_staff_roles(self, email, shared_key, required_shared_key):
        """
        Get staff roles by email with shared key authentication
        
        Args:
            email: Staff email
            shared_key: Provided shared key
            required_shared_key: Expected shared key
            
        Returns:
            list: Staff roles
        """
        # Validate shared key authentication
        if not email or not shared_key:
            raise BusinessLogicError("Email and sharedKey are required", 400)
        
        if shared_key != required_shared_key:
            raise BusinessLogicError("Invalid sharedKey provided", 401)
        
        # Get staff record
        staff_record = db.get_staff_record(email)
        if not staff_record:
            raise BusinessLogicError(f"No staff record found for email: {email}", 404)
        
        return staff_record.get('roles', [])


def get_analytics_manager():
    """Factory function to get AnalyticsManager instance"""
    return AnalyticsManager()


def get_inquiry_manager():
    """Factory function to get InquiryManager instance"""
    return InquiryManager()


def get_invoice_manager():
    """Factory function to get InvoiceManager instance"""
    return InvoiceManager()


def get_price_manager():
    """Factory function to get PriceManager instance"""
    return PriceManager()


def get_user_manager():
    """Factory function to get UserManager instance"""
    return UserManager()


def get_message_manager():
    """Factory function to get MessageManager instance"""
    return MessageManager()


def get_staff_role_manager():
    """Factory function to get StaffRoleManager instance"""
    return StaffRoleManager()
