import response_utils as resp
import business_logic_utils as biz

@biz.handle_business_logic_error
def lambda_handler(event, context):
    """
    Get ALL invoices (including cancelled ones) based on date range - Admin API
    
    This endpoint returns all invoices including cancelled ones for administrative 
    and audit purposes. Cancelled invoices are marked with status: 'cancelled'.
    
    Query parameters:
    - start_date, end_date (YYYY-MM-DD format) - REQUIRED
    - limit (optional) - defaults to 2000
    """
    # Get query parameters
    query_params = event.get('queryStringParameters', {}) or {}
    start_date = query_params.get('start_date')
    end_date = query_params.get('end_date')
    limit = query_params.get('limit', '2000')
    
    # Validate required parameters
    if not start_date:
        raise biz.BusinessLogicError("start_date parameter is required (YYYY-MM-DD format)")
    
    if not end_date:
        raise biz.BusinessLogicError("end_date parameter is required (YYYY-MM-DD format)")
    
    # Get invoice manager and retrieve ALL invoices (including cancelled ones)
    invoice_manager = biz.get_invoice_manager()
    invoices = invoice_manager.get_all_invoices_by_date_range_formatted(start_date, end_date, limit)
    
    # Count active vs cancelled invoices for summary
    active_count = sum(1 for inv in invoices if inv.get('status') != 'cancelled')
    cancelled_count = sum(1 for inv in invoices if inv.get('status') == 'cancelled')
    
    return resp.success_response({
        "invoices": resp.convert_decimal(invoices),
        "count": len(invoices),
        "summary": {
            "total": len(invoices),
            "active": active_count,
            "cancelled": cancelled_count
        },
        "query": {
            "start_date": start_date,
            "end_date": end_date,
            "limit": limit
        }
    })