import response_utils as resp
import business_logic_utils as biz

@biz.handle_business_logic_error
def lambda_handler(event, context):
    try:
        # Get price manager and validate staff authentication
        price_manager = biz.get_price_manager()
        staff_context = price_manager.validate_staff_authentication(event)
        
        # Get all prices
        price_data = price_manager.get_all_prices()
        
        return resp.success_response({
            "itemPrices": resp.convert_decimal(price_data['item_prices']),
            "servicePrices": resp.convert_decimal(price_data['service_prices']),
            "timestamp": price_data['timestamp']
        })

    except Exception as e:
        print(f"Error in get prices lambda: {str(e)}")
        return resp.error_response("Internal server error", 500)
