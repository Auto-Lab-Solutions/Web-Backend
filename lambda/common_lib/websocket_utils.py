"""
WebSocket Manager for WebSocket operations

This module provides managers for WebSocket connection management,
user initialization, staff initialization, and related operations.
"""

import sys
import os
import uuid
import time

# Add common_lib to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'common_lib'))

import db_utils as db
import wsgw_utils as wsgw
import auth_utils as auth
from exceptions import BusinessLogicError


class WebSocketManager:
    """Base manager for WebSocket operations"""
    
    def __init__(self):
        pass
    
    def get_wsgw_client(self, domain, stage):
        """Get WebSocket API Gateway client"""
        client = wsgw.get_apigateway_client(domain, stage)
        if not client:
            raise BusinessLogicError(f"Failed to get API Gateway client for domain: {domain}, stage: {stage}", 500)
        return client
    
    def validate_connection_exists(self, connection_id):
        """Validate that a connection exists"""
        if not db.get_connection(connection_id):
            raise BusinessLogicError(f"Connection not found for connectionId: {connection_id}", 404)
        return True
    
    def send_error_notification(self, wsgw_client, connection_id, error_code, error_message=None):
        """Send error notification to connection"""
        message = {
            "type": "connection",
            "subtype": "init",
            "success": False,
            "error": error_code
        }
        if error_message:
            message["message"] = error_message
        
        return wsgw.send_notification(wsgw_client, connection_id, message)
    
    def send_success_notification(self, wsgw_client, connection_id, data=None):
        """Send success notification to connection"""
        message = {
            "type": "connection",
            "subtype": "init",
            "success": True
        }
        if data:
            message.update(data)
        
        return wsgw.send_notification(wsgw_client, connection_id, message)


class ConnectionManager(WebSocketManager):
    """Manager for WebSocket connection operations"""
    
    def create_connection(self, connection_id):
        """Create a new WebSocket connection"""
        return db.create_connection(connection_id)
    
    def disconnect_connection(self, event):
        """Handle WebSocket disconnection"""
        connection_id = event['requestContext']['connectionId']
        domain = event["requestContext"]["domainName"]
        stage = event["requestContext"]["stage"]

        connection_item = db.get_connection(connection_id)
        if not connection_item:
            print(f"Connection not found for connectionId: {connection_id}")
            return {"statusCode": 200}

        db.delete_connection(connection_id)

        user_id = connection_item.get('userId')
        if not user_id:
            print(f"Connection closed for connectionId: {connection_id} with no userId.")
            return {"statusCode": 200}
        
        wsgw_client = self.get_wsgw_client(domain, stage)

        message_body = {
            "type": "notification",
            "subtype": "user-disconnected",
            "success": True,
            "userId": user_id,
            "lastSeen": str(int(time.time()))
        }

        # delete all uninitialized connections
        db.delete_all_uninitialized_connections()
        
        if not connection_item.get('staff'):
            db.update_user_disconnected_time(user_id)
            user_record = db.get_user_record(user_id)
            assigned_to = user_record.get('assignedTo') if user_record else ''
            staff_connections = db.get_assigned_or_all_staff_connections(assigned_to)
            for connection in staff_connections:
                staff_conn_id = connection.get('connectionId')
                wsgw.send_notification(wsgw_client, staff_conn_id, message_body)

        print(f"Connection closed for connectionId: {connection_id} with userId: {user_id}")
        return {"statusCode": 200}


class UserInitManager(WebSocketManager):
    """Manager for user WebSocket initialization"""
    
    def initialize_user_connection(self, event):
        """Initialize user WebSocket connection"""
        connection_id = event.get('connectionId')
        domain = event.get('domain')
        stage = event.get('stage')
        request_body = event.get('body', {})
        
        user_id = request_body.get('userId', '')
        user_email = request_body.get('userEmail', '')
        user_name = request_body.get('userName', '')
        user_device = request_body.get('userDevice', '')
        user_location = request_body.get('userLocation', '')

        wsgw_client = self.get_wsgw_client(domain, stage)
        self.validate_connection_exists(connection_id)

        assigned_to = ''
        user_record = None

        if user_id:
            db.delete_old_connections(user_id)
            user_record = db.get_user_record(user_id)
            if user_record:
                if 'assignedTo' in user_record:
                    assigned_to = user_record.get('assignedTo')
            else:
                self.send_error_notification(wsgw_client, connection_id, "INVALID_USER_ID")
                return {"statusCode": 400}

        user_id = user_id or str(uuid.uuid4())

        # Update connection with userId and staff status
        connection_data = {
            'userId': user_id,
            'staff': 'false'
        }
        update_success = db.update_connection(connection_id, connection_data)
        if not update_success:
            print(f"Failed to update connection {connection_id} with userId {user_id}")
            self.send_error_notification(wsgw_client, connection_id, "UPDATE_CONNECTION_FAILED")
            return {"statusCode": 500}

        # Create or update user record
        new_user_record = db.build_user_record(
            user_id,
            user_record,
            user_email=user_email,
            user_name=user_name,
            user_device=user_device,
            user_location=user_location,
            assigned_to=assigned_to
        )
        create_or_update_success = db.create_or_update_user_record(new_user_record)
        if not create_or_update_success:
            print(f"Failed to create or update user record for userId {user_id}")
            self.send_error_notification(wsgw_client, connection_id, "UPDATE_USER_RECORD_FAILED")
            return {"statusCode": 500}

        # Send success notification to staff
        message_body = {
            "type": "notification",
            "subtype": "user-connected",
            "userId": user_id,
            "userEmail": user_email,
            "userName": user_name,
            "userDevice": user_device,
            "userLocation": user_location,
            "assignedTo": assigned_to
        }
        receivers = db.get_assigned_or_all_staff_connections(assigned_to=assigned_to)
        if receivers:
            for staff_conn in receivers:
                staff_conn_id = staff_conn.get('connectionId')
                wsgw.send_notification(wsgw_client, staff_conn_id, message_body)
        
        # Send success notification to user
        user_data = {
            "userId": user_id,
            "userEmail": user_email,
            "userName": user_name,
            "userDevice": user_device,
            "userLocation": user_location,
            "assignedTo": assigned_to
        }
        self.send_success_notification(wsgw_client, connection_id, user_data)

        print(f"Connection established for connectionId: {connection_id} with userId: {user_id}")
        return {"statusCode": 200}


class StaffInitManager(WebSocketManager):
    """Manager for staff WebSocket initialization"""
    
    def __init__(self):
        super().__init__()
        self.permitted_roles = ['CUSTOMER_SUPPORT', 'CLERK']
    
    def initialize_staff_connection(self, event):
        """Initialize staff WebSocket connection"""
        connection_id = event.get('connectionId')
        domain = event.get('domain')
        stage = event.get('stage')
        request_body = event.get('body', {})
        token = request_body.get('token', '')

        wsgw_client = self.get_wsgw_client(domain, stage)
        self.validate_connection_exists(connection_id)

        # Validate token
        user_email = auth.get_user_email(token)
        if not user_email:
            self.send_error_notification(wsgw_client, connection_id, "INVALID_TOKEN")
            return {"statusCode": 401}
        
        # Validate staff user
        staff_user_record = db.get_staff_record(user_email)
        if not staff_user_record:
            self.send_error_notification(wsgw_client, connection_id, "INVALID_USER")
            return {"statusCode": 404}
        
        staff_user_id = staff_user_record.get('userId')
        staff_roles = staff_user_record.get('roles', [])
        if not staff_user_id or not staff_roles:
            self.send_error_notification(wsgw_client, connection_id, "MISSING_USER_ID_OR_ROLES")
            return {"statusCode": 400}

        # Validate staff roles
        if not any(role in staff_roles for role in self.permitted_roles):
            self.send_error_notification(wsgw_client, connection_id, "UNAUTHORIZED_ROLE")
            return {"statusCode": 403}
        
        # Clean up old connections and update current connection
        db.delete_old_connections(staff_user_id)

        connection_data = {
            'userId': staff_user_id,
            'staff': 'true'
        }
        update_success = db.update_connection(connection_id, connection_data)

        if not update_success:
            self.send_error_notification(wsgw_client, connection_id, "UPDATE_CONNECTION_FAILED")
            return {"statusCode": 500}

        # Send success notification
        staff_data = {
            "userId": staff_user_id
        }
        self.send_success_notification(wsgw_client, connection_id, staff_data)

        print(f"Connection established for connectionId: {connection_id} with userId: {staff_user_id}")
        return {"statusCode": 200}


class PingManager(WebSocketManager):
    """Manager for WebSocket ping operations"""
    
    def handle_ping(self, event):
        """Handle WebSocket ping"""
        connection_id = event.get('connectionId')
        domain = event.get('domain')
        stage = event.get('stage')
        request_body = event.get('body', {})
        
        user_id = request_body.get('userId', '')
        print(f"Received ping for connection {connection_id} with userId {user_id}")

        return {"statusCode": 200}


def get_connection_manager():
    """Factory function to get ConnectionManager instance"""
    return ConnectionManager()


def get_user_init_manager():
    """Factory function to get UserInitManager instance"""
    return UserInitManager()


def get_staff_init_manager():
    """Factory function to get StaffInitManager instance"""
    return StaffInitManager()


def get_ping_manager():
    """Factory function to get PingManager instance"""
    return PingManager()
