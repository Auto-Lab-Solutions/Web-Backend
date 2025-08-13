import json
import boto3
import os
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from botocore.exceptions import ClientError

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
ses_client = boto3.client('ses')

# Environment variables
ENVIRONMENT = os.environ.get('ENVIRONMENT', 'production')
SUPPRESSION_TABLE_NAME = os.environ.get('SUPPRESSION_TABLE_NAME')
ANALYTICS_TABLE_NAME = os.environ.get('ANALYTICS_TABLE_NAME')

# DynamoDB tables
suppression_table = dynamodb.Table(SUPPRESSION_TABLE_NAME)
analytics_table = dynamodb.Table(ANALYTICS_TABLE_NAME)

def lambda_handler(event, context):
    """
    Manage email suppression list - API for checking, adding, removing suppressed emails
    """
    logger.info(f"Email suppression manager invoked: {json.dumps(event, default=str)}")
    
    try:
        # Parse the request
        http_method = event.get('httpMethod', 'GET')
        path = event.get('path', '')
        query_params = event.get('queryStringParameters') or {}
        body = event.get('body')
        
        if body:
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                body = {}
        
        # Route to appropriate handler based on HTTP method and path
        if http_method == 'GET' and '/check' in path:
            return check_suppression_status(query_params)
        elif http_method == 'GET' and '/list' in path:
            return list_suppressed_emails(query_params)
        elif http_method == 'POST' and '/add' in path:
            return add_to_suppression(body)
        elif http_method == 'DELETE' and '/remove' in path:
            return remove_from_suppression(query_params)
        elif http_method == 'GET' and '/analytics' in path:
            return get_email_analytics(query_params)
        elif http_method == 'POST' and '/cleanup' in path:
            return cleanup_expired_suppressions()
        else:
            return {
                'statusCode': 404,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'Endpoint not found'})
            }
            
    except Exception as e:
        logger.error(f"Error in email suppression manager: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'error': 'Internal server error',
                'details': str(e)
            })
        }

def check_suppression_status(query_params):
    """
    Check if an email address is suppressed
    """
    try:
        email = query_params.get('email')
        if not email:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'Email parameter required'})
            }
        
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
                logger.error(f"Error checking SES suppression: {e}")
        
        result = {
            'email': email,
            'is_suppressed': len(local_suppressions) > 0 or ses_suppressed,
            'local_suppressions': local_suppressions,
            'ses_suppressed': ses_suppressed,
            'ses_reason': ses_reason,
            'checked_at': datetime.utcnow().isoformat() + 'Z'
        }
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps(result)
        }
        
    except Exception as e:
        logger.error(f"Error checking suppression status: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)})
        }

def list_suppressed_emails(query_params):
    """
    List suppressed email addresses with pagination
    """
    try:
        limit = int(query_params.get('limit', 50))
        suppression_type = query_params.get('type')
        last_evaluated_key = query_params.get('lastKey')
        
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
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps(result, default=str)
        }
        
    except Exception as e:
        logger.error(f"Error listing suppressed emails: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)})
        }

def add_to_suppression(body):
    """
    Manually add an email to suppression list
    """
    try:
        email = body.get('email')
        reason = body.get('reason', 'manual')
        notes = body.get('notes', '')
        
        if not email:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'Email is required'})
            }
        
        current_time = datetime.utcnow()
        iso_timestamp = current_time.isoformat() + 'Z'
        
        # TTL: keep manual suppressions for 1 year
        ttl = int((current_time + timedelta(days=365)).timestamp())
        
        suppression_item = {
            'email': email,
            'suppression_type': reason,
            'created_at': iso_timestamp,
            'notes': notes,
            'environment': ENVIRONMENT,
            'ttl': ttl,
            'status': 'active',
            'manual_addition': True
        }
        
        suppression_table.put_item(Item=suppression_item)
        
        # Also add to SES account-level suppression if bounce or complaint
        if reason in ['bounce', 'complaint']:
            ses_reason = 'BOUNCE' if reason == 'bounce' else 'COMPLAINT'
            try:
                ses_client.put_suppressed_destination(
                    EmailAddress=email,
                    Reason=ses_reason
                )
            except ClientError as e:
                if e.response['Error']['Code'] != 'AlreadyExistsException':
                    logger.error(f"Error adding to SES suppression: {e}")
        
        logger.info(f"Manually added {email} to suppression list for {reason}")
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'message': f'Added {email} to suppression list',
                'email': email,
                'reason': reason,
                'added_at': iso_timestamp
            })
        }
        
    except Exception as e:
        logger.error(f"Error adding to suppression: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)})
        }

