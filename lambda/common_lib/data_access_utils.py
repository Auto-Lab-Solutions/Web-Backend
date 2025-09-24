"""
Data Access Manager for API operations

This module provides managers for common data access patterns used across
API Lambda functions, including analytics, inquiries, prices, users, etc.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from collections import defaultdict, Counter

import db_utils as db
import request_utils as req
from exceptions import BusinessLogicError


class DataAccessManager:
    """Base manager for common data access patterns"""
    
    def __init__(self):
        pass
    
    def validate_staff_authentication(self, event, required_roles=None):
        """
        Validate staff authentication and return staff context
        
        Args:
            event: Lambda event
            required_roles: List of required roles (optional)
            
        Returns:
            dict: Staff context with user info and roles
            
        Raises:
            BusinessLogicError: If authentication fails
        """
        staff_user_email = req.get_staff_user_email(event)
        if not staff_user_email:
            raise BusinessLogicError("Unauthorized: Staff authentication required", 401)
        
        staff_user_record = db.get_staff_record(staff_user_email)
        if not staff_user_record:
            raise BusinessLogicError(f"No staff record found for email: {staff_user_email}", 404)
        
        staff_roles = staff_user_record.get('roles', [])
        staff_user_id = staff_user_record.get('userId')
        
        # Check role requirements if specified
        if required_roles:
            if not any(role in staff_roles for role in required_roles):
                required_roles_str = ', '.join(required_roles)
                raise BusinessLogicError(f"Unauthorized: {required_roles_str} role required", 403)
        
        return {
            'staff_user_email': staff_user_email,
            'staff_user_id': staff_user_id,
            'staff_roles': staff_roles,
            'staff_record': staff_user_record
        }
    
    def validate_shared_key_authentication(self, event, required_shared_key):
        """
        Validate shared key authentication
        
        Args:
            event: Lambda event
            required_shared_key: Expected shared key value
            
        Returns:
            str: Email from request
            
        Raises:
            BusinessLogicError: If authentication fails
        """
        email = req.get_query_param(event, 'email')
        shared_key = req.get_header(event, 'shared-api-key')
        
        if not email or not shared_key:
            raise BusinessLogicError("Email and sharedKey are required", 400)
        
        if shared_key != required_shared_key:
            raise BusinessLogicError("Invalid sharedKey provided", 401)
        
        return email
    
    def validate_date_parameter(self, date_str, param_name='date'):
        """
        Validate date parameter in YYYY-MM-DD format
        
        Args:
            date_str: Date string to validate
            param_name: Parameter name for error messages
            
        Returns:
            datetime: Parsed datetime object
            
        Raises:
            BusinessLogicError: If date format is invalid
        """
        if not date_str:
            raise BusinessLogicError(f"{param_name} parameter is required", 400)
        
        try:
            # Parse date and set Perth timezone
            return datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=ZoneInfo('Australia/Perth'))
        except ValueError:
            raise BusinessLogicError(f"{param_name} must be in YYYY-MM-DD format", 400)
    
    def validate_date_range(self, start_date_str, end_date_str, max_days=None):
        """
        Validate date range parameters
        
        Args:
            start_date_str: Start date string
            end_date_str: End date string
            max_days: Maximum allowed range in days (optional)
            
        Returns:
            tuple: (start_datetime, end_datetime)
            
        Raises:
            BusinessLogicError: If date range is invalid
        """
        start_dt = self.validate_date_parameter(start_date_str, 'startDate')
        end_dt = self.validate_date_parameter(end_date_str, 'endDate')
        
        if end_dt < start_dt:
            raise BusinessLogicError("End date must be on or after start date", 400)
        
        if max_days:
            range_days = (end_dt - start_dt).days
            if range_days > max_days:
                raise BusinessLogicError(f"Date range cannot exceed {max_days} days", 400)
        
        return start_dt, end_dt
    
    def validate_timestamp_range(self, start_timestamp_str, end_timestamp_str, max_seconds=None):
        """
        Validate timestamp range parameters
        
        Args:
            start_timestamp_str: Start timestamp string
            end_timestamp_str: End timestamp string
            max_seconds: Maximum allowed range in seconds (optional)
            
        Returns:
            tuple: (start_timestamp, end_timestamp)
            
        Raises:
            BusinessLogicError: If timestamp range is invalid
        """
        if not start_timestamp_str or not end_timestamp_str:
            raise BusinessLogicError("start_date and end_date parameters are required (timestamps)", 400)
        
        try:
            start_timestamp = int(start_timestamp_str)
            end_timestamp = int(end_timestamp_str)
        except ValueError:
            raise BusinessLogicError("start_date and end_date must be valid timestamps", 400)
        
        if end_timestamp <= start_timestamp:
            raise BusinessLogicError("end_date must be greater than start_date", 400)
        
        if max_seconds:
            range_seconds = end_timestamp - start_timestamp
            if range_seconds > max_seconds:
                max_days = max_seconds // (24 * 60 * 60)
                raise BusinessLogicError(f"Date range cannot exceed {max_days} days", 400)
        
        return start_timestamp, end_timestamp

    def validate_date_range(self, start_date_str, end_date_str, max_days=None):
        """
        Validate date range parameters in YYYY-MM-DD format
        
        Args:
            start_date_str: Start date string in YYYY-MM-DD format
            end_date_str: End date string in YYYY-MM-DD format
            max_days: Maximum allowed range in days (optional)
            
        Returns:
            tuple: (start_timestamp, end_timestamp)
            
        Raises:
            BusinessLogicError: If date range is invalid
        """
        from datetime import datetime, timezone
        
        if not start_date_str or not end_date_str:
            raise BusinessLogicError("start_date and end_date parameters are required (YYYY-MM-DD format)", 400)
        
        try:
            # Parse dates in YYYY-MM-DD format with Perth timezone
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').replace(tzinfo=ZoneInfo('Australia/Perth'))
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').replace(tzinfo=ZoneInfo('Australia/Perth'))
            
            # Convert to end of day for end_date to include the entire day
            end_date = end_date.replace(hour=23, minute=59, second=59)
            
        except ValueError:
            raise BusinessLogicError("start_date and end_date must be in YYYY-MM-DD format", 400)
        
        if end_date <= start_date:
            raise BusinessLogicError("end_date must be greater than or equal to start_date", 400)
        
        if max_days:
            range_days = (end_date - start_date).days
            if range_days > max_days:
                raise BusinessLogicError(f"Date range cannot exceed {max_days} days", 400)
        
        # Convert to timestamps
        start_timestamp = int(start_date.timestamp())
        end_timestamp = int(end_date.timestamp())
        
        return start_timestamp, end_timestamp


class InquiryManager(DataAccessManager):
    """Manager for inquiry data operations"""
    
    def get_inquiry_by_id(self, inquiry_id):
        """Get single inquiry by ID"""
        if not inquiry_id:
            raise BusinessLogicError("Inquiry ID is required", 400)
        
        inquiry = db.get_inquiry(inquiry_id)
        if not inquiry:
            raise BusinessLogicError("Inquiry not found", 404)
        
        return inquiry
    
    def get_all_inquiries_with_filters(self, event):
        """Get all inquiries with optional filters"""
        inquiries = db.get_all_inquiries()
        # Filter to last 2 months
        now = int(datetime.now(ZoneInfo('Australia/Perth')).timestamp())
        two_months_ago = now - 60 * 24 * 60 * 60  # 60 days in seconds
        inquiries = [inq for inq in inquiries if int(inq.get('createdAt', 0)) >= two_months_ago]
        # Apply query parameter filters (implementation would be moved from original function)
        inquiries = self._apply_inquiry_filters(inquiries, event)
        # Sort by creation date (newest first)
        inquiries.sort(key=lambda x: x.get('createdAt', 0), reverse=True)
        return inquiries
    
    def _apply_inquiry_filters(self, inquiries, event):
        """Apply query parameter filters to inquiries"""
        if not inquiries:
            return inquiries
        
        # Get filter parameters from query string
        status = req.get_query_param(event, 'status')
        start_date = req.get_query_param(event, 'startDate')
        end_date = req.get_query_param(event, 'endDate')
        user_id = req.get_query_param(event, 'userId')
        
        filtered_inquiries = inquiries
        
        # Filter by status
        if status:
            filtered_inquiries = [
                inquiry for inquiry in filtered_inquiries 
                if inquiry.get('status', '').upper() == status.upper()
            ]
        
        # Filter by userId
        if user_id:
            filtered_inquiries = [
                inquiry for inquiry in filtered_inquiries 
                if inquiry.get('userId', '') == user_id
            ]
        
        # Filter by date range
        if start_date:
            if end_date:
                # Filter by date range
                filtered_inquiries = [
                    inquiry for inquiry in filtered_inquiries 
                    if start_date <= inquiry.get('createdDate', '') <= end_date
                ]
            else:
                # Filter from start date onwards
                filtered_inquiries = [
                    inquiry for inquiry in filtered_inquiries 
                    if inquiry.get('createdDate', '') >= start_date
                ]
        elif end_date:
            # Filter up to end date
            filtered_inquiries = [
                inquiry for inquiry in filtered_inquiries 
                if inquiry.get('createdDate', '') <= end_date
            ]
        
        return filtered_inquiries


class InvoiceManager(DataAccessManager):
    """Manager for invoice data operations"""
    
    def get_invoices_by_date_range(self, start_date_str, end_date_str, limit_str='2000'):
        """
        Get invoices within date range
        
        Args:
            start_date_str: Start timestamp string
            end_date_str: End timestamp string  
            limit_str: Limit parameter string
            
        Returns:
            list: Invoices within date range
        """
        # Validate timestamp range (max 90 days)
        max_range = 90 * 24 * 60 * 60  # 90 days in seconds
        start_timestamp, end_timestamp = self.validate_timestamp_range(
            start_date_str, end_date_str, max_range
        )
        
        # Validate limit
        try:
            limit = int(limit_str)
        except (ValueError, TypeError):
            limit = 2000
        
        # Get invoices from database
        invoices = db.get_invoices_by_date_range(start_timestamp, end_timestamp, limit)
        return invoices

    def get_invoices_by_date_range_formatted(self, start_date_str, end_date_str, limit_str='2000'):
        """
        Get invoices within date range using YYYY-MM-DD format (excludes cancelled invoices)
        
        Args:
            start_date_str: Start date string in YYYY-MM-DD format
            end_date_str: End date string in YYYY-MM-DD format  
            limit_str: Limit parameter string
            
        Returns:
            list: Active invoices within date range (cancelled invoices excluded)
        """
        # Validate date range (max 90 days)
        start_timestamp, end_timestamp = self.validate_date_range(
            start_date_str, end_date_str, max_days=90
        )
        
        # Validate limit
        try:
            limit = int(limit_str)
        except (ValueError, TypeError):
            limit = 2000
        
        # Get invoices from database (excludes cancelled invoices)
        invoices = db.get_invoices_by_date_range(start_timestamp, end_timestamp, limit)
        return invoices

    def get_all_invoices_by_date_range_formatted(self, start_date_str, end_date_str, limit_str='2000'):
        """
        Get ALL invoices within date range using YYYY-MM-DD format (includes cancelled invoices)
        
        This method is intended for administrative purposes where all invoices need to be retrieved,
        including cancelled ones for audit and reporting purposes.
        
        Args:
            start_date_str: Start date string in YYYY-MM-DD format
            end_date_str: End date string in YYYY-MM-DD format  
            limit_str: Limit parameter string
            
        Returns:
            list: All invoices within date range (including cancelled invoices)
        """
        # Validate date range (max 90 days)
        start_timestamp, end_timestamp = self.validate_date_range(
            start_date_str, end_date_str, max_days=90
        )
        
        # Validate limit
        try:
            limit = int(limit_str)
        except (ValueError, TypeError):
            limit = 2000
        
        # Get ALL invoices from database (including cancelled invoices)
        invoices = db.get_all_invoices_by_date_range(start_timestamp, end_timestamp, limit)
        return invoices


class PriceManager(DataAccessManager):
    """Manager for price data operations"""
    
    def get_all_prices(self):
        """Get all item and service prices"""
        item_prices = db.get_all_item_prices()
        service_prices = db.get_all_service_prices()
        
        return {
            'item_prices': item_prices,
            'service_prices': service_prices,
            'timestamp': datetime.now(ZoneInfo('Australia/Perth')).isoformat()
        }


class UserManager(DataAccessManager):
    """Manager for user data operations"""
    
    def get_all_users(self):
        """Get all customer and staff users, excluding inactive customers (not seen in 2 months)"""
        now = int(datetime.now(ZoneInfo('Australia/Perth')).timestamp())
        two_months_ago = now - 60 * 24 * 60 * 60  # 60 days in seconds
        customer_users = db.get_all_users()
        # Only include customers with lastSeen in last 2 months (or if lastSeen missing, include by default)
        filtered_customers = [u for u in customer_users if not u.get('lastSeen') or int(u.get('lastSeen', 0)) >= two_months_ago]
        staff_users = db.get_all_staff_records()
        return {
            'customer_users': filtered_customers,
            'staff_users': staff_users
        }


class MessageManager(DataAccessManager):
    """Manager for message data operations"""
    
    @staticmethod
    def send_message(staff_user_email=None, client_id=None, message_id=None, message=None):
        """
        Send a message between staff and client with notifications
        
        Args:
            staff_user_email: Email of the staff user sending the message
            client_id: ID of the client (can be sender or receiver)
            message_id: Unique ID for the message
            message: Message content
            
        Returns:
            dict: Result with message details and success status
        """
        # Validate required parameters
        if not message_id or not message or not client_id:
            raise BusinessLogicError("messageId, message, and clientId are required", 400)
        
        sender_id = None
        receiver_id = None
        sender_name = "Unknown"
        
        # Determine sender and receiver based on staff_user_email presence
        if staff_user_email:
            # Staff is sending message to client
            staff_record = db.get_staff_record(staff_user_email)
            if not staff_record:
                raise BusinessLogicError("Staff user not found", 404)
            
            sender_id = staff_record.get('userId')
            sender_name = staff_record.get('name', staff_user_email)
            receiver_id = client_id
            
            # Validate client exists
            if not db.get_user_record(client_id):
                raise BusinessLogicError(f"Client with userId {client_id} does not exist", 404)
        else:
            # Client is sending message to staff (broadcast to all staff)
            client_record = db.get_user_record(client_id)
            if not client_record:
                raise BusinessLogicError(f"Client with userId {client_id} does not exist", 404)
            
            sender_id = client_id
            sender_name = client_record.get('name', 'Customer')
            receiver_id = "ALL"  # Broadcast to all staff
        
        # Build and create message data
        message_data = db.build_message_data(message_id, message, sender_id, receiver_id)
        create_success = db.create_message(message_data)
        
        if not create_success:
            raise BusinessLogicError("Failed to create message", 500)
        
        # Send notifications
        try:
            import sync_websocket_utils as sync_ws
            import notification_utils as notif
            
            if staff_user_email:
                # Staff is sending message to client - notify the client directly via websocket
                sync_ws.send_message_websocket_notification(message_id, sender_id, receiver_id, message)
            else:
                # Client is sending message - check if client has assigned staff
                client_record = db.get_user_record(client_id)
                assigned_to = client_record.get('assignedTo') if client_record else None
                
                if assigned_to:
                    # Client has assigned staff - only notify that specific staff member
                    print(f"Client {client_id} has assigned staff {assigned_to} - sending targeted notification")
                    sync_ws.send_message_websocket_notification(message_id, sender_id, assigned_to, message)
                    notif.queue_message_firebase_notification(message_id, sender_name, staff_user_ids=[assigned_to])
                else:
                    # Client has no assigned staff - broadcast to all staff
                    print(f"Client {client_id} has no assigned staff - broadcasting to all staff")
                    sync_ws.send_message_websocket_notification(message_id, sender_id, "ALL", message)
                    notif.queue_message_firebase_notification(message_id, sender_name, 'staff')
        
        except Exception as e:
            print(f"Warning: Failed to send notifications for message {message_id}: {str(e)}")
            # Continue execution even if notifications fail
        
        return {
            "messageId": message_id,
            "senderId": sender_id,
            "receiverId": receiver_id,
            "message": message,
            "sent": True,
            "senderName": sender_name
        }
    
    def get_user_messages(self, client_id):
        """
        Get all messages for a user
        
        Args:
            client_id: User ID to get messages for
            
        Returns:
            list: Sorted messages for the user
        """
        if not client_id:
            raise BusinessLogicError("clientId is required", 400)
        
        # Validate client is not staff
        if db.get_staff_record(client_id):
            raise BusinessLogicError("Cannot retrieve messages for staff userId", 400)
        
        # Validate user exists
        if not db.get_user_record(client_id):
            raise BusinessLogicError(f"User with userId {client_id} does not exist", 404)
        
        # Get messages where user is sender or receiver
        sender_messages = db.get_messages_by_index(
            index_name='senderId-index', 
            key_name='senderId', 
            key_value=client_id
        )
        receiver_messages = db.get_messages_by_index(
            index_name='receiverId-index', 
            key_name='receiverId', 
            key_value=client_id
        )
        
        all_messages = sender_messages + receiver_messages
        # Filter to last 2 months
        now = int(datetime.now(ZoneInfo('Australia/Perth')).timestamp())
        two_months_ago = now - 60 * 24 * 60 * 60  # 60 days in seconds
        filtered_messages = [msg for msg in all_messages if int(msg.get('createdAt', 0)) >= two_months_ago]
        # Sort by creation date (newest first)
        sorted_messages = sorted(
            filtered_messages,
            key=lambda x: int(x.get('createdAt', 0)),
            reverse=True
        )
        return sorted_messages


class StaffRoleManager(DataAccessManager):
    """Manager for staff role operations"""
    
    def get_staff_roles(self, email, shared_key, required_shared_key):
        """
        Get staff roles by email with shared key authentication
        
        Args:
            email: Staff email
            shared_key: Provided shared key
            required_shared_key: Expected shared key
            
        Returns:
            list: Staff roles
        """
        print(f"StaffRoleManager.get_staff_roles called with email: {email}")
        
        # Validate shared key authentication
        if not email or not shared_key:
            print("Missing email or shared_key parameter")
            raise BusinessLogicError("Email and sharedKey are required", 400)
        
        if shared_key != required_shared_key:
            print("Invalid shared key provided")
            raise BusinessLogicError("Invalid sharedKey provided", 401)
        
        print("Shared key validation successful")
        
        try:
            # Get staff record with enhanced error handling
            print(f"Querying staff record for email: {email}")
            staff_record = db.get_staff_record(email, raise_on_error=True)
            
            if not staff_record:
                print(f"No staff record found for email: {email}")
                raise BusinessLogicError(f"No staff record found for email: {email}", 404)
            
            print(f"Staff record found: {staff_record}")
            roles = staff_record.get('roles', [])
            print(f"Extracted roles: {roles}")
            
            return roles
            
        except BusinessLogicError:
            # Re-raise business logic errors as-is
            raise
        except Exception as e:
            print(f"Unexpected error in get_staff_roles: {str(e)}")
            print(f"Error type: {type(e).__name__}")
            import traceback
            traceback.print_exc()
            raise BusinessLogicError(f"Database error while retrieving staff roles: {str(e)}", 500)


def get_inquiry_manager():
    """Factory function to get InquiryManager instance"""
    return InquiryManager()


def get_invoice_manager():
    """Factory function to get InvoiceManager instance"""
    return InvoiceManager()


def get_price_manager():
    """Factory function to get PriceManager instance"""
    return PriceManager()


def get_user_manager():
    """Factory function to get UserManager instance"""
    return UserManager()


def get_message_manager():
    """Factory function to get MessageManager instance"""
    return MessageManager()


def get_staff_role_manager():
    """Factory function to get StaffRoleManager instance"""
    return StaffRoleManager()
