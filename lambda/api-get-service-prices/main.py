from datetime import datetime
import db_utils as db
import response_utils as resp
import request_utils as req

def lambda_handler(event, context):
    try:
        staff_user_email = req.get_staff_user_email(event)
        staff_user_record = db.get_staff_record(staff_user_email)
        if not staff_user_record:
            return resp.error_response("Unauthorized: Staff user not found.")

        # Get service prices from the database
        service_prices = db.get_service_prices()
        return resp.success_response({
            "servicePrices": resp.convert_decimal(service_prices)
        })

    except Exception as e:
        print(f"Error in get service prices lambda: {str(e)}")
        return resp.error_response("Internal server error", 500)
