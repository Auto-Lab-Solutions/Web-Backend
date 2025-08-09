import boto3
import os
import uuid
from datetime import datetime, timezone
from io import BytesIO
import base64
from decimal import Decimal
import json
import email_utils as email

# AWS clients
s3_client = boto3.client('s3')

# Environment variables
REPORTS_BUCKET = os.environ.get('REPORTS_BUCKET')
CLOUDFRONT_DOMAIN = os.environ.get('CLOUDFRONT_DOMAIN')
FRONTEND_ROOT_URL = os.environ.get('FRONTEND_ROOT_URL')

class InvoiceGenerator:
    """
    Invoice generator creating professional HTML invoices optimized for web and mobile viewing
    """
    
    def __init__(self):
        self.company_info = {
            'name': 'Auto Lab Solutions',
            'address': '70b Division St, Welshpool WA 6106, Australia',
            'phone': '+61 451 237 048',
            'email': 'autolabsolutions1@gmail.com',
            'website': 'www.autolabsolutions.com',
            'description': 'We deliver cutting-edge automotive inspection and repair solutions with state-of-the-art technology, expert service, and a commitment to safety and quality.'
        }
    
    def generate_invoice(self, invoice_data):
        """
        Generate an HTML invoice and upload to S3
        
        Args:
            invoice_data (dict): Invoice data containing:
                - payment_intent_id: Stripe payment intent ID
                - user_info: Customer information
                - items: List of service/item details
                - payment_info: Payment details
                - invoice_number: Invoice number
                - qr_code_url: (Optional) URL to encode in QR code
                - invoice_type: (Optional) "order" or "appointment" for context-specific QR messaging
                - discount_percentage: (Optional) Percentage discount
                - discount_amount: (Optional) Fixed discount amount
                - currency: (Optional) Currency code, defaults to 'AUD'
                - total_amount: (Optional) Pre-calculated total amount. If not provided, will be calculated from items and discounts
                - calculated_discount: (Optional) Pre-calculated discount amount for display purposes
                
        Returns:
            dict: {
                'success': bool,
                'invoice_id': str,
                's3_key': str,
                'file_url': str,
                'html_size': int,
                'format': str,
                'error': str (if any)
            }
        """
        try:
            # Set default currency if not provided
            if 'currency' not in invoice_data or not invoice_data.get('currency'):
                invoice_data['currency'] = 'AUD'
            
            # Generate unique invoice ID
            invoice_id = f"INV-{uuid.uuid4().hex[:8].upper()}"
            
            # Create HTML content
            try:
                html_content = self._create_html_invoice(invoice_data, invoice_id)
            except Exception as html_error:
                print(f"ERROR in _create_html_invoice: {html_error}")
                raise html_error
            
            # Generate HTML invoice
            try:
                html_bytes = html_content.encode('utf-8')
                s3_key = f"invoices/{datetime.now().year}/{datetime.now().month:02d}/{invoice_id}.html"
                
                upload_result = self._upload_html_to_s3(html_bytes, s3_key)
                
                if upload_result['success']:
                    return {
                        'success': True,
                        'invoice_id': invoice_id,
                        's3_key': s3_key,
                        'file_url': upload_result['file_url'],
                        'html_size': len(html_bytes),
                        'format': 'html'
                    }
                else:
                    return {
                        'success': False,
                        'error': upload_result.get('error', 'Failed to upload HTML invoice to S3')
                    }
                    
            except Exception as html_error:
                return {
                    'success': False,
                    'error': f"HTML invoice generation failed: {html_error}"
                }
                
        except Exception as e:
            print(f"Error generating invoice: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _create_html_invoice(self, invoice_data, invoice_id):
        """Create HTML content for the invoice"""
        
        # Get currency symbol
        currency_code = invoice_data.get('currency', 'AUD')
        currency_symbol = self._get_currency_symbol(currency_code)
        
        # Use pre-calculated values from invoice_data
        total_amount = Decimal(str(invoice_data.get('total_amount')))
        subtotal = sum(Decimal(str(item.get('amount', 0))) for item in invoice_data.get('items', []))
        calculated_discount = Decimal(str(invoice_data.get('calculated_discount', 0)))
        discount_amount = Decimal(str(invoice_data.get('discount_amount', 0)))
        discount_percentage = Decimal(str(invoice_data.get('discount_percentage', 0)))
        
        # Generate QR code if URL is provided and determine context
        qr_code_url = invoice_data.get('qr_code_url')
        qr_code_base64 = None
        qr_context = {
            'title': 'View Details',
            'description': 'Scan to access your information online'
        }
        
        # Generate QR code if URL is provided
        if qr_code_url:
            qr_code_base64 = self._generate_qr_code(qr_code_url)
        else:
            qr_code_base64 = None
            
        # Determine context based on invoice type or URL pattern
        invoice_type = invoice_data.get('invoice_type', '').lower()
        
        if qr_code_url and invoice_type == 'order' or (qr_code_url and 'order' in qr_code_url.lower()):
            qr_context = {
                'title': 'Track Your Order',
                'description': 'Scan to view order status'
            }
        elif qr_code_url and invoice_type == 'appointment' or (qr_code_url and 'appointment' in qr_code_url.lower()):
            qr_context = {
                'title': 'View Appointment',
                'description': 'Scan to view appointment status'
            }
        elif qr_code_url and 'service' in qr_code_url.lower():
            qr_context = {
                'title': 'Service Details',
                'description': 'Scan to view service details'
            }
        else:
            # Generic fallback
            qr_context = {
                'title': 'View Details Online',
                'description': 'Scan to access your information online'
            }
        
        # Format current date
        invoice_date = invoice_data.get('invoice_date', datetime.now().strftime('%d/%m/%Y'))
        html_template = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Invoice {invoice_id}</title>
            <style>
                @page {{
                    size: A4;
                    margin: 1cm;
                }}
                
                body {{
                    font-family: 'Arial', sans-serif;
                    font-size: 14px;
                    line-height: 1.6;
                    color: #0F172A;
                    margin: 0;
                    padding: 15px;
                    background-color: #ffffff;
                    min-height: 100vh;
                    display: flex;
                    flex-direction: column;
                }}
                
                .header {{
                    display: flex;
                    justify-content: space-between;
                    align-items: flex-start;
                    margin-bottom: 20px;
                    border-bottom: 3px solid #18181B;
                    background: linear-gradient(135deg, #27272a 0%, #18181B 100%);
                    color: #F3F4F6;
                    padding: 20px;
                    margin: -15px -15px 20px -15px;
                    gap: 20px;
                }}
                
                .company-info {{
                    flex: 1;
                }}
                
                .company-name {{
                    font-size: 38px;
                    font-weight: bold;
                    color: #22C55E;
                    margin-bottom: 6px;
                    text-shadow: 0 1px 2px rgba(0,0,0,0.3);
                    line-height: 1.2;
                }}
                
                .company-details {{
                    font-size: 14px;
                    color: #a1a1aa;
                    line-height: 1.4;
                }}
                
                .invoice-info {{
                    text-align: right;
                    flex: 1;
                }}
                
                .invoice-title {{
                    font-size: 48px;
                    font-weight: bold;
                    color: #F59E0B;
                    margin-bottom: 8px;
                    text-shadow: 0 1px 2px rgba(0,0,0,0.3);
                    line-height: 1.1;
                }}
                
                .invoice-number {{
                    font-size: 20px;
                    color: #F3F4F6;
                    margin-bottom: 4px;
                    font-weight: 600;
                }}
                
                .invoice-date {{
                    font-size: 16px;
                    color: #a1a1aa;
                }}
                
                .billing-section {{
                    display: flex;
                    justify-content: space-between;
                    margin-bottom: 25px;
                    gap: 20px;
                }}
                
                .billing-info {{
                    flex: 1;
                    background-color: #f8f9fa;
                    padding: 16px;
                    border-radius: 8px;
                    border-left: 4px solid #22C55E;
                }}
                
                .payment-info {{
                    flex: 1;
                    background-color: #f8f9fa;
                    padding: 16px;
                    border-radius: 8px;
                    border-left: 4px solid #F59E0B;
                }}
                
                .section-title {{
                    font-size: 18px;
                    font-weight: bold;
                    color: #18181B;
                    margin-bottom: 10px;
                    border-bottom: 2px solid #3f3f46;
                    padding-bottom: 4px;
                }}
                
                .billing-info div:not(.section-title) {{
                    font-size: 17px;
                    line-height: 1.5;
                }}
                
                .payment-info div:not(.section-title) {{
                    font-size: 17px;
                    line-height: 1.5;
                }}
                
                .items-table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-bottom: 25px;
                    border-radius: 8px;
                    overflow: hidden;
                    box-shadow: 0 2px 8px rgba(24, 24, 27, 0.1);
                }}
                
                .items-table th {{
                    background: linear-gradient(135deg, #27272a 0%, #18181B 100%);
                    color: #F3F4F6;
                    padding: 16px 14px;
                    text-align: left;
                    font-weight: bold;
                    font-size: 18px;
                    letter-spacing: 0.5px;
                    vertical-align: middle;
                }}
                
                .items-table th.text-center {{
                    text-align: center;
                }}
                
                .items-table th.text-right {{
                    text-align: right;
                }}
                
                .items-table td {{
                    padding: 16px 14px;
                    border-bottom: 1px solid #D1D5DB;
                    vertical-align: middle;
                    font-size: 18px;
                }}
                
                .items-table tr:nth-child(even) {{
                    background-color: #f8f9fa;
                }}
                
                .items-table tr:hover {{
                    background-color: rgba(34, 197, 94, 0.05);
                }}
                
                .text-right {{
                    text-align: right;
                }}
                
                .text-center {{
                    text-align: center;
                }}
                
                .totals-section {{
                    display: flex;
                    justify-content: flex-end;
                    align-items: flex-start;
                    margin-bottom: 40px;
                    gap: 25px;
                }}
                
                .totals-table {{
                    width: 350px;
                    border-collapse: collapse;
                    border-radius: 8px;
                    overflow: hidden;
                    box-shadow: 0 2px 8px rgba(24, 24, 27, 0.1);
                }}
                
                .totals-table td {{
                    padding: 14px 22px;
                    border-bottom: 1px solid #D1D5DB;
                    background-color: #f8f9fa;
                    font-size: 18px;
                }}
                
                .totals-table .total-row {{
                    font-weight: bold;
                    font-size: 22px;
                    background: linear-gradient(135deg, #22C55E 0%, #16A34A 100%);
                    color: #000000;
                    text-shadow: none;
                }}
                
                .totals-table .total-row td {{
                    color: #000000 !important;
                    font-weight: bold;
                }}
                
                .totals-table .subtotal-row {{
                    color: #18181B;
                    font-weight: 600;
                }}
                
                .totals-table .discount-row {{
                    color: #F59E0B;
                    font-weight: 600;
                    font-style: italic;
                }}
                
                .footer {{
                    margin-top: 40px;
                    padding-top: 18px;
                    border-top: 2px solid #D1D5DB;
                    font-size: 11px;
                    color: #71717A;
                    text-align: center;
                    background-color: #f8f9fa;
                    padding: 18px;
                    border-radius: 8px;
                }}
                
                .note-section {{
                    margin-top: 60px;
                    padding: 18px;
                    background: linear-gradient(135deg, rgba(34, 197, 94, 0.05) 0%, rgba(34, 197, 94, 0.02) 100%);
                    border-left: 5px solid #22C55E;
                    border-radius: 0 8px 8px 0;
                    box-shadow: 0 2px 4px rgba(34, 197, 94, 0.1);
                }}
                
                .note-title {{
                    font-weight: bold;
                    color: #18181B;
                    margin-bottom: 8px;
                    font-size: 14px;
                }}
                
                .note-section div:not(.note-title) {{
                    font-size: 14px;
                }}
                
                .payment-status {{
                    color: #22C55E;
                    font-weight: 700;
                    font-size: 17px;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }}
                
                .amount-highlight {{
                    color: #18181B;
                    font-weight: bold;
                }}
                
                .payment-method {{
                    color: #1D4ED8;
                    font-weight: 600;
                    font-size: 17px;
                }}
                
                .qr-code-section {{
                    width: 200px;
                    padding: 18px;
                    background: linear-gradient(135deg, rgba(34, 197, 94, 0.05) 0%, rgba(34, 197, 94, 0.02) 100%);
                    border: 2px solid #22C55E;
                    border-radius: 8px;
                    text-align: center;
                    box-shadow: 0 2px 8px rgba(34, 197, 94, 0.1);
                }}
                
                .qr-code-title {{
                    font-weight: bold;
                    color: #18181B;
                    margin-bottom: 12px;
                    font-size: 13px;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }}
                
                .qr-code-image {{
                    display: inline-block;
                    padding: 6px;
                    background-color: white;
                    border-radius: 6px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                    margin-bottom: 8px;
                }}
                
                .qr-code-description {{
                    font-size: 11px;
                    color: #71717A;
                    margin-top: 6px;
                    line-height: 1.3;
                    font-style: italic;
                }}
                
                .main-content {{
                    flex: 1;
                    display: flex;
                    flex-direction: column;
                }}
                
                .content-spacer {{
                    flex: 1;
                    min-height: 40px;
                }}
                
                .company-details-mobile {{
                    display: none;
                }}
                
                .company-details-desktop {{
                    display: block;
                }}
                
                /* Mobile responsive styles */
                @media screen and (max-width: 768px) {{
                    body {{
                        font-size: 12px !important;
                        padding: 10px !important;
                    }}
                    
                    .company-name {{
                        font-size: 24px !important;
                    }}
                    
                    .company-details {{
                        font-size: 10px !important;
                    }}
                    
                    .invoice-title {{
                        font-size: 36px !important;
                    }}
                    
                    .invoice-number {{
                        font-size: 16px !important;
                    }}
                    
                    .invoice-date {{
                        font-size: 12px !important;
                    }}
                    
                    .section-title {{
                        font-size: 14px !important;
                    }}
                    
                    .billing-info div:not(.section-title) {{
                        font-size: 14px !important;
                    }}
                    
                    .payment-info div:not(.section-title) {{
                        font-size: 14px !important;
                    }}
                    
                    .billing-info div:not(.section-title) span {{
                        font-size: 14px !important;
                    }}
                    
                    .payment-info div:not(.section-title) span {{
                        font-size: 14px !important;
                    }}
                    
                    .items-table th {{
                        font-size: 14px !important;
                        padding: 10px 12px !important;
                        font-weight: 700 !important;
                    }}
                    
                    .items-table td {{
                        font-size: 12px !important;
                        padding: 8px 12px !important;
                    }}
                    
                    .item-name {{
                        font-size: 16px !important;
                        font-weight: 600 !important;
                    }}
                    
                    .item-description {{
                        font-size: 11px !important;
                    }}
                    
                    .totals-table td {{
                        font-size: 12px !important;
                        padding: 8px 12px !important;
                    }}
                    
                    .totals-table .total-row {{
                        font-size: 16px !important;
                    }}
                    
                    .payment-status {{
                        font-size: 12px !important;
                    }}
                    
                    .payment-method {{
                        font-size: 12px !important;
                    }}
                    
                    .qr-code-section {{
                        width: 180px !important;
                        padding: 20px !important;
                    }}
                    
                    .qr-code-title {{
                        font-size: 14px !important;
                    }}
                    
                    .qr-code-description {{
                        font-size: 12px !important;
                    }}
                    
                    .qr-code-image img {{
                        width: 100px !important;
                        height: 100px !important;
                    }}
                    
                    .footer {{
                        font-size: 8px !important;
                        padding: 12px !important;
                    }}
                    
                    .note-section {{
                        padding: 12px !important;
                    }}
                    
                    .note-title {{
                        font-size: 10px !important;
                    }}
                    
                    .note-section div:not(.note-title) {{
                        font-size: 9px !important;
                    }}
                    
                    .header {{
                        flex-direction: row !important;
                        justify-content: space-between !important;
                        align-items: flex-start !important;
                        text-align: left !important;
                        gap: 15px !important;
                    }}
                    
                    .company-info {{
                        flex: 1 !important;
                        text-align: left !important;
                        order: 1 !important;
                    }}
                    
                    .invoice-info {{
                        flex: 1 !important;
                        text-align: right !important;
                        order: 2 !important;
                        margin-left: auto !important;
                    }}
                    
                    .invoice-info * {{
                        text-align: right !important;
                    }}
                    
                    .company-details-mobile {{
                        display: block !important;
                    }}
                    
                    .company-details-desktop {{
                        display: none !important;
                    }}
                    
                    .billing-section {{
                        flex-direction: column !important;
                        gap: 15px !important;
                    }}
                    
                    .totals-section {{
                        flex-direction: column !important;
                        align-items: flex-end !important;
                        gap: 15px !important;
                    }}
                    
                    .qr-code-section {{
                        order: 2 !important;
                        align-self: center !important;
                    }}
                    
                    .totals-table {{
                        order: 1 !important;
                        width: 100% !important;
                        max-width: 300px !important;
                    }}
                }}
                
                @media screen and (max-width: 480px) {{
                    body {{
                        font-size: 10px !important;
                        padding: 5px !important;
                    }}
                    
                    .company-name {{
                        font-size: 18px !important;
                    }}
                    
                    .invoice-title {{
                        font-size: 32px !important;
                    }}
                    
                    .items-table th {{
                        font-size: 12px !important;
                        padding: 8px 10px !important;
                        font-weight: 700 !important;
                    }}
                    
                    .items-table th,
                    .items-table td {{
                        font-size: 10px !important;
                        padding: 6px 10px !important;
                    }}
                    
                    .item-name {{
                        font-size: 14px !important;
                        font-weight: 600 !important;
                    }}
                    
                    .item-description {{
                        font-size: 10px !important;
                    }}
                    
                    .totals-table td {{
                        font-size: 10px !important;
                        padding: 6px 8px !important;
                    }}
                    
                    .totals-table .total-row {{
                        font-size: 14px !important;
                    }}
                    
                    .qr-code-section {{
                        width: 160px !important;
                        padding: 16px !important;
                        order: 2 !important;
                        align-self: center !important;
                    }}
                    
                    .qr-code-title {{
                        font-size: 12px !important;
                    }}
                    
                    .qr-code-description {{
                        font-size: 10px !important;
                    }}
                    
                    .qr-code-image img {{
                        width: 90px !important;
                        height: 90px !important;
                    }}
                    
                    .footer {{
                        font-size: 7px !important;
                        padding: 8px !important;
                    }}
                    
                    .note-section div:not(.note-title) {{
                        font-size: 8px !important;
                    }}
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <div class="company-info">
                    <div class="company-name">{self.company_info['name']}</div>
                    <div class="company-details company-details-desktop">
                        {self.company_info['address']}<br>
                        Phone: {self.company_info['phone']}<br>
                        Email: {self.company_info['email']}<br>
                        Website: {self.company_info['website']}
                    </div>
                    <div class="company-details company-details-mobile">
                        {self.company_info['address']}<br>
                        {self.company_info['phone']}<br>
                        {self.company_info['email']}<br>
                        {self.company_info['website']}
                    </div>
                </div>
                <div class="invoice-info">
                    <div class="invoice-title">INVOICE</div>
                    <div class="invoice-number">#{invoice_id}</div>
                    <div class="invoice-date">Date: {invoice_date}</div>
                </div>
            </div>
            
            <div class="main-content">
                <div class="billing-section">
                    <div class="billing-info">
                        <div class="section-title">Billed To:</div>
                        <div>
                            <strong style="color: #18181B; font-size: 17px;">{invoice_data.get('user_info', {}).get('name', 'N/A')}</strong><br>
                            <span style="color: #3f3f46; font-size: 17px;">{invoice_data.get('user_info', {}).get('email', 'N/A')}</span><br>
                            <span style="color: #3f3f46; font-size: 17px;">{invoice_data.get('user_info', {}).get('phone', '')}</span><br>
                        </div>
                    </div>
                    <div class="payment-info">
                        <div class="section-title">Payment Information:</div>
                        <div>
                            Payment Method: <span class="payment-method">{invoice_data.get('payment_info', {}).get('method', 'N/A').upper()}</span><br>
                            Payment Status: <span class="payment-status">{invoice_data.get('payment_info', {}).get('status', 'N/A')}</span><br>
                            Reference: <span style="color: #3f3f46; font-size: 17px;">{invoice_data.get('payment_intent_id', 'N/A')}</span><br>
                            Transaction Date: <span style="color: #18181B; font-weight: 600; font-size: 17px;">{invoice_data.get('payment_info', {}).get('date', invoice_date)}</span>
                        </div>
                    </div>
                </div>
            
            <table class="items-table">
                <thead>
                    <tr>
                        <th style="width: 50%">Item/Service</th>
                        <th style="width: 15%" class="text-center">Quantity</th>
                        <th style="width: 17.5%" class="text-right">Unit Price ({currency_symbol})</th>
                        <th style="width: 17.5%" class="text-right">Amount ({currency_symbol})</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        # Add items to the table
        for item in invoice_data.get('items', []):
            item_name = item.get('name', 'N/A')
            item_description = item.get('description', '')
            quantity = item.get('quantity', 1)
            unit_price = Decimal(str(item.get('unit_price', 0)))
            amount = Decimal(str(item.get('amount', 0)))
            
            if item_description:
                item_display = f"<span class='item-name'>{item_name}</span><br><small class='item-description' style='color: #71717A; font-style: italic; font-size: 16px;'>{item_description}</small>"
            else:
                item_display = f"<span class='item-name'>{item_name}</span>"
            
            html_template += f"""
                    <tr>
                        <td style="color: #18181B; font-weight: 500; font-size: 18px;">{item_display}</td>
                        <td class="text-center" style="color: #3f3f46; font-weight: 600; font-size: 18px;">{quantity}</td>
                        <td class="text-right" style="color: #18181B; font-weight: bold; font-size: 18px;">{currency_symbol} {unit_price:.2f}</td>
                        <td class="text-right" style="color: #18181B; font-weight: bold; font-size: 18px;">{currency_symbol} {amount:.2f}</td>
                    </tr>
            """
        
        html_template += f"""
                </tbody>
            </table>
            
            <div class="totals-section">"""
        
        # Add QR code section first if QR code is available
        if qr_code_base64:
            html_template += f"""
                <div class="qr-code-section">
                    <div class="qr-code-title">{qr_context['title']}</div>
                    <div class="qr-code-image">
                        <img src="data:image/png;base64,{qr_code_base64}" alt="QR Code" style="width: 100px; height: 100px;"/>
                    </div>
                    <div class="qr-code-description">
                        {qr_context['description']}
                    </div>
                </div>"""
        
        html_template += f"""
                <table class="totals-table">
                    <tr class="subtotal-row">
                        <td style="color: #18181B;">Subtotal:</td>
                        <td class="text-right" style="color: #18181B; font-weight: bold;">{currency_symbol} {subtotal:.2f}</td>
                    </tr>"""
        
        # Add discount row only if there's a discount
        if calculated_discount > 0:
            if discount_percentage > 0:
                discount_label = f"Discount ({discount_percentage:.1f}%):"
            else:
                discount_label = "Discount:"
            
            html_template += f"""
                    <tr class="discount-row">
                        <td style="color: #F59E0B;">{discount_label}</td>
                        <td class="text-right" style="color: #F59E0B; font-weight: bold;">-{currency_symbol} {calculated_discount:.2f}</td>
                    </tr>"""
        
        html_template += f"""
                    <tr class="total-row">
                        <td style="color: #000000; font-weight: bold;">TOTAL:</td>
                        <td class="text-right" style="color: #000000; font-weight: bold;">{currency_symbol} {total_amount:.2f}</td>
                    </tr>
                </table>
            </div>
            
            <div class="content-spacer"></div>
            
            <div class="note-section">
                <div class="note-title">Thank You for Your Business!</div>
                <div style="color: #3f3f46;">Thank you for choosing <strong style="color: #22C55E;">{self.company_info['name']}</strong>! This invoice has been automatically generated for your payment. We appreciate your trust in our automotive services.</div>
            </div>
            </div>
            
            <div class="footer">
                <div style="margin-bottom: 10px;">
                    <strong style="color: #18181B;">Auto Lab Solutions</strong> - Professional Automotive Inspection Services
                </div>
                <div style="margin-bottom: 8px; color: #3f3f46;">
                    We deliver cutting-edge automotive inspection and repair solutions with expert service and a commitment to safety and quality.
                </div>
                <div>
                    This is a computer-generated invoice. For any queries, please contact us at <strong style="color: #22C55E;">{self.company_info['email']}</strong>.
                </div>
            </div>
        </body>
        </html>
        """
        
        return html_template
    
    def _upload_html_to_s3(self, html_bytes, s3_key):
        """Upload HTML invoice to S3 bucket"""
        try:
            if not REPORTS_BUCKET or not CLOUDFRONT_DOMAIN:
                raise ValueError("REPORTS_BUCKET or CLOUDFRONT_DOMAIN environment variable not set")

            s3_client.put_object(
                Bucket=REPORTS_BUCKET,
                Key=s3_key,
                Body=html_bytes,
                ContentType='text/html',
                Metadata={
                    'generated_at': datetime.now(timezone.utc).isoformat(),
                    'generator': 'auto-lab-invoice-generator',
                    'format': 'html'
                }
            )
            
            # Generate file URL (assuming CloudFront distribution)
            file_url = f"https://{CLOUDFRONT_DOMAIN}/{s3_key}"

            return {
                'success': True,
                'file_url': file_url
            }
            
        except Exception as e:
            print(f"Error uploading HTML to S3: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    def _generate_qr_code(self, url):
        """
        Generate a QR code for the given URL and return it as base64 encoded string
        
        Args:
            url (str): The URL to encode in the QR code
            
        Returns:
            str: Base64 encoded QR code image or None if generation fails
        """
        try:
            # Import qrcode with error handling
            try:
                import qrcode
            except ImportError as import_error:
                return None
            except Exception as import_error:
                return None
            
            # Create QR code
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            
            qr.add_data(url)
            qr.make(fit=True)
            
            # Create image
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Convert to base64
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode()
            
            return img_str
            
        except Exception as e:
            return None

    def _get_currency_symbol(self, currency_code):
        """Get currency symbol for display"""
        currency_symbols = {
            'AUD': 'A$',
            'USD': '$',
            'EUR': '€',
            'GBP': '£',
            'JPY': '¥',
            'CAD': 'C$',
            'NZD': 'NZ$'
        }
        return currency_symbols.get(currency_code.upper(), currency_code.upper())


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
                'quantity': 1,
                'unit_price': float(record.get('price', 0)),
                'amount': float(record.get('price', 0))
            })
        
        # Payment information
        payment_info = {
            'method': record.get('paymentMethod', 'Unknown'),
            'status': 'completed' if record.get('paymentStatus') == 'paid' else 'pending',
            'date': datetime.now().strftime('%d/%m/%Y')
        }
        
        # Generate QR code URL for order/appointment tracking
        reference_id = record.get(f'{record_type}Id')
        qr_code_url = f"{FRONTEND_ROOT_URL}/{record_type}/{reference_id}"
        
        # Prepare invoice data
        invoice_data = {
            'payment_intent_id': payment_intent_id or 'N/A',
            'currency': record.get('currency', 'AUD'),
            'invoice_date': datetime.now().strftime('%d/%m/%Y'),
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
            # Save invoice record to database
            current_timestamp = int(datetime.now().timestamp())
            invoice_record = {
                'invoiceId': result['invoice_id'],
                'paymentIntentId': payment_intent_id or 'N/A',
                'referenceNumber': reference_id,
                'referenceType': record_type,
                's3Key': result['s3_key'],
                'fileUrl': result['file_url'],
                'fileSize': result.get('html_size', 0),
                'format': 'html',
                'createdAt': current_timestamp,
                'invoiceDate': datetime.fromtimestamp(current_timestamp).strftime('%d/%m/%Y'),
                'status': 'generated'
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
                'invoiceFormat': 'html'
            }
            
            try:
                create_result = db_utils.create_invoice_record(invoice_record)
            except Exception as db_error:
                create_result = False
                
            if not create_result:
                print("Warning: Invoice generated but failed to save record to database")
            
            # Add invoice_url to result for updating the order/appointment record
            result['invoice_url'] = result['file_url']
        
        return result
        
    except Exception as e:
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
        
        # Prepare invoice data
        invoice_data = {
            'payment_intent_id': record_data.get('paymentIntentId'),
            'currency': record_data.get('currency', 'AUD'),
            'invoice_date': record_data.get('invoiceDate', 
                datetime.fromtimestamp(
                    int(record_data.get('createdAt', datetime.now().timestamp()))
                ).strftime('%d/%m/%Y')
            ),
            'user_info': {
                'name': record_data.get('customerName', 'Valued Customer'),
                'email': record_data.get('customerEmail', ''),
                'phone': record_data.get('customerPhone', '')
            },
            'payment_info': {
                'method': record_data.get('paymentMethod', 'Card'),
                'status': record_data.get('paymentStatus', 'completed'),
                'date': record_data.get('paymentDate', record_data.get('invoiceDate', 
                    datetime.fromtimestamp(
                        int(record_data.get('createdAt', datetime.now().timestamp()))
                    ).strftime('%d/%m/%Y')
                ))
            },
            'items': [],
            'discount_amount': 0,  # Default no discount
            'discount_percentage': 0,  # Default no percentage discount
        }
        
        # Add items from payment data (new API structure)
        if record_data.get('items'):
            processed_items = []
            for item in record_data['items']:
                processed_item = {
                    'name': item.get('name', 'Service'),
                    'description': item.get('description', ''),
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
            # Save invoice record to database
            current_timestamp = int(datetime.now().timestamp())
            invoice_record = {
                'invoiceId': result['invoice_id'],
                'paymentIntentId': record_data.get('paymentIntentId', 'N/A'),
                'referenceNumber': record_data.get('invoiceId', result['invoice_id']),
                'referenceType': 'api_generated',
                's3Key': result['s3_key'],
                'fileUrl': result['file_url'],
                'fileSize': result.get('html_size', 0),
                'format': 'html',
                'createdAt': current_timestamp,
                'invoiceDate': datetime.fromtimestamp(current_timestamp).strftime('%d/%m/%Y'),
                'status': 'generated'
            }
            
            # Add metadata for the manual invoice
            invoice_record['metadata'] = {
                'userName': record_data.get('customerName', 'N/A'),
                'userEmail': record_data.get('customerEmail', 'N/A'),
                'userPhone': record_data.get('customerPhone', 'N/A'),
                'paymentMethod': record_data.get('paymentMethod', 'unknown'),
                'paymentStatus': record_data.get('paymentStatus', 'completed'),
                'totalAmount': record_data.get('totalAmount', 0),
                'invoiceFormat': 'html',
                'invoiceType': 'manual'
            }
            
            try:
                create_result = db_utils.create_invoice_record(invoice_record)
                if not create_result:
                    print("Warning: Invoice generated but failed to save record to database")
            except Exception as db_error:
                print(f"Warning: Invoice generated but failed to save record to database: {db_error}")
            
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
                        'referenceNumber': record_data.get('invoiceId', result['invoice_id']),
                        'paymentDate': current_timestamp
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
        return {
            'success': False,
            'error': str(e)
        }