def remove_from_suppression(query_params):
    """
    Remove an email from suppression list
    """
    try:
        email = query_params.get('email')
        suppression_type = query_params.get('type')
        
        if not email:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'Email parameter required'})
            }
        
        removed_count = 0
        
        if suppression_type:
            # Remove specific suppression type
            try:
                suppression_table.update_item(
                    Key={'email': email, 'suppression_type': suppression_type},
                    UpdateExpression='SET #status = :status',
                    ExpressionAttributeNames={'#status': 'status'},
                    ExpressionAttributeValues={':status': 'removed'}
                )
                removed_count += 1
            except ClientError as e:
                if e.response['Error']['Code'] != 'ResourceNotFoundException':
                    raise
        else:
            # Remove all suppressions for this email
            response = suppression_table.query(
                KeyConditionExpression=boto3.dynamodb.conditions.Key('email').eq(email)
            )
            
            for item in response['Items']:
                if item.get('status') == 'active':
                    suppression_table.update_item(
                        Key={'email': email, 'suppression_type': item['suppression_type']},
                        UpdateExpression='SET #status = :status',
                        ExpressionAttributeNames={'#status': 'status'},
                        ExpressionAttributeValues={':status': 'removed'}
                    )
                    removed_count += 1
        
        # Remove from SES account-level suppression
        try:
            ses_client.delete_suppressed_destination(EmailAddress=email)
            logger.info(f"Removed {email} from SES suppression list")
        except ClientError as e:
            if e.response['Error']['Code'] != 'NotFoundException':
                logger.error(f"Error removing from SES suppression: {e}")
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'message': f'Removed {email} from suppression list',
                'email': email,
                'removed_count': removed_count,
                'removed_at': datetime.utcnow().isoformat() + 'Z'
            })
        }
        
    except Exception as e:
        logger.error(f"Error removing from suppression: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)})
        }

def get_email_analytics(query_params):
    """
    Get email analytics for an email address
    """
    try:
        email = query_params.get('email')
        days = int(query_params.get('days', 30))
        
        if not email:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json'},
                'body': json.dumps({'error': 'Email parameter required'})
            }
        
        # Query analytics for the past N days
        start_date = datetime.utcnow() - timedelta(days=days)
        start_timestamp = start_date.isoformat() + 'Z'
        
        response = analytics_table.query(
            KeyConditionExpression=boto3.dynamodb.conditions.Key('email').eq(email) & 
                                 boto3.dynamodb.conditions.Key('timestamp').gte(start_timestamp),
            ScanIndexForward=False,  # Latest first
            Limit=100
        )
        
        events = []
        event_counts = {'delivery': 0, 'bounce': 0, 'complaint': 0}
        
        for item in response['Items']:
            event_type = item['event_type']
            event_counts[event_type] = event_counts.get(event_type, 0) + 1
            
            events.append({
                'timestamp': item['timestamp'],
                'event_type': event_type,
                'details': {k: v for k, v in item.items() 
                           if k not in ['email', 'timestamp', 'ttl', 'date_partition']}
            })
        
        result = {
            'email': email,
            'period_days': days,
            'event_counts': event_counts,
            'events': events,
            'total_events': len(events)
        }
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps(result, default=str)
        }
        
    except Exception as e:
        logger.error(f"Error getting email analytics: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)})
        }

def cleanup_expired_suppressions():
    """
    Clean up expired suppressions (those past their TTL)
    """
    try:
        current_timestamp = int(datetime.utcnow().timestamp())
        removed_count = 0
        
        # Scan for expired items
        response = suppression_table.scan(
            FilterExpression=boto3.dynamodb.conditions.Attr('ttl').lt(current_timestamp) & 
                           boto3.dynamodb.conditions.Attr('status').eq('active')
        )
        
        for item in response['Items']:
            # Mark as expired rather than deleting (for audit trail)
            suppression_table.update_item(
                Key={'email': item['email'], 'suppression_type': item['suppression_type']},
                UpdateExpression='SET #status = :status',
                ExpressionAttributeNames={'#status': 'status'},
                ExpressionAttributeValues={':status': 'expired'}
            )
            removed_count += 1
        
        logger.info(f"Cleaned up {removed_count} expired suppressions")
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({
                'message': f'Cleaned up {removed_count} expired suppressions',
                'removed_count': removed_count,
                'cleanup_time': datetime.utcnow().isoformat() + 'Z'
            })
        }
        
    except Exception as e:
        logger.error(f"Error cleaning up suppressions: {str(e)}", exc_info=True)
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps({'error': str(e)})
        }
