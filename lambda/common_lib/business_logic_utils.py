"""
Business logic utilities for common operations across Lambda functions
This module provides unified access to all business logic managers
"""

import functools

# Import managers from specialized modules
from appointment_manager import AppointmentManager, AppointmentUpdateManager
from order_manager import OrderManager, OrderUpdateManager
from payment_manager import PaymentManager
from email_manager import EmailManager
from email_suppression_manager import EmailSuppressionManager
from notification_manager import NotificationManager, InvoiceManager
from backup_restore_utils import BackupRestoreManager, get_backup_restore_manager
from websocket_utils import (
    WebSocketManager, ConnectionManager, UserInitManager, StaffInitManager, PingManager,
    get_connection_manager, get_user_init_manager, get_staff_init_manager, get_ping_manager
)
from data_access_utils import (
    DataAccessManager, InquiryManager, InvoiceManager as DataInvoiceManager,
    PriceManager, UserManager, MessageManager, StaffRoleManager,
    get_inquiry_manager, get_invoice_manager,
    get_price_manager, get_user_manager, get_message_manager, get_staff_role_manager
)
from analytics_manager import AnalyticsManager, get_analytics_manager
from unavailable_slots_utils import UnavailableSlotManager, get_unavailable_slot_manager
from upload_utils import UploadManager, get_upload_manager
from exceptions import BusinessLogicError


def handle_business_logic_error(func):
    """Decorator to handle BusinessLogicError exceptions"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except BusinessLogicError as e:
            print(f"BusinessLogicError in {func.__name__}: {e.message} (status: {e.status_code})")
            import response_utils as resp
            return resp.error_response(e.message, e.status_code)
        except Exception as e:
            print(f"Unexpected error in {func.__name__}: {str(e)}")
            print(f"Error type: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            import response_utils as resp
            return resp.error_response(f"Internal server error: {str(e)}", 500)
    return wrapper


# Export all managers for backward compatibility
__all__ = [
    # Manager classes
    'AppointmentManager',
    'AppointmentUpdateManager', 
    'OrderManager',
    'OrderUpdateManager',
    'PaymentManager',
    'EmailManager',
    'EmailSuppressionManager',
    'NotificationManager',
    'InvoiceManager',
    'BackupRestoreManager',
    'WebSocketManager',
    'ConnectionManager',
    'UserInitManager',
    'StaffInitManager',
    'PingManager',
    'DataAccessManager',
    'InquiryManager', 
    'DataInvoiceManager',
    'PriceManager',
    'UserManager',
    'MessageManager',
    'StaffRoleManager',
    'AnalyticsManager',
    'UnavailableSlotManager',
    'UploadManager',
    
    # Factory functions
    'get_backup_restore_manager',
    'get_connection_manager',
    'get_user_init_manager',
    'get_staff_init_manager',
    'get_ping_manager',
    'get_inquiry_manager',
    'get_invoice_manager',
    'get_price_manager',
    'get_user_manager',
    'get_message_manager',
    'get_staff_role_manager',
    'get_analytics_manager',
    'get_unavailable_slot_manager',
    'get_upload_manager',
    
    # Exception and decorator
    'BusinessLogicError',
    'handle_business_logic_error'
]
