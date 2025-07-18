import boto3
import os
import uuid
from datetime import datetime
import db_utils as db
import response_utils as resp
import request_utils as req

# Environment variables
S3_BUCKET_NAME = os.environ.get('REPORTS_BUCKET_NAME')
CLOUDFRONT_DOMAIN = os.environ.get('CLOUDFRONT_DOMAIN')
PERMITTED_ROLES = ['MECHANIC']

# Initialize S3 client
s3_client = boto3.client('s3')

def lambda_handler(event, context):
    try:
        # Get staff user information and body parameters
        staff_user_email = req.get_staff_user_email(event)
        appointment_id = req.get_body_param(event, 'appointmentId')
        file_name = req.get_body_param(event, 'fileName')
        file_type = req.get_body_param(event, 'fileType')
        file_size = req.get_body_param(event, 'fileSize')

        if not staff_user_email:
            return resp.error_response("Unauthorized: Staff authentication required", 401)
            
        staff_user_record = db.get_staff_record(staff_user_email)
        if not staff_user_record:
            return resp.error_response(f"No staff record found for email: {staff_user_email}", 404)
        
        staff_roles = staff_user_record.get('roles', [])
        staff_user_id = staff_user_record.get('userId')
        
        # Check if staff has required permissions
        if not any(role in staff_roles for role in PERMITTED_ROLES):
            return resp.error_response("Unauthorized: Insufficient permissions", 403)
        
        # Validate required parameters
        if not appointment_id or not file_name or not file_type:
            return resp.error_response("appointmentId, fileName, and fileType are required")
        
        # Validate appointment exists
        existing_appointment = db.get_appointment(appointment_id)
        if not existing_appointment:
            return resp.error_response("Appointment not found", 404)
        
        # Validate file type (only PDF allowed)
        if file_type.lower() not in ['application/pdf', 'pdf']:
            return resp.error_response("Only PDF files are allowed for reports")
        
        # Validate file size (max 10MB)
        if file_size and int(file_size) > 10 * 1024 * 1024:
            return resp.error_response("File size exceeds maximum limit of 10MB")
        
        # Generate unique file key
        file_extension = '.pdf'
        if not file_name.lower().endswith('.pdf'):
            file_name += file_extension
        
        # Create unique key with timestamp and UUID
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_id = str(uuid.uuid4())[:8]
        file_key = f"reports/{appointment_id}/{timestamp}_{unique_id}_{file_name}"
        
        # Set content type
        content_type = 'application/pdf'
        
        # Generate presigned URL for upload
        presigned_url = generate_presigned_upload_url(
            bucket_name=S3_BUCKET_NAME,
            key=file_key,
            content_type=content_type,
            expires_in=3600  # 1 hour
        )
        
        if not presigned_url:
            return resp.error_response("Failed to generate presigned URL", 500)
        
        # Generate public URL for accessing the uploaded file
        public_url = f"https://{CLOUDFRONT_DOMAIN}/{file_key}"
        
        # Store report metadata in the appointment
        report_metadata = {
            'fileName': file_name,
            'fileKey': file_key,
            'fileType': content_type,
            'fileSize': file_size,
            'uploadedBy': staff_user_id,
            'uploadedAt': int(datetime.now().timestamp()),
            'publicUrl': public_url
        }
        
        return resp.success_response({
            "message": "Presigned URL generated successfully",
            "presignedUrl": presigned_url,
            "publicUrl": public_url,
            "fileKey": file_key,
            "reportMetadata": report_metadata,
            "expiresIn": 3600
        })
        
    except Exception as e:
        print(f"Error in upload reports lambda: {str(e)}")
        return resp.error_response("Internal server error", 500)


def generate_presigned_upload_url(bucket_name, key, content_type, expires_in=3600):
    """Generate a presigned URL for uploading files to S3"""
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
        return None

