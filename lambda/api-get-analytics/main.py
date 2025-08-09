from datetime import datetime, timedelta
from collections import defaultdict, Counter
import db_utils as db
import response_utils as resp
import request_utils as req

def lambda_handler(event, context):
    """
    Main lambda handler for analytics queries
    Supports various query types for generating reports, graphs, and tables
    """
    try:
        # Get staff user email from the authorizer context
        staff_user_email = req.get_staff_user_email(event)
        
        # Get query parameters
        query_type = req.get_body_param(event, 'queryType')
        parameters = req.get_body_param(event, 'parameters') or {}
        
        if not query_type:
            return resp.error_response("Query type is required")
        
        # Determine user context
        if staff_user_email:
            # Staff user access
            staff_user_record = db.get_staff_record(staff_user_email)
            if not staff_user_record:
                return resp.error_response(f"No staff record found for email: {staff_user_email}", 404)
            
            staff_roles = staff_user_record.get('roles', [])
            staff_user_id = staff_user_record.get('userId')
            
            # Check if user has analytics access (assuming CUSTOMER_SUPPORT, CLERK, or ADMIN roles can access analytics)
            if not any(role in staff_roles for role in ['CUSTOMER_SUPPORT', 'CLERK', 'ADMIN', 'MANAGER']):
                return resp.error_response("Unauthorized: Analytics access requires appropriate staff role", 403)
            
            user_context = {
                'user_id': staff_user_id,
                'user_email': staff_user_email,
                'is_staff': True,
                'roles': staff_roles
            }
        else:
            return resp.error_response("Unauthorized: Analytics access requires staff authentication", 401)
        
        # Route to appropriate query handler
        result = route_query(query_type, parameters, user_context)
        
        return resp.success_response({
            'queryType': query_type,
            'data': resp.convert_decimal(result),
            'timestamp': datetime.now().isoformat()
        })
        
    except ValueError as e:
        return resp.error_response(str(e), 400)
    except Exception as e:
        print(f"Error in analytics query: {str(e)}")
        return resp.error_response(f"Internal server error: {str(e)}", 500)

def route_query(query_type, parameters, user_context):
    """Route the query to the appropriate handler function"""
    
    query_handlers = {
        # Orders analytics
        'orders_by_category': get_orders_by_category,
        'orders_by_item': get_orders_by_item,
        'orders_by_status': get_orders_by_status,
        'orders_by_mechanic': get_orders_by_mechanic,
        'daily_orders': get_daily_orders,
        'monthly_orders': get_monthly_orders,
        'orders_revenue': get_orders_revenue,
        
        # Appointments analytics
        'appointments_by_service': get_appointments_by_service,
        'appointments_by_plan': get_appointments_by_plan,
        'appointments_by_status': get_appointments_by_status,
        'appointments_by_mechanic': get_appointments_by_mechanic_analytics,
        'daily_appointments': get_daily_appointments,
        'monthly_appointments': get_monthly_appointments,
        'appointments_revenue': get_appointments_revenue,
        
        # Combined analytics
        'daily_income': get_daily_income,
        'monthly_income': get_monthly_income,
        'yearly_income': get_yearly_income,
        'revenue_breakdown': get_revenue_breakdown,
        
        # Staff analytics
        'staff_performance': get_staff_performance,
        'mechanic_workload': get_mechanic_workload,
        
        # Customer analytics
        'customer_activity': get_customer_activity,
        'top_customers': get_top_customers,
        
        # Trend analytics
        'daily_trends': get_daily_trends,
        'monthly_trends': get_monthly_trends,
        'service_popularity': get_service_popularity,
        'item_popularity': get_item_popularity,
        
        # Summary analytics
        'dashboard_summary': get_dashboard_summary,
        'financial_summary': get_financial_summary,
    }
    
    handler = query_handlers.get(query_type)
    if not handler:
        raise ValueError(f"Unsupported query type: {query_type}")
    
    return handler(parameters, user_context)

# ==================== ORDERS ANALYTICS ====================

def get_orders_by_category(parameters, user_context):
    """Get orders grouped by category"""
    start_date = parameters.get('startDate')
    end_date = parameters.get('endDate')
    
    orders = db.get_all_orders()
    category_data = defaultdict(lambda: {'count': 0, 'revenue': 0, 'items': []})
    
    for order in orders:
        if filter_by_date_range(order, start_date, end_date):
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

def get_orders_by_item(parameters, user_context):
    """Get orders grouped by item"""
    start_date = parameters.get('startDate')
    end_date = parameters.get('endDate')
    category_id = parameters.get('categoryId')
    
    orders = db.get_all_orders()
    item_data = defaultdict(lambda: {'count': 0, 'revenue': 0, 'totalQuantity': 0})
    
    for order in orders:
        if filter_by_date_range(order, start_date, end_date):
            if category_id and order.get('categoryId') != category_id:
                continue
                
            item_id = order.get('itemId', 0)
            item_key = f"Item {item_id}"
            
            item_data[item_key]['count'] += 1
            item_data[item_key]['revenue'] += float(order.get('totalPrice', 0))
            item_data[item_key]['totalQuantity'] += order.get('quantity', 0)
    
    return dict(item_data)

