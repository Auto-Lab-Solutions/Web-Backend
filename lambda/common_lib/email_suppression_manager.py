"""
Email Suppression Management Module
Handles email bounce/complaint processing and suppression list management
"""

import boto3
import os
import json
from datetime import datetime, timedelta
from botocore.exceptions import ClientError

import permission_utils as perm
from exceptions import BusinessLogicError
from email_manager import EmailManager


class EmailSuppressionManager:
    """Manages email suppression and bounce handling"""
    
    @staticmethod
    def manage_suppression(staff_user_email, action, email_addresses):
        """Handle email bounce/complaint management"""
        # Validate staff permissions  
        staff_context = perm.PermissionValidator.validate_staff_access(
            staff_user_email,
            required_roles=['ADMIN', 'CUSTOMER_SUPPORT']
        )
        
        if not email_addresses:
            raise BusinessLogicError("Email addresses are required")
        
        if isinstance(email_addresses, str):
            email_addresses = [email_addresses]
        
        # Validate email format
        for email_addr in email_addresses:
            if not EmailManager._is_valid_email(email_addr):
                raise BusinessLogicError(f"Invalid email address: {email_addr}")
        
        try:
            if action == 'add':
                return EmailSuppressionManager._add_to_suppression_list(email_addresses)
            elif action == 'remove':
                return EmailSuppressionManager._remove_from_suppression_list(email_addresses)
            elif action == 'check':
                return EmailSuppressionManager._check_suppression_status(email_addresses)
            else:
                raise BusinessLogicError("Invalid action. Must be 'add', 'remove', or 'check'")
                
        except Exception as e:
            print(f"Suppression management error: {str(e)}")
            raise BusinessLogicError(f"Failed to manage suppression list: {str(e)}", 500)
    
    @staticmethod
    def process_bounce(email_address, bounce_type, bounce_subtype, notification):
        """Process a bounce notification and determine if suppression is needed"""
        # Bounce types that should result in permanent suppression
        PERMANENT_BOUNCE_TYPES = [
            'Permanent',
            'Undetermined'  # Treat undetermined as permanent to be safe
        ]
        
        PERMANENT_BOUNCE_SUBTYPES = [
            'General',
            'NoEmail', 
            'Suppressed',
            'OnAccountSuppressionList'
        ]
        
        try:
            # Determine if this should result in permanent suppression
            should_suppress = (
                bounce_type in PERMANENT_BOUNCE_TYPES or
                bounce_subtype in PERMANENT_BOUNCE_SUBTYPES
            )
            
            if should_suppress:
                # Add to suppression list
                suppression_result = EmailSuppressionManager._add_bounce_to_suppression_list(
                    email_address, 
                    bounce_type, 
                    bounce_subtype,
                    notification
                )
                
                # Record analytics
                EmailSuppressionManager._record_bounce_analytics(
                    email_address,
                    bounce_type,
                    bounce_subtype,
                    notification,
                    suppressed=True
                )
                
                return {
                    'suppressed': True,
                    'reason': f'{bounce_type}/{bounce_subtype}'
                }
            else:
                # Just record analytics for transient bounces
                EmailSuppressionManager._record_bounce_analytics(
                    email_address,
                    bounce_type,
                    bounce_subtype,
                    notification,
                    suppressed=False
                )
                
                return {
                    'suppressed': False,
                    'reason': f'Transient bounce: {bounce_type}/{bounce_subtype}'
                }
                
        except Exception as e:
            print(f"Error processing bounce: {str(e)}")
            return {
                'suppressed': False,
                'error': str(e)
            }
    
    @staticmethod
    def process_complaint(email_address, complaint_feedback_type, complaint_subtype, notification):
        """Process a complaint notification and add to suppression"""
        try:
            # Always suppress emails that generate complaints - complaints are serious
            suppression_result = EmailSuppressionManager._add_complaint_to_suppression_list(
                email_address, 
                complaint_feedback_type, 
                complaint_subtype,
                notification
            )
            
            # Record analytics
            EmailSuppressionManager._record_complaint_analytics(
                email_address,
                complaint_feedback_type,
                complaint_subtype,
                notification
            )
            
            return {
                'suppressed': True,
                'reason': f'Complaint: {complaint_feedback_type}/{complaint_subtype}'
            }
                
        except Exception as e:
            print(f"Error processing complaint: {str(e)}")
            return {
                'suppressed': False,
                'error': str(e)
            }

    @staticmethod
    def check_suppression_status(email):
        """Check if an email address is suppressed with detailed status"""
        # Initialize AWS clients
        dynamodb = boto3.resource('dynamodb')
        ses_client = boto3.client('ses')
        
        # Environment variables
        SUPPRESSION_TABLE_NAME = os.environ.get('SUPPRESSION_TABLE_NAME')
        
        try:
            if not SUPPRESSION_TABLE_NAME:
                raise BusinessLogicError("Suppression table not configured")
            
            suppression_table = dynamodb.Table(SUPPRESSION_TABLE_NAME)
            
            # Check local suppression table
            response = suppression_table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key('email').eq(email)
            )
            
            local_suppressions = []
            for item in response['Items']:
                if item.get('status') == 'active':
                    local_suppressions.append({
                        'type': item['suppression_type'],
                        'created_at': item['created_at'],
                        'reason': item.get('bounce_type') or item.get('complaint_type', 'Unknown')
                    })
            
            # Check SES account-level suppression
            ses_suppressed = False
            ses_reason = None
            try:
                ses_response = ses_client.get_suppressed_destination(EmailAddress=email)
                ses_suppressed = True
                ses_reason = ses_response.get('SuppressedDestination', {}).get('Reason')
            except ClientError as e:
                if e.response['Error']['Code'] != 'NotFoundException':
                    print(f"Error checking SES suppression: {e}")
            
            result = {
                'email': email,
                'is_suppressed': len(local_suppressions) > 0 or ses_suppressed,
                'local_suppressions': local_suppressions,
                'ses_suppressed': ses_suppressed,
                'ses_reason': ses_reason,
                'checked_at': datetime.utcnow().isoformat() + 'Z'
            }
            
            return result
            
        except Exception as e:
            print(f"Error checking suppression status: {str(e)}")
            raise BusinessLogicError(f"Failed to check suppression status: {str(e)}")

    @staticmethod
    def list_suppressed_emails(limit=50, suppression_type=None, last_evaluated_key=None):
        """List suppressed email addresses with pagination"""
        # Initialize AWS clients
        dynamodb = boto3.resource('dynamodb')
        
        # Environment variables
        SUPPRESSION_TABLE_NAME = os.environ.get('SUPPRESSION_TABLE_NAME')
        
        try:
            if not SUPPRESSION_TABLE_NAME:
                raise BusinessLogicError("Suppression table not configured")
            
            suppression_table = dynamodb.Table(SUPPRESSION_TABLE_NAME)
            
            if limit > 100:
                limit = 100  # Maximum limit
            
            scan_kwargs = {
                'Limit': limit,
                'FilterExpression': boto3.dynamodb.conditions.Attr('status').eq('active')
            }
            
            if suppression_type:
                scan_kwargs['FilterExpression'] &= boto3.dynamodb.conditions.Attr('suppression_type').eq(suppression_type)
            
            if last_evaluated_key:
                try:
                    scan_kwargs['ExclusiveStartKey'] = json.loads(last_evaluated_key)
                except:
                    pass  # Invalid lastKey, ignore
            
            response = suppression_table.scan(**scan_kwargs)
            
            items = []
            for item in response['Items']:
                items.append({
                    'email': item['email'],
                    'suppression_type': item['suppression_type'],
                    'created_at': item['created_at'],
                    'reason': item.get('bounce_type') or item.get('complaint_type', 'Unknown')
                })
            
            result = {
                'items': items,
                'count': len(items),
                'lastEvaluatedKey': json.dumps(response.get('LastEvaluatedKey')) if response.get('LastEvaluatedKey') else None
            }
            
            return result
            
        except Exception as e:
            print(f"Error listing suppressed emails: {str(e)}")
            raise BusinessLogicError(f"Failed to list suppressed emails: {str(e)}")

    @staticmethod
    def _add_to_suppression_list(email_addresses):
        """Add emails to suppression list"""
        dynamodb = boto3.resource('dynamodb')
        table_name = os.environ.get('EMAIL_SUPPRESSION_TABLE_NAME')
        
        if not table_name:
            raise BusinessLogicError("Email suppression table not configured")
        
        table = dynamodb.Table(table_name)
        results = []
        
        for email in email_addresses:
            try:
                table.put_item(
                    Item={
                        'email': email.lower(),
                        'reason': 'manual_addition',
                        'timestamp': datetime.utcnow().isoformat(),
                        'status': 'suppressed'
                    }
                )
                results.append({'email': email, 'status': 'added'})
            except Exception as e:
                results.append({'email': email, 'status': 'failed', 'error': str(e)})
        
        return {'action': 'add', 'results': results}
    
    @staticmethod 
    def _remove_from_suppression_list(email_addresses):
        """Remove emails from suppression list"""
        dynamodb = boto3.resource('dynamodb')
        table_name = os.environ.get('EMAIL_SUPPRESSION_TABLE_NAME')
        
        if not table_name:
            raise BusinessLogicError("Email suppression table not configured")
        
        table = dynamodb.Table(table_name)
        results = []
        
        for email in email_addresses:
            try:
                table.delete_item(Key={'email': email.lower()})
                results.append({'email': email, 'status': 'removed'})
            except Exception as e:
                results.append({'email': email, 'status': 'failed', 'error': str(e)})
        
        return {'action': 'remove', 'results': results}
    
    @staticmethod
    def _check_suppression_status(email_addresses):
        """Check suppression status of emails"""
        dynamodb = boto3.resource('dynamodb')
        table_name = os.environ.get('EMAIL_SUPPRESSION_TABLE_NAME')
        
        if not table_name:
            raise BusinessLogicError("Email suppression table not configured")
        
        table = dynamodb.Table(table_name)
        results = []
        
        for email in email_addresses:
            try:
                response = table.get_item(Key={'email': email.lower()})
                if 'Item' in response:
                    results.append({
                        'email': email,
                        'suppressed': True,
                        'reason': response['Item'].get('reason', 'unknown'),
                        'timestamp': response['Item'].get('timestamp', 'unknown')
                    })
                else:
                    results.append({'email': email, 'suppressed': False})
            except Exception as e:
                results.append({'email': email, 'status': 'error', 'error': str(e)})
        
        return {'action': 'check', 'results': results}

    @staticmethod
    def _add_bounce_to_suppression_list(email_address, bounce_type, bounce_subtype, notification):
        """Add an email address to the suppression list due to bounce"""
        # Initialize AWS clients
        dynamodb = boto3.resource('dynamodb')
        ses_client = boto3.client('ses')
        
        # Environment variables
        SUPPRESSION_TABLE_NAME = os.environ.get('SUPPRESSION_TABLE_NAME')
        ENVIRONMENT = os.environ.get('ENVIRONMENT', 'production')
        
        try:
            if not SUPPRESSION_TABLE_NAME:
                return False
            
            suppression_table = dynamodb.Table(SUPPRESSION_TABLE_NAME)
            
            mail_info = notification.get('mail', {})
            
            current_time = datetime.utcnow()
            iso_timestamp = current_time.isoformat() + 'Z'
            
            # TTL: keep suppressions for 1 year (can be extended if needed)
            ttl = int((current_time + timedelta(days=365)).timestamp())
            
            suppression_item = {
                'email': email_address,
                'suppression_type': 'bounce',
                'bounce_type': bounce_type,
                'bounce_subtype': bounce_subtype,
                'created_at': iso_timestamp,
                'message_id': mail_info.get('messageId', ''),
                'source': mail_info.get('source', ''),
                'environment': ENVIRONMENT,
                'ttl': ttl,
                'status': 'active',
                'reason': f'Bounce: {bounce_type}/{bounce_subtype}'
            }
            
            suppression_table.put_item(Item=suppression_item)
            print(f"Added {email_address} to suppression list for {bounce_type}/{bounce_subtype}")
            
            # Also add to SES account-level suppression list
            try:
                ses_client.put_suppressed_destination(
                    EmailAddress=email_address,
                    Reason='BOUNCE'
                )
                print(f"Added {email_address} to SES account-level suppression list")
            except ClientError as e:
                # Don't fail if already exists
                if e.response['Error']['Code'] != 'AlreadyExistsException':
                    print(f"Error adding to SES suppression list: {e}")
            
            return True
            
        except Exception as e:
            print(f"Error adding to suppression list: {str(e)}")
            return False

    @staticmethod
    def _add_complaint_to_suppression_list(email_address, complaint_feedback_type, complaint_subtype, notification):
        """Add an email address to the suppression list due to complaint"""
        # Initialize AWS clients
        dynamodb = boto3.resource('dynamodb')
        ses_client = boto3.client('ses')
        
        # Environment variables
        SUPPRESSION_TABLE_NAME = os.environ.get('SUPPRESSION_TABLE_NAME')
        ENVIRONMENT = os.environ.get('ENVIRONMENT', 'production')
        
        try:
            if not SUPPRESSION_TABLE_NAME:
                return False
            
            suppression_table = dynamodb.Table(SUPPRESSION_TABLE_NAME)
            
            complaint_info = notification.get('complaint', {})
            mail_info = notification.get('mail', {})
            
            current_time = datetime.utcnow()
            iso_timestamp = current_time.isoformat() + 'Z'
            
            # TTL: keep suppressions for 2 years for complaints (more serious than bounces)
            ttl = int((current_time + timedelta(days=730)).timestamp())
            
            suppression_item = {
                'email': email_address,
                'suppression_type': 'complaint',
                'complaint_feedback_type': complaint_feedback_type,
                'complaint_subtype': complaint_subtype,
                'created_at': iso_timestamp,
                'message_id': mail_info.get('messageId', ''),
                'source': mail_info.get('source', ''),
                'feedback_id': complaint_info.get('feedbackId', ''),
                'user_agent': complaint_info.get('userAgent', ''),
                'arrival_date': complaint_info.get('arrivalDate', ''),
                'environment': ENVIRONMENT,
                'ttl': ttl,
                'status': 'active',
                'reason': f'Complaint: {complaint_feedback_type}/{complaint_subtype}'
            }
            
            suppression_table.put_item(Item=suppression_item)
            print(f"Added {email_address} to suppression list for {complaint_feedback_type}/{complaint_subtype}")
            
            # Also add to SES account-level suppression list
            try:
                ses_client.put_suppressed_destination(
                    EmailAddress=email_address,
                    Reason='COMPLAINT'
                )
                print(f"Added {email_address} to SES account-level suppression list")
            except ClientError as e:
                # Don't fail if already exists
                if e.response['Error']['Code'] != 'AlreadyExistsException':
                    print(f"Error adding to SES suppression list: {e}")
            
            return True
            
        except Exception as e:
            print(f"Error adding complaint to suppression list: {str(e)}")
            return False

    @staticmethod
    def _record_bounce_analytics(email_address, bounce_type, bounce_subtype, notification, suppressed=False):
        """Record bounce analytics for reporting and monitoring"""
        # Initialize AWS clients
        dynamodb = boto3.resource('dynamodb')
        
        # Environment variables
        ANALYTICS_TABLE_NAME = os.environ.get('ANALYTICS_TABLE_NAME')
        ENVIRONMENT = os.environ.get('ENVIRONMENT', 'production')
        
        try:
            if not ANALYTICS_TABLE_NAME:
                return  # Analytics not configured
            
            analytics_table = dynamodb.Table(ANALYTICS_TABLE_NAME)
            
            mail_info = notification.get('mail', {})
            bounce_info = notification.get('bounce', {})
            
            current_time = datetime.utcnow()
            iso_timestamp = current_time.isoformat() + 'Z'
            
            # TTL: keep analytics for 2 years
            ttl = int((current_time + timedelta(days=730)).timestamp())
            
            analytics_item = {
                'email': email_address,
                'timestamp': iso_timestamp,
                'event_type': 'bounce',
                'bounce_type': bounce_type,
                'bounce_subtype': bounce_subtype,
                'suppressed': suppressed,
                'message_id': mail_info.get('messageId', ''),
                'source': mail_info.get('source', ''),
                'destination': mail_info.get('destination', []),
                'environment': ENVIRONMENT,
                'ttl': ttl,
                'date_partition': current_time.strftime('%Y-%m-%d')
            }
            
            analytics_table.put_item(Item=analytics_item)
            print(f"Recorded bounce analytics for {email_address}")
            
        except Exception as e:
            print(f"Error recording bounce analytics: {str(e)}")

    @staticmethod
    def _record_complaint_analytics(email_address, complaint_feedback_type, complaint_subtype, notification):
        """Record complaint analytics for reporting and monitoring"""
        # Initialize AWS clients
        dynamodb = boto3.resource('dynamodb')
        
        # Environment variables
        ANALYTICS_TABLE_NAME = os.environ.get('ANALYTICS_TABLE_NAME')
        ENVIRONMENT = os.environ.get('ENVIRONMENT', 'production')
        
        try:
            if not ANALYTICS_TABLE_NAME:
                return  # Analytics not configured
            
            analytics_table = dynamodb.Table(ANALYTICS_TABLE_NAME)
            
            complaint_info = notification.get('complaint', {})
            mail_info = notification.get('mail', {})
            
            current_time = datetime.utcnow()
            iso_timestamp = current_time.isoformat() + 'Z'
            
            # TTL: keep analytics for 2 years
            ttl = int((current_time + timedelta(days=730)).timestamp())
            
            analytics_item = {
                'email': email_address,
                'timestamp': iso_timestamp,
                'event_type': 'complaint',
                'complaint_feedback_type': complaint_feedback_type or 'Unknown',
                'complaint_subtype': complaint_subtype or 'Unknown',
                'suppressed': True,  # Always suppress complaints
                'message_id': mail_info.get('messageId', ''),
                'source': mail_info.get('source', ''),
                'feedback_id': complaint_info.get('feedbackId', ''),
                'user_agent': complaint_info.get('userAgent', ''),
                'arrival_date': complaint_info.get('arrivalDate', ''),
                'environment': ENVIRONMENT,
                'ttl': ttl,
                'date_partition': current_time.strftime('%Y-%m-%d'),
                'complaint_timestamp': complaint_info.get('timestamp', iso_timestamp)
            }
            
            analytics_table.put_item(Item=analytics_item)
            print(f"Recorded complaint analytics for {email_address}")
            
        except Exception as e:
            print(f"Error recording complaint analytics: {str(e)}")

    @staticmethod
    def _record_delivery_analytics(email_address, timestamp, processing_time_millis,
                                 smtp_response, reporting_mta, remote_mta_ip,
                                 message_id, source_email):
        """Record delivery analytics for reporting and monitoring"""
        # Initialize AWS clients
        dynamodb = boto3.resource('dynamodb')
        
        # Environment variables
        ANALYTICS_TABLE_NAME = os.environ.get('ANALYTICS_TABLE_NAME')
        ENVIRONMENT = os.environ.get('ENVIRONMENT', 'production')
        
        try:
            if not ANALYTICS_TABLE_NAME:
                return  # Analytics not configured
            
            analytics_table = dynamodb.Table(ANALYTICS_TABLE_NAME)
            
            current_time = datetime.utcnow()
            iso_timestamp = current_time.isoformat() + 'Z'
            
            # TTL: keep analytics for 1 year (less than bounce/complaint data)
            ttl = int((current_time + timedelta(days=365)).timestamp())
            
            analytics_item = {
                'email': email_address,
                'timestamp': iso_timestamp,
                'event_type': 'delivery',
                'date_partition': current_time.strftime('%Y-%m-%d'),
                'processing_time_millis': processing_time_millis or 0,
                'smtp_response': smtp_response or 'Unknown',
                'reporting_mta': reporting_mta or 'Unknown',
                'remote_mta_ip': remote_mta_ip or 'Unknown',
                'message_id': message_id,
                'source_email': source_email,
                'environment': ENVIRONMENT,
                'ttl': ttl,
                'created_at': iso_timestamp,
                'delivery_timestamp': timestamp or iso_timestamp
            }
            
            analytics_table.put_item(Item=analytics_item)
            print(f"Recorded delivery analytics for {email_address}")
            
        except Exception as e:
            print(f"Error recording delivery analytics: {str(e)}")
