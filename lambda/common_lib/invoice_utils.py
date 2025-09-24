import boto3
import os
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from io import BytesIO
import base64
from decimal import Decimal
import json
import email_utils as email
import validation_utils as valid

# PDF invoice generator will be imported only when needed
ProfessionalInvoicePDFGenerator = None

def _ensure_pdf_generator():
    """Import PDF generator only when needed"""
    global ProfessionalInvoicePDFGenerator
    if ProfessionalInvoicePDFGenerator is None:
        try:
            from pdf_invoice_generator import ProfessionalInvoicePDFGenerator as PDFGen
            ProfessionalInvoicePDFGenerator = PDFGen
            print("✓ PDF invoice generator imported successfully")
        except SyntaxError as e:
            print(f"✗ Syntax error importing PDF generator: {e}")
            raise ImportError(f"Failed to import PDF generator due to syntax error: {e}")
        except ImportError as e:
            print(f"✗ Import error importing PDF generator: {e}")
            raise

# AWS clients
s3_client = boto3.client('s3')

# Environment variables
REPORTS_BUCKET = os.environ.get('REPORTS_BUCKET')
CLOUDFRONT_DOMAIN = os.environ.get('CLOUDFRONT_DOMAIN')
FRONTEND_ROOT_URL = os.environ.get('FRONTEND_ROOT_URL')
MAIL_FROM_ADDRESS = os.environ.get('MAIL_FROM_ADDRESS')
FRONTEND_URL = os.environ.get('FRONTEND_ROOT_URL')