def get_orders_by_status(parameters, user_context):
    """Get orders grouped by status"""
    start_date = parameters.get('startDate')
    end_date = parameters.get('endDate')
    
    orders = db.get_all_orders()
    status_data = defaultdict(lambda: {'count': 0, 'revenue': 0})
    
    for order in orders:
        if filter_by_date_range(order, start_date, end_date):
            status = order.get('status', 'UNKNOWN')
            status_data[status]['count'] += 1
            status_data[status]['revenue'] += float(order.get('totalPrice', 0))
    
    return dict(status_data)

def get_orders_by_mechanic(parameters, user_context):
    """Get orders grouped by assigned mechanic"""
    start_date = parameters.get('startDate')
    end_date = parameters.get('endDate')
    
    orders = db.get_all_orders()
    mechanic_data = defaultdict(lambda: {'count': 0, 'revenue': 0, 'orders': []})
    
    for order in orders:
        if filter_by_date_range(order, start_date, end_date):
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

def get_daily_orders(parameters, user_context):
    """Get daily orders count and revenue"""
    start_date = parameters.get('startDate')
    end_date = parameters.get('endDate', datetime.now().strftime('%Y-%m-%d'))
    
    orders = db.get_all_orders()
    daily_data = defaultdict(lambda: {'count': 0, 'revenue': 0, 'paid': 0, 'unpaid': 0})
    
    for order in orders:
        if filter_by_date_range(order, start_date, end_date):
            date = order.get('createdDate', '')
            if date:
                daily_data[date]['count'] += 1
                daily_data[date]['revenue'] += float(order.get('totalPrice', 0))
                
                if order.get('paymentStatus', 'pending') == 'paid':
                    daily_data[date]['paid'] += 1
                else:
                    daily_data[date]['unpaid'] += 1
    
    return dict(daily_data)

def get_monthly_orders(parameters, user_context):
    """Get monthly orders count and revenue"""
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

def get_orders_revenue(parameters, user_context):
    """Get detailed orders revenue analysis"""
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
        if filter_by_date_range(order, start_date, end_date):
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

def get_appointments_by_service(parameters, user_context):
    """Get appointments grouped by service"""
    start_date = parameters.get('startDate')
    end_date = parameters.get('endDate')
    
    appointments = db.get_all_appointments()
    service_data = defaultdict(lambda: {'count': 0, 'revenue': 0, 'appointments': []})
    
    for appointment in appointments:
        if filter_by_date_range(appointment, start_date, end_date):
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

def get_appointments_by_plan(parameters, user_context):
    """Get appointments grouped by plan"""
    start_date = parameters.get('startDate')
    end_date = parameters.get('endDate')
    service_id = parameters.get('serviceId')
    
    appointments = db.get_all_appointments()
    plan_data = defaultdict(lambda: {'count': 0, 'revenue': 0})
    
    for appointment in appointments:
        if filter_by_date_range(appointment, start_date, end_date):
            if service_id and appointment.get('serviceId') != service_id:
                continue
                
            plan_id = appointment.get('planId', 0)
            plan_key = f"Plan {plan_id}"
            
            plan_data[plan_key]['count'] += 1
            plan_data[plan_key]['revenue'] += float(appointment.get('price', 0))
    
    return dict(plan_data)

def get_appointments_by_status(parameters, user_context):
    """Get appointments grouped by status"""
    start_date = parameters.get('startDate')
    end_date = parameters.get('endDate')
    
    appointments = db.get_all_appointments()
    status_data = defaultdict(lambda: {'count': 0, 'revenue': 0})
    
    for appointment in appointments:
        if filter_by_date_range(appointment, start_date, end_date):
            status = appointment.get('status', 'UNKNOWN')
            status_data[status]['count'] += 1
            status_data[status]['revenue'] += float(appointment.get('price', 0))
    
    return dict(status_data)

def get_appointments_by_mechanic_analytics(parameters, user_context):
    """Get appointments grouped by assigned mechanic"""
    start_date = parameters.get('startDate')
    end_date = parameters.get('endDate')
    
    appointments = db.get_all_appointments()
    mechanic_data = defaultdict(lambda: {'count': 0, 'revenue': 0, 'appointments': []})
    
    for appointment in appointments:
        if filter_by_date_range(appointment, start_date, end_date):
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

def get_daily_appointments(parameters, user_context):
    """Get daily appointments count and revenue"""
    start_date = parameters.get('startDate')
    end_date = parameters.get('endDate', datetime.now().strftime('%Y-%m-%d'))
    
    appointments = db.get_all_appointments()
    daily_data = defaultdict(lambda: {'count': 0, 'revenue': 0, 'paid': 0, 'unpaid': 0})
    
    for appointment in appointments:
        if filter_by_date_range(appointment, start_date, end_date):
            date = appointment.get('createdDate', '')
            if date:
                daily_data[date]['count'] += 1
                daily_data[date]['revenue'] += float(appointment.get('price', 0))
                
                if appointment.get('paymentStatus', 'pending') == 'paid':
                    daily_data[date]['paid'] += 1
                else:
                    daily_data[date]['unpaid'] += 1
    
    return dict(daily_data)

