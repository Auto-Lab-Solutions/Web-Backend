import json, boto3, os, email
from datetime import datetime
from decimal import Decimal
from botocore.exceptions import ClientError
from boto3.dynamodb.types import TypeDeserializer

import response_utils as resp
import request_utils as req
import db_utils as db

# AWS clients
s3_client = boto3.client('s3')
dynamodb = boto3.client('dynamodb')
deserializer = TypeDeserializer()

# Environment variables
EMAIL_STORAGE_BUCKET = os.environ.get('EMAIL_STORAGE_BUCKET')
EMAIL_METADATA_TABLE = os.environ.get('EMAIL_METADATA_TABLE')

# ------------------  Email Retrieval Functions ------------------

def lambda_handler(event, context):
    """API Gateway handler for retrieving emails"""
    try:
        print(f"Get emails request: {json.dumps(event)}")
        
        # Validate staff authentication
        staff_email = req.get_staff_user_email(event)
        staff_user_record = db.get_staff_record(staff_email)
        if not staff_user_record:
            return resp.error_response(f"No staff record found for email: {staff_email}.")
        
        # Extract pagination parameters
        limit = req.get_query_param(event, 'limit', 50)
        offset = req.get_query_param(event, 'offset', 0)

        # Extract filter parameters
        to_email = req.get_query_param(event, 'to_email')
        from_email = req.get_query_param(event, 'from_email')
        start_date = req.get_query_param(event, 'start_date')
        end_date = req.get_query_param(event, 'end_date')
        is_read = req.get_query_param(event, 'is_read')
        has_attachments = req.get_query_param(event, 'has_attachments')

        # Check if this is a request for a specific email
        path_params = event.get('pathParameters', {})
        if path_params and path_params.get('id'):
            email_id = path_params['id']
            email_data = get_email_by_id_full(email_id)
            
            if email_data:
                # Mark as read when retrieved
                update_email_read_status(email_id, True)
                return resp.success_response({'email': email_data})
            else:
                return resp.error_response(404, 'Email not found')
        
        # Get emails with filters
        emails_result = get_emails(
            to_email=to_email,
            from_email=from_email,
            start_date=start_date,
            end_date=end_date,
            is_read=is_read,
            has_attachments=has_attachments,
            limit=limit,
            offset=offset
        )
        
        return resp.success_response(emails_result)
        
    except Exception as e:
        print(f"Error in email handler: {str(e)}")
        return resp.error_response(500, f"Internal server error: {str(e)}")



def get_email_by_id_full(email_id):
    """Get a single email by ID with full content"""
    try:
        # Get email metadata from DynamoDB
        email_item = get_email_by_id(email_id)
        
        if not email_item:
            return None
        
        # Get full email content from S3
        if email_item.get('s3_bucket') and email_item.get('s3_key'):
            try:
                s3_response = s3_client.get_object(
                    Bucket=email_item['s3_bucket'],
                    Key=email_item['s3_key']
                )
                raw_email = s3_response['Body'].read()
                
                # Parse email content
                email_message = email.message_from_bytes(raw_email)
                
                # Extract attachments info
                attachments = []
                for part in email_message.walk():
                    if part.get_content_disposition() == 'attachment':
                        filename = part.get_filename()
                        if filename:
                            attachments.append({
                                'filename': filename,
                                'content_type': part.get_content_type(),
                                'size': len(part.get_payload(decode=True))
                            })
                
                # Get full body content
                text_body = None
                html_body = None
                
                for part in email_message.walk():
                    content_type = part.get_content_type()
                    if content_type == 'text/plain':
                        text_body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                    elif content_type == 'text/html':
                        html_body = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                
                email_item.update({
                    'body_text': text_body,
                    'body_html': html_body,
                    'attachments': attachments,
                    'raw_headers': dict(email_message.items())
                })
                
            except Exception as e:
                print(f"Error getting email content from S3: {str(e)}")
        
        return convert_decimal(email_item)
        
    except Exception as e:
        print(f"Error getting email by ID: {str(e)}")
        return None

def get_email_content_preview(s3_bucket, s3_key):
    """Get email content preview from S3"""
    try:
        if not s3_bucket or not s3_key:
            return {}
        
        s3_response = s3_client.get_object(Bucket=s3_bucket, Key=s3_key)
        raw_email = s3_response['Body'].read()
        
        # Parse email content
        email_message = email.message_from_bytes(raw_email)
        
        preview = {}
        
        # Extract text and HTML parts
        for part in email_message.walk():
            content_type = part.get_content_type()
            if content_type == 'text/plain':
                text_content = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                preview['body_text_preview'] = text_content[:500] + ('...' if len(text_content) > 500 else '')
            elif content_type == 'text/html':
                html_content = part.get_payload(decode=True).decode('utf-8', errors='ignore')
                preview['body_html_preview'] = html_content[:1000] + ('...' if len(html_content) > 1000 else '')
        
        return preview
        
    except Exception as e:
        print(f"Error getting email content preview: {str(e)}")
        return {}
    
