import boto3
import os
import uuid
from datetime import datetime, timezone
from io import BytesIO
import base64
from decimal import Decimal
import json

# AWS clients
s3_client = boto3.client('s3')

# Environment variables
REPORTS_BUCKET = os.environ.get('REPORTS_BUCKET')
CLOUDFRONT_DOMAIN = os.environ.get('CLOUDFRONT_DOMAIN')
FRONTEND_ROOT_URL = os.environ.get('FRONTEND_ROOT_URL')

class InvoiceGenerator:
    """
    Invoice generator using WeasyPrint to create PDF invoices
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
        Generate a PDF invoice and upload to S3
        
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
                
        Returns:
            dict: {
                'success': bool,
                'invoice_id': str,
                's3_key': str,
                'file_url': str,
                'error': str (if any)
            }
        """
        try:
            # Generate unique invoice ID
            invoice_id = f"INV-{uuid.uuid4().hex[:8].upper()}"
            
            # Create HTML content
            try:
                html_content = self._create_html_invoice(invoice_data, invoice_id)
            except Exception as html_error:
                print(f"ERROR in _create_html_invoice: {html_error}")
                raise html_error
            
            # Generate PDF
            try:
                pdf_bytes = self._html_to_pdf(html_content)
                print(f"PDF generated successfully (size: {len(pdf_bytes)} bytes)")
                
                # Upload to S3
                s3_key = f"invoices/{datetime.now().year}/{datetime.now().month:02d}/{invoice_id}.pdf"
                upload_result = self._upload_to_s3(pdf_bytes, s3_key)
                
                if upload_result['success']:
                    return {
                        'success': True,
                        'invoice_id': invoice_id,
                        's3_key': s3_key,
                        'file_url': upload_result['file_url'],
                        'pdf_size': len(pdf_bytes),
                        'format': 'pdf'
                    }
                else:
                    return {
                        'success': False,
                        'error': upload_result.get('error', 'Failed to upload PDF to S3')
                    }
            except Exception as pdf_error:
                print(f"PDF generation failed: {pdf_error}")
                
                # Fallback: Upload HTML content instead
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
                            'format': 'html',
                            'note': 'Generated as HTML due to PDF conversion limitations in Lambda environment'
                        }
                    else:
                        return {
                            'success': False,
                            'error': f"Both PDF and HTML upload failed. PDF error: {pdf_error}. HTML error: {upload_result.get('error')}"
                        }
                except Exception as html_error:
                    return {
                        'success': False,
                        'error': f"PDF generation failed: {pdf_error}. HTML fallback also failed: {html_error}"
                    }
                
        except Exception as e:
            print(f"Error generating invoice: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _create_html_invoice(self, invoice_data, invoice_id):
        """Create HTML content for the invoice"""
        
        # Calculate totals
        subtotal = sum(Decimal(str(item.get('amount', 0))) for item in invoice_data.get('items', []))
        discount_amount = Decimal(str(invoice_data.get('discount_amount', 0)))
        discount_percentage = Decimal(str(invoice_data.get('discount_percentage', 0)))
        
        # Calculate discount (either fixed amount or percentage)
        if discount_percentage > 0:
            calculated_discount = subtotal * (discount_percentage / 100)
        else:
            calculated_discount = discount_amount
        
        total_amount = subtotal - calculated_discount
        
        # Generate QR code if URL is provided and determine context
        qr_code_url = invoice_data.get('qr_code_url')
        qr_code_base64 = None
        qr_context = {
            'title': 'View Details',
            'description': 'Scan to access your information online'
        }
        
        # Skip QR code generation in Lambda environment to avoid hanging
        print("Skipping QR code generation to avoid import hang in Lambda environment")
        print(f"QR code URL would have been: {qr_code_url}")
        qr_code_base64 = None
            
        print("Setting QR context based on invoice type...")
        # Determine context based on invoice type or URL pattern
        invoice_type = invoice_data.get('invoice_type', '').lower()
        print(f"Invoice type: {invoice_type}")
        
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
        print(f"QR context set: {qr_context}")
        
        print("Formatting current date...")
        # Format current date
        current_date = datetime.now().strftime('%d/%m/%Y')
        print(f"Current date: {current_date}")
        
        print("Creating HTML template...")
        html_template = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Invoice {invoice_id}</title>
            <style>
                @page {{
                    size: A4;
                    margin: 1cm;
                }}
                
                body {{
                    font-family: 'Arial', sans-serif;
                    font-size: 12px;
                    line-height: 1.6;
                    color: #0F172A;
                    margin: 0;
                    padding: 20px;
                    background-color: #ffffff;
                }}
                
                .header {{
                    display: flex;
                    justify-content: space-between;
                    align-items: flex-start;
                    margin-bottom: 30px;
                    border-bottom: 3px solid #18181B;
                    padding-bottom: 20px;
                    background: linear-gradient(135deg, #27272a 0%, #18181B 100%);
                    color: #F3F4F6;
                    padding: 25px;
                    margin: -20px -20px 30px -20px;
                }}
                
                .company-info {{
                    flex: 1;
                }}
                
                .company-name {{
                    font-size: 26px;
                    font-weight: bold;
                    color: #22C55E;
                    margin-bottom: 8px;
                    text-shadow: 0 1px 2px rgba(0,0,0,0.3);
                }}
                
                .company-details {{
                    font-size: 11px;
                    color: #a1a1aa;
                    line-height: 1.5;
                }}
                
                .invoice-info {{
                    text-align: right;
                    flex: 1;
                }}
                
                .invoice-title {{
                    font-size: 32px;
                    font-weight: bold;
                    color: #F59E0B;
                    margin-bottom: 10px;
                    text-shadow: 0 1px 2px rgba(0,0,0,0.3);
                }}
                
                .invoice-number {{
                    font-size: 15px;
                    color: #F3F4F6;
                    margin-bottom: 5px;
                    font-weight: 600;
                }}
                
                .invoice-date {{
                    font-size: 12px;
                    color: #a1a1aa;
                }}
                
                .billing-section {{
                    display: flex;
                    justify-content: space-between;
                    margin-bottom: 30px;
                    gap: 30px;
                }}
                
                .billing-info {{
                    flex: 1;
                    background-color: #f8f9fa;
                    padding: 20px;
                    border-radius: 8px;
                    border-left: 4px solid #22C55E;
                }}
                
                .payment-info {{
                    flex: 1;
                    background-color: #f8f9fa;
                    padding: 20px;
                    border-radius: 8px;
                    border-left: 4px solid #F59E0B;
                }}
                
                .section-title {{
                    font-size: 14px;
                    font-weight: bold;
                    color: #18181B;
                    margin-bottom: 12px;
                    border-bottom: 2px solid #3f3f46;
                    padding-bottom: 6px;
                }}
                
                .items-table {{
                    width: 100%;
                    border-collapse: collapse;
                    margin-bottom: 30px;
                    border-radius: 8px;
                    overflow: hidden;
                    box-shadow: 0 2px 8px rgba(24, 24, 27, 0.1);
                }}
                
                .items-table th {{
                    background: linear-gradient(135deg, #27272a 0%, #18181B 100%);
                    color: #F3F4F6;
                    padding: 15px 12px;
                    text-align: left;
                    font-weight: bold;
                    font-size: 13px;
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
                    padding: 12px 12px;
                    border-bottom: 1px solid #D1D5DB;
                    vertical-align: middle;
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
                    justify-content: space-between;
                    align-items: flex-start;
                    margin-bottom: 30px;
                    gap: 30px;
                }}
                
                .totals-table {{
                    width: 320px;
                    border-collapse: collapse;
                    border-radius: 8px;
                    overflow: hidden;
                    box-shadow: 0 2px 8px rgba(24, 24, 27, 0.1);
                }}
                
                .totals-table td {{
                    padding: 12px 20px;
                    border-bottom: 1px solid #D1D5DB;
                    background-color: #f8f9fa;
                }}
                
                .totals-table .total-row {{
                    font-weight: bold;
                    font-size: 16px;
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
                    padding-top: 20px;
                    border-top: 2px solid #D1D5DB;
                    font-size: 11px;
                    color: #71717A;
                    text-align: center;
                    background-color: #f8f9fa;
                    padding: 20px;
                    border-radius: 8px;
                }}
                
                .note-section {{
                    margin-top: 30px;
                    padding: 20px;
                    background: linear-gradient(135deg, rgba(34, 197, 94, 0.05) 0%, rgba(34, 197, 94, 0.02) 100%);
                    border-left: 5px solid #22C55E;
                    border-radius: 0 8px 8px 0;
                    box-shadow: 0 2px 4px rgba(34, 197, 94, 0.1);
                }}
                
                .note-title {{
                    font-weight: bold;
                    color: #18181B;
                    margin-bottom: 8px;
                    font-size: 13px;
                }}
                
                .status-badge {{
                    display: inline-block;
                    padding: 4px 12px;
                    background-color: #22C55E;
                    color: white;
                    border-radius: 20px;
                    font-size: 11px;
                    font-weight: bold;
                    text-transform: uppercase;
                    letter-spacing: 0.5px;
                }}
                
                .amount-highlight {{
                    color: #18181B;
                    font-weight: bold;
                }}
                
                .payment-method {{
                    color: #F59E0B;
                    font-weight: 600;
                }}
                
                .qr-code-section {{
                    width: 180px;
                    padding: 15px;
                    background: linear-gradient(135deg, rgba(34, 197, 94, 0.05) 0%, rgba(34, 197, 94, 0.02) 100%);
                    border: 2px solid #22C55E;
                    border-radius: 8px;
                    text-align: center;
                    box-shadow: 0 2px 8px rgba(34, 197, 94, 0.1);
                }}
                
                .qr-code-title {{
                    font-weight: bold;
                    color: #18181B;
                    margin-bottom: 10px;
                    font-size: 11px;
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
                    font-size: 9px;
                    color: #71717A;
                    margin-top: 6px;
                    line-height: 1.3;
                    font-style: italic;
                }}
            </style>
        </head>
        <body>
            <div class="header">
                <div class="company-info">
                    <div class="company-name">{self.company_info['name']}</div>
                    <div class="company-details">
                        {self.company_info['address']}<br>
                        Phone: {self.company_info['phone']}<br>
                        Email: {self.company_info['email']}<br>
                        Website: {self.company_info['website']}
                    </div>
                </div>
                <div class="invoice-info">
                    <div class="invoice-title">INVOICE</div>
                    <div class="invoice-number">#{invoice_id}</div>
                    <div class="invoice-date">Date: {current_date}</div>
                </div>
            </div>                <div class="billing-section">
                <div class="billing-info">
                    <div class="section-title">Billed To:</div>
                    <div>
                        <strong style="color: #18181B; font-size: 14px;">{invoice_data.get('user_info', {}).get('name', 'N/A')}</strong><br>
                        <span style="color: #3f3f46;">{invoice_data.get('user_info', {}).get('email', 'N/A')}</span><br>
                        <span style="color: #3f3f46;">{invoice_data.get('user_info', {}).get('phone', '')}</span><br>
                    </div>
                </div>
                <div class="payment-info">
                    <div class="section-title">Payment Information:</div>
                    <div>
                        Payment Method: <span class="payment-method">{invoice_data.get('payment_info', {}).get('method', 'N/A')}</span><br>
                        Payment Status: <span class="status-badge">{invoice_data.get('payment_info', {}).get('status', 'N/A')}</span><br>
                        Reference: <span style="color: #3f3f46; font-family: monospace; font-size: 11px;">{invoice_data.get('payment_intent_id', 'N/A')}</span><br>
                        Transaction Date: <span style="color: #18181B; font-weight: 600;">{invoice_data.get('payment_info', {}).get('date', current_date)}</span>
                    </div>
                </div>
            </div>
            
            <table class="items-table">
                <thead>
                    <tr>
                        <th style="width: 50%">Item/Service</th>
                        <th style="width: 15%" class="text-center">Quantity</th>
                        <th style="width: 17.5%" class="text-right">Unit Price</th>
                        <th style="width: 17.5%" class="text-right">Amount</th>
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
                item_display = f"{item_name}<br><small style='color: #71717A; font-style: italic;'>{item_description}</small>"
            else:
                item_display = item_name
            
            html_template += f"""
                    <tr>
                        <td style="color: #18181B; font-weight: 500;">{item_display}</td>
                        <td class="text-center" style="color: #3f3f46; font-weight: 600;">{quantity}</td>
                        <td class="text-right" style="color: #18181B; font-weight: bold;">${unit_price:.2f}</td>
                        <td class="text-right" style="color: #18181B; font-weight: bold;">${amount:.2f}</td>
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
                        <td class="text-right" style="color: #18181B; font-weight: bold;">${subtotal:.2f}</td>
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
                        <td class="text-right" style="color: #F59E0B; font-weight: bold;">-${calculated_discount:.2f}</td>
                    </tr>"""
        
        html_template += f"""
                    <tr class="total-row">
                        <td style="color: #000000; font-weight: bold;">TOTAL:</td>
                        <td class="text-right" style="color: #000000; font-weight: bold;">${total_amount:.2f}</td>
                    </tr>
                </table>
            </div>
            
            <div class="note-section">
                <div class="note-title">Thank You for Your Business!</div>
                <div style="color: #3f3f46;">Thank you for choosing <strong style="color: #22C55E;">{self.company_info['name']}</strong>! This invoice has been automatically generated for your payment. We appreciate your trust in our automotive services.</div>
            </div>"""
        
        html_template += f"""
            
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
        
        print(f"HTML template created successfully (length: {len(html_template)} chars)")
        return html_template
    
    def _html_to_pdf(self, html_content):
        """Convert HTML to PDF using WeasyPrint"""
        try:
            print("=== Starting HTML to PDF conversion ===")
            print(f"HTML content length: {len(html_content)} chars")
            
            # Add timeout protection for WeasyPrint import
            import signal
            import sys
            
            def timeout_handler(signum, frame):
                raise TimeoutError("WeasyPrint import timed out")
            
            # Set a 10-second timeout for the import
            print("Setting timeout for WeasyPrint import...")
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(10)  # 10 second timeout
            
            try:
                print("Importing WeasyPrint with timeout protection...")
                from weasyprint import HTML
                signal.alarm(0)  # Cancel the alarm
                print("WeasyPrint imported successfully")
            except TimeoutError:
                signal.alarm(0)  # Cancel the alarm
                error_msg = "WeasyPrint import timed out - this indicates missing system dependencies in Lambda environment"
                print(error_msg)
                raise ImportError(error_msg)
            except ImportError as import_error:
                signal.alarm(0)  # Cancel the alarm
                error_msg = f"WeasyPrint not available: {str(import_error)}. This may be due to missing system dependencies."
                print(error_msg)
                raise ImportError(error_msg)
            except Exception as import_error:
                signal.alarm(0)  # Cancel the alarm
                error_msg = f"WeasyPrint import failed: {str(import_error)}"
                print(error_msg)
                raise ImportError(error_msg)
            
            print("Creating HTML document object...")
            # Create PDF from HTML
            html_doc = HTML(string=html_content)
            print("HTML document object created")
            
            print("Converting to PDF...")
            pdf_bytes = html_doc.write_pdf()
            print(f"PDF conversion successful, size: {len(pdf_bytes)} bytes")
            
            return pdf_bytes
        except ImportError as e:
            print(f"WeasyPrint import/dependency error: {str(e)}")
            import traceback
            print(f"WeasyPrint error traceback: {traceback.format_exc()}")
            raise e
        except Exception as e:
            print(f"Error converting HTML to PDF: {str(e)}")
            import traceback
            print(f"PDF conversion traceback: {traceback.format_exc()}")
            raise e
    
    def _upload_to_s3(self, pdf_bytes, s3_key):
        """Upload PDF to S3 bucket"""
        try:
            if not REPORTS_BUCKET or not CLOUDFRONT_DOMAIN:
                raise ValueError("REPORTS_BUCKET or CLOUDFRONT_DOMAIN environment variable not set")

            s3_client.put_object(
                Bucket=REPORTS_BUCKET,
                Key=s3_key,
                Body=pdf_bytes,
                ContentType='application/pdf',
                Metadata={
                    'generated_at': datetime.now(timezone.utc).isoformat(),
                    'generator': 'auto-lab-invoice-generator'
                }
            )
            
            # Generate file URL (assuming CloudFront distribution)
            file_url = f"https://{CLOUDFRONT_DOMAIN}/{s3_key}"

            return {
                'success': True,
                'file_url': file_url
            }
            
        except Exception as e:
            print(f"Error uploading to S3: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _upload_html_to_s3(self, html_bytes, s3_key):
        """Upload HTML to S3 bucket as fallback when PDF generation fails"""
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
                    'format': 'html-fallback',
                    'reason': 'pdf-generation-failed'
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

    def generate_invoice_from_payment(self, payment_data, user_data=None, order_data=None):
        """
        Generate invoice from payment data
        
        Args:
            payment_data (dict): Payment record from database
            user_data (dict, optional): User information
            order_data (dict, optional): Order information with items
            
        Returns:
            dict: Invoice generation result
        """
        try:
            # Prepare invoice data
            invoice_data = {
                'payment_intent_id': payment_data.get('paymentIntentId'),
                'user_info': {
                    'name': user_data.get('name') if user_data else payment_data.get('customerName', 'Valued Customer'),
                    'email': user_data.get('email') if user_data else payment_data.get('customerEmail', ''),
                    'phone': user_data.get('phone', '') if user_data else '',
                    'address': user_data.get('address', '') if user_data else ''
                },
                'payment_info': {
                    'method': payment_data.get('paymentMethod', 'Card'),
                    'status': payment_data.get('status', 'completed'),
                    'date': datetime.fromtimestamp(
                        int(payment_data.get('createdAt', datetime.now().timestamp()))
                    ).strftime('%d/%m/%Y'),
                    'amount': payment_data.get('amount', 0)
                },
                'items': [],
                'discount_amount': 0,  # Default no discount
                'discount_percentage': 0  # Default no percentage discount
            }
            
            # Add items from order data or payment metadata
            if order_data and 'items' in order_data:
                invoice_data['items'] = order_data['items']
                # Include discount information if available
                invoice_data['discount_amount'] = order_data.get('discount_amount', 0)
                invoice_data['discount_percentage'] = order_data.get('discount_percentage', 0)
            else:
                # Create a single line item from payment data
                amount = float(payment_data.get('amount', 0)) / 100  # Convert from cents
                invoice_data['items'] = [{
                    'name': 'Auto Service',
                    'description': f"Payment Reference: {payment_data.get('referenceNumber', 'N/A')}",
                    'quantity': 1,
                    'unit_price': amount,
                    'amount': amount
                }]
                # Check for discount in payment metadata
                invoice_data['discount_amount'] = payment_data.get('discount_amount', 0)
                invoice_data['discount_percentage'] = payment_data.get('discount_percentage', 0)
            
            return self.generate_invoice(invoice_data)
            
        except Exception as e:
            print(f"Error generating invoice from payment: {str(e)}")
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
            str: Base64 encoded QR code image
        """
        try:
            print(f"Starting QR code generation for URL: {url}")
            
            # Add timeout protection for qrcode import
            import signal
            import sys
            
            def timeout_handler(signum, frame):
                raise TimeoutError("QR code import timed out")
            
            # Set a 5-second timeout for the import
            print("Setting timeout for qrcode import...")
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(5)  # 5 second timeout
            
            try:
                print("Importing qrcode module with timeout protection...")
                import qrcode
                signal.alarm(0)  # Cancel the alarm
                print("qrcode module imported successfully")
            except TimeoutError:
                signal.alarm(0)  # Cancel the alarm
                print("QR code import timed out - skipping QR code generation")
                return None
            except Exception as import_error:
                signal.alarm(0)  # Cancel the alarm
                print(f"QR code import failed: {import_error}")
                return None
            
            print("Creating QRCode object...")
            # Create QR code
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            print("QRCode object created")
            
            print("Adding data to QR code...")
            qr.add_data(url)
            print("Data added to QR code")
            
            print("Making QR code...")
            qr.make(fit=True)
            print("QR code made")
            
            print("Creating QR code image...")
            # Create image
            img = qr.make_image(fill_color="black", back_color="white")
            print("QR code image created")
            
            print("Converting to base64...")
            # Convert to base64
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            img_str = base64.b64encode(buffered.getvalue()).decode()
            print(f"QR code converted to base64 (length: {len(img_str)})")
            
            return img_str
        except Exception as e:
            print(f"Error generating QR code: {str(e)}")
            import traceback
            print(f"QR code generation traceback: {traceback.format_exc()}")
            return None

def create_invoice_for_payment(payment_intent_id, user_data=None, order_data=None):
    """
    Convenience function to create an invoice for a payment
    
    Args:
        payment_intent_id (str): Payment intent ID
        user_data (dict, optional): User information
        order_data (dict, optional): Order information
        
    Returns:
        dict: Invoice generation result
    """
    try:
        # Import here to avoid circular imports
        import db_utils
        
        # Get payment data
        payment_data = db_utils.get_payment_by_intent_id(payment_intent_id)
        if not payment_data:
            return {
                'success': False,
                'error': f'Payment with intent ID {payment_intent_id} not found'
            }
        
        # Generate invoice
        generator = InvoiceGenerator()
        result = generator.generate_invoice_from_payment(payment_data, user_data, order_data)
        
        if result['success']:
            # Save invoice record to database
            invoice_record = {
                'invoiceId': result['invoice_id'],
                'paymentIntentId': payment_intent_id,
                's3Key': result['s3_key'],
                'fileUrl': result['file_url'],
                'pdfSize': result['pdf_size'],
                'createdAt': int(datetime.now().timestamp()),
                'status': 'generated'
            }
            
            create_result = db_utils.create_invoice_record(invoice_record)
            if not create_result:
                print("Warning: Invoice generated but failed to save record to database")
        
        return result
        
    except Exception as e:
        print(f"Error in create_invoice_for_payment: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }

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
        # Debug environment variables
        import os
        print("=== Environment Variables Debug ===")
        required_vars = [
            'STAFF_TABLE', 'USERS_TABLE', 'CONNECTIONS_TABLE', 'MESSAGES_TABLE',
            'UNAVAILABLE_SLOTS_TABLE', 'APPOINTMENTS_TABLE', 'SERVICE_PRICES_TABLE',
            'ORDERS_TABLE', 'ITEM_PRICES_TABLE', 'INQUIRIES_TABLE', 'PAYMENTS_TABLE',
            'INVOICES_TABLE', 'REPORTS_BUCKET', 'CLOUDFRONT_DOMAIN', 'FRONTEND_ROOT_URL'
        ]
        
        for var in required_vars:
            value = os.environ.get(var, 'NOT_SET')
            print(f"{var}: {value}")
        print("=== End Environment Variables ===")
        
        # Import db_utils here to avoid circular imports
        print("Importing db_utils...")
        import db_utils
        print("db_utils imported successfully")

        print(f"Processing {record_type} record...")
        if record_type == 'order':
            user_data = {
                'name': record.get('customerName', 'N/A'),
                'email': record.get('customerEmail', 'N/A'),
                'phone': record.get('customerPhone', 'N/A')
            }
        else:  # appointment
            if record.get('isBuyer'):
                user_data = {
                    'name': record.get('buyerName', 'N/A'),
                    'email': record.get('buyerEmail', 'N/A'),
                    'phone': record.get('buyerPhone', 'N/A')
                }
            else:
                user_data = {
                    'name': record.get('sellerName', 'N/A'),
                    'email': record.get('sellerEmail', 'N/A'),
                    'phone': record.get('sellerPhone', 'N/A')
                }
        
        print("User data extracted successfully")
        
        # Extract items from record
        items = []
        print("Extracting items from record...")
        
        if record_type == 'order':
            # For orders, get items from the order
            order_items = record.get('items', [])
            print(f"Found {len(order_items)} order items")
            
            for i, item in enumerate(order_items):
                print(f"Processing item {i+1}: {item}")
                try:
                    print("Calling get_category_item_names...")
                    category_name, item_name = db_utils.get_category_item_names(item.get('categoryId'), item.get('itemId'))
                    print(f"Retrieved names: category='{category_name}', item='{item_name}'")
                except Exception as e:
                    print(f"Error getting category/item names: {e}")
                    category_name, item_name = "Unknown Category", "Unknown Item"
                vehicle_info = {
                    'make': record.get('carMake', 'N/A'),
                    'model': record.get('carModel', 'N/A'),
                    'year': record.get('carYear', 'N/A')
                }
                items.append({
                    'name': item_name,
                    'description': f"{vehicle_info['make']} {vehicle_info['model']} {vehicle_info['year']} | {category_name}",
                    'quantity': item.get('quantity', 1),
                    'unit_price': float(item.get('price', 0)),
                    'amount': float(item.get('totalPrice', 0))
                })
        else:  # appointment
            print("Processing appointment record...")
            # For appointments, create a single item
            try:
                print("Calling get_service_plan_names...")
                service_name, plan_name = db_utils.get_service_plan_names(record.get('serviceId'), record.get('planId'))
                print(f"Retrieved names: service='{service_name}', plan='{plan_name}'")
            except Exception as e:
                print(f"Error getting service/plan names: {e}")
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
        
        print("Preparing invoice data...")
        # Payment information
        payment_info = {
            'method': record.get('paymentMethod', 'Unknown'),
            'status': 'completed' if record.get('paymentStatus') == 'paid' else 'pending',
            'date': datetime.now().strftime('%d/%m/%Y'),
            'amount': float(record.get('totalAmount', 0)) if record_type == 'order' else float(record.get('price', 0))
        }
        
        # Generate QR code URL for order/appointment tracking
        reference_id = record.get(f'{record_type}Id')
        qr_code_url = f"{FRONTEND_ROOT_URL}/{record_type}/{reference_id}"
        
        # Prepare invoice data
        invoice_data = {
            'payment_intent_id': payment_intent_id or 'N/A',
            'user_info': user_data,
            'items': items,
            'payment_info': payment_info,
            'discount_percentage': 0,
            'discount_amount': 0,
            'qr_code_url': qr_code_url,
            'invoice_type': record_type
        }
        
        print("Creating InvoiceGenerator instance...")
        # Generate the invoice
        generator = InvoiceGenerator()
        print("Calling generate_invoice...")
        result = generator.generate_invoice(invoice_data)
        print(f"Invoice generation result: {result}")
        
        if result['success']:
            print("Invoice generated successfully, saving to database...")
            # Save invoice record to database
            invoice_record = {
                'invoiceId': result['invoice_id'],
                'paymentIntentId': payment_intent_id or 'N/A',
                'referenceNumber': reference_id,
                'referenceType': record_type,
                's3Key': result['s3_key'],
                'fileUrl': result['file_url'],
                'fileSize': result.get('pdf_size') or result.get('html_size', 0),
                'format': result.get('format', 'unknown'),
                'createdAt': int(datetime.now().timestamp()),
                'status': 'generated'
            }

            # Add note if it's HTML fallback
            if result.get('format') == 'html':
                invoice_record['note'] = result.get('note', 'Generated as HTML due to system limitations')

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
                'totalAmount': payment_info['amount'],
                'invoiceFormat': result.get('format', 'unknown')
            }
            
            print("Calling create_invoice_record...")
            try:
                create_result = db_utils.create_invoice_record(invoice_record)
                print(f"Invoice record creation result: {create_result}")
            except Exception as db_error:
                print(f"Error creating invoice record: {db_error}")
                create_result = False
                
            if not create_result:
                print("Warning: Invoice generated but failed to save record to database")
            
            # Add invoice_url to result for updating the order/appointment record
            result['invoice_url'] = result['file_url']
            print("Invoice processing completed successfully")
        else:
            print(f"Invoice generation failed: {result.get('error')}")
        
        return result
        
    except Exception as e:
        print(f"Error in create_invoice_for_order_or_appointment: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }
