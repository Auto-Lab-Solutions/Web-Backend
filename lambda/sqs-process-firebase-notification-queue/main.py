import json
import os
import sys
import time
import boto3
import logging
from firebase_admin import credentials, messaging, initialize_app
from botocore.exceptions import ClientError

# Add common_lib to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'common_lib'))

import db_utils as db
import response_utils as resp
import business_logic_utils as biz

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize Firebase Admin SDK
firebase_app = None

def initialize_firebase():
    """Initialize Firebase Admin SDK with service account credentials"""
    global firebase_app
    
    if firebase_app is not None:
        return firebase_app
    
    try:
        # Get Firebase configuration from environment variables
        firebase_project_id = os.environ.get('FIREBASE_PROJECT_ID')
        firebase_service_account_key = os.environ.get('FIREBASE_SERVICE_ACCOUNT_KEY')
        
        if not firebase_project_id or not firebase_service_account_key:
            logger.error("Firebase configuration missing. Please set FIREBASE_PROJECT_ID and FIREBASE_SERVICE_ACCOUNT_KEY environment variables.")
            return None
        
        # Parse the service account key JSON
        try:
            service_account_info = json.loads(firebase_service_account_key)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Firebase service account key JSON: {str(e)}")
            return None
        
        # Initialize Firebase Admin SDK
        cred = credentials.Certificate(service_account_info)
        firebase_app = initialize_app(cred, {
            'projectId': firebase_project_id
        })
        
        logger.info(f"Firebase Admin SDK initialized for project: {firebase_project_id}")
        return firebase_app
        
    except Exception as e:
        logger.error(f"Failed to initialize Firebase Admin SDK: {str(e)}")
        return None

def get_staff_fcm_tokens(staff_user_ids):
    """Get FCM tokens for staff users"""
    if not staff_user_ids:
        return []
    
    tokens = []
    
    try:
        for staff_user_id in staff_user_ids:
            # Get staff record to retrieve FCM token
            staff_record = db.get_staff_record_by_user_id(staff_user_id)
            if staff_record:
                staff_record = resp.convert_decimal(staff_record)
                fcm_token = staff_record.get('fcmToken')
                if fcm_token:
                    tokens.append({
                        'token': fcm_token,
                        'userId': staff_user_id,
                        'name': staff_record.get('name', 'Staff Member')
                    })
        
        logger.info(f"Found {len(tokens)} FCM tokens for {len(staff_user_ids)} staff users")
        return tokens
        
    except Exception as e:
        logger.error(f"Error getting staff FCM tokens: {str(e)}")
        return []

def get_all_staff_fcm_tokens(roles=None):
    """Get FCM tokens for all staff users with specified roles"""
    try:
        # Get all staff records
        staff_records = db.get_all_staff_records()
        if not staff_records:
            logger.warning("No staff records found")
            return []
        
        tokens = []
        
        for staff_record in staff_records:
            staff_record = resp.convert_decimal(staff_record)
            
            # Check if staff has required roles (if specified)
            if roles:
                staff_roles = staff_record.get('roles', [])
                if not any(role in staff_roles for role in roles):
                    continue
            
            # Check if staff is active
            if not staff_record.get('isActive', True):
                continue
            
            fcm_token = staff_record.get('fcmToken')
            if fcm_token:
                tokens.append({
                    'token': fcm_token,
                    'userId': staff_record.get('userId'),
                    'name': staff_record.get('name', 'Staff Member'),
                    'roles': staff_record.get('roles', [])
                })
        
        logger.info(f"Found {len(tokens)} FCM tokens for staff with roles: {roles}")
        return tokens
        
    except Exception as e:
        logger.error(f"Error getting all staff FCM tokens: {str(e)}")
        return []

def send_firebase_notification(notification_data):
    """Send Firebase Cloud Messaging notification"""
    
    # Initialize Firebase if not already done
    firebase_app = initialize_firebase()
    if not firebase_app:
        logger.error("Firebase not initialized. Cannot send notifications.")
        return False
    
    try:
        notification_type = notification_data.get('notification_type')
        target_type = notification_data.get('target_type', 'user')  # 'user' or 'broadcast'
        
        if target_type == 'broadcast':
            # Broadcast to all staff or staff with specific roles
            roles = notification_data.get('roles', [])
            fcm_tokens = get_all_staff_fcm_tokens(roles)
            
            # Filter out excluded users if specified
            excluded_users = notification_data.get('excluded_users', [])
            if excluded_users:
                fcm_tokens = [token for token in fcm_tokens if token.get('userId') not in excluded_users]
        else:
            # Send to specific staff users
            staff_user_ids = notification_data.get('staff_user_ids', [])
            if isinstance(staff_user_ids, str):
                staff_user_ids = [staff_user_ids]
            
            # Filter out excluded users if specified
            excluded_users = notification_data.get('excluded_users', [])
            if excluded_users:
                staff_user_ids = [uid for uid in staff_user_ids if uid not in excluded_users]
            
            fcm_tokens = get_staff_fcm_tokens(staff_user_ids)
        
        if not fcm_tokens:
            logger.warning(f"No FCM tokens found for notification type: {notification_type}")
            return True  # Not an error, just no recipients
        
        # Prepare the notification message
        title = notification_data.get('title', 'Auto Lab Solutions')
        body = notification_data.get('body', 'You have a new notification')
        data = notification_data.get('data', {})
        
        # Add notification metadata
        data.update({
            'notification_type': notification_type,
            'timestamp': str(int(time.time())),
            'environment': os.environ.get('ENVIRONMENT', 'development')
        })
        
        # Send notifications to all tokens
        success_count = 0
        failed_tokens = []
        
        for token_info in fcm_tokens:
            try:
                message = messaging.Message(
                    notification=messaging.Notification(
                        title=title,
                        body=body
                    ),
                    data=data,
                    token=token_info['token'],
                    android=messaging.AndroidConfig(
                        priority='high',
                        notification=messaging.AndroidNotification(
                            channel_id='default',
                            priority='high'
                        )
                    ),
                    apns=messaging.APNSConfig(
                        headers={'apns-priority': '10'},
                        payload=messaging.APNSPayload(
                            aps=messaging.Aps(
                                alert=messaging.ApsAlert(
                                    title=title,
                                    body=body
                                ),
                                badge=1,
                                sound='default'
                            )
                        )
                    )
                )
                
                # Send the message
                response = messaging.send(message)
                logger.info(f"Successfully sent notification to {token_info['name']} (ID: {token_info['userId']}): {response}")
                success_count += 1
                
            except messaging.UnregisteredError:
                logger.warning(f"FCM token unregistered for user {token_info['userId']}. Token should be removed from database.")
                failed_tokens.append(token_info)
            except messaging.SenderIdMismatchError:
                logger.error(f"Sender ID mismatch for user {token_info['userId']}")
                failed_tokens.append(token_info)
            except Exception as e:
                logger.error(f"Failed to send notification to {token_info['name']} (ID: {token_info['userId']}): {str(e)}")
                failed_tokens.append(token_info)
        
        # Log results
        logger.info(f"Firebase notification results - Success: {success_count}, Failed: {len(failed_tokens)}")
        
        # TODO: Consider removing invalid tokens from database
        # This could be implemented as a separate cleanup process
        
        return success_count > 0
        
    except Exception as e:
        logger.error(f"Error sending Firebase notification: {str(e)}")
        return False

@biz.handle_business_logic_error
def lambda_handler(event, context):
    """
    Process Firebase notification messages from SQS queue with enhanced error handling
    """
    try:
        logger.info(f"Processing {len(event.get('Records', []))} Firebase notification messages")
        
        processed_count = 0
        failed_count = 0
        
        for record in event.get('Records', []):
            try:
                # Parse the SQS message
                message_body = json.loads(record['body'])
                notification_type = message_body.get('notification_type', 'unknown')
                logger.info(f"Processing Firebase notification: {notification_type}")
                
                # Send the Firebase notification
                success = send_firebase_notification(message_body)
                
                if success:
                    processed_count += 1
                    logger.info(f"Successfully processed Firebase notification: {notification_type}")
                else:
                    failed_count += 1
                    logger.error(f"Failed to process Firebase notification: {notification_type}")
                
            except json.JSONDecodeError as e:
                failed_count += 1
                logger.error(f"Failed to parse SQS message body as JSON: {str(e)}")
            except Exception as e:
                failed_count += 1
                logger.error(f"Error processing Firebase notification message: {str(e)}")
        
        logger.info(f"Firebase notification processing completed - Processed: {processed_count}, Failed: {failed_count}")
        
        # Return success response using standard response format
        return resp.success_response({
            'message': f'Successfully processed {processed_count} Firebase notifications',
            'processed': processed_count,
            'failed': failed_count,
            'total_messages': len(event.get('Records', []))
        })
        
    except Exception as e:
        logger.error(f"Critical error in Firebase notification processing: {str(e)}")
        raise biz.BusinessLogicError(f"Firebase notification processing failed: {str(e)}", 500)