def get_monthly_appointments(parameters, user_context):
    """Get monthly appointments count and revenue"""
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

def get_appointments_revenue(parameters, user_context):
    """Get detailed appointments revenue analysis"""
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
        if filter_by_date_range(appointment, start_date, end_date):
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

# ==================== COMBINED ANALYTICS ====================

def get_daily_income(parameters, user_context):
    """Get combined daily income from orders and appointments"""
    start_date = parameters.get('startDate')
    end_date = parameters.get('endDate', datetime.now().strftime('%Y-%m-%d'))
    
    orders = db.get_all_orders()
    appointments = db.get_all_appointments()
    
    daily_income = defaultdict(lambda: {
        'orders': {'count': 0, 'revenue': 0, 'paid': 0, 'unpaid': 0},
        'appointments': {'count': 0, 'revenue': 0, 'paid': 0, 'unpaid': 0},
        'total': {'count': 0, 'revenue': 0, 'paid': 0, 'unpaid': 0}
    })
    
    # Process orders
    for order in orders:
        if filter_by_date_range(order, start_date, end_date):
            date = order.get('createdDate', '')
            if date:
                revenue = float(order.get('totalPrice', 0))
                daily_income[date]['orders']['count'] += 1
                daily_income[date]['orders']['revenue'] += revenue
                daily_income[date]['total']['count'] += 1
                daily_income[date]['total']['revenue'] += revenue
                
                if order.get('paymentStatus', 'pending') == 'paid':
                    daily_income[date]['orders']['paid'] += 1
                    daily_income[date]['total']['paid'] += 1
                else:
                    daily_income[date]['orders']['unpaid'] += 1
                    daily_income[date]['total']['unpaid'] += 1
    
    # Process appointments
    for appointment in appointments:
        if filter_by_date_range(appointment, start_date, end_date):
            date = appointment.get('createdDate', '')
            if date:
                revenue = float(appointment.get('price', 0))
                daily_income[date]['appointments']['count'] += 1
                daily_income[date]['appointments']['revenue'] += revenue
                daily_income[date]['total']['count'] += 1
                daily_income[date]['total']['revenue'] += revenue
                
                if appointment.get('paymentStatus', 'pending') == 'paid':
                    daily_income[date]['appointments']['paid'] += 1
                    daily_income[date]['total']['paid'] += 1
                else:
                    daily_income[date]['appointments']['unpaid'] += 1
                    daily_income[date]['total']['unpaid'] += 1
    
    return dict(daily_income)

def get_monthly_income(parameters, user_context):
    """Get combined monthly income from orders and appointments"""
    year = parameters.get('year', datetime.now().year)
    
    orders = db.get_all_orders()
    appointments = db.get_all_appointments()
    
    monthly_income = defaultdict(lambda: {
        'orders': {'count': 0, 'revenue': 0, 'paid': 0, 'unpaid': 0},
        'appointments': {'count': 0, 'revenue': 0, 'paid': 0, 'unpaid': 0},
        'total': {'count': 0, 'revenue': 0, 'paid': 0, 'unpaid': 0}
    })
    
    # Process orders
    for order in orders:
        created_date = order.get('createdDate', '')
        if created_date and created_date.startswith(str(year)):
            month = created_date[:7]  # YYYY-MM format
            revenue = float(order.get('totalPrice', 0))
            
            monthly_income[month]['orders']['count'] += 1
            monthly_income[month]['orders']['revenue'] += revenue
            monthly_income[month]['total']['count'] += 1
            monthly_income[month]['total']['revenue'] += revenue
            
            if order.get('paymentStatus', 'pending') == 'paid':
                monthly_income[month]['orders']['paid'] += 1
                monthly_income[month]['total']['paid'] += 1
            else:
                monthly_income[month]['orders']['unpaid'] += 1
                monthly_income[month]['total']['unpaid'] += 1
    
    # Process appointments
    for appointment in appointments:
        created_date = appointment.get('createdDate', '')
        if created_date and created_date.startswith(str(year)):
            month = created_date[:7]  # YYYY-MM format
            revenue = float(appointment.get('price', 0))
            
            monthly_income[month]['appointments']['count'] += 1
            monthly_income[month]['appointments']['revenue'] += revenue
            monthly_income[month]['total']['count'] += 1
            monthly_income[month]['total']['revenue'] += revenue
            
            if appointment.get('paymentStatus', 'pending') == 'paid':
                monthly_income[month]['appointments']['paid'] += 1
                monthly_income[month]['total']['paid'] += 1
            else:
                monthly_income[month]['appointments']['unpaid'] += 1
                monthly_income[month]['total']['unpaid'] += 1
    
    return dict(monthly_income)

