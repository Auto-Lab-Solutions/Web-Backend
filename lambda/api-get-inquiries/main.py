from datetime import datetime
import db_utils as db
import response_utils as resp
import request_utils as req

def lambda_handler(event, context):
    try:
        # Only staff users can access inquiries
        staff_user_email = req.get_staff_user_email(event)
        if not staff_user_email:
            return resp.error_response("Unauthorized: Staff authentication required", 401)
        
        staff_user_record = db.get_staff_record(staff_user_email)
        if not staff_user_record:
            return resp.error_response("Unauthorized: Staff user not found", 404)
        
        # Get inquiry ID from path parameters (optional)
        inquiry_id = req.get_path_param(event, 'inquiryId')
        
        if inquiry_id:
            # Get single inquiry by ID
            inquiry = db.get_inquiry(inquiry_id)
            if not inquiry:
                return resp.error_response("Inquiry not found", 404)
            
            return resp.success_response({
                "inquiry": resp.convert_decimal(inquiry)
            })
        else:
            # Get all inquiries
            inquiries = db.get_all_inquiries()
            
            # Apply additional query parameter filters
            inquiries = apply_query_filters(inquiries, event)
            
            # Sort inquiries by creation date (newest first)
            inquiries.sort(key=lambda x: x.get('createdAt', 0), reverse=True)
            
            return resp.success_response({
                "inquiries": resp.convert_decimal(inquiries),
                "count": len(inquiries)
            })
        
    except Exception as e:
        print(f"Error in get inquiries lambda: {str(e)}")
        return resp.error_response("Internal server error", 500)


def apply_query_filters(inquiries, event):
    """Apply query parameter filters to the inquiries list"""
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
