import db_utils as db
import response_utils as resp
import request_utils as req


def lambda_handler(event, context):
    """
    Get invoices based on date range
    
    Query parameters:
    - start_date, end_date (timestamps) - REQUIRED
    - limit (optional) - defaults to 100
    """
    try:
        # For invoice list requests, date range is required
        query_params = event.get('queryStringParameters', {}) or {}
        start_date = query_params.get('start_date')
        end_date = query_params.get('end_date')
        
        # Validate required date parameters
        if not start_date or not end_date:
            return resp.error_response(
                "start_date and end_date parameters are required (timestamps)", 400
            )
        
        try:
            start_timestamp = int(start_date)
            end_timestamp = int(end_date)
        except ValueError:
            return resp.error_response(
                "start_date and end_date must be valid timestamps", 400
            )
        
        # Validate date range (max 90 days)
        max_range = 90 * 24 * 60 * 60  # 90 days in seconds
        if end_timestamp - start_timestamp > max_range:
            return resp.error_response(
                "Date range cannot exceed 90 days", 400
            )
        
        if end_timestamp <= start_timestamp:
            return resp.error_response(
                "end_date must be greater than start_date", 400
            )
        
        # Get limit parameter
        limit = int(query_params.get('limit', 2000))
        
        # Get all invoices within date range
        invoices = db.get_invoices_by_date_range(start_timestamp, end_timestamp, limit)
        
        return resp.success_response({
            "invoices": resp.convert_decimal(invoices),
            "count": len(invoices),
            "date_range": {
                "start_date": start_timestamp,
                "end_date": end_timestamp
            }
        })
    
    except Exception as e:
        print(f"Error in lambda_handler: {str(e)}")
        return resp.error_response(f"Internal server error: {str(e)}", 500)