def get_yearly_income(parameters, user_context):
    """Get yearly income summary"""
    start_year = parameters.get('startYear', datetime.now().year - 2)
    end_year = parameters.get('endYear', datetime.now().year)
    
    orders = db.get_all_orders()
    appointments = db.get_all_appointments()
    
    yearly_income = defaultdict(lambda: {
        'orders': {'count': 0, 'revenue': 0},
        'appointments': {'count': 0, 'revenue': 0},
        'total': {'count': 0, 'revenue': 0}
    })
    
    # Process orders
    for order in orders:
        created_date = order.get('createdDate', '')
        if created_date:
            year = int(created_date[:4])
            if start_year <= year <= end_year:
                revenue = float(order.get('totalPrice', 0))
                yearly_income[year]['orders']['count'] += 1
                yearly_income[year]['orders']['revenue'] += revenue
                yearly_income[year]['total']['count'] += 1
                yearly_income[year]['total']['revenue'] += revenue
    
    # Process appointments
    for appointment in appointments:
        created_date = appointment.get('createdDate', '')
        if created_date:
            year = int(created_date[:4])
            if start_year <= year <= end_year:
                revenue = float(appointment.get('price', 0))
                yearly_income[year]['appointments']['count'] += 1
                yearly_income[year]['appointments']['revenue'] += revenue
                yearly_income[year]['total']['count'] += 1
                yearly_income[year]['total']['revenue'] += revenue
    
    return dict(yearly_income)

def get_revenue_breakdown(parameters, user_context):
    """Get detailed revenue breakdown"""
    start_date = parameters.get('startDate')
    end_date = parameters.get('endDate')
    
    orders = db.get_all_orders()
    appointments = db.get_all_appointments()
    
    breakdown = {
        'orders': {
            'total': 0,
            'paid': 0,
            'unpaid': 0,
            'byCategory': defaultdict(float),
            'byStatus': defaultdict(float)
        },
        'appointments': {
            'total': 0,
            'paid': 0,
            'unpaid': 0,
            'byService': defaultdict(float),
            'byStatus': defaultdict(float)
        },
        'summary': {
            'totalRevenue': 0,
            'ordersPercentage': 0,
            'appointmentsPercentage': 0
        }
    }
    
    # Process orders
    for order in orders:
        if filter_by_date_range(order, start_date, end_date):
            revenue = float(order.get('totalPrice', 0))
            breakdown['orders']['total'] += revenue
            
            if order.get('paymentStatus', 'pending') == 'paid':
                breakdown['orders']['paid'] += revenue
            else:
                breakdown['orders']['unpaid'] += revenue
            
            category_id = order.get('categoryId', 0)
            breakdown['orders']['byCategory'][f"Category {category_id}"] += revenue
            
            status = order.get('status', 'UNKNOWN')
            breakdown['orders']['byStatus'][status] += revenue
    
    # Process appointments
    for appointment in appointments:
        if filter_by_date_range(appointment, start_date, end_date):
            revenue = float(appointment.get('price', 0))
            breakdown['appointments']['total'] += revenue
            
            if appointment.get('paymentStatus', 'pending') == 'paid':
                breakdown['appointments']['paid'] += revenue
            else:
                breakdown['appointments']['unpaid'] += revenue
            
            service_id = appointment.get('serviceId', 0)
            breakdown['appointments']['byService'][f"Service {service_id}"] += revenue
            
            status = appointment.get('status', 'UNKNOWN')
            breakdown['appointments']['byStatus'][status] += revenue
    
    # Calculate summary
    total_revenue = breakdown['orders']['total'] + breakdown['appointments']['total']
    breakdown['summary']['totalRevenue'] = total_revenue
    
    if total_revenue > 0:
        breakdown['summary']['ordersPercentage'] = (breakdown['orders']['total'] / total_revenue) * 100
        breakdown['summary']['appointmentsPercentage'] = (breakdown['appointments']['total'] / total_revenue) * 100
    
    # Convert defaultdicts to regular dicts
    breakdown['orders']['byCategory'] = dict(breakdown['orders']['byCategory'])
    breakdown['orders']['byStatus'] = dict(breakdown['orders']['byStatus'])
    breakdown['appointments']['byService'] = dict(breakdown['appointments']['byService'])
    breakdown['appointments']['byStatus'] = dict(breakdown['appointments']['byStatus'])
    
    return breakdown

# ==================== STAFF ANALYTICS ====================

def get_staff_performance(parameters, user_context):
    """Get staff performance analytics"""
    start_date = parameters.get('startDate')
    end_date = parameters.get('endDate')
    
    staff_records = db.get_all_staff_records()
    orders = db.get_all_orders()
    appointments = db.get_all_appointments()
    
    staff_performance = {}
    
    for staff in staff_records:
        staff_id = staff.get('userId', '')
        staff_email = staff.get('userEmail', '')
        staff_name = staff.get('userName', staff_email)
        
        performance = {
            'staffInfo': {
                'userId': staff_id,
                'email': staff_email,
                'name': staff_name,
                'roles': staff.get('roles', [])
            },
            'orders': {'count': 0, 'revenue': 0},
            'appointments': {'count': 0, 'revenue': 0},
            'total': {'count': 0, 'revenue': 0}
        }
        
        # Count assigned orders
        for order in orders:
            if (order.get('assignedMechanicId') == staff_id and 
                filter_by_date_range(order, start_date, end_date)):
                performance['orders']['count'] += 1
                performance['orders']['revenue'] += float(order.get('totalPrice', 0))
        
        # Count assigned appointments
        for appointment in appointments:
            if (appointment.get('assignedMechanicId') == staff_id and 
                filter_by_date_range(appointment, start_date, end_date)):
                performance['appointments']['count'] += 1
                performance['appointments']['revenue'] += float(appointment.get('price', 0))
        
        # Calculate totals
        performance['total']['count'] = performance['orders']['count'] + performance['appointments']['count']
        performance['total']['revenue'] = performance['orders']['revenue'] + performance['appointments']['revenue']
        
        staff_performance[staff_id] = performance
    
    return staff_performance

