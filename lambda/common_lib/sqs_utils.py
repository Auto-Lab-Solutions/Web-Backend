"""
SQS utilities for invoice generation (legacy module)
This module is deprecated - use InvoiceManager from notification_manager instead
"""

from notification_manager import invoice_manager

# Legacy functions for backward compatibility
def queue_invoice_generation(record, record_type, payment_intent_id):
    """Queue invoice generation for asynchronous processing (deprecated - use InvoiceManager)"""
    return invoice_manager.queue_invoice_generation(record, record_type, payment_intent_id)

def generate_invoice_synchronously(record, record_type, payment_intent_id):
    """Generate invoice synchronously (deprecated - use InvoiceManager)"""
    return invoice_manager._generate_invoice_synchronously(record, record_type, payment_intent_id)

def send_payment_confirmation_email_with_invoice(record, record_type, invoice_url, payment_intent_id):
    """Send payment confirmation email with invoice (deprecated - use InvoiceManager)"""
    return invoice_manager._send_payment_confirmation_email_with_invoice(record, record_type, invoice_url, payment_intent_id)
