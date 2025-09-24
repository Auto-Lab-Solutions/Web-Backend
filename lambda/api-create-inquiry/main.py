import uuid
import db_utils as db
import response_utils as resp
import request_utils as req
from notification_manager import notification_manager

def lambda_handler(event, context):
    try:
        # Get inquiry data from request body
        inquiry_data = req.get_body_param(event, 'inquiryData')
        user_id = req.get_body_param(event, 'userId')
        
        if not inquiry_data or not user_id:
            return resp.error_response("inquiryData and userId are required")

        user_record = db.get_user_record(user_id)
        if not user_record:
            return resp.error_response(f"No user record found for userId: {user_id}")
        
        # Validate inquiry data
        valid, msg = validate_inquiry_data(inquiry_data)
        if not valid:
            return resp.error_response(msg)
        
        # Generate unique inquiry ID
        inquiry_id = str(uuid.uuid4())
        
        # Build inquiry data
        inquiry_data_db = db.build_inquiry_data(
            inquiry_id=inquiry_id,
            first_name=inquiry_data.get('firstName'),
            last_name=inquiry_data.get('lastName'),
            email=inquiry_data.get('email'),
            message=inquiry_data.get('message'),
            user_id=user_id
        )
        
        # Create inquiry in database
        success = db.create_inquiry(inquiry_data_db)
        if not success:
            return resp.error_response("Failed to create inquiry", 500)
        
        # Send notifications to staff users
        send_inquiry_notifications(inquiry_id, inquiry_data_db)
        
        # Return success response
        return resp.success_response({
            "message": "Inquiry submitted successfully",
            "inquiryId": inquiry_id
        })
        
    except Exception as e:
        print(f"Error in create inquiry lambda: {str(e)}")
        return resp.error_response("Internal server error", 500)


def validate_inquiry_data(inquiry_data):
    """Validate inquiry data"""
    if not inquiry_data:
        return False, "Inquiry data is required"
    
    # Required fields
    required_fields = ['firstName', 'lastName', 'email', 'message']
    for field in required_fields:
        if field not in inquiry_data or not inquiry_data[field]:
            return False, f"{field} is required"
    
    # Validate email format
    email = inquiry_data.get('email', '')
    if '@' not in email or '.' not in email:
        return False, "Invalid email format"
    
    # Validate field lengths
    if len(inquiry_data.get('firstName', '')) > 50:
        return False, "First name must be 50 characters or less"
    
    if len(inquiry_data.get('lastName', '')) > 50:
        return False, "Last name must be 50 characters or less"
    
    if len(inquiry_data.get('email', '')) > 100:
        return False, "Email must be 100 characters or less"
    
    if len(inquiry_data.get('message', '')) > 1000:
        return False, "Message must be 1000 characters or less"
    
    # Validate message minimum length
    if len(inquiry_data.get('message', '').strip()) < 10:
        return False, "Message must be at least 10 characters long"
    
    return True, "Valid"


def send_inquiry_notifications(inquiry_id, inquiry_data):
    """Send notifications to staff about new inquiry"""
    try:
        # Extract data from DynamoDB format
        first_name = inquiry_data.get('firstName', {}).get('S', '') if isinstance(inquiry_data.get('firstName'), dict) else inquiry_data.get('firstName', '')
        last_name = inquiry_data.get('lastName', {}).get('S', '') if isinstance(inquiry_data.get('lastName'), dict) else inquiry_data.get('lastName', '')
        email = inquiry_data.get('email', {}).get('S', '') if isinstance(inquiry_data.get('email'), dict) else inquiry_data.get('email', '')
        message = inquiry_data.get('message', {}).get('S', '') if isinstance(inquiry_data.get('message'), dict) else inquiry_data.get('message', '')
        
        customer_name = f"{first_name} {last_name}".strip()
        
        # Prepare WebSocket notification data
        notification_data = {
            "type": "inquiry",
            "subtype": "create",
            "inquiryId": inquiry_id,
            "customerName": customer_name,
            "email": email,
            "message": message[:100] + "..." if len(message) > 100 else message
        }
        
        # Removed: WebSocket notification for inquiries (not messaging-related)
        # As per requirements, websocket notifications are only for messaging scenarios
        
        # Queue Firebase push notification to all staff with customer name
        notification_manager.queue_inquiry_firebase_notification(inquiry_id, customer_name)
        
        print(f"Inquiry notification queued for staff - Customer: {customer_name}")
        
    except Exception as e:
        print(f"Error queueing inquiry notifications: {str(e)}")
