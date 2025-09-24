
from datetime import datetime, timedelta
import response_utils as resp
import request_utils as req
import business_logic_utils as biz
from analytics_manager import get_analytics_manager
from exceptions import BusinessLogicError

@biz.handle_business_logic_error
def lambda_handler(event, context):
    """
    Main lambda handler for analytics queries - provides comprehensive business intelligence
    
    Query parameters:
    - start_date (YYYY-MM-DD format) - Required for comprehensive analytics
    - end_date (YYYY-MM-DD format) - Required for comprehensive analytics  
    - analytics_type (optional) - Filter for specific analytics: revenue, services, products, customers, vehicles, payments, bookings, trends, operations
    - quick_metrics (optional) - Set to 'true' for quick dashboard metrics (uses last 30 days)
    - days_back (optional) - Number of days back for quick metrics (default 30)
    
    Staff authentication required with ADMIN or MANAGER roles.
    """
    
    # Validate staff authentication with required roles
    staff_context = biz.DataAccessManager().validate_staff_authentication(
        event, 
        required_roles=['ADMIN', 'CUSTOMER_SUPPORT']  # Allow customer support to view analytics
    )
    
    # Get query parameters
    query_params = event.get('queryStringParameters', {}) or {}
    quick_metrics = query_params.get('quick_metrics', '').lower() == 'true'
    
    # Get analytics manager
    analytics_manager = get_analytics_manager()
    
    if quick_metrics:
        # Handle quick metrics request
        days_back_str = query_params.get('days_back', '30')
        try:
            # Handle both integer and float string inputs
            days_back = int(float(days_back_str))
            if days_back < 1 or days_back > 365:
                raise ValueError("Days back must be between 1 and 365")
        except (ValueError, TypeError):
            raise BusinessLogicError("days_back must be a valid number between 1 and 365", 400)
        
        analytics_result = analytics_manager.get_quick_metrics(days_back)
        
        return resp.success_response({
            "analytics": resp.convert_decimal(analytics_result),
            "request_type": "quick_metrics",
            "staff_user": staff_context['staff_user_email']
        })
    
    else:
        # Handle comprehensive analytics request
        start_date = query_params.get('start_date')
        end_date = query_params.get('end_date')
        analytics_type = query_params.get('analytics_type')
        
        # Validate required parameters for comprehensive analytics
        if not start_date:
            raise BusinessLogicError("start_date parameter is required (YYYY-MM-DD format)", 400)
        
        if not end_date:
            raise BusinessLogicError("end_date parameter is required (YYYY-MM-DD format)", 400)
        
        # Validate analytics type if provided
        valid_analytics_types = [
            'revenue', 'services', 'products', 'customers', 
            'vehicles', 'payments', 'bookings', 'trends', 'operations'
        ]
        
        if analytics_type and analytics_type.lower() not in valid_analytics_types:
            raise BusinessLogicError(
                f"Invalid analytics_type. Valid values: {', '.join(valid_analytics_types)}", 
                400
            )
        
        # Get comprehensive analytics
        analytics_result = analytics_manager.get_comprehensive_analytics(
            start_date, 
            end_date, 
            analytics_type
        )
        
        return resp.success_response({
            "analytics": resp.convert_decimal(analytics_result),
            "request_type": "comprehensive",
            "filters": {
                "start_date": start_date,
                "end_date": end_date,
                "analytics_type": analytics_type
            },
            "staff_user": staff_context['staff_user_email']
        })
