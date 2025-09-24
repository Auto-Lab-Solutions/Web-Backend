import boto3
import os
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
from botocore.exceptions import ClientError

# Environment variables
REPORTS_BUCKET_NAME = os.environ.get('REPORTS_BUCKET')
CLOUDFRONT_DOMAIN = os.environ.get('CLOUDFRONT_DOMAIN')

# Initialize S3 client
s3_client = boto3.client('s3')

def generate_presigned_upload_url(bucket_name, key, content_type, expires_in=3600):
    """Generate a presigned URL for uploading files to S3"""
    # Validate input parameters
    if not bucket_name:
        raise ValueError("bucket_name cannot be None or empty")
    if not key:
        raise ValueError("key cannot be None or empty")  
    if not content_type:
        raise ValueError("content_type cannot be None or empty")
    
    try:
        presigned_url = s3_client.generate_presigned_url(
            'put_object',
            Params={
                'Bucket': bucket_name,
                'Key': key,
                'ContentType': content_type,
            },
            ExpiresIn=expires_in
        )
        return presigned_url
    except Exception as e:
        print(f"Error generating presigned URL: {str(e)}")
        print(f"Parameters: bucket_name={bucket_name}, key={key}, content_type={content_type}, expires_in={expires_in}")
        return None


def generate_unique_file_key(prefix, appointment_id, file_name):
    """Generate a unique file key for S3 storage"""
    timestamp = datetime.now(ZoneInfo('Australia/Perth')).strftime('%Y%m%d_%H%M%S')
    unique_id = str(uuid.uuid4())[:8]
    
    # Ensure file has proper extension
    if not file_name.lower().endswith('.pdf'):
        file_name += '.pdf'
    
    return f"{prefix}/{appointment_id}/{timestamp}_{unique_id}_{file_name}"


def generate_public_url(cloudfront_domain=None, file_key=None):
    """Generate public URL using CloudFront domain"""
    domain = cloudfront_domain or CLOUDFRONT_DOMAIN
    if not domain:
        print(f"Warning: CLOUDFRONT_DOMAIN not available, falling back to S3 URL for file: {file_key}")
        # Fallback to S3 URL if CloudFront domain is not available
        if not REPORTS_BUCKET_NAME:
            raise ValueError("Neither CLOUDFRONT_DOMAIN nor REPORTS_BUCKET_NAME environment variable is set")
        fallback_url = f"https://{REPORTS_BUCKET_NAME}.s3.amazonaws.com/{file_key}"
        print(f"Generated fallback S3 URL: {fallback_url}")
        return fallback_url
    
    # Ensure domain doesn't have protocol prefix
    if domain.startswith('http://') or domain.startswith('https://'):
        domain = domain.split('://', 1)[1]
    
    cloudfront_url = f"https://{domain}/{file_key}"
    print(f"Generated CloudFront URL: {cloudfront_url}")
    return cloudfront_url


def generate_reports_base_url(cloudfront_domain=None):
    """
    Generate base URL for reports with robust fallback
    
    Args:
        cloudfront_domain (str, optional): CloudFront domain override
        
    Returns:
        str: Base URL for reports
    """
    domain = cloudfront_domain or CLOUDFRONT_DOMAIN
    if not domain:
        # Fallback to S3 URL if CloudFront domain is not available
        if not REPORTS_BUCKET_NAME:
            raise ValueError("Neither CLOUDFRONT_DOMAIN nor REPORTS_BUCKET_NAME environment variable is set")
        return f"https://{REPORTS_BUCKET_NAME}.s3.amazonaws.com"
    
    # Ensure domain doesn't have protocol prefix
    if domain.startswith('http://') or domain.startswith('https://'):
        domain = domain.split('://', 1)[1]
    
    return f"https://{domain}"


def generate_report_presigned_upload_url(appointment_id, file_name, expires_in=3600):
    """Generate a presigned URL for uploading report files with default configuration"""
    file_key = generate_unique_file_key("reports", appointment_id, file_name)
    content_type = 'application/pdf'
    
    presigned_url = generate_presigned_upload_url(
        bucket_name=REPORTS_BUCKET_NAME,
        key=file_key,
        content_type=content_type,
        expires_in=expires_in
    )
    
    if presigned_url:
        public_url = generate_public_url(file_key=file_key)
        return {
            'presignedUrl': presigned_url,
            'publicUrl': public_url,
            'fileKey': file_key,
            'contentType': content_type
        }
    return None

def put_object(bucket_name, key, content, content_type='application/json'):
    """Upload an object to S3"""
    try:
        s3_client.put_object(
            Bucket=bucket_name,
            Key=key,
            Body=content,
            ContentType=content_type
        )
        print(f"Successfully uploaded object to s3://{bucket_name}/{key}")
        return True
    except ClientError as e:
        print(f"Error uploading object to S3: {e}")
        raise

def get_object(bucket_name, key):
    """Download an object from S3"""
    try:
        response = s3_client.get_object(Bucket=bucket_name, Key=key)
        return response['Body'].read().decode('utf-8')
    except ClientError as e:
        print(f"Error downloading object from S3: {e}")
        raise

def list_objects(bucket_name, prefix=''):
    """List objects in S3 bucket with optional prefix"""
    try:
        objects = []
        paginator = s3_client.get_paginator('list_objects_v2')
        page_iterator = paginator.paginate(Bucket=bucket_name, Prefix=prefix)
        
        for page in page_iterator:
            for obj in page.get('Contents', []):
                objects.append(obj['Key'])
        
        return objects
    except ClientError as e:
        print(f"Error listing objects in S3: {e}")
        raise

def list_objects_with_metadata(bucket_name, prefix=''):
    """List objects in S3 bucket with metadata"""
    try:
        objects = []
        paginator = s3_client.get_paginator('list_objects_v2')
        page_iterator = paginator.paginate(Bucket=bucket_name, Prefix=prefix)
        
        for page in page_iterator:
            objects.extend(page.get('Contents', []))
        
        return objects
    except ClientError as e:
        print(f"Error listing objects with metadata in S3: {e}")
        raise

def copy_object(source_bucket, source_key, dest_bucket, dest_key):
    """Copy an object from one S3 location to another"""
    try:
        copy_source = {'Bucket': source_bucket, 'Key': source_key}
        s3_client.copy(copy_source, dest_bucket, dest_key)
        print(f"Copied s3://{source_bucket}/{source_key} to s3://{dest_bucket}/{dest_key}")
        return True
    except ClientError as e:
        print(f"Error copying object in S3: {e}")
        raise

def delete_object(bucket_name, key):
    """Delete an object from S3"""
    try:
        s3_client.delete_object(Bucket=bucket_name, Key=key)
        print(f"Deleted s3://{bucket_name}/{key}")
        return True
    except ClientError as e:
        print(f"Error deleting object from S3: {e}")
        raise

def object_exists(bucket_name, key):
    """Check if an object exists in S3"""
    try:
        s3_client.head_object(Bucket=bucket_name, Key=key)
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            return False
        else:
            raise