def get_mechanic_workload(parameters, user_context):
    """Get mechanic workload distribution"""
    start_date = parameters.get('startDate')
    end_date = parameters.get('endDate')
    
    mechanics = db.get_all_mechanic_records()
    orders = db.get_all_orders()
    appointments = db.get_all_appointments()
    
    workload = {}
    
    for mechanic in mechanics:
        mechanic_id = mechanic.get('userId', '')
        
        workload[mechanic_id] = {
            'mechanicInfo': {
                'userId': mechanic_id,
                'email': mechanic.get('userEmail', ''),
                'name': mechanic.get('userName', '')
            },
            'assigned': {'orders': 0, 'appointments': 0},
            'completed': {'orders': 0, 'appointments': 0},
            'pending': {'orders': 0, 'appointments': 0},
            'revenue': {'orders': 0, 'appointments': 0}
        }
        
        # Count orders
        for order in orders:
            if (order.get('assignedMechanicId') == mechanic_id and 
                filter_by_date_range(order, start_date, end_date)):
                workload[mechanic_id]['assigned']['orders'] += 1
                workload[mechanic_id]['revenue']['orders'] += float(order.get('totalPrice', 0))
                
                status = order.get('status', '').upper()
                if status == 'COMPLETED':
                    workload[mechanic_id]['completed']['orders'] += 1
                elif status in ['PENDING', 'IN_PROGRESS']:
                    workload[mechanic_id]['pending']['orders'] += 1
        
        # Count appointments
        for appointment in appointments:
            if (appointment.get('assignedMechanicId') == mechanic_id and 
                filter_by_date_range(appointment, start_date, end_date)):
                workload[mechanic_id]['assigned']['appointments'] += 1
                workload[mechanic_id]['revenue']['appointments'] += float(appointment.get('price', 0))
                
                status = appointment.get('status', '').upper()
                if status == 'COMPLETED':
                    workload[mechanic_id]['completed']['appointments'] += 1
                elif status in ['PENDING', 'CONFIRMED', 'IN_PROGRESS']:
                    workload[mechanic_id]['pending']['appointments'] += 1
    
    return workload

# ==================== CUSTOMER ANALYTICS ====================

def get_customer_activity(parameters, user_context):
    """Get customer activity analytics"""
    start_date = parameters.get('startDate')
    end_date = parameters.get('endDate')
    
    users = db.get_all_users()
    orders = db.get_all_orders()
    appointments = db.get_all_appointments()
    
    customer_activity = {}
    
    for user in users:
        user_id_key = user.get('userId', '')
        
        activity = {
            'userInfo': {
                'userId': user_id_key,
                'email': user.get('userEmail', ''),
                'name': user.get('userName', ''),
                'assignedTo': user.get('assignedTo', '')
            },
            'orders': {'count': 0, 'totalSpent': 0},
            'appointments': {'count': 0, 'totalSpent': 0},
            'total': {'count': 0, 'totalSpent': 0},
            'lastActivity': None
        }
        
        last_activity_date = None
        
        # Count user's orders
        for order in orders:
            if (order.get('createdUserId') == user_id_key and 
                filter_by_date_range(order, start_date, end_date)):
                activity['orders']['count'] += 1
                activity['orders']['totalSpent'] += float(order.get('totalPrice', 0))
                
                order_date = order.get('createdDate', '')
                if order_date and (not last_activity_date or order_date > last_activity_date):
                    last_activity_date = order_date
        
        # Count user's appointments
        for appointment in appointments:
            if (appointment.get('createdUserId') == user_id_key and 
                filter_by_date_range(appointment, start_date, end_date)):
                activity['appointments']['count'] += 1
                activity['appointments']['totalSpent'] += float(appointment.get('price', 0))
                
                appointment_date = appointment.get('createdDate', '')
                if appointment_date and (not last_activity_date or appointment_date > last_activity_date):
                    last_activity_date = appointment_date
        
        # Calculate totals
        activity['total']['count'] = activity['orders']['count'] + activity['appointments']['count']
        activity['total']['totalSpent'] = activity['orders']['totalSpent'] + activity['appointments']['totalSpent']
        activity['lastActivity'] = last_activity_date
        
        # Only include customers with activity
        if activity['total']['count'] > 0:
            customer_activity[user_id_key] = activity
    
    return customer_activity

