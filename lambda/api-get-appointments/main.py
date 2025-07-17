from datetime import datetime
import db_utils as db
import response_utils as resp
import request_utils as req

def lambda_handler(event, context):
    try:
        staff_user_email = req.get_staff_user_email(event)
        appointment_id = req.get_path_param(event, 'appointmentId')
        user_id = req.get_body_param(event, 'userId')
        
    # scenarios:
    # 1. staff user - CUSTOMER_SUPPORT role - get single appointment by ID, get all appointments
    # 2. staff user - MECHANIC role - get single appointment by ID, get all appointments assigned to them
    # 3. customer user - get single appointment by ID, get all appointments created by them