def get_emails(to_email=None, from_email=None, start_date=None, end_date=None, 
               is_read=None, has_attachments=None, limit=50, offset=0):
    """Retrieve emails from DynamoDB with optional filters"""
    try:
        # Convert date strings to timestamps for filtering
        start_timestamp = None
        end_timestamp = None
        
        if start_date:
            start_timestamp = int(datetime.fromisoformat(start_date.replace('Z', '+00:00')).timestamp())
        if end_date:
            end_timestamp = int(datetime.fromisoformat(end_date.replace('Z', '+00:00')).timestamp())
        
        # Get emails from database
        result = get_emails_from_db(
            to_email=to_email,
            from_email=from_email,
            start_date=start_timestamp,
            end_date=end_timestamp,
            limit=limit + offset  # Get more to handle offset
        )
        
        emails = result['items']
        
        # Apply client-side filtering for fields not handled in DB query
        if is_read is not None:
            is_read_bool = is_read.lower() == 'true'
            emails = [email for email in emails if email.get('is_read') == is_read_bool]
        
        if has_attachments is not None:
            has_attachments_bool = has_attachments.lower() == 'true'
            emails = [email for email in emails if email.get('has_attachments') == has_attachments_bool]
        
        # Apply pagination
        paginated_emails = emails[offset:offset + limit]
        
        # Add email content preview for each email
        for email_item in paginated_emails:
            if not email_item.get('body_text_preview') and not email_item.get('body_html_preview'):
                try:
                    content_preview = get_email_content_preview(
                        email_item.get('s3_bucket', EMAIL_STORAGE_BUCKET),
                        email_item.get('s3_key')
                    )
                    email_item.update(content_preview)
                except Exception as e:
                    print(f"Error getting content preview for {email_item.get('message_id')}: {str(e)}")
        
        return {
            'emails': [convert_decimal(email) for email in paginated_emails],
            'total_count': len(emails),
            'has_more': len(emails) > offset + limit,
            'offset': offset,
            'limit': limit
        }
        
    except Exception as e:
        print(f"Error retrieving emails: {str(e)}")
        return {
            'emails': [],
            'total_count': 0,
            'has_more': False,
            'error': str(e)
        }
    
def update_email_read_status(email_id, is_read=True):
    """Update email read status"""
    try:
        dynamodb.update_item(
            TableName=EMAIL_METADATA_TABLE,
            Key={'message_id': {'S': email_id}},
            UpdateExpression='SET is_read = :is_read, updated_at = :updated_at',
            ExpressionAttributeValues={
                ':is_read': {'BOOL': is_read},
                ':updated_at': {'S': datetime.utcnow().isoformat() + 'Z'}
            }
        )
        print(f"Updated read status for email {email_id}")
        return True
        
    except ClientError as e:
        print(f"Error updating email read status: {e.response['Error']['Message']}")
        return False

def convert_decimal(obj):
    """Convert Decimal types to native Python types for JSON serialization"""
    if isinstance(obj, list):
        return [convert_decimal(item) for item in obj]
    elif isinstance(obj, dict):
        return {key: convert_decimal(value) for key, value in obj.items()}
    elif isinstance(obj, Decimal):
        return float(obj)
    else:
        return obj
    
def get_email_by_id(email_id):
    """Get a specific email by ID"""
    try:
        response = dynamodb.get_item(
            TableName=EMAIL_METADATA_TABLE,
            Key={'message_id': {'S': email_id}}
        )
        
        if 'Item' in response:
            return deserialize_item(response['Item'])
        return None
        
    except ClientError as e:
        print(f"Error getting email by ID {email_id}: {e.response['Error']['Message']}")
        return None
    
def get_emails_from_db(to_email=None, from_email=None, start_date=None, end_date=None, 
                      limit=50, last_evaluated_key=None):
    """Get emails from DynamoDB with filtering and pagination"""
    try:
        scan_kwargs = {
            'TableName': EMAIL_METADATA_TABLE,
            'Limit': limit
        }
        
        # Build filter expressions
        filter_expressions = []
        expression_values = {}
        expression_names = {}
        
        if to_email:
            filter_expressions.append("#to_email = :to_email")
            expression_values[':to_email'] = {'S': to_email}
            expression_names['#to_email'] = 'to_email'
        
        if from_email:
            filter_expressions.append("#from_email = :from_email")
            expression_values[':from_email'] = {'S': from_email}
            expression_names['#from_email'] = 'from_email'
        
        if start_date:
            filter_expressions.append("#timestamp >= :start_date")
            expression_values[':start_date'] = {'N': str(start_date)}
            expression_names['#timestamp'] = 'timestamp'
            
        if end_date:
            filter_expressions.append("#timestamp <= :end_date")
            expression_values[':end_date'] = {'N': str(end_date)}
            expression_names['#timestamp'] = 'timestamp'
        
        if filter_expressions:
            scan_kwargs['FilterExpression'] = ' AND '.join(filter_expressions)
            scan_kwargs['ExpressionAttributeValues'] = expression_values
            scan_kwargs['ExpressionAttributeNames'] = expression_names
        
        if last_evaluated_key:
            scan_kwargs['ExclusiveStartKey'] = last_evaluated_key
        
        # Use query or scan based on the filters
        if to_email and not from_email:
            # Use GSI if querying by to_email only
            scan_kwargs.update({
                'IndexName': 'ToEmailIndex',
                'KeyConditionExpression': 'to_email = :to_email',
                'ExpressionAttributeValues': {':to_email': {'S': to_email}},
                'ExpressionAttributeNames': {'#to_email': 'to_email'}
            })
            response = dynamodb.query(**scan_kwargs)
        else:
            response = dynamodb.scan(**scan_kwargs)
        
        # Deserialize items
        items = [deserialize_item(item) for item in response.get('Items', [])]
        
        return {
            'items': items,
            'last_evaluated_key': response.get('LastEvaluatedKey'),
            'count': len(items)
        }
        
    except ClientError as e:
        print(f"Error querying emails: {e.response['Error']['Message']}")
        return {'items': [], 'last_evaluated_key': None, 'count': 0}


def deserialize_item(item):
    """Deserialize DynamoDB item"""
    return {k: deserializer.deserialize(v) for k, v in item.items()} if item else None


