"""
Invoice Data Utilities
Utility functions for invoice data operations that don't require PDF generation
"""

import validation_utils as valid

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
        from zoneinfo import ZoneInfo
        
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
        
        # Convert scheduled_date to analytics format (DD/MM/YYYY) using validation function
        try:
            effective_date = valid.DataValidator.validate_and_convert_date_to_analytics_format(
                scheduled_date, 'scheduled_date'
            )
        except valid.ValidationError as e:
            print(f"Invalid date format for scheduled_date: {scheduled_date}. Error: {e.message}")
            return False
        
        # Update the effective date in analytics data
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
