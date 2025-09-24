import response_utils as resp
import request_utils as req
import permission_utils as perm
import business_logic_utils as biz
from payment_manager import PaymentManager

def lambda_handler(event, context):
    """
    Lambda function to confirm manual payments (cash and bank transfers) for appointments and orders.
    
    This function allows authorized staff to manually confirm payments that were made outside 
    of the Stripe payment system, such as cash payments or bank transfers.
    
    Request Parameters:
    - referenceNumber: The appointment or order ID
    - type: 'appointment' or 'order'
    - paymentMethod: 'cash', 'bank_transfer', or 'card' (defaults to 'cash' for backward compatibility)
    - revert: Boolean to revert payment status to pending (optional, defaults to false)
    
    Returns:
    - Success response with updated payment status and method
    - Error response if validation fails or operation cannot be completed
    """
    try:
        print(f"Event received: {event}")
        print(f"Context: {context}")
        
        # Validate staff permissions
        staff_user_email = req.get_staff_user_email(event)
        print(f"Staff user email: {staff_user_email}")
        
        if not staff_user_email:
            return resp.error_response("Staff user email is required for authorization", 401)
        
        staff_context = perm.PermissionValidator.validate_staff_access(
            staff_user_email,
            required_roles=['ADMIN']
        )
        print(f"Staff context validated: {staff_context}")
        
        # Get request parameters
        reference_number = req.get_body_param(event, 'referenceNumber')
        payment_type = req.get_body_param(event, 'type')
        payment_method = req.get_body_param(event, 'paymentMethod', 'cash')
        revert = req.get_body_param(event, 'revert', False)
        
        print(f"Request parameters: referenceNumber={reference_number}, type={payment_type}, paymentMethod={payment_method}, revert={revert}")
        
        # Validate required parameters
        if not reference_number:
            return resp.error_response("referenceNumber is required", 400)
        if not payment_type:
            return resp.error_response("type is required", 400)
        if payment_type not in ['appointment', 'order']:
            return resp.error_response("type must be 'appointment' or 'order'", 400)
        if payment_method not in ['cash', 'bank_transfer', 'card']:
            return resp.error_response("paymentMethod must be 'cash', 'bank_transfer', or 'card'", 400)
        
        print("Parameter validation passed")
        
        # Use business logic for payment confirmation
        if revert:
            print("Attempting to revert payment confirmation")
            result = PaymentManager.revert_payment_confirmation(
                reference_number=reference_number,
                payment_type=payment_type,
                staff_user_id=staff_context['staff_user_id']
            )
        else:
            print("Attempting to confirm manual payment")
            result = PaymentManager.confirm_manual_payment(
                reference_number=reference_number,
                payment_type=payment_type,
                payment_method=payment_method,
                staff_user_id=staff_context['staff_user_id']
            )
        
        print(f"Payment operation result: {result}")
        return resp.success_response(result)
        
    except perm.PermissionError as e:
        print(f"PermissionError: {e.message} (status: {e.status_code})")
        return resp.error_response(e.message, e.status_code)
    except biz.BusinessLogicError as e:
        print(f"BusinessLogicError: {e.message} (status: {e.status_code})")
        return resp.error_response(e.message, e.status_code)
    except Exception as e:
        print(f"Unexpected error: {str(e)}")
        print(f"Error type: {type(e).__name__}")
        import traceback
        traceback.print_exc()
        return resp.error_response(f"Internal server error: {str(e)}", 500)


