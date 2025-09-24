"""
Email Attachment Management System
Handles extraction, storage, and retrieval of email attachments
"""

import os
import boto3
import hashlib
import mimetypes
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import List, Dict, Optional, Tuple
import base64


class AttachmentManager:
    """Manages email attachment storage and retrieval"""
    
    def __init__(self):
        self.s3_client = boto3.client('s3')
        self.dynamodb = boto3.client('dynamodb')
        
        # Get bucket and table names from environment
        self.attachments_bucket = os.environ.get('EMAIL_ATTACHMENTS_BUCKET')
        self.attachments_table = os.environ.get('EMAIL_ATTACHMENTS_TABLE')
        
        # Validate that required environment variables are set
        if not self.attachments_bucket:
            print("Warning: EMAIL_ATTACHMENTS_BUCKET environment variable not set")
            # Use a fallback bucket name format that matches the infrastructure
            account_id = boto3.client('sts').get_caller_identity().get('Account', 'unknown')
            environment = os.environ.get('ENVIRONMENT', 'development')
            self.attachments_bucket = f'auto-lab-email-attachments-{environment}-{account_id}'
            print(f"Using fallback bucket name: {self.attachments_bucket}")
        
        if not self.attachments_table:
            print("Warning: EMAIL_ATTACHMENTS_TABLE environment variable not set")
            environment = os.environ.get('ENVIRONMENT', 'development')
            self.attachments_table = f'EmailAttachments-{environment}'
            print(f"Using fallback table name: {self.attachments_table}")
        
        # Verify bucket exists or provide helpful error message
        try:
            self.s3_client.head_bucket(Bucket=self.attachments_bucket)
            print(f"Successfully verified access to attachments bucket: {self.attachments_bucket}")
        except Exception as e:
            error_msg = str(e)
            if '403' in error_msg or 'Forbidden' in error_msg:
                print(f"Warning: Access denied to attachments bucket '{self.attachments_bucket}': {error_msg}")
                print("This indicates insufficient S3 permissions. Please update the Lambda execution role.")
                print("Required permissions: s3:HeadBucket, s3:ListBucket, s3:GetObject, s3:PutObject, s3:DeleteObject")
                print("Email sending will continue, but attachments will not be stored separately.")
            elif '404' in error_msg or 'NoSuchBucket' in error_msg:
                print(f"Warning: Attachments bucket '{self.attachments_bucket}' does not exist: {error_msg}")
                print("Please deploy the S3CloudFrontStack to create the bucket.")
            else:
                print(f"Warning: Cannot access attachments bucket '{self.attachments_bucket}': {error_msg}")
                print("This may indicate network issues or other AWS service problems.")
        
    def extract_and_store_attachments(self, email_message, message_id: str, email_s3_bucket: str, 
                                    email_s3_key: str) -> List[Dict]:
        """
        Extract attachments from email message and store them in S3
        
        Args:
            email_message: Parsed email message object
            message_id: Email message ID
            email_s3_bucket: S3 bucket where original email is stored
            email_s3_key: S3 key where original email is stored
            
        Returns:
            List of attachment metadata dictionaries
        """
        attachments = []
        
        try:
            if not email_message.is_multipart():
                return attachments
            
            attachment_index = 0
            for part in email_message.walk():
                content_disposition = part.get_content_disposition()
                
                if content_disposition == 'attachment':
                    attachment_data = self._process_attachment_part(
                        part, message_id, attachment_index, email_s3_bucket, email_s3_key
                    )
                    
                    if attachment_data:
                        attachments.append(attachment_data)
                        attachment_index += 1
                        
        except Exception as e:
            print(f"Error extracting attachments for message {message_id}: {str(e)}")
        
        return attachments
    
    def _process_attachment_part(self, part, message_id: str, attachment_index: int, 
                               email_s3_bucket: str, email_s3_key: str) -> Optional[Dict]:
        """Process individual attachment part"""
        try:
            # Get attachment filename
            filename = part.get_filename()
            if not filename:
                filename = f"attachment_{attachment_index}"
            
            # Get content type
            content_type = part.get_content_type()
            if not content_type:
                content_type, _ = mimetypes.guess_type(filename)
                if not content_type:
                    content_type = 'application/octet-stream'
            
            # Get attachment content
            attachment_content = part.get_payload(decode=True)
            if not attachment_content:
                print(f"Warning: No content found for attachment {filename}")
                return None
            
            # Calculate size and hash
            size_bytes = len(attachment_content)
            content_hash = hashlib.sha256(attachment_content).hexdigest()
            
            # Generate unique attachment ID
            attachment_id = f"{message_id}_{attachment_index}_{content_hash[:8]}"
            
            # Create S3 key for attachment
            s3_key = f"attachments/{message_id}/{attachment_id}_{filename}"
            
            # Store attachment in S3
            self.s3_client.put_object(
                Bucket=self.attachments_bucket,
                Key=s3_key,
                Body=attachment_content,
                ContentType=content_type,
                Metadata={
                    'message_id': message_id,
                    'original_filename': filename,
                    'attachment_index': str(attachment_index),
                    'content_hash': content_hash,
                    'upload_date': datetime.now(ZoneInfo('Australia/Perth')).isoformat()
                }
            )
            
            # Create attachment metadata
            attachment_metadata = {
                'attachmentId': attachment_id,
                'messageId': message_id,
                'filename': filename,
                'contentType': content_type,
                'sizeBytes': size_bytes,
                'contentHash': content_hash,
                's3Bucket': self.attachments_bucket,
                's3Key': s3_key,
                'attachmentIndex': attachment_index,
                'uploadDate': datetime.now(ZoneInfo('Australia/Perth')).isoformat(),
                'emailS3Bucket': email_s3_bucket,
                'emailS3Key': email_s3_key
            }
            
            # Store attachment metadata in DynamoDB
            self._store_attachment_metadata(attachment_metadata)
            
            print(f"Successfully stored attachment: {filename} ({size_bytes} bytes)")
            return attachment_metadata
            
        except Exception as e:
            print(f"Error processing attachment {filename}: {str(e)}")
            return None
    
    def store_sent_email_attachment(self, message_id: str, attachment_content: bytes, 
                                  filename: str, attachment_index: int) -> Optional[Dict]:
        """
        Store attachment from a sent email separately in S3 and DynamoDB
        
        Args:
            message_id: Email message ID
            attachment_content: Raw attachment content (bytes)
            filename: Original filename
            attachment_index: Index of attachment in email
            
        Returns:
            Attachment metadata dictionary or None if storage failed
        """
        try:
            # Validate inputs
            if not message_id or not attachment_content or not filename:
                print(f"Invalid input parameters for attachment storage")
                return None
            
            # Check if bucket and table are properly configured
            if not self.attachments_bucket or not self.attachments_table:
                print(f"Attachment storage not properly configured - bucket: {self.attachments_bucket}, table: {self.attachments_table}")
                return None
            
            # Determine content type
            content_type, _ = mimetypes.guess_type(filename)
            if not content_type:
                content_type = 'application/octet-stream'
            
            # Calculate size and hash
            size_bytes = len(attachment_content)
            content_hash = hashlib.sha256(attachment_content).hexdigest()
            
            # Generate unique attachment ID
            attachment_id = f"{message_id}_{attachment_index}_{content_hash[:8]}"
            
            # Create S3 key for attachment
            s3_key = f"sent-attachments/{message_id}/{attachment_id}_{filename}"
            
            # Store attachment in S3 with error handling
            try:
                self.s3_client.put_object(
                    Bucket=self.attachments_bucket,
                    Key=s3_key,
                    Body=attachment_content,
                    ContentType=content_type,
                    Metadata={
                        'message_id': message_id,
                        'original_filename': filename,
                        'attachment_index': str(attachment_index),
                        'content_hash': content_hash,
                        'upload_date': datetime.now(ZoneInfo('Australia/Perth')).isoformat(),
                        'attachment_type': 'sent_email'
                    }
                )
                print(f"Successfully uploaded attachment to S3: {s3_key}")
            except Exception as s3_error:
                if 'NoSuchBucket' in str(s3_error):
                    print(f"S3 bucket '{self.attachments_bucket}' does not exist. Please deploy the infrastructure.")
                    print("To deploy: Run the CloudFormation stack deployment that creates the S3CloudFrontStack")
                else:
                    print(f"Failed to upload attachment to S3: {str(s3_error)}")
                return None
            
            # Create attachment metadata
            attachment_metadata = {
                'attachmentId': attachment_id,
                'messageId': message_id,
                'filename': filename,
                'contentType': content_type,
                'sizeBytes': size_bytes,
                'contentHash': content_hash,
                's3Bucket': self.attachments_bucket,
                's3Key': s3_key,
                'attachmentIndex': attachment_index,
                'uploadDate': datetime.now(ZoneInfo('Australia/Perth')).isoformat(),
                'emailS3Bucket': '',  # Sent emails aren't stored in S3
                'emailS3Key': '',     # Sent emails aren't stored in S3
                'attachmentType': 'sent_email'
            }
            
            # Store attachment metadata in DynamoDB
            try:
                self._store_attachment_metadata(attachment_metadata)
                print(f"Successfully stored attachment metadata in DynamoDB")
            except Exception as db_error:
                print(f"Failed to store attachment metadata in DynamoDB: {str(db_error)}")
                # Clean up S3 object if DynamoDB storage failed
                try:
                    self.s3_client.delete_object(Bucket=self.attachments_bucket, Key=s3_key)
                    print(f"Cleaned up S3 object after DynamoDB failure")
                except:
                    pass
                return None
            
            print(f"Successfully stored sent email attachment: {filename} ({size_bytes} bytes)")
            return attachment_metadata
            
        except Exception as e:
            print(f"Error storing sent email attachment {filename}: {str(e)}")
            return None
    
    def _store_attachment_metadata(self, attachment_metadata: Dict):
        """Store attachment metadata in DynamoDB"""
        try:
            # Create TTL (2 years from now)
            now_perth = datetime.now(ZoneInfo('Australia/Perth'))
            ttl = int(now_perth.timestamp() + (2 * 365 * 24 * 60 * 60))
            created_timestamp = int(now_perth.timestamp() * 1000)
            
            item = {
                'attachmentId': {'S': attachment_metadata['attachmentId']},
                'messageId': {'S': attachment_metadata['messageId']},
                'filename': {'S': attachment_metadata['filename']},
                'contentType': {'S': attachment_metadata['contentType']},
                'sizeBytes': {'N': str(attachment_metadata['sizeBytes'])},
                'contentHash': {'S': attachment_metadata['contentHash']},
                's3Bucket': {'S': attachment_metadata['s3Bucket']},
                's3Key': {'S': attachment_metadata['s3Key']},
                'attachmentIndex': {'N': str(attachment_metadata['attachmentIndex'])},
                'uploadDate': {'S': attachment_metadata['uploadDate']},
                'emailS3Bucket': {'S': attachment_metadata.get('emailS3Bucket', '')},
                'emailS3Key': {'S': attachment_metadata.get('emailS3Key', '')},
                'ttl': {'N': str(ttl)},
                'createdAt': {'N': str(created_timestamp)},
                'isDeleted': {'BOOL': False}
            }
            
            # Add attachment type if provided (for sent vs received emails)
            if 'attachmentType' in attachment_metadata:
                item['attachmentType'] = {'S': attachment_metadata['attachmentType']}
            
            self.dynamodb.put_item(
                TableName=self.attachments_table,
                Item=item
            )
            
        except Exception as e:
            print(f"Error storing attachment metadata: {str(e)}")
            raise
    
    def get_attachments_for_email(self, message_id: str) -> List[Dict]:
        """Get all attachments for a specific email"""
        try:
            response = self.dynamodb.query(
                TableName=self.attachments_table,
                IndexName='messageId-index',
                KeyConditionExpression='messageId = :messageId',
                FilterExpression='isDeleted = :false',
                ExpressionAttributeValues={
                    ':messageId': {'S': message_id},
                    ':false': {'BOOL': False}
                }
            )
            
            attachments = []
            for item in response.get('Items', []):
                attachment = self._convert_dynamodb_attachment_to_dict(item)
                attachments.append(attachment)
            
            # Sort by attachment index
            attachments.sort(key=lambda x: x.get('attachmentIndex', 0))
            return attachments
            
        except Exception as e:
            print(f"Error retrieving attachments for message {message_id}: {str(e)}")
            return []
    
    def get_attachment_by_id(self, attachment_id: str) -> Optional[Dict]:
        """Get attachment metadata by attachment ID"""
        try:
            response = self.dynamodb.get_item(
                TableName=self.attachments_table,
                Key={'attachmentId': {'S': attachment_id}}
            )
            
            if 'Item' in response:
                return self._convert_dynamodb_attachment_to_dict(response['Item'])
            
            return None
            
        except Exception as e:
            print(f"Error retrieving attachment {attachment_id}: {str(e)}")
            return None
    
    def get_attachment_content(self, attachment_id: str) -> Optional[Tuple[bytes, str, str]]:
        """
        Get attachment content from S3
        
        Returns:
            Tuple of (content_bytes, content_type, filename) or None if not found
        """
        try:
            # Get attachment metadata
            attachment = self.get_attachment_by_id(attachment_id)
            if not attachment:
                print(f"Attachment {attachment_id} not found in database")
                return None
            
            # Download content from S3
            response = self.s3_client.get_object(
                Bucket=attachment['s3Bucket'],
                Key=attachment['s3Key']
            )
            
            content = response['Body'].read()
            content_type = attachment['contentType']
            filename = attachment['filename']
            
            return content, content_type, filename
            
        except Exception as e:
            print(f"Error retrieving attachment content for {attachment_id}: {str(e)}")
            return None
    
    def get_attachment_download_url(self, attachment_id: str, expires_in: int = 3600) -> Optional[str]:
        """
        Generate a presigned URL for attachment download
        
        Args:
            attachment_id: Attachment ID
            expires_in: URL expiration time in seconds (default 1 hour)
            
        Returns:
            Presigned URL string or None if attachment not found
        """
        try:
            # Get attachment metadata
            attachment = self.get_attachment_by_id(attachment_id)
            if not attachment:
                return None
            
            # Generate presigned URL
            url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': attachment['s3Bucket'],
                    'Key': attachment['s3Key'],
                    'ResponseContentDisposition': f'attachment; filename="{attachment["filename"]}"',
                    'ResponseContentType': attachment['contentType']
                },
                ExpiresIn=expires_in
            )
            
            return url
            
        except Exception as e:
            print(f"Error generating download URL for {attachment_id}: {str(e)}")
            return None
    
    def delete_attachment(self, attachment_id: str) -> bool:
        """Soft delete an attachment (mark as deleted, don't remove from S3)"""
        try:
            # Mark as deleted in DynamoDB
            self.dynamodb.update_item(
                TableName=self.attachments_table,
                Key={'attachmentId': {'S': attachment_id}},
                UpdateExpression='SET isDeleted = :true, deletedAt = :deletedAt',
                ExpressionAttributeValues={
                    ':true': {'BOOL': True},
                    ':deletedAt': {'S': datetime.now(ZoneInfo('Australia/Perth')).isoformat()}
                }
            )
            
            return True
            
        except Exception as e:
            print(f"Error deleting attachment {attachment_id}: {str(e)}")
            return False
    
    def _convert_dynamodb_attachment_to_dict(self, item: Dict) -> Dict:
        """Convert DynamoDB item to readable attachment format"""
        return {
            'attachmentId': item.get('attachmentId', {}).get('S', ''),
            'messageId': item.get('messageId', {}).get('S', ''),
            'filename': item.get('filename', {}).get('S', ''),
            'contentType': item.get('contentType', {}).get('S', ''),
            'sizeBytes': int(item.get('sizeBytes', {}).get('N', '0')),
            'contentHash': item.get('contentHash', {}).get('S', ''),
            's3Bucket': item.get('s3Bucket', {}).get('S', ''),
            's3Key': item.get('s3Key', {}).get('S', ''),
            'attachmentIndex': int(item.get('attachmentIndex', {}).get('N', '0')),
            'uploadDate': item.get('uploadDate', {}).get('S', ''),
            'emailS3Bucket': item.get('emailS3Bucket', {}).get('S', ''),
            'emailS3Key': item.get('emailS3Key', {}).get('S', ''),
            'attachmentType': item.get('attachmentType', {}).get('S', 'received_email'),  # Default to received_email for backward compatibility
            'isDeleted': item.get('isDeleted', {}).get('BOOL', False)
        }
    
    def get_attachment_stats(self, message_id: str) -> Dict:
        """Get attachment statistics for an email"""
        attachments = self.get_attachments_for_email(message_id)
        
        total_size = sum(att['sizeBytes'] for att in attachments)
        
        stats = {
            'count': len(attachments),
            'totalSizeBytes': total_size,
            'totalSizeMB': round(total_size / (1024 * 1024), 2),
            'types': list(set(att['contentType'] for att in attachments))
        }
        
        return stats
