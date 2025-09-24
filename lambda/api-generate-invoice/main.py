import time
from datetime import datetime
from zoneinfo import ZoneInfo
import db_utils as db
import response_utils as resp
import request_utils as req
import validation_utils as valid
import business_logic_utils as biz
import email_utils as email
from notification_manager import invoice_manager


@biz.handle_business_logic_error
@valid.handle_validation_error
def lambda_handler(event, context):
    """
    Generate an invoice for manual transactions (cash/bank transfers)
    
    This function handles invoice generation for transactions that were processed
    outside of Stripe (cash payments and bank transfers). It accepts all required
    data in the request body to generate invoices synchronously.
    
    Expected event body:
    {
        "payment_method": "cash", "bank_transfer", or "card",
        "reference_number": "APT001 or ORD001" (optional - will use Invoice Id if not provided)
        "customer_data": {
            "name": "John Doe",
            "email": "john@example.com",    # optional, defaults to N/A
            "phone": "+1234567890"      # optional, defaults to N/A
        },
        "transaction_data": {
            "currency": "AUD",  # optional, defaults to AUD
            "payment_date": "08/08/2025"  # optional, defaults to current date
        },
        "vehicle_data": {
            "make": "Toyota",
            "model": "Camry", 
            "year": 2020    # optional, defaults to ""
        },
        "items": [
            {
                "name": "Service 1",
                "totalAmount": 50.00,
                "description": "Basic service"  # optional, defaults to ""
                # Note: Services (items with only totalAmount) will display empty quantity and unit price columns
            },
            {
                "name": "Item 1",
                "unitPrice": 100.00,
                "quantity": 1,
                "totalAmount": 100.00,  # optional, defaults to unitPrice * quantity
                "description": "Premium item"  # optional, defaults to ""
                # Note: Items (with unitPrice and quantity) will display these values in respective columns
            }
        ]
    }
    """
    # Parse request body
    body = req.get_body(event)
    
    # Validate required parameters
    payment_method = req.get_body_param(event, 'payment_method')
    reference_number = req.get_body_param(event, 'reference_number')
    customer_data = req.get_body_param(event, 'customer_data')
    transaction_data = req.get_body_param(event, 'transaction_data')
    vehicle_data = req.get_body_param(event, 'vehicle_data')
    items = req.get_body_param(event, 'items')
    
    # Validate all request data using validation utilities
    validate_all_request_data(payment_method, customer_data, transaction_data, vehicle_data, items)
    
    # Generate reference number if not provided
    if not reference_number:
        reference_number = "<INVOICE_ID>"
    
    # Generate unique payment intent ID for manual transactions
    payment_intent_id = f"{payment_method}_{reference_number}"
    
    # Set transaction defaults and ensure invoice ID matches reference number
    set_transaction_defaults(transaction_data)
    
    # Prepare vehicle description
    vehicle_description = prepare_vehicle_description(vehicle_data)
    
    # Enhance items with vehicle information
    enhanced_items, total_amount = enhance_items_with_vehicle_info(items, vehicle_description)
    
    # Prepare record data in the format expected by invoice generation
    record_data = {
        "customerName": customer_data['name'],
        "customerEmail": customer_data.get('email', 'N/A'),
        "customerPhone": customer_data.get('phone', 'N/A'),
        "carMake": vehicle_data.get('make', 'N/A'),
        "carModel": vehicle_data.get('model', 'N/A'),
        "carYear": vehicle_data.get('year', 'N/A'),
        "paymentMethod": payment_method,
        "paymentStatus": "completed",
        "paymentIntentId": payment_intent_id,
        "paymentDate": transaction_data.get('payment_date', datetime.now(ZoneInfo('Australia/Perth')).strftime('%d/%m/%Y')),
        "items": enhanced_items,
        "currency": transaction_data.get('currency', 'AUD'),
        "totalAmount": total_amount,
    }
    
    # Generate invoice synchronously using invoice manager
    invoice_generation_result = invoice_manager._generate_invoice_synchronously(
        record_data, 
        "invoice", 
        payment_intent_id
    )
    
    if invoice_generation_result.get('success'):
        # Extract invoice URL and other required fields from the result
        invoice_url = invoice_generation_result.get('invoice_url')
        invoice_id = invoice_generation_result.get('invoice_id')
        payment_intent_id_result = invoice_generation_result.get('payment_intent_id')
        
        # The invoice manager handles email sending internally,
        # so we just return success with the provided data
        response_data = {
            "message": "Invoice generated successfully",
            "invoice_id": invoice_id,
            "reference_number": payment_intent_id_result or payment_intent_id,
            "payment_intent_id": payment_intent_id_result or payment_intent_id,
            "payment_method": payment_method,
            "invoice_url": invoice_url,
            "generated_at": datetime.now(ZoneInfo('Australia/Perth')).strftime('%Y-%m-%dT%H:%M:%S%z')
        }
        
        return resp.success_response(response_data)
    else:
        error_message = invoice_generation_result.get('error', 'Unknown error occurred during invoice generation')
        raise biz.BusinessLogicError(f"Failed to generate invoice: {error_message}", 500)