def get_top_customers(parameters, user_context):
    """Get top customers by spending or activity"""
    limit = parameters.get('limit', 10)
    sort_by = parameters.get('sortBy', 'totalSpent')  # totalSpent, totalCount, lastActivity
    start_date = parameters.get('startDate')
    end_date = parameters.get('endDate')
    
    customer_activity = get_customer_activity(parameters, user_context)
    
    # Sort customers based on the specified criteria
    if sort_by == 'totalSpent':
        sorted_customers = sorted(
            customer_activity.items(),
            key=lambda x: x[1]['total']['totalSpent'],
            reverse=True
        )
    elif sort_by == 'totalCount':
        sorted_customers = sorted(
            customer_activity.items(),
            key=lambda x: x[1]['total']['count'],
            reverse=True
        )
    elif sort_by == 'lastActivity':
        sorted_customers = sorted(
            customer_activity.items(),
            key=lambda x: x[1]['lastActivity'] or '1900-01-01',
            reverse=True
        )
    else:
        sorted_customers = list(customer_activity.items())
    
    # Return top customers
    top_customers = dict(sorted_customers[:limit])
    
    return {
        'topCustomers': top_customers,
        'sortBy': sort_by,
        'limit': limit,
        'totalCustomers': len(customer_activity)
    }

# ==================== TREND ANALYTICS ====================

def get_daily_trends(parameters, user_context):
    """Get daily trends for the last 30 days"""
    days = parameters.get('days', 30)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)
    
    # Override parameters for daily income function
    trend_params = {
        'startDate': start_date.strftime('%Y-%m-%d'),
        'endDate': end_date.strftime('%Y-%m-%d')
    }
    
    daily_data = get_daily_income(trend_params, user_context)
    
    # Fill in missing dates with zero values
    trends = {}
    current_date = start_date
    
    while current_date <= end_date:
        date_str = current_date.strftime('%Y-%m-%d')
        if date_str in daily_data:
            trends[date_str] = daily_data[date_str]
        else:
            trends[date_str] = {
                'orders': {'count': 0, 'revenue': 0, 'paid': 0, 'unpaid': 0},
                'appointments': {'count': 0, 'revenue': 0, 'paid': 0, 'unpaid': 0},
                'total': {'count': 0, 'revenue': 0, 'paid': 0, 'unpaid': 0}
            }
        current_date += timedelta(days=1)
    
    return trends

def get_monthly_trends(parameters, user_context):
    """Get monthly trends for the last 12 months"""
    months = parameters.get('months', 12)
    
    trends = {}
    current_date = datetime.now()
    
    for i in range(months):
        # Calculate the month/year for each iteration
        target_date = current_date - timedelta(days=30 * i)
        year = target_date.year
        month_key = target_date.strftime('%Y-%m')
        
        # Get monthly data for this year
        monthly_data = get_monthly_income({'year': year}, user_context)
        
        if month_key in monthly_data:
            trends[month_key] = monthly_data[month_key]
        else:
            trends[month_key] = {
                'orders': {'count': 0, 'revenue': 0, 'paid': 0, 'unpaid': 0},
                'appointments': {'count': 0, 'revenue': 0, 'paid': 0, 'unpaid': 0},
                'total': {'count': 0, 'revenue': 0, 'paid': 0, 'unpaid': 0}
            }
    
    return trends

def get_service_popularity(parameters, user_context):
    """Get service popularity rankings"""
    start_date = parameters.get('startDate')
    end_date = parameters.get('endDate')
    
    appointments = db.get_all_appointments()
    service_stats = defaultdict(lambda: {
        'count': 0,
        'revenue': 0,
        'completedCount': 0,
        'averageRating': 0,
        'plans': defaultdict(int)
    })
    
    for appointment in appointments:
        if filter_by_date_range(appointment, start_date, end_date):
            service_id = appointment.get('serviceId', 0)
            plan_id = appointment.get('planId', 0)
            
            service_stats[service_id]['count'] += 1
            service_stats[service_id]['revenue'] += float(appointment.get('price', 0))
            service_stats[service_id]['plans'][plan_id] += 1
            
            if appointment.get('status', '').upper() == 'COMPLETED':
                service_stats[service_id]['completedCount'] += 1
    
    # Convert to regular dict and sort by popularity
    popularity_ranking = {}
    for service_id, stats in service_stats.items():
        stats['plans'] = dict(stats['plans'])
        stats['completionRate'] = (
            (stats['completedCount'] / stats['count'] * 100) 
            if stats['count'] > 0 else 0
        )
        popularity_ranking[f"Service {service_id}"] = stats
    
    # Sort by count (popularity)
    sorted_services = sorted(
        popularity_ranking.items(),
        key=lambda x: x[1]['count'],
        reverse=True
    )
    
    return {
        'serviceRanking': dict(sorted_services),
        'totalServices': len(service_stats)
    }

