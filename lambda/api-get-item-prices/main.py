from datetime import datetime
import db_utils as db
import response_utils as resp
import request_utils as req

def lambda_handler(event, context):
    try:
        staff_user_email = req.get_staff_user_email(event)
        
        # Only staff users can access item prices
        if not staff_user_email:
            return resp.error_response("Unauthorized: Staff authentication required", 401)
        
        staff_user_record = db.get_staff_record(staff_user_email)
        if not staff_user_record:
            return resp.error_response("Unauthorized: Staff user not found", 404)

        # Get item prices from the database
        item_prices = db.get_all_item_prices()
        return resp.success_response({
            "itemPrices": resp.convert_decimal(item_prices),
            "count": len(item_prices)
        })

    except Exception as e:
        print(f"Error in get item prices lambda: {str(e)}")
        return resp.error_response("Internal server error", 500)
