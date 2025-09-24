#!/usr/bin/env python3

import os
import uuid
import base64
import random
from datetime import datetime
from zoneinfo import ZoneInfo
from io import BytesIO
from decimal import Decimal
import boto3

# ReportLab imports
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter, A4, A3, A5, legal
from reportlab.lib.units import inch
from reportlab.lib.colors import Color, HexColor

# AWS clients
s3_client = boto3.client('s3')

# Tax rate constant - GST rate for Australia
GST_RATE = Decimal('0.10')  # 10% GST rate

# Environment variables
REPORTS_BUCKET = os.environ.get('REPORTS_BUCKET')
CLOUDFRONT_DOMAIN = os.environ.get('CLOUDFRONT_DOMAIN')
FRONTEND_ROOT_URL = os.environ.get('FRONTEND_ROOT_URL')
MAIL_FROM_ADDRESS = os.environ.get('MAIL_FROM_ADDRESS')
FRONTEND_URL = os.environ.get('FRONTEND_ROOT_URL')


class ProfessionalInvoicePDFGenerator:
    """
    Professional PDF invoice generator using ReportLab
    Creates high-quality, professional PDF invoices for Auto Lab Solutions
    """
    
    def __init__(self):
        # Company information
        self.company_info = {
            'name': 'Auto Lab Solutions',
            'address': '70b Division St, Welshpool WA 6106, Australia',
            'address_line1': '70b Division St',
            'address_line2': 'Welshpool WA 6106, Australia',
            'phone': '+61 451 237 048',
            'email': MAIL_FROM_ADDRESS or 'mail@autolabsolutions.com',
            'website': "www." + FRONTEND_URL.replace('https://', '').replace('http://', '') if FRONTEND_URL else 'www.autolabsolutions.com',
            'abn': '12 345 678 901',
            'description': 'Professional Automotive Inspection & Diagnostic Services'
        }
        
        # Professional color palette
        self.colors = {
            'brand_green': (0.13, 0.77, 0.37),      # #22C55E - Primary brand color
            'brand_orange': (0.96, 0.62, 0.04),     # #F59E0B - Secondary accent
            'dark_gray': (0.15, 0.15, 0.17),        # #27272a - Primary text
            'medium_gray': (0.4, 0.4, 0.4),         # #666666 - Secondary text
            'light_gray': (0.96, 0.96, 0.96),       # #F5F5F5 - Background
            'white': (1, 1, 1),                     # #FFFFFF - White
            'black': (0, 0, 0),                     # #000000 - Black
            'success_green': (0.13, 0.77, 0.37),    # For paid status
            'warning_orange': (0.96, 0.62, 0.04),   # For pending status
        }
        
        # Layout constants for consistent design
        self.layout = {
            'margin': 50,
            'header_height': 125,  # Increased from 110 to add slight space below company details
            'footer_height': 80,
            'line_height': 15,
            'section_spacing': 20,  # Reduced from 25 to provide more room
            'table_row_height': 35,
            'table_header_height': 30,
        }
    
    def _get_centered_section_x(self, page_width, margin=60):
        """Calculate centered X position for consistent section width"""
        # Calculate same width as items table
        total_col = margin + 450
        section_width = (total_col + 80) - margin  # 470pt
        
        # Center the section on the page
        available_width = page_width + (2 * margin)  # Full page width
        centered_x = (available_width - section_width) / 2
        
        return centered_x, section_width
    
    def generate_invoice_pdf(self, invoice_data):
        """
        Generate a professional PDF invoice
        
        Args:
            invoice_data (dict): Invoice data containing:
                - payment_intent_id: Payment reference ID
                - user_info: Customer information (name, email, phone)
                - items: List of service/item details
                - payment_info: Payment details (method, status, date)
                - currency: Currency code (default: 'AUD')
                - total_amount: Total amount
                - calculated_discount: Discount amount
                - invoice_date: Invoice date
                
        Returns:
            dict: {
                'success': bool,
                'invoice_id': str,
                'payment_intent_id': str,
                's3_key': str,
                'file_url': str,
                'pdf_size': int,
                'format': str,
                'error': str (if any)
            }
        """
        try:
            # Generate unique invoice ID
            invoice_id = f"INV-{uuid.uuid4().hex[:8].upper()}"
            
            # Update payment intent ID if needed
            payment_intent_id = invoice_data.get('payment_intent_id')
            if payment_intent_id and payment_intent_id.endswith('<INVOICE_ID>'):
                payment_intent_id = payment_intent_id.replace('<INVOICE_ID>', 'inv_' + invoice_id.split('-')[1].lower())
                invoice_data['payment_intent_id'] = payment_intent_id
            
            # Generate PDF content
            pdf_data = self._create_pdf_invoice(invoice_data, invoice_id)
            
            if not pdf_data:
                return {
                    'success': False,
                    'error': 'Failed to generate PDF content'
                }
            
            # Upload to S3
            s3_key = f"invoices/{datetime.now(ZoneInfo('Australia/Perth')).year}/{datetime.now(ZoneInfo('Australia/Perth')).month:02d}/{invoice_id}.pdf"
            upload_result = self._upload_pdf_to_s3(pdf_data, s3_key)
            
            if upload_result['success']:
                return {
                    'success': True,
                    'invoice_id': invoice_id,
                    'payment_intent_id': payment_intent_id,
                    's3_key': s3_key,
                    'file_url': upload_result['file_url'],
                    'pdf_size': len(pdf_data),
                    'format': 'pdf'
                }
            else:
                # S3 upload failed, but we can still provide a fallback response
                print("S3 upload failed, creating fallback response with local PDF data")
                fallback_url = upload_result.get('fallback_url', 'PDF generated but upload failed')
                
                return {
                    'success': True,  # Mark as success since PDF was generated
                    'invoice_id': invoice_id,
                    'payment_intent_id': payment_intent_id,
                    's3_key': s3_key,
                    'file_url': fallback_url,  # Use fallback URL
                    'pdf_size': len(pdf_data),
                    'format': 'pdf',
                    'warning': f"S3 upload failed: {upload_result.get('error', 'Unknown error')}"
                }
                
        except Exception as e:
            print(f"Error generating PDF invoice: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _create_pdf_invoice(self, invoice_data, invoice_id):
        """Create PDF content for the invoice using ReportLab"""
        try:
            # Create PDF in memory
            buffer = BytesIO()
            
            # Use A4 page size for professional invoices
            page_size = A4
            c = canvas.Canvas(buffer, pagesize=page_size)
            width, height = page_size
            
            # Calculate layout dimensions
            page_width = width - (2 * self.layout['margin'])
            
            # Draw professional header
            self._draw_header(c, width, height, invoice_id, invoice_data)
            
            # Draw billing and payment sections
            content_y = height - self.layout['header_height'] - 40
            content_y = self._draw_billing_section(c, content_y, invoice_data)
            
            # Draw items table
            content_y = self._draw_items_table(c, content_y, invoice_data, page_width)
            
            # Draw totals section
            content_y = self._draw_totals_section(c, content_y, invoice_data, page_width)
            
            # Draw thank you section
            content_y = self._draw_thank_you_section(c, content_y, page_width)
            
            # Draw professional footer
            self._draw_footer(c, width, height)
            
            # Save the PDF
            c.save()
            
            # Get PDF data
            pdf_data = buffer.getvalue()
            buffer.close()
            
            # Basic validation
            if not pdf_data or len(pdf_data) < 100:
                print(f"ERROR: Invalid PDF data size: {len(pdf_data) if pdf_data else 0}")
                return None
            
            if not pdf_data.startswith(b'%PDF-'):
                print("ERROR: PDF header missing")
                return None
            
            print(f"Generated professional PDF invoice: {len(pdf_data)} bytes")
            return pdf_data
            
        except Exception as e:
            print(f"Error creating PDF invoice: {str(e)}")
            return None
    
    def _draw_header(self, c, width, height, invoice_id, invoice_data):
        """Draw professional header with company branding"""
        # Header background with greenish professional gradient
        header_height = self.layout['header_height']
        
        # Create sophisticated gradient background with light green tones (matching thank you section)
        # Base layer - very light green tint
        c.setFillColorRGB(0.97, 1.0, 0.97)  # Same as thank you section
        c.rect(0, height - header_height, width, header_height, fill=1, stroke=0)
        
        # Professional green gradient simulation
        for i in range(6):
            # Create a sophisticated gradient from light green to near-white
            gradient_factor = i / 5.0  # 0 to 1
            r = 0.97 + (gradient_factor * 0.03)  # 0.97 to 1.0
            g = 1.0  # Keep green at maximum for fresh look
            b = 0.97 + (gradient_factor * 0.03)  # 0.97 to 1.0
            c.setFillColorRGB(r, g, b)
            strip_height = header_height // 6
            c.rect(0, height - header_height + (i * strip_height), width, strip_height, fill=1, stroke=0)
        
        # Header content area positioning (no background box to preserve gradient)
        section_width = 515  # Maximum width with proper margins
        page_center = A4[0] / 2
        centered_x = page_center - (section_width / 2)
        
        # Top accent strip with matching green color
        c.setFillColorRGB(*self.colors['brand_green'])
        c.rect(0, height - 8, width, 8, fill=1, stroke=0)
        
        # Bottom accent strip with same green color (matching thank you section)
        c.setFillColorRGB(*self.colors['brand_green'])
        c.rect(0, height - header_height, width, 3, fill=1, stroke=0)
        
        # Company branding - constrained to centered section width  
        company_y = height - 45  # Moved down from -35 for better positioning
        
        # Get centered positioning manually
        section_width = 515  # Maximum width with proper margins
        page_center = A4[0] / 2
        centered_x = page_center - (section_width / 2)
        header_right_edge = centered_x + section_width
        
        # Calculate safe area for company info within centered section
        invoice_box_width = 180
        invoice_x = header_right_edge - invoice_box_width
        company_safe_width = invoice_x - centered_x - 20  # 20pt gap
        
        c.setFillColorRGB(*self.colors['brand_green'])
        c.setFont("Helvetica-Bold", 24)  # Smaller font to fit better
        company_name = self.company_info['name']
        company_name_width = c.stringWidth(company_name, "Helvetica-Bold", 24)
        
        # Ensure company name fits in safe area
        if company_name_width > company_safe_width:
            # Use smaller font
            c.setFont("Helvetica-Bold", 18)
            company_name_width = c.stringWidth(company_name, "Helvetica-Bold", 18)
        
        c.drawString(centered_x, company_y, company_name)
        
        # Company tagline - ensure it fits in safe area
        c.setFillColorRGB(*self.colors['medium_gray'])
        c.setFont("Helvetica-Oblique", 10)
        tagline = self.company_info['description']
        tagline_width = c.stringWidth(tagline, "Helvetica-Oblique", 10)
        if tagline_width > company_safe_width:
            # Truncate if too long
            while tagline_width > company_safe_width and len(tagline) > 10:
                tagline = tagline[:-4] + "..."
                tagline_width = c.stringWidth(tagline, "Helvetica-Oblique", 10)
        c.drawString(centered_x, company_y - 18, tagline)  # Moved closer from -25 to -18
        
        # Contact information - constrain to safe area
        contact_y = company_y - 38  # Moved closer from -55 to -38
        c.setFillColorRGB(*self.colors['dark_gray'])
        c.setFont("Helvetica", 9)
        
        # Calculate column positions within centered area
        col1_x = centered_x
        col2_x = centered_x + (company_safe_width / 2)
        
        # Left column
        c.drawString(col1_x, contact_y, self.company_info['address_line1'])
        c.drawString(col1_x, contact_y - 12, self.company_info['address_line2'])
        c.drawString(col1_x, contact_y - 24, f"ABN: {self.company_info['abn']}")
        
        # Right column with clear labels
        c.drawString(col2_x, contact_y, f"Phone: {self.company_info['phone']}")
        c.drawString(col2_x, contact_y - 12, f"Email: {self.company_info['email']}")
        c.drawString(col2_x, contact_y - 24, f"Web: {self.company_info['website']}")
        
        # Invoice section - positioned after calculating safe area
        invoice_y = height - 50
        
                # Invoice box - use previously calculated position
        invoice_box_width = 180
        invoice_title_height = 35
        invoice_details_height = 50  # Increased height for better proportions
        
        # Invoice title box with clean styling
        c.setFillColorRGB(*self.colors['brand_orange'])
        c.rect(invoice_x, invoice_y, invoice_box_width, invoice_title_height, fill=1, stroke=0)
        
        c.setFillColorRGB(*self.colors['white'])
        c.setFont("Helvetica-Bold", 20)
        invoice_text_width = c.stringWidth("INVOICE", "Helvetica-Bold", 20)
        c.drawString(invoice_x + invoice_box_width/2 - invoice_text_width/2, invoice_y + 10, "INVOICE")
        
        # Invoice details box - perfectly aligned with title box
        details_y = invoice_y - invoice_details_height
        c.setFillColorRGB(0.99, 0.99, 1.0)  # Light blue-white background
        c.setStrokeColorRGB(*self.colors['brand_orange'])
        c.setLineWidth(2)
        # Adjust rectangle to account for 2pt stroke width (1pt on each side)
        c.rect(invoice_x + 1, details_y + 1, invoice_box_width - 2, invoice_details_height - 2, fill=1, stroke=1)
        
        # Invoice information vertically centered within the details box
        info_x = invoice_x + 12
        # Calculate center position: total height is 50pt, text block is ~16pt, so center at 25pt from bottom + 8pt offset
        info_y = details_y + (invoice_details_height / 2) + 8  # Vertically centered
        
        invoice_date = invoice_data.get('invoice_date', datetime.now(ZoneInfo('Australia/Perth')).strftime('%d %B %Y'))
        c.setFillColorRGB(*self.colors['dark_gray'])
        c.setFont("Helvetica-Bold", 10)  # Smaller font for labels
        c.drawString(info_x, info_y, "Invoice ID:")
        c.setFont("Helvetica", 10)
        c.drawRightString(invoice_x + invoice_box_width - 12, info_y, invoice_id)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(info_x, info_y - 16, "Invoice Date:")  # Better line spacing
        c.setFont("Helvetica", 10)
        c.drawRightString(invoice_x + invoice_box_width - 12, info_y - 16, invoice_date)
    
    def _draw_billing_section(self, c, start_y, invoice_data):
        """Draw billing and payment information section"""
        # Get centered positioning manually  
        section_width = 515  # Maximum width with proper margins
        page_center = A4[0] / 2
        centered_x = page_center - (section_width / 2)
        full_section_width = section_width
        
        # Split into two columns within the centered full width
        col1_width = (full_section_width * 0.4) - 10  # 40% of full width
        col1_x = centered_x
        
        col2_width = (full_section_width * 0.6) - 10  # 60% of full width  
        col2_x = centered_x + col1_width + 20
        
        # Section headers
        section_y = start_y
        self._draw_section_header(c, col1_x, section_y, "BILLED TO", col1_width)
        self._draw_section_header(c, col2_x, section_y, "PAYMENT DETAILS", col2_width)
        
        # Content boxes
        box_height = 90
        box_y = section_y - 10
        
        # Bill To box
        c.setFillColorRGB(0.99, 0.99, 0.99)
        c.setStrokeColorRGB(0.9, 0.9, 0.9)
        c.setLineWidth(1)
        c.rect(col1_x, box_y - box_height, col1_width, box_height, fill=1, stroke=1)
        
        # Brand accent line
        c.setFillColorRGB(*self.colors['brand_green'])
        c.rect(col1_x, box_y - box_height, 4, box_height, fill=1, stroke=0)
        
        # Billing information
        info_x = col1_x + 20
        info_y = box_y - 25
        
        user_info = invoice_data.get('user_info', {})
        c.setFillColorRGB(*self.colors['dark_gray'])
        c.setFont("Helvetica", 12)
        c.drawString(info_x, info_y, user_info.get('name', 'Valued Customer'))
        
        c.setFont("Helvetica", 10)
        c.drawString(info_x, info_y - 15, user_info.get('email', 'N/A'))
        if user_info.get('phone'):
            c.drawString(info_x, info_y - 30, user_info.get('phone'))
        
        # Payment Details box
        c.setFillColorRGB(0.99, 0.99, 0.99)
        c.setStrokeColorRGB(*self.colors['brand_green'])
        c.setLineWidth(1)
        c.rect(col2_x, box_y - box_height, col2_width, box_height, fill=1, stroke=1)
        
        # Green accent for payment
        c.setFillColorRGB(*self.colors['brand_green'])
        c.rect(col2_x, box_y - box_height, 4, box_height, fill=1, stroke=0)
        
        # Payment details with optimized spacing
        pay_info_x = col2_x + 20
        pay_info_y = box_y - 25
        label_width = 85  # Reduced from 100 to give more space for values
        
        payment_info = invoice_data.get('payment_info', {})
        
        c.setFillColorRGB(*self.colors['dark_gray'])
        c.setFont("Helvetica", 10)
        c.drawString(pay_info_x, pay_info_y, "Payment Method:")
        c.setFont("Helvetica", 10)
        c.drawString(pay_info_x + label_width, pay_info_y, payment_info.get('method', 'N/A').upper())
        
        c.setFont("Helvetica", 10)
        c.drawString(pay_info_x, pay_info_y - 15, "Payment Status:")
        
        # Color-coded status
        status = payment_info.get('status', 'pending').lower()
        if status == 'completed' or status == 'paid':
            c.setFillColorRGB(*self.colors['success_green'])
            status_text = "✓ PAID"
        else:
            c.setFillColorRGB(*self.colors['warning_orange'])
            status_text = "⏳ PENDING"
        
        c.setFont("Helvetica-Bold", 10)
        c.drawString(pay_info_x + label_width, pay_info_y - 15, status_text)
        
        c.setFillColorRGB(*self.colors['dark_gray'])
        c.setFont("Helvetica", 10)
        c.drawString(pay_info_x, pay_info_y - 30, "Reference ID:")
        c.setFont("Helvetica", 9)  # Back to 9pt font with more space
        ref_id = invoice_data.get('payment_intent_id', 'N/A')
        
        # Calculate available space for reference ID (now much wider)
        available_width = col2_width - label_width - 40  # Account for margins
        ref_id_width = c.stringWidth(ref_id, "Helvetica", 9)
        
        # With the wider payment box, most reference IDs should fit
        if ref_id_width > available_width and len(ref_id) > 15:
            # Only truncate if absolutely necessary
            char_width = ref_id_width / len(ref_id)
            max_chars = int(available_width / char_width) - 3
            if max_chars > 15:  # Ensure reasonable minimum length
                ref_id = ref_id[:max_chars] + "..."
        
        c.drawString(pay_info_x + label_width, pay_info_y - 30, ref_id)
        
        c.setFont("Helvetica", 10)
        c.drawString(pay_info_x, pay_info_y - 45, "Payment Date:")
        c.setFont("Helvetica", 10)
        c.drawString(pay_info_x + label_width, pay_info_y - 45, payment_info.get('date', 'N/A'))
        
        return box_y - box_height - self.layout['section_spacing']
    
    def _draw_section_header(self, c, x, y, title, width_val=200):
        """Draw a section header with professional styling"""
        c.setFillColorRGB(*self.colors['brand_green'])
        c.setFont("Helvetica-Bold", 12)
        c.drawString(x, y, title)
        
        # Clean underline
        c.setLineWidth(2)
        c.setStrokeColorRGB(*self.colors['brand_green'])
        c.line(x, y - 3, x + width_val, y - 3)
    
    def _draw_items_table(self, c, start_y, invoice_data, page_width):
        """Draw professional items/services table with tax breakdown"""
        # Get centered positioning manually - match thank you section width
        section_width = 515  # Same width as thank you section for consistent margins
        page_center = A4[0] / 2
        centered_x = page_center - (section_width / 2)
        table_width = section_width
        
        # Table dimensions
        table_y = start_y
        table_start_y = table_y - 20
        row_height = self.layout['table_row_height']
        header_height = self.layout['table_header_height']
        
        # Column positions - moved closer to TOTAL column for compact layout
        desc_col = centered_x + 15
        qty_col = centered_x + 280  # Moved closer to the right
        net_price_col = centered_x + 320  # Moved closer to the right
        gst_col = centered_x + 380  # Moved closer to the right
        total_col = centered_x + 440  # Kept at right edge
        
        # Draw section header aligned with BILLED TO heading
        self._draw_section_header(c, centered_x, table_y, "SERVICES & ITEMS", table_width)
        
        # Table header
        c.setFillColorRGB(*self.colors['dark_gray'])
        c.rect(centered_x, table_start_y - header_height, table_width, header_height, fill=1, stroke=0)
        
        # Header text with smaller font to fit more columns
        c.setFillColorRGB(*self.colors['white'])
        c.setFont("Helvetica-Bold", 9)
        header_y = table_start_y - 20

        c.drawString(desc_col, header_y, "SERVICE/ITEM")

        qty_text_width = c.stringWidth("QTY", "Helvetica-Bold", 9)
        c.drawString(qty_col + 15 - qty_text_width/2, header_y, "QTY")

        net_text_width = c.stringWidth("NET PRICE", "Helvetica-Bold", 9)
        c.drawString(net_price_col + 25 - net_text_width/2, header_y, "NET PRICE")
        
        gst_text_width = c.stringWidth("GST (10%)", "Helvetica-Bold", 9)
        c.drawString(gst_col + 25 - gst_text_width/2, header_y, "GST (10%)")
        
        total_text_width = c.stringWidth("TOTAL", "Helvetica-Bold", 9)
        c.drawString(total_col + 20 - total_text_width/2, header_y, "TOTAL")
        
        # Table rows
        current_y = table_start_y - header_height
        items = invoice_data.get('items', [])
        
        for i, item in enumerate(items):
            # Row background (alternating)
            if i % 2 == 0:
                c.setFillColorRGB(0.98, 0.98, 0.98)
                c.rect(centered_x, current_y - row_height, table_width, row_height, fill=1, stroke=0)
            
            # Item name
            c.setFillColorRGB(*self.colors['dark_gray'])
            c.setFont("Helvetica-Bold", 10)
            item_name = item.get('name', 'N/A')
            # Truncate item name if too long
            if len(item_name) > 50:
                item_name = item_name[:47] + "..."
            c.drawString(desc_col, current_y - 15, item_name)
            
            # Item description (if available) - this contains the plan name
            description = item.get('description', '')
            if description:
                c.setFillColorRGB(0.5, 0.5, 0.5)
                c.setFont("Helvetica", 8)
                # Simply show much more text - no complex calculations
                if len(description) > 80:  # Much longer limit
                    description = description[:77] + "..."
                c.drawString(desc_col, current_y - 28, description)
            
            # Calculate tax breakdown
            item_type = item.get('type', 'item')
            quantity = item.get('quantity', 1)
            unit_price_incl_gst = Decimal(str(item.get('unit_price', 0)))
            amount_incl_gst = Decimal(str(item.get('amount', 0)))
            
            # Calculate net price (excluding GST) and GST amount
            if item_type == 'service':
                # For services, show the total net amount (since it's a service with no unit breakdown)
                net_amount = amount_incl_gst / (1 + GST_RATE)
                gst_amount = amount_incl_gst - net_amount
                qty_display = "1"  # Show 1 for services instead of "—"
                net_price_display = f"{net_amount:.2f}"  # Show net service amount
            else:
                # For items, calculate per-unit net price
                net_unit_price = unit_price_incl_gst / (1 + GST_RATE)
                net_amount = net_unit_price * quantity
                gst_amount = amount_incl_gst - net_amount
                qty_display = str(quantity)
                net_price_display = f"{net_unit_price:.2f}"
            
            c.setFillColorRGB(*self.colors['dark_gray'])
            
            # Centered quantity
            c.setFont("Helvetica", 10)
            qty_width = c.stringWidth(qty_display, "Helvetica", 10)
            c.drawString(qty_col + 15 - qty_width/2, current_y - 21, qty_display)
            
            # Centered net price
            net_price_width = c.stringWidth(net_price_display, "Helvetica", 10)
            c.drawString(net_price_col + 25 - net_price_width/2, current_y - 21, net_price_display)
            
            # Centered GST amount
            gst_display = f"{gst_amount:.2f}"
            gst_width = c.stringWidth(gst_display, "Helvetica", 10)
            c.drawString(gst_col + 25 - gst_width/2, current_y - 21, gst_display)
            
            # Centered total (bold)
            c.setFont("Helvetica-Bold", 10)
            total_text = f"{amount_incl_gst:.2f}"
            total_width = c.stringWidth(total_text, "Helvetica-Bold", 10)
            c.drawString(total_col + 20 - total_width/2, current_y - 21, total_text)
            
            current_y -= row_height
        
        # Table border
        c.setStrokeColorRGB(0.8, 0.8, 0.8)
        c.setLineWidth(1)
        c.rect(centered_x, current_y, table_width, table_start_y - current_y, fill=0, stroke=1)
        
        return current_y - self.layout['section_spacing']
    
    def _draw_totals_section(self, c, start_y, invoice_data, page_width):
        """Draw totals section with professional styling and tax breakdown"""
        # Calculate totals
        total_amount = Decimal(str(invoice_data.get('total_amount', 0)))
        calculated_discount = Decimal(str(invoice_data.get('calculated_discount', 0)))
        
        # Calculate subtotal
        items = invoice_data.get('items', [])
        subtotal_incl_gst = sum(Decimal(str(item.get('amount', 0))) for item in items)
        
        # Calculate net amount and GST from the subtotal
        subtotal_net = subtotal_incl_gst / (1 + GST_RATE)
        subtotal_gst = subtotal_incl_gst - subtotal_net
        
        # Calculate final amounts after discount
        final_net = total_amount / (1 + GST_RATE)
        final_gst = total_amount - final_net
        
        # Totals positioning - align with consistent table width (match thank you section)
        totals_width = 280  # Increased width for tax breakdown
        totals_height = 120 if calculated_discount > 0 else 100  # Reduced height to bring closer
        
        # Get centered positioning manually - same as thank you section
        section_width = 515  # Same width as thank you section and items table
        page_center = A4[0] / 2
        centered_x = page_center - (section_width / 2)
        table_width = section_width
        totals_x = centered_x + table_width - totals_width
        totals_y = start_y
        
        # Totals container
        c.setFillColorRGB(0.99, 0.99, 0.99)
        c.setStrokeColorRGB(0.85, 0.85, 0.85)
        c.setLineWidth(1)
        c.rect(totals_x, totals_y - totals_height, totals_width, totals_height, fill=1, stroke=1)
        
        # Totals content with better spacing
        content_y = totals_y - 22  # Better top margin
        label_x = totals_x + 18  # More left margin
        value_x = totals_x + totals_width - 18  # More right margin
        
        # Show subtotal breakdown if different from total (i.e., if there's a discount)
        if calculated_discount > 0:
            c.setFillColorRGB(*self.colors['dark_gray'])
            c.setFont("Helvetica", 10)
            c.drawString(label_x, content_y, "Subtotal (Net):")
            c.setFont("Helvetica", 10)
            c.drawRightString(value_x, content_y, f"AUD {subtotal_net:.2f}")
            
            # Subtotal GST
            c.setFont("Helvetica", 10)
            c.drawString(label_x, content_y - 16, "Subtotal GST (10%):")
            c.setFont("Helvetica", 10)
            c.drawRightString(value_x, content_y - 16, f"AUD {subtotal_gst:.2f}")
            
            # Subtotal including GST
            c.setFont("Helvetica", 10)
            c.drawString(label_x, content_y - 32, "Subtotal:")
            c.setFont("Helvetica-Bold", 10)
            c.drawRightString(value_x, content_y - 32, f"AUD {subtotal_incl_gst:.2f}")
            
            # Discount
            c.setFont("Helvetica", 10)
            c.drawString(label_x, content_y - 48, "Discount:")
            c.setFont("Helvetica-Bold", 10)
            c.drawRightString(value_x, content_y - 48, f"AUD -{calculated_discount:.2f}")
            
            content_y -= 48  # Adjust for discount lines
        else:
            # No discount - show net and GST breakdown
            c.setFillColorRGB(*self.colors['dark_gray'])
            c.setFont("Helvetica", 10)
            c.drawString(label_x, content_y, "Net Amount:")
            c.setFont("Helvetica", 10)
            c.drawRightString(value_x, content_y, f"AUD {final_net:.2f}")
            
            # GST amount
            c.setFont("Helvetica", 10)
            c.drawString(label_x, content_y - 16, "GST (10%):")
            c.setFont("Helvetica", 10)
            c.drawRightString(value_x, content_y - 16, f"AUD {final_gst:.2f}")
            
            content_y -= 16  # Adjust for next line
        
        # Total with brand accent background - reduced gap
        total_box_height = 32  # Slightly taller
        total_box_y = totals_y - totals_height + 5  # Reduced gap from 2 to 5
        c.setFillColorRGB(*self.colors['brand_green'])
        c.rect(totals_x + 2, total_box_y, totals_width - 4, total_box_height, fill=1, stroke=0)
        
        # Total amount text with proper spacing
        c.setFillColorRGB(*self.colors['white'])
        c.setFont("Helvetica-Bold", 12)
        c.drawString(label_x, total_box_y + 10, "TOTAL AMOUNT:")
        c.setFont("Helvetica-Bold", 13)
        c.drawRightString(value_x, total_box_y + 10, f"AUD {total_amount:.2f}")
        
        return totals_y - totals_height - self.layout['section_spacing']
    
    def _draw_thank_you_section(self, c, start_y, page_width):
        """Draw professional thank you section"""
        thanks_height = 65  # Slightly taller for better spacing
        
        # Get centered positioning manually
        section_width = 515  # Maximum width with proper margins
        page_center = A4[0] / 2  
        centered_x = page_center - (section_width / 2)
        
        # Ensure we don't overlap with footer - check if we have enough space
        footer_height = self.layout['footer_height']
        min_y_position = footer_height + 20  # 20pt buffer above footer
        
        # Adjust position if thank you section would overlap footer
        if start_y - thanks_height < min_y_position:
            start_y = min_y_position + thanks_height
        
        # Thank you container
        c.setFillColorRGB(0.97, 1.0, 0.97)  # Very light green tint
        c.setStrokeColorRGB(*self.colors['brand_green'])
        c.setLineWidth(2)
        c.rect(centered_x, start_y - thanks_height, section_width, thanks_height, fill=1, stroke=1)
        
        # Thank you content with better alignment and smaller text
        content_y = start_y - 22  # Better top margin
        content_x = centered_x + 25  # Better left margin
        
        c.setFillColorRGB(*self.colors['brand_green'])
        c.setFont("Helvetica-Bold", 12)  # Reduced from 16 to 12
        title_text = "Thank You for Choosing Auto Lab Solutions!"
        c.drawString(content_x, content_y, title_text)
        
        c.setFillColorRGB(*self.colors['dark_gray'])
        c.setFont("Helvetica", 9)  # Reduced from 11 to 9
        c.drawString(content_x, content_y - 18, "We appreciate your trust in our professional automotive services.")  # Better line spacing
        c.drawString(content_x, content_y - 32, "Your vehicle's safety and performance are our top priorities.")  # Better line spacing
        
        return start_y - thanks_height - self.layout['section_spacing']
    
    def _draw_footer(self, c, width, height):
        """Draw professional footer"""
        footer_height = self.layout['footer_height']
        
        # Footer background
        c.setFillColorRGB(0.96, 0.96, 0.96)
        c.rect(0, 0, width, footer_height, fill=1, stroke=0)
        
        # Top border with brand color
        c.setFillColorRGB(*self.colors['brand_green'])
        c.rect(0, footer_height - 2, width, 2, fill=1, stroke=0)
        
        # Footer content with better alignment
        footer_center = width / 2
        
        # Company name - centered
        c.setFillColorRGB(*self.colors['dark_gray'])
        c.setFont("Helvetica-Bold", 10)
        company_text = f"{self.company_info['name']} Pty Ltd"
        company_width = c.stringWidth(company_text, "Helvetica-Bold", 10)
        c.drawString(footer_center - company_width/2, footer_height - 22, company_text)
        
        # Description - centered
        c.setFont("Helvetica", 8)
        desc_text = self.company_info['description']
        desc_width = c.stringWidth(desc_text, "Helvetica", 8)
        c.drawString(footer_center - desc_width/2, footer_height - 36, desc_text)
        
        # Contact information in footer - better spacing and alignment
        c.setFont("Helvetica", 7)
        footer_y = footer_height - 50
        
        # Left side - ABN
        c.drawString(60, footer_y, f"ABN: {self.company_info['abn']}")
        
        # Center - Email
        email_width = c.stringWidth(self.company_info['email'], "Helvetica", 7)
        c.drawString(footer_center - email_width/2, footer_y, self.company_info['email'])
        
        # Right side - Website
        website_width = c.stringWidth(self.company_info['website'], "Helvetica", 7)
        c.drawString(width - 60 - website_width, footer_y, self.company_info['website'])
        
        # Legal notice
        c.setFillColorRGB(0.5, 0.5, 0.5)
        c.setFont("Helvetica", 6)
        c.drawString(footer_center - 100, footer_height - 65, "This invoice is computer-generated and digitally verified. No signature required.")
    
    def _upload_pdf_to_s3(self, pdf_data, s3_key):
        """Upload PDF invoice to S3 bucket with fallback handling"""
        try:
            if not REPORTS_BUCKET:
                print("Warning: REPORTS_BUCKET environment variable not set - cannot upload to S3")
                print(f"Available environment variables: CLOUDFRONT_DOMAIN={CLOUDFRONT_DOMAIN}, FRONTEND_ROOT_URL={FRONTEND_ROOT_URL}")
                return {
                    'success': False,
                    'error': "REPORTS_BUCKET environment variable not set",
                    'fallback_url': f"data:application/pdf;base64,{base64.b64encode(pdf_data).decode()}"
                }

            print(f"Uploading PDF to S3 bucket: {REPORTS_BUCKET}, key: {s3_key}")
            print(f"PDF size: {len(pdf_data)} bytes")
            s3_client.put_object(
                Bucket=REPORTS_BUCKET,
                Key=s3_key,
                Body=pdf_data,
                ContentType='application/pdf',
                Metadata={
                    'generated_at': datetime.now(ZoneInfo('Australia/Perth')).isoformat(),
                    'generator': 'auto-lab-pdf-invoice-generator',
                    'format': 'pdf'
                }
            )
            
            # Generate file URL with fallback logic
            if CLOUDFRONT_DOMAIN:
                file_url = f"https://{CLOUDFRONT_DOMAIN}/{s3_key}"
            else:
                # Fallback to S3 URL if CloudFront domain is not available
                file_url = f"https://{REPORTS_BUCKET}.s3.amazonaws.com/{s3_key}"

            print(f"PDF successfully uploaded to S3: {file_url}")
            return {
                'success': True,
                'file_url': file_url
            }
            
        except Exception as e:
            print(f"Error uploading PDF to S3: {str(e)}")
            print(f"S3 upload failed, providing fallback response")
            return {
                'success': False,
                'error': str(e),
                'fallback_url': f"data:application/pdf;base64,{base64.b64encode(pdf_data).decode()}"
            }

    def _get_currency_symbol(self, currency_code):
        """Get currency symbol for display"""
        currency_symbols = {
            'AUD': 'AUD ',
            'USD': 'USD ',
            'EUR': 'EUR ',
            'GBP': 'GBP ',
            'JPY': 'JPY ',
        }
        return currency_symbols.get(currency_code.upper(), f'{currency_code.upper()} ')