def send_invoice_email(invoice_result, customer_email, customer_name, email_subject=None):
    """
    Send invoice email to customer with PDF attachment from S3
    
    Args:
        invoice_result (dict): Result from generate_invoice containing file info
        customer_email (str): Customer's email address
        customer_name (str): Customer's name
        email_subject (str, optional): Custom email subject
        
    Returns:
        dict: Email sending result
    """
    try:
        if not invoice_result.get('success'):
            return {
                'success': False,
                'error': 'Invalid invoice result provided'
            }
        
        invoice_id = invoice_result.get('invoice_id')
        s3_key = invoice_result.get('s3_key')
        
        if not all([invoice_id, s3_key, customer_email]):
            return {
                'success': False,
                'error': 'Missing required parameters: invoice_id, s3_key, or customer_email'
            }
        
        # Download PDF from S3 for attachment
        try:
            bucket_name = os.environ.get('S3_BUCKET_NAME')
            if not bucket_name:
                raise Exception("S3_BUCKET_NAME environment variable not set")
            
            response = s3_client.get_object(Bucket=bucket_name, Key=s3_key)
            pdf_content = response['Body'].read()
            
        except Exception as e:
            print(f"Error downloading PDF from S3: {str(e)}")
            return {
                'success': False,
                'error': f'Failed to download PDF: {str(e)}'
            }
        
        # Prepare email content
        if not email_subject:
            email_subject = f"Invoice {invoice_id} - Auto Lab Solutions"
        
        # HTML email body
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background: linear-gradient(135deg, #1e40af, #3b82f6); color: white; padding: 30px; text-align: center; border-radius: 8px 8px 0 0;">
                    <h1 style="margin: 0; font-size: 2em;">Auto Lab Solutions</h1>
                    <p style="margin: 10px 0 0 0; opacity: 0.9;">Professional Automotive Services</p>
                </div>
                
                <div style="background: #f8f9fa; padding: 30px; border-radius: 0 0 8px 8px; border: 1px solid #e5e7eb;">
                    <h2 style="color: #1e40af; margin-top: 0;">Thank you for your business!</h2>
                    
                    <p>Dear {customer_name},</p>
                    
                    <p>Thank you for choosing Auto Lab Solutions. Your invoice is attached to this email as a PDF document.</p>
                    
                    <div style="background: white; padding: 20px; border-radius: 6px; border-left: 4px solid #1e40af; margin: 20px 0;">
                        <h3 style="margin-top: 0; color: #1e40af;">Invoice Details</h3>
                        <p><strong>Invoice Number:</strong> {invoice_id}</p>
                        <p><strong>Date:</strong> {datetime.now(ZoneInfo('Australia/Perth')).strftime('%d %B %Y')}</p>
                    </div>
                    
                    <p>If you have any questions about this invoice or our services, please don't hesitate to contact us:</p>
                    
                    <div style="background: white; padding: 15px; border-radius: 6px; margin: 20px 0;">
                        <p style="margin: 5px 0;"><strong>Email:</strong> {MAIL_FROM_ADDRESS or 'mail@autolabsolutions.com'}</p>
                        <p style="margin: 5px 0;"><strong>Phone:</strong> +61 451 237 048</p>
                        <p style="margin: 5px 0;"><strong>Address:</strong> 70b Division St, Welshpool WA 6106, Australia</p>
                    </div>
                    
                    <p>We appreciate your business and look forward to serving you again!</p>
                    
                    <p style="margin-top: 30px;">
                        Best regards,<br>
                        <strong>Auto Lab Solutions Team</strong>
                    </p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Plain text fallback
        text_body = f"""
        Auto Lab Solutions - Invoice {invoice_id}
        
        Dear {customer_name},
        
        Thank you for choosing Auto Lab Solutions. Your invoice is attached to this email as a PDF document.
        
        Invoice Details:
        - Invoice Number: {invoice_id}
        - Date: {datetime.now(ZoneInfo('Australia/Perth')).strftime('%d %B %Y')}
        
        If you have any questions about this invoice or our services, please contact us:
        
        Email: {MAIL_FROM_ADDRESS or 'mail@autolabsolutions.com'}
        Phone: +61 451 237 048
        Address: 70b Division St, Welshpool WA 6106, Australia
        
        We appreciate your business and look forward to serving you again!
        
        Best regards,
        Auto Lab Solutions Team
        """
        
        # Send email with PDF attachment
        email_result = email.send_email_with_attachment(
            to_email=customer_email,
            subject=email_subject,
            html_body=html_body,
            text_body=text_body,
            attachment_data=pdf_content,
            attachment_filename=f"Invoice_{invoice_id}.pdf",
            attachment_content_type="application/pdf"
        )
        
        if email_result.get('success'):
            print(f"Invoice email sent successfully to {customer_email}")
            return {
                'success': True,
                'message_id': email_result.get('message_id'),
                'invoice_id': invoice_id
            }
        else:
            print(f"Failed to send invoice email: {email_result.get('error')}")
            return {
                'success': False,
                'error': email_result.get('error', 'Unknown email sending error')
            }
            
    except Exception as e:
        print(f"Error sending invoice email: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }


class InvoiceGenerator:
    """
    Professional PDF invoice generator for Auto Lab Solutions
    """
    
    def __init__(self):
        self.company_info = {
            'name': 'Auto Lab Solutions',
            'address': '70b Division St, Welshpool WA 6106, Australia',
            'address_line1': '70b Division St',
            'address_line2': 'Welshpool WA 6106, Australia',
            'phone': '+61 451 237 048',
            'email': MAIL_FROM_ADDRESS or 'mail@autolabsolutions.com',
            'website': FRONTEND_URL.replace('https://', '').replace('http://', '') if FRONTEND_URL else 'www.autolabsolutions.com',
            'description': 'We deliver cutting-edge automotive inspection and repair solutions with state-of-the-art technology, expert service, and a commitment to safety and quality.'
        }
        
        # Initialize PDF generator only when needed
        _ensure_pdf_generator()
        self.pdf_generator = ProfessionalInvoicePDFGenerator()
        print("PDF invoice generator initialized")
    
    def generate_invoice(self, invoice_data):
        """
        Generate a professional PDF invoice
        
        Args:
            invoice_data (dict): Invoice data containing:
                - payment_intent_id: Payment intent ID
                - user_info: Customer information
                - items: List of service/item details. Each item should include:
                  * name: Item/service name
                  * description: (Optional) Item description
                  * type: 'service' or 'item' - services display empty quantity/unit price
                  * quantity: Number of items (ignored for services)
                  * unit_price: Price per unit (ignored for services)
                  * amount: Total amount for this line item
                - payment_info: Payment details
                - currency: (Optional) Currency code, defaults to 'AUD'
                - total_amount: Total amount
                - calculated_discount: Discount amount for display purposes
                
        Returns:
            dict: {
                'success': bool,
                'invoice_id': str,
                'payment_intent_id': str,
                's3_key': str,
                'file_url': str,
                'pdf_size': int,
                'format': str ('pdf'),
                'error': str (if any)
            }
        """
        try:
            # Set default currency if not provided
            if 'currency' not in invoice_data or not invoice_data.get('currency'):
                invoice_data['currency'] = 'AUD'
            
            print("Generating PDF invoice using ReportLab")
            
            # Generate PDF invoice
            result = self.pdf_generator.generate_invoice_pdf(invoice_data)
            
            return result
                
        except Exception as e:
            print(f"Error generating PDF invoice: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }


def get_s3_bucket_name():
    """Get the S3 bucket name from environment variables"""
    return os.environ.get('S3_BUCKET_NAME')


def get_cloudfront_domain():
    """Get the CloudFront domain from environment variables"""
    return os.environ.get('CLOUDFRONT_DOMAIN')


def get_frontend_url():
    """Get the frontend URL from environment variables"""
    return os.environ.get('FRONTEND_ROOT_URL')


def create_invoice_for_order_or_appointment(record, record_type, payment_intent_id=None):
    """
    Create an invoice for an order or appointment record
    
    Args:
        record (dict): Order or appointment record
        record_type (str): 'order' or 'appointment'
        payment_intent_id (str, optional): Payment intent ID if available
        
    Returns:
        dict: Invoice generation result with invoice_url for saving to record
    """
    try:
        # Import db_utils here to avoid circular imports
        import db_utils

        if record_type == 'order':
            user_data = {
                'name': record.get('customerName', 'Valued Customer'),
                'email': record.get('customerEmail', ''),
                'phone': record.get('customerPhone', '')
            }
        else:  # appointment
            if record.get('isBuyer'):
                user_data = {
                    'name': record.get('buyerName', 'Valued Customer'),
                    'email': record.get('buyerEmail', ''),
                    'phone': record.get('buyerPhone', '')
                }
            else:
                user_data = {
                    'name': record.get('sellerName', 'Valued Customer'),
                    'email': record.get('sellerEmail', ''),
                    'phone': record.get('sellerPhone', '')
                }
        
        # Extract items from record
        items = []
        
        if record_type == 'order':
            # For orders, get items from the order
            order_items = record.get('items', [])
            
            for i, item in enumerate(order_items):
                try:
                    category_name, item_name = db_utils.get_category_item_names(item.get('categoryId'), item.get('itemId'))
                except Exception as e:
                    category_name, item_name = "Unknown Category", "Unknown Item"
                vehicle_info = {
                    'make': record.get('carMake', '<Car Make>'),
                    'model': record.get('carModel', '<Car Model>'),
                    'year': record.get('carYear', '<Car Year>')
                }
                items.append({
                    'name': item_name,
                    'description': f"{vehicle_info['make']} {vehicle_info['model']} {vehicle_info['year']} | {category_name}",
                    'type': 'item',  # Physical item
                    'quantity': item.get('quantity', 1),
                    'unit_price': float(item.get('price', 0)),
                    'amount': float(item.get('totalPrice', 0))
                })
        else:  # appointment
            # For appointments, create a single item
            try:
                service_name, plan_name = db_utils.get_service_plan_names(record.get('serviceId'), record.get('planId'))
            except Exception as e:
                service_name, plan_name = "Unknown Service", "Unknown Plan"
            vehicle_info = {
                'make': record.get('carMake', 'N/A'),
                'model': record.get('carModel', 'N/A'),
                'year': record.get('carYear', 'N/A')
            }
            items.append({
                'name': service_name,
                'description': f"{vehicle_info['make']} {vehicle_info['model']} {vehicle_info['year']} | {plan_name}",
                'type': 'service',  # Service item
                'quantity': 1,
                'unit_price': float(record.get('price', 0)),
                'amount': float(record.get('price', 0))
            })
        
        # Payment information
        payment_info = {
            'method': record.get('paymentMethod', 'Unknown'),
            'status': 'completed' if record.get('paymentStatus') == 'paid' else 'pending',
            'date': datetime.now(ZoneInfo('Australia/Perth')).strftime('%d/%m/%Y')
        }
        
        # Generate QR code URL for order/appointment tracking
        reference_id = record.get(f'{record_type}Id')
        qr_code_url = f"{FRONTEND_ROOT_URL}/{record_type}/{reference_id}"
        
        # Prepare invoice data
        invoice_data = {
            'payment_intent_id': payment_intent_id or 'N/A',
            'currency': record.get('currency', 'AUD'),
            'invoice_date': datetime.now(ZoneInfo('Australia/Perth')).strftime('%d/%m/%Y'),
            'invoice_type': record_type,
            'qr_code_url': qr_code_url,
            'user_info': user_data,
            'payment_info': payment_info,
            'items': items,
            'discount_amount': 0,
            'discount_percentage': 0,
        }
        
        # Calculate total amount at this level
        subtotal = sum(Decimal(str(item.get('amount', 0))) for item in items)
        discount_amount = Decimal(str(invoice_data.get('discount_amount', 0)))
        discount_percentage = Decimal(str(invoice_data.get('discount_percentage', 0)))
        
        # Calculate discount (either fixed amount or percentage)
        if discount_percentage > 0:
            calculated_discount = subtotal * (discount_percentage / 100)
        else:
            calculated_discount = discount_amount
        
        total_amount = subtotal - calculated_discount
        
        # Add the calculated values to invoice_data
        invoice_data['total_amount'] = total_amount
        invoice_data['calculated_discount'] = calculated_discount
        
        # Generate the invoice
        generator = InvoiceGenerator()
        result = generator.generate_invoice(invoice_data)
        
        if result['success']:
            # Generate analytics data for the invoice
            analytics_data = generate_analytics_data(record, record_type, payment_intent_id)
            
            # Save invoice record to database
            current_timestamp = int(datetime.now(ZoneInfo('Australia/Perth')).timestamp())
            invoice_record = {
                'invoiceId': result['invoice_id'],
                'paymentIntentId': result.get('payment_intent_id', 'N/A'),
                'referenceNumber': reference_id,
                'referenceType': record_type,
                's3Key': result['s3_key'],
                'fileUrl': result['file_url'],
                'fileSize': result.get('pdf_size', 0),
                'format': result.get('format', 'pdf'),  # Always PDF now
                'createdAt': current_timestamp,
                'status': 'generated',
                'analyticsData': analytics_data
            }

            # Remove the note field and simplify metadata
            invoice_record['metadata'] = {
                'userName': user_data.get('name', 'N/A'),
                'userEmail': user_data.get('email', 'N/A'),
                'userPhone': user_data.get('phone', 'N/A'),
                'vehicleMake': record.get('carMake', 'N/A'),
                'vehicleModel': record.get('carModel', 'N/A'),
                'vehicleYear': record.get('carYear', 'N/A'),
                'items': [item['name'] for item in items],
                'paymentMethod': payment_info['method'],
                'paymentStatus': payment_info['status'],
                'totalAmount': float(total_amount),
                'invoiceFormat': 'pdf'  # Always PDF now
            }
            
            try:
                create_result = db_utils.create_invoice_record(invoice_record)
                if not create_result:
                    print("Warning: Invoice generated but failed to save record to database")
            except Exception as db_error:
                print(f"Warning: Invoice generated but failed to save record to database: {db_error}")
                # Don't fail the invoice generation if database save fails
                
            # Add invoice_url to result for updating the order/appointment record
            result['invoice_url'] = result['file_url']
        
        return result
        
    except Exception as e:
        print(f"Error creating invoice for order/appointment: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'error': str(e)
        }


def generate_invoice_for_payment(record_data):
    """
    Generate invoice for payment data and save to database
    Similar to create_invoice_for_order_or_appointment but for API payment data
    
    Args:
        record_data (dict): Payment record data from API
        
    Returns:
        dict: Invoice generation result with invoice_url for API response
    """
    try:
        # Import db_utils here to avoid circular imports
        import db_utils

        payment_date = record_data.get('paymentDate', 
            datetime.fromtimestamp(
                int(record_data.get('createdAt', datetime.now(ZoneInfo('Australia/Perth')).timestamp()))
            ).strftime('%d/%m/%Y')
        )
        
        # Prepare invoice data
        invoice_data = {
            'payment_intent_id': record_data.get('paymentIntentId'),
            'currency': record_data.get('currency', 'AUD'),
            'invoice_date': record_data.get('paymentDate',
                datetime.fromtimestamp(
                    int(record_data.get('createdAt', datetime.now(ZoneInfo('Australia/Perth')).timestamp()))
                ).strftime('%d/%m/%Y')
            ),
            'user_info': {
                'name': record_data.get('customerName', 'Valued Customer'),
                'email': record_data.get('customerEmail', ''),
                'phone': record_data.get('customerPhone', '')
            },
            'payment_info': {
                'method': record_data.get('paymentMethod', 'Stripe'),
                'status': record_data.get('paymentStatus', 'completed'),
                'date': payment_date
            },
            'items': [],
            'discount_amount': 0,  # Default no discount
            'discount_percentage': 0,  # Default no percentage discount
        }
        
        # Add items from payment data (new API structure)
        if record_data.get('items'):
            processed_items = []
            for item in record_data['items']:
                # Use the type that was already determined during enhancement, if available
                # Otherwise, determine if it's a service or item based on data structure
                if 'type' in item:
                    # Trust the type that was already determined (e.g., by API enhancement)
                    item_type = item['type']
                else:
                    # Fallback: determine type based on original data structure
                    # If only totalAmount is provided (no unitPrice/quantity), treat as service
                    has_unit_price = item.get('unitPrice') is not None
                    has_quantity = item.get('quantity') is not None
                    item_type = 'item' if (has_unit_price and has_quantity) else 'service'
                
                processed_item = {
                    'name': item.get('name', 'Service'),
                    'description': item.get('description', ''),
                    'type': item_type,
                    'quantity': item.get('quantity', 1),
                    'unit_price': float(item.get('unitPrice', item.get('totalAmount', 0))),
                    'amount': float(item.get('totalAmount', 0))
                }
                processed_items.append(processed_item)
            invoice_data['items'] = processed_items
        else:
            # Create a single line item from payment data
            amount = float(record_data.get('totalAmount', 0))
            invoice_data['items'] = [{
                'name': 'Auto Service',
                'description': f"Payment Reference: {record_data.get('invoiceId', 'N/A')}",
                'type': 'service',  # Default to service for legacy data
                'quantity': 1,
                'unit_price': amount,
                'amount': amount
            }]
        
        # Calculate total amount at this level
        subtotal = sum(Decimal(str(item.get('amount', 0))) for item in invoice_data['items'])
        discount_amount = Decimal(str(invoice_data.get('discount_amount', 0)))
        discount_percentage = Decimal(str(invoice_data.get('discount_percentage', 0)))
        
        # Calculate discount (either fixed amount or percentage)
        if discount_percentage > 0:
            calculated_discount = subtotal * (discount_percentage / 100)
        else:
            calculated_discount = discount_amount
        
        total_amount = subtotal - calculated_discount
        
        # Add the calculated values to invoice_data
        invoice_data['total_amount'] = total_amount
        invoice_data['calculated_discount'] = calculated_discount
        
        # Generate the invoice
        generator = InvoiceGenerator()
        result = generator.generate_invoice(invoice_data)
        
        if result['success']:
            payment_intent_id = result.get('payment_intent_id')
            reference_type = 'invoice_id' if payment_intent_id.split('_')[1] == 'inv' else 'admin_set'
            # Generate analytics data for the manual invoice
            analytics_data = generate_analytics_data(record_data, reference_type, result.get('payment_intent_id'))
            
            # Save invoice record to database
            current_timestamp = int(datetime.now(ZoneInfo('Australia/Perth')).timestamp())
            invoice_record = {
                'invoiceId': result.get('invoice_id'),
                'paymentIntentId': payment_intent_id,
                'referenceNumber': payment_intent_id,
                'referenceType': reference_type,
                's3Key': result['s3_key'],
                'fileUrl': result['file_url'],
                'fileSize': result.get('pdf_size', 0),
                'format': result.get('format', 'pdf'),  # Always PDF now
                'createdAt': current_timestamp,
                'status': 'generated',
                'analyticsData': analytics_data
            }
            
            # Add metadata for the manual invoice
            invoice_record['metadata'] = {
                'userName': record_data.get('customerName', 'N/A'),
                'userEmail': record_data.get('customerEmail', 'N/A'),
                'userPhone': record_data.get('customerPhone', 'N/A'),
                'paymentMethod': record_data.get('paymentMethod', 'unknown'),
                'paymentDate': payment_date,
                'paymentStatus': record_data.get('paymentStatus', 'completed'),
                'totalAmount': record_data.get('totalAmount', 0),
                'invoiceFormat': 'pdf',  # Always PDF now
            }
            
            try:
                create_result = db_utils.create_invoice_record(invoice_record)
                if not create_result:
                    print("Warning: Invoice generated but failed to save record to database")
            except Exception as db_error:
                print(f"Warning: Invoice generated but failed to save record to database: {db_error}")
                # Don't fail the invoice generation if database save fails
                
            # Add invoice_url to result for API response
            result['invoice_url'] = result['file_url']
            
            # Send payment confirmation email with actual invoice URL
            try:
                customer_email = record_data.get('customerEmail')
                customer_name = record_data.get('customerName', 'Valued Customer')
                
                if customer_email:
                    # Prepare payment data for email
                    payment_data = {
                        'amount': f"{record_data.get('totalAmount', 0):.2f}",
                        'paymentMethod': record_data.get('paymentMethod', 'Unknown'),
                        'referenceNumber': payment_intent_id,
                        'paymentDate': payment_date
                    }
                    
                    # Send final payment confirmation email with invoice
                    email.send_payment_confirmation_email(
                        customer_email, 
                        customer_name, 
                        payment_data, 
                        result['file_url']
                    )
                    print(f"Payment confirmation email sent to {customer_email}")
                else:
                    print("No customer email available for payment confirmation")
                    
            except Exception as email_error:
                print(f"Failed to send payment confirmation email: {str(email_error)}")
                # Don't fail the invoice generation if email fails
        
        return result
        
    except Exception as e:
        print(f"Error generating invoice for payment: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'error': str(e)
        }


def generate_analytics_data(record, record_type, payment_intent_id=None):
    """
    Generate analytics data for invoice records based on the format specified in analyticsData.md
    
    Args:
        record (dict): Appointment or order record, or manual payment data
        record_type (str): 'appointment', 'order', or 'manual'
        payment_intent_id (str, optional): Payment intent ID if available
        
    Returns:
        dict: Analytics data in the required format
    """
    try:
        # Import db_utils here to avoid circular imports
        import db_utils
        
        analytics_data = {
            "operation_type": "transaction",
            "operation_data": {
                "services": [],
                "orders": [],
                "customerId": "",
                "vehicleDetails": {},
                "paymentDetails": {},
                "bookingDetails": {}
            }
        }
        
        # Set customer ID (email)
        if record_type == 'appointment':
            if record.get('isBuyer'):
                analytics_data["operation_data"]["customerId"] = record.get('buyerEmail', '')
            else:
                analytics_data["operation_data"]["customerId"] = record.get('sellerEmail', '')
        elif record_type == 'order':
            analytics_data["operation_data"]["customerId"] = record.get('customerEmail', '')
        else:  # manual
            analytics_data["operation_data"]["customerId"] = record.get('customerEmail', '')
        
        # Set vehicle details
        vehicle_details = {
            "make": record.get('carMake', ''),
            "model": record.get('carModel', ''),
            "year": record.get('carYear', '')
        }
        analytics_data["operation_data"]["vehicleDetails"] = vehicle_details
        
        # Set payment details
        if record.get('paidAt'):
            # convert timestamp to date using Perth timezone
            payment_date = datetime.fromtimestamp(record.get('paidAt'), ZoneInfo('Australia/Perth')).strftime('%d/%m/%Y')
        else:
            payment_date = record.get('paymentDate', '')
        payment_method = record.get('paymentMethod', 'unknown')
        payment_amount = record.get('paymentAmount') or record.get('price') or record.get('totalAmount', 0)

        # Determine if payment was made before operation
        paid_before_operation = False
        if record_type in ['appointment', 'order']:
            # For booked appointments/orders, check if payment status is paid
            paid_before_operation = record.get('paymentStatus') == 'paid'
        # For manual transactions, always false as specified
        
        # Calculate effective date - use scheduled date if available, otherwise payment date
        effective_date = ''
        if record_type in ['appointment', 'order']:
            scheduled_date = record.get('scheduledDate', '')
            if scheduled_date:
                # Use validation function to convert to analytics format (DD/MM/YYYY)
                try:
                    effective_date = valid.DataValidator.validate_and_convert_date_to_analytics_format(
                        scheduled_date, 'scheduledDate'
                    )
                except valid.ValidationError as e:
                    print(f"Warning: Invalid scheduled date format '{scheduled_date}': {e.message}")
                    # Fall back to payment_date if scheduled_date is invalid
                    try:
                        effective_date = valid.DataValidator.validate_and_convert_date_to_analytics_format(
                            payment_date, 'paymentDate'
                        )
                    except valid.ValidationError:
                        effective_date = payment_date
            else:
                # Use payment_date and convert to analytics format
                try:
                    effective_date = valid.DataValidator.validate_and_convert_date_to_analytics_format(
                        payment_date, 'paymentDate'
                    )
                except valid.ValidationError:
                    effective_date = payment_date
        else:
            # For manual transactions, use payment date and convert to analytics format
            try:
                effective_date = valid.DataValidator.validate_and_convert_date_to_analytics_format(
                    payment_date, 'paymentDate'
                )
            except valid.ValidationError:
                effective_date = payment_date
        
        analytics_data["operation_data"]["paymentDetails"] = {
            "payment_method": payment_method,
            "amount": str(payment_amount),
            "date": payment_date,
            "paid_before_operation": 1 if paid_before_operation else 0
        }
        
        # Set effective date at operation_data level
        analytics_data["operation_data"]["effectiveDate"] = effective_date        # Set booking details
        booking_details = {
            "bookedBy": "",
            "bookedDate": "",
            "bookedAt": ""
        }
        
        if record_type == 'appointment' or record_type == 'order':
            created_user_id = record.get('createdUserId', '')
            
            # Determine bookedBy value
            if created_user_id:
                # Check if it's a staff member or regular user
                staff_record = db_utils.get_staff_record_by_user_id(created_user_id)
                if staff_record:
                    booking_details["bookedBy"] = "STAFF"
                else:
                    # Check if user exists in Users table
                    user_record = db_utils.get_user_record(created_user_id)
                    if user_record:
                        booking_details["bookedBy"] = created_user_id
                    else:
                        booking_details["bookedBy"] = "NONE"
            else:
                booking_details["bookedBy"] = "NONE"
            
            # Set booking date and timestamp
            if booking_details["bookedBy"] != "NONE":
                booking_details["bookedDate"] = record.get('createdDate', '')
                booking_details["bookedAt"] = str(record.get('createdAt', ''))
            
        else:  # manual transaction
            booking_details["bookedBy"] = "NONE"
        
        analytics_data["operation_data"]["bookingDetails"] = booking_details
        
        # Set services and orders based on record type
        if record_type == 'appointment':
            # For appointments, add service information
            service_id = record.get('serviceId')
            plan_id = record.get('planId')
            
            try:
                service_name, plan_name = db_utils.get_service_plan_names(service_id, plan_id)
            except:
                service_name, plan_name = "Unknown Service", "Unknown Plan"
            
            # Use plan name as service name as specified
            analytics_data["operation_data"]["services"].append({
                "service_name": plan_name,
                "price": str(record.get('price', 0))
            })
            
        elif record_type == 'order':
            # For orders, add items information
            order_items = record.get('items', [])
            
            for item in order_items:
                try:
                    category_name, item_name = db_utils.get_category_item_names(
                        item.get('categoryId'), 
                        item.get('itemId')
                    )
                except:
                    item_name = "Unknown Item"
                
                analytics_data["operation_data"]["orders"].append({
                    "item_name": item_name,
                    "unit_price": str(item.get('price', 0)),
                    "quantity": str(item.get('quantity', 1)),
                    "total_price": str(item.get('totalPrice', 0))
                })
                
        else:  # manual transaction
            # For manual transactions, extract from items in record
            items = record.get('items', [])
            
            for item in items:
                item_type = item.get('type', 'item')
                
                if item_type == 'service':
                    analytics_data["operation_data"]["services"].append({
                        "service_name": item.get('name', ''),
                        "price": str(item.get('totalAmount', 0))
                    })
                else:
                    analytics_data["operation_data"]["orders"].append({
                        "item_name": item.get('name', ''),
                        "unit_price": str(item.get('unitPrice', 0)),
                        "quantity": str(item.get('quantity', 1)),
                        "total_price": str(item.get('totalAmount', 0))
                    })
        
        return analytics_data
        
    except Exception as e:
        print(f"Error generating analytics data: {str(e)}")
        # Return a basic structure with empty data if generation fails
        return {
            "operation_type": "transaction",
            "operation_data": {
                "services": [],
                "orders": [],
                "customerId": "",
                "vehicleDetails": {
                    "make": "",
                    "model": "",
                    "year": ""
                },
                "paymentDetails": {
                    "payment_method": "unknown",
                    "amount": "0",
                    "date": "",
                    "paid_before_operation": 0
                },
                "bookingDetails": {
                    "bookedBy": "NONE",
                    "bookedDate": "",
                    "bookedAt": ""
                },
                "effectiveDate": ""
            }
        }

def update_invoice_effective_date(reference_number, reference_type, scheduled_date):
    """
    Update the effectiveDate in invoice analytics data when appointment/order is scheduled
    
    Args:
        reference_number (str): Reference number for appointment or order
        reference_type (str): 'appointment' or 'order'
        scheduled_date (str): Scheduled date in YYYY-MM-DD format
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        import db_utils
        from datetime import datetime
        
        # Get the existing invoice
        invoice = db_utils.get_invoice_by_reference(reference_number, reference_type)
        if not invoice:
            print(f"No invoice found for {reference_type} {reference_number}")
            return False
        
        # Get the analytics data
        analytics_data = invoice.get('analyticsData', {})
        if not analytics_data:
            print(f"No analytics data found in invoice for {reference_type} {reference_number}")
            return False
        
        # Convert scheduled_date from YYYY-MM-DD to DD/MM/YYYY format for consistency in Perth timezone
        try:
            # Parse the date and assign Perth timezone
            date_obj = datetime.strptime(scheduled_date, '%Y-%m-%d').replace(tzinfo=ZoneInfo('Australia/Perth'))
            effective_date = date_obj.strftime('%d/%m/%Y')
        except:
            print(f"Invalid date format for scheduled_date: {scheduled_date}")
            return False
        
        # Update the effectiveDate at operation_data level
        operation_data = analytics_data.get('operation_data', {})
        
        # Only update if the current effective date is different
        current_effective_date = operation_data.get('effectiveDate', '')
        if current_effective_date != effective_date:
            operation_data['effectiveDate'] = effective_date
            
            # Update the invoice analytics data
            success = db_utils.update_invoice_analytics_data(invoice['invoiceId'], analytics_data)
            if success:
                print(f"Updated effectiveDate to {effective_date} for invoice {invoice['invoiceId']}")
                return True
            else:
                print(f"Failed to update invoice analytics data for {invoice['invoiceId']}")
                return False
        else:
            print(f"EffectiveDate already set to {effective_date} for invoice {invoice['invoiceId']}")
            return True
        
    except Exception as e:
        print(f"Error updating invoice effective date: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
