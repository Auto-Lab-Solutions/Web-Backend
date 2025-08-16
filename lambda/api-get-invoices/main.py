import os
import sys

# Add common_lib to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'common_lib'))

import response_utils as resp
import business_logic_utils as biz

@biz.handle_business_logic_error
def lambda_handler(event, context):
    """
    Get invoices based on date range
    
    Query parameters:
    - start_date, end_date (timestamps) - REQUIRED
    - limit (optional) - defaults to 2000
    """
    try:
        # Get query parameters
        query_params = event.get('queryStringParameters', {}) or {}
        start_date = query_params.get('start_date')
        end_date = query_params.get('end_date')
        limit = query_params.get('limit', '2000')
        
        # Get invoice manager and retrieve invoices
        invoice_manager = biz.get_invoice_manager()
        invoices = invoice_manager.get_invoices_by_date_range(start_date, end_date, limit)
        
        return resp.success_response({
            "invoices": resp.convert_decimal(invoices),
            "count": len(invoices),
            "query": {
                "start_date": start_date,
                "end_date": end_date,
                "limit": limit
            }
        })

    except Exception as e:
        print(f"Error in get invoices lambda: {str(e)}")
        return resp.error_response("Internal server error", 500)
        
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