def get_item_popularity(parameters, user_context):
    """Get item popularity rankings"""
    start_date = parameters.get('startDate')
    end_date = parameters.get('endDate')
    
    orders = db.get_all_orders()
    item_stats = defaultdict(lambda: {
        'count': 0,
        'revenue': 0,
        'totalQuantity': 0,
        'completedCount': 0,
        'categories': defaultdict(int)
    })
    
    for order in orders:
        if filter_by_date_range(order, start_date, end_date):
            item_id = order.get('itemId', 0)
            category_id = order.get('categoryId', 0)
            quantity = order.get('quantity', 0)
            
            item_stats[item_id]['count'] += 1
            item_stats[item_id]['revenue'] += float(order.get('totalPrice', 0))
            item_stats[item_id]['totalQuantity'] += quantity
            item_stats[item_id]['categories'][category_id] += 1
            
            if order.get('status', '').upper() == 'COMPLETED':
                item_stats[item_id]['completedCount'] += 1
    
    # Convert to regular dict and sort by popularity
    popularity_ranking = {}
    for item_id, stats in item_stats.items():
        stats['categories'] = dict(stats['categories'])
        stats['completionRate'] = (
            (stats['completedCount'] / stats['count'] * 100) 
            if stats['count'] > 0 else 0
        )
        stats['averageQuantityPerOrder'] = (
            stats['totalQuantity'] / stats['count'] 
            if stats['count'] > 0 else 0
        )
        popularity_ranking[f"Item {item_id}"] = stats
    
    # Sort by total quantity (popularity)
    sorted_items = sorted(
        popularity_ranking.items(),
        key=lambda x: x[1]['totalQuantity'],
        reverse=True
    )
    
    return {
        'itemRanking': dict(sorted_items),
        'totalItems': len(item_stats)
    }

# ==================== SUMMARY ANALYTICS ====================

def get_dashboard_summary(parameters, user_context):
    """Get dashboard summary with key metrics"""
    # Default to current month if no date range specified
    today = datetime.now()
    start_date = parameters.get('startDate', today.replace(day=1).strftime('%Y-%m-%d'))
    end_date = parameters.get('endDate', today.strftime('%Y-%m-%d'))
    
    orders = db.get_all_orders()
    appointments = db.get_all_appointments()
    users = db.get_all_users()
    staff = db.get_all_staff_records()
    
    summary = {
        'period': {
            'startDate': start_date,
            'endDate': end_date
        },
        'orders': {
            'total': 0,
            'completed': 0,
            'pending': 0,
            'revenue': 0,
            'paidRevenue': 0
        },
        'appointments': {
            'total': 0,
            'completed': 0,
            'pending': 0,
            'revenue': 0,
            'paidRevenue': 0
        },
        'customers': {
            'total': len(users),
            'active': 0,
            'newThisPeriod': 0
        },
        'staff': {
            'total': len(staff),
            'mechanics': len([s for s in staff if 'MECHANIC' in s.get('roles', [])]),
            'active': 0
        },
        'revenue': {
            'total': 0,
            'paid': 0,
            'unpaid': 0,
            'ordersPercentage': 0,
            'appointmentsPercentage': 0
        }
    }
    
    # Process orders
    for order in orders:
        if filter_by_date_range(order, start_date, end_date):
            summary['orders']['total'] += 1
            revenue = float(order.get('totalPrice', 0))
            summary['orders']['revenue'] += revenue
            
            status = order.get('status', '').upper()
            if status == 'COMPLETED':
                summary['orders']['completed'] += 1
            elif status in ['PENDING', 'IN_PROGRESS']:
                summary['orders']['pending'] += 1
            
            if order.get('paymentStatus', 'pending') == 'paid':
                summary['orders']['paidRevenue'] += revenue
    
    # Process appointments
    for appointment in appointments:
        if filter_by_date_range(appointment, start_date, end_date):
            summary['appointments']['total'] += 1
            revenue = float(appointment.get('price', 0))
            summary['appointments']['revenue'] += revenue
            
            status = appointment.get('status', '').upper()
            if status == 'COMPLETED':
                summary['appointments']['completed'] += 1
            elif status in ['PENDING', 'CONFIRMED', 'IN_PROGRESS']:
                summary['appointments']['pending'] += 1
            
            if appointment.get('paymentStatus', 'pending') == 'paid':
                summary['appointments']['paidRevenue'] += revenue
    
    # Calculate revenue summary
    summary['revenue']['total'] = summary['orders']['revenue'] + summary['appointments']['revenue']
    summary['revenue']['paid'] = summary['orders']['paidRevenue'] + summary['appointments']['paidRevenue']
    summary['revenue']['unpaid'] = summary['revenue']['total'] - summary['revenue']['paid']
    
    if summary['revenue']['total'] > 0:
        summary['revenue']['ordersPercentage'] = (summary['orders']['revenue'] / summary['revenue']['total']) * 100
        summary['revenue']['appointmentsPercentage'] = (summary['appointments']['revenue'] / summary['revenue']['total']) * 100
    
    # Count active customers (those with activity in the period)
    active_customers = set()
    for order in orders:
        if filter_by_date_range(order, start_date, end_date):
            active_customers.add(order.get('createdUserId'))
    
    for appointment in appointments:
        if filter_by_date_range(appointment, start_date, end_date):
            active_customers.add(appointment.get('createdUserId'))
    
    summary['customers']['active'] = len(active_customers)
    
    return summary

