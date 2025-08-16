import response_utils as resp
import request_utils as req
import permission_utils as perm
import business_logic_utils as biz
from payment_manager import PaymentManager

@perm.handle_permission_error
@biz.handle_business_logic_error
def lambda_handler(event, context):
    """
    Lambda function to confirm manual payments (cash and bank transfers) for appointments and orders.
    
    This function allows authorized staff to manually confirm payments that were made outside 
    of the Stripe payment system, such as cash payments or bank transfers.
    
    Request Parameters:
    - referenceNumber: The appointment or order ID
    - type: 'appointment' or 'order'
    - paymentMethod: 'cash' or 'bank_transfer' (defaults to 'cash' for backward compatibility)
    - revert: Boolean to revert payment status to pending (optional, defaults to false)
    
    Returns:
    - Success response with updated payment status and method
    - Error response if validation fails or operation cannot be completed
    """
    # Validate staff permissions
    staff_user_email = req.get_staff_user_email(event)
    staff_context = perm.PermissionValidator.validate_staff_access(
        staff_user_email,
        required_roles=['ADMIN']
    )
    
    # Get request parameters
    reference_number = req.get_body_param(event, 'referenceNumber')
    payment_type = req.get_body_param(event, 'type')
    payment_method = req.get_body_param(event, 'paymentMethod', 'cash')
    revert = req.get_body_param(event, 'revert', False)
    
    # Validate required parameters
    if not reference_number:
        raise biz.BusinessLogicError("referenceNumber is required")
    if not payment_type:
        raise biz.BusinessLogicError("type is required")
    if payment_type not in ['appointment', 'order']:
        raise biz.BusinessLogicError("type must be 'appointment' or 'order'")
    if payment_method not in ['cash', 'bank_transfer']:
        raise biz.BusinessLogicError("paymentMethod must be 'cash' or 'bank_transfer'")
    
    # Use business logic for payment confirmation
    if revert:
        result = PaymentManager.revert_payment_confirmation(
            reference_number=reference_number,
            payment_type=payment_type,
            staff_user_id=staff_context['staff_user_id']
        )
    else:
        result = PaymentManager.confirm_manual_payment(
            reference_number=reference_number,
            payment_type=payment_type,
            payment_method=payment_method,
            staff_user_id=staff_context['staff_user_id']
        )
    
    return resp.success_response(result)
    return resp.success_response(result)