def validate_request_parameters(payment_method, customer_data, transaction_data, vehicle_data, items):
    """Validate all required request parameters"""
    
    # Validate payment method
    if not payment_method:
        return "payment_method is required"
    if payment_method not in ['cash', 'bank_transfer', 'card']:
        return "payment_method must be 'cash', 'bank_transfer', or 'card'"
    
    # Validate required sections
    if not customer_data:
        return "customer_data is required"
    if not transaction_data:
        return "transaction_data is required"
    if not vehicle_data:
        return "vehicle_data is required"
    if not items:
        return "items is required"
    if not isinstance(items, list) or len(items) == 0:
        return "items must be a non-empty array"
    
    return None  # No errors


def validate_customer_data(customer_data):
    """Validate customer data fields"""
    
    # Validate required fields
    if not customer_data.get('name'):
        return "customer_data.name is required"
    
    # Validate optional fields if provided
    if 'email' in customer_data and customer_data.get('email'):
        if not req.validate_email(customer_data.get('email')):
            return "customer_data.email is invalid"
    
    if 'phone' in customer_data and customer_data.get('phone'):
        if not req.validate_phone_number(customer_data.get('phone')):
            return "customer_data.phone is invalid"
    
    return None  # No errors


def validate_vehicle_data(vehicle_data):
    """Validate vehicle data fields"""
    
    required_vehicle_fields = ['make', 'model']
    for field in required_vehicle_fields:
        if not vehicle_data.get(field):
            return f"vehicle_data.{field} is required"
    
    return None  # No errors


def validate_items_structure(items):
    """Validate items array structure and content"""
    
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            return f"items[{i}] must be an object"
        
        if not item.get('name'):
            return f"items[{i}].name is required"
        
        # Check if either totalAmount is provided OR both unitPrice and quantity are provided
        has_total_amount = item.get('totalAmount') is not None
        has_unit_price_and_quantity = (item.get('unitPrice') is not None and 
                                      item.get('quantity') is not None)
        
        if not has_total_amount and not has_unit_price_and_quantity:
            return f"items[{i}] must have either totalAmount or both unitPrice and quantity"
        
        # Validate data types
        if item.get('totalAmount') is not None and not isinstance(item.get('totalAmount'), (int, float)):
            return f"items[{i}].totalAmount must be a number"
        
        if item.get('unitPrice') is not None and not isinstance(item.get('unitPrice'), (int, float)):
            return f"items[{i}].unitPrice must be a number"
        
        if item.get('quantity') is not None and not isinstance(item.get('quantity'), int):
            return f"items[{i}].quantity must be an integer"
    
    return None  # No errors


def validate_all_request_data(payment_method, customer_data, transaction_data, vehicle_data, items):
    """Validate all request data and return error message if any validation fails"""
    
    # Validate request parameters
    error = validate_request_parameters(payment_method, customer_data, transaction_data, vehicle_data, items)
    if error:
        return error
    
    # Validate customer data
    error = validate_customer_data(customer_data)
    if error:
        return error
    
    # Validate vehicle data
    error = validate_vehicle_data(vehicle_data)
    if error:
        return error
    
    # Validate items structure
    error = validate_items_structure(items)
    if error:
        return error
    
    return None  # All validations passed


def set_transaction_defaults(transaction_data):
    """Set default values for optional transaction fields"""
    
    if 'currency' not in transaction_data:
        transaction_data['currency'] = 'AUD'
    if 'payment_date' not in transaction_data:
        transaction_data['payment_date'] = datetime.now(ZoneInfo('Australia/Perth')).strftime('%d/%m/%Y')
    if 'confirmation_reference' not in transaction_data:
        transaction_data['confirmation_reference'] = 'N/A'


def prepare_vehicle_description(vehicle_data):
    """Prepare vehicle description string for items"""
    
    vehicle_parts = []
    vehicle_parts.append(vehicle_data['make'])
    vehicle_parts.append(vehicle_data['model'])
    if vehicle_data.get('year'):
        vehicle_parts.append(str(vehicle_data['year']))
    
    return f"{' '.join(vehicle_parts)}"


def enhance_items_with_vehicle_info(items, vehicle_description):
    """Enhance items with vehicle information and calculate totals"""
    
    enhanced_items = []
    total_amount = 0
    
    for item in items:
        enhanced_item = item.copy()

        # Determine item type based on structure
        # If only totalAmount is provided (no unitPrice/quantity), treat as service
        has_unit_price = 'unitPrice' in enhanced_item
        has_quantity = 'quantity' in enhanced_item
        item_type = 'item' if (has_unit_price and has_quantity) else 'service'
        enhanced_item['type'] = item_type

        # Set quantity and unit price if not provided
        if 'totalAmount' in enhanced_item:
            if 'quantity' not in enhanced_item:
                enhanced_item['quantity'] = 1
            if 'unitPrice' not in enhanced_item:
                enhanced_item['unitPrice'] = enhanced_item.get('totalAmount', 0) / enhanced_item.get('quantity', 1)
        else:
            enhanced_item['totalAmount'] = enhanced_item.get('unitPrice', 0) * enhanced_item.get('quantity', 1)
        
        # Set default description if not provided
        if 'description' not in enhanced_item:
            enhanced_item['description'] = vehicle_description
        else:
            enhanced_item['description'] += vehicle_description
        
        enhanced_items.append(enhanced_item)
        total_amount += enhanced_item.get('totalAmount', 0)
    
    return enhanced_items, total_amount