def get_financial_summary(parameters, user_context):
    """Get detailed financial summary"""
    start_date = parameters.get('startDate')
    end_date = parameters.get('endDate')
    
    orders = db.get_all_orders()
    appointments = db.get_all_appointments()
    
    financial_summary = {
        'revenue': {
            'orders': {'total': 0, 'paid': 0, 'unpaid': 0, 'count': 0},
            'appointments': {'total': 0, 'paid': 0, 'unpaid': 0, 'count': 0},
            'combined': {'total': 0, 'paid': 0, 'unpaid': 0, 'count': 0}
        },
        'breakdown': {
            'byStatus': defaultdict(lambda: {'orders': 0, 'appointments': 0, 'total': 0}),
            'byPaymentStatus': {
                'paid': {'orders': 0, 'appointments': 0, 'total': 0},
                'unpaid': {'orders': 0, 'appointments': 0, 'total': 0}
            }
        },
        'averages': {
            'orderValue': 0,
            'appointmentValue': 0,
            'combinedValue': 0
        },
        'trends': {
            'dailyAverage': 0,
            'weeklyProjection': 0,
            'monthlyProjection': 0
        }
    }
    
    # Process orders
    for order in orders:
        if filter_by_date_range(order, start_date, end_date):
            revenue = float(order.get('totalPrice', 0))
            financial_summary['revenue']['orders']['total'] += revenue
            financial_summary['revenue']['orders']['count'] += 1
            
            status = order.get('status', 'UNKNOWN')
            financial_summary['breakdown']['byStatus'][status]['orders'] += revenue
            financial_summary['breakdown']['byStatus'][status]['total'] += revenue
            
            if order.get('paymentStatus', 'pending') == 'paid':
                financial_summary['revenue']['orders']['paid'] += revenue
                financial_summary['breakdown']['byPaymentStatus']['paid']['orders'] += revenue
                financial_summary['breakdown']['byPaymentStatus']['paid']['total'] += revenue
            else:
                financial_summary['revenue']['orders']['unpaid'] += revenue
                financial_summary['breakdown']['byPaymentStatus']['unpaid']['orders'] += revenue
                financial_summary['breakdown']['byPaymentStatus']['unpaid']['total'] += revenue
    
    # Process appointments
    for appointment in appointments:
        if filter_by_date_range(appointment, start_date, end_date):
            revenue = float(appointment.get('price', 0))
            financial_summary['revenue']['appointments']['total'] += revenue
            financial_summary['revenue']['appointments']['count'] += 1
            
            status = appointment.get('status', 'UNKNOWN')
            financial_summary['breakdown']['byStatus'][status]['appointments'] += revenue
            financial_summary['breakdown']['byStatus'][status]['total'] += revenue
            
            if appointment.get('paymentStatus', 'pending') == 'paid':
                financial_summary['revenue']['appointments']['paid'] += revenue
                financial_summary['breakdown']['byPaymentStatus']['paid']['appointments'] += revenue
                financial_summary['breakdown']['byPaymentStatus']['paid']['total'] += revenue
            else:
                financial_summary['revenue']['appointments']['unpaid'] += revenue
                financial_summary['breakdown']['byPaymentStatus']['unpaid']['appointments'] += revenue
                financial_summary['breakdown']['byPaymentStatus']['unpaid']['total'] += revenue
    
    # Calculate combined totals
    financial_summary['revenue']['combined']['total'] = (
        financial_summary['revenue']['orders']['total'] + 
        financial_summary['revenue']['appointments']['total']
    )
    financial_summary['revenue']['combined']['paid'] = (
        financial_summary['revenue']['orders']['paid'] + 
        financial_summary['revenue']['appointments']['paid']
    )
    financial_summary['revenue']['combined']['unpaid'] = (
        financial_summary['revenue']['orders']['unpaid'] + 
        financial_summary['revenue']['appointments']['unpaid']
    )
    financial_summary['revenue']['combined']['count'] = (
        financial_summary['revenue']['orders']['count'] + 
        financial_summary['revenue']['appointments']['count']
    )
    
    # Calculate averages
    if financial_summary['revenue']['orders']['count'] > 0:
        financial_summary['averages']['orderValue'] = (
            financial_summary['revenue']['orders']['total'] / 
            financial_summary['revenue']['orders']['count']
        )
    
    if financial_summary['revenue']['appointments']['count'] > 0:
        financial_summary['averages']['appointmentValue'] = (
            financial_summary['revenue']['appointments']['total'] / 
            financial_summary['revenue']['appointments']['count']
        )
    
    if financial_summary['revenue']['combined']['count'] > 0:
        financial_summary['averages']['combinedValue'] = (
            financial_summary['revenue']['combined']['total'] / 
            financial_summary['revenue']['combined']['count']
        )
    
    # Calculate trend projections (simplified)
    if start_date and end_date:
        try:
            start = datetime.strptime(start_date, '%Y-%m-%d')
            end = datetime.strptime(end_date, '%Y-%m-%d')
            days = (end - start).days + 1
            
            if days > 0:
                daily_avg = financial_summary['revenue']['combined']['total'] / days
                financial_summary['trends']['dailyAverage'] = daily_avg
                financial_summary['trends']['weeklyProjection'] = daily_avg * 7
                financial_summary['trends']['monthlyProjection'] = daily_avg * 30
        except:
            pass
    
    # Convert defaultdicts to regular dicts
    financial_summary['breakdown']['byStatus'] = dict(financial_summary['breakdown']['byStatus'])
    
    return financial_summary

# ==================== UTILITY FUNCTIONS ====================

def filter_by_date_range(item, start_date=None, end_date=None):
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
