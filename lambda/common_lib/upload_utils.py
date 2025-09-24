"""
Upload Manager for API operations

This module provides managers for file upload operations,
including validation and S3 presigned URL generation for both
reports and attachments.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import db_utils as db
import s3_utils as s3
import request_utils as req
from exceptions import BusinessLogicError
from data_access_utils import DataAccessManager


class UploadManager(DataAccessManager):
    """Manager for file upload operations (reports and attachments)"""
    
    def __init__(self):
        super().__init__()
        self.permitted_roles = ['MECHANIC', 'CLERK', 'CUSTOMER_SUPPORT', 'ADMIN']
        self.max_file_size = 10 * 1024 * 1024  # 10MB
        
        # Define allowed file types for different upload types
        self.allowed_file_types = {
            'report': ['application/pdf', 'pdf'],
            'attachment': [
                'application/pdf', 'pdf',
                'image/jpeg', 'image/jpg', 'image/png', 'image/gif',
                'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                'text/plain', 'text/csv',
                'application/zip', 'application/x-zip-compressed'
            ]
        }
    
    def generate_upload_url(self, event, staff_context):
        """
        Generate presigned URL for file upload (reports or attachments)
        
        Args:
            event: Lambda event with request parameters
            staff_context: Staff context from authentication
            
        Returns:
            dict: Upload URL and metadata
        """
        # Validate staff has required permissions
        if not any(role in staff_context['staff_roles'] for role in self.permitted_roles):
            roles_str = ', '.join(self.permitted_roles)
            raise BusinessLogicError(f"Unauthorized: {roles_str} role required", 403)
        
        # Get request parameters
        upload_type = req.get_body_param(event, 'uploadType')  # Required parameter
        reference_id = req.get_body_param(event, 'referenceId')
        file_name = req.get_body_param(event, 'fileName')
        file_type = req.get_body_param(event, 'fileType')
        file_size = req.get_body_param(event, 'fileSize')
        
        # Validate required parameters
        if not upload_type:
            raise BusinessLogicError("uploadType is required and must be either 'report' or 'attachment'", 400)
        if not reference_id or not file_name or not file_type:
            raise BusinessLogicError("referenceId, fileName, and fileType are required", 400)
        
        # Validate upload type
        if upload_type not in ['report', 'attachment']:
            raise BusinessLogicError("uploadType must be either 'report' or 'attachment'", 400)
        
        # Validate reference exists based on upload type
        if upload_type == 'report':
            existing_record = db.get_appointment(reference_id)
            if not existing_record:
                raise BusinessLogicError("Appointment not found", 404)
        elif upload_type == 'attachment':
            # For attachments, we might be attaching to appointments, orders, or emails
            # Let's check if it's a valid reference (could be appointment, order, or message)
            existing_record = (db.get_appointment(reference_id) or 
                             db.get_order(reference_id) or 
                             self._check_email_message_exists(reference_id))
            if not existing_record:
                raise BusinessLogicError("Reference record not found", 404)
        
        # Validate file type
        allowed_types = self.allowed_file_types.get(upload_type, [])
        if file_type.lower() not in allowed_types:
            if upload_type == 'report':
                raise BusinessLogicError("Only PDF files are allowed for reports", 400)
            else:
                raise BusinessLogicError(f"File type '{file_type}' not allowed for attachments", 400)
        
        # Validate file size
        if file_size and int(file_size) > self.max_file_size:
            max_size_mb = self.max_file_size // (1024 * 1024)
            raise BusinessLogicError(f"File size exceeds maximum limit of {max_size_mb}MB", 400)
        
        # Generate S3 key and presigned URL
        timestamp = datetime.now(ZoneInfo('Australia/Perth')).strftime('%Y%m%d_%H%M%S')
        if upload_type == 'report':
            s3_key = f"reports/{reference_id}/{timestamp}_{file_name}"
        else:  # attachment
            s3_key = f"attachments/{reference_id}/{timestamp}_{file_name}"
        
        try:
            upload_url_data = s3.generate_presigned_upload_url(
                bucket_name=s3.REPORTS_BUCKET_NAME,
                key=s3_key,
                content_type=file_type,
                expires_in=3600  # 1 hour
            )
            
            # Create metadata for the upload
            upload_metadata = {
                's3Key': s3_key,
                'fileName': file_name,
                'fileType': file_type,
                'fileSize': int(file_size) if file_size else 0,  # Ensure integer type
                'uploadType': upload_type,
                'uploadedBy': staff_context['staff_user_id'],
                'uploadedAt': datetime.now(ZoneInfo('Australia/Perth')).isoformat(),
                'status': 'pending_upload',
                'reviewed': False  # New field for admin approval
            }
            
            # Add metadata to the relevant record
            cloudfront_url = None
            if upload_type == 'report':
                cloudfront_url = self._add_report_to_appointment(reference_id, upload_metadata)
            else:  # attachment
                self._add_attachment_metadata(reference_id, upload_metadata, upload_type)
            
            response_data = {
                'uploadUrl': upload_url_data,
                'uploadFields': {},  # Simple presigned URL doesn't have fields
                's3Key': s3_key,
                'referenceId': reference_id,
                'uploadType': upload_type,
                'metadata': upload_metadata,
                'expiresIn': 3600,
                'instructions': {
                    'method': 'PUT',
                    'note': 'Use the uploadUrl for direct PUT upload with Content-Type header'
                }
            }
            
            # Add CloudFront URL to response if available (for reports)
            if cloudfront_url:
                response_data['fileUrl'] = cloudfront_url
            
            return response_data
            
        except Exception as e:
            raise BusinessLogicError(f"Failed to generate upload URL: {str(e)}", 500)
    
    def _check_email_message_exists(self, message_id):
        """Check if an email message exists in the system"""
        try:
            # This would need to be implemented based on your email storage system
            # For now, return True to allow attachment uploads to email threads
            return True
        except:
            return False
    
    def _add_attachment_metadata(self, reference_id, attachment_metadata, upload_type):
        """Add attachment metadata to the relevant record"""
        try:
            # Try to add to appointment first
            appointment = db.get_appointment(reference_id)
            if appointment:
                attachments = appointment.get('attachments', [])
                attachments.append(attachment_metadata)
                update_data = {
                    'attachments': attachments,
                    'updatedAt': datetime.now(ZoneInfo('Australia/Perth')).isoformat()
                }
                db.update_appointment(reference_id, update_data)
                return
            
            # Try to add to order
            order = db.get_order(reference_id)
            if order:
                attachments = order.get('attachments', [])
                attachments.append(attachment_metadata)
                update_data = {
                    'attachments': attachments,
                    'updatedAt': datetime.now(ZoneInfo('Australia/Perth')).isoformat()
                }
                db.update_order(reference_id, update_data)
                return
            
            # For email attachments, we might need a different approach
            # This could be handled by storing attachment metadata separately
            print(f"Warning: Could not find record {reference_id} to attach file metadata")
            
        except Exception as e:
            print(f"Warning: Failed to update record with attachment metadata: {str(e)}")
            # Don't fail the entire operation if this fails
    
    
    def _add_report_to_appointment(self, appointment_id, report_metadata):
        """Add report metadata to appointment record"""
        try:
            # Validate report metadata before adding
            if not report_metadata.get('s3Key'):
                raise BusinessLogicError("Report metadata missing s3Key", 500)
            if not report_metadata.get('fileName'):
                raise BusinessLogicError("Report metadata missing fileName", 500)
            
            # Generate CloudFront URL for the report
            cloudfront_url = s3.generate_public_url(file_key=report_metadata['s3Key'])
            report_metadata['fileUrl'] = cloudfront_url
            print(f"Generated CloudFront URL for report: {cloudfront_url}")
            
            # Get current appointment
            appointment = db.get_appointment(appointment_id)
            if not appointment:
                raise BusinessLogicError("Appointment not found", 404)
            
            # Add report to reports list
            reports = appointment.get('reports', [])
            reports.append(report_metadata)
            
            # Update appointment with new reports list
            update_data = {
                'reports': reports,
                'updatedAt': datetime.now(ZoneInfo('Australia/Perth')).isoformat()
            }
            
            success = db.update_appointment(appointment_id, update_data)
            if not success:
                raise BusinessLogicError("Failed to update appointment with report metadata", 500)
            
            # Return the CloudFront URL for use in response
            return cloudfront_url
            
        except BusinessLogicError:
            # Re-raise business logic errors
            raise
        except Exception as e:
            print(f"Error: Failed to update appointment with report metadata: {str(e)}")
            raise BusinessLogicError(f"Failed to add report to appointment: {str(e)}", 500)
    
    def validate_upload_completion(self, reference_id, s3_key, staff_context, upload_type='report'):
        """
        Validate that a file upload was completed successfully
        
        Args:
            reference_id: Reference ID (appointment, order, or message)
            s3_key: S3 key of uploaded file
            staff_context: Staff context
            upload_type: Type of upload ('report' or 'attachment')
            
        Returns:
            dict: Validation result
        """
        try:
            # Check if file exists in S3
            file_exists = s3.object_exists(s3.REPORTS_BUCKET_NAME, s3_key)
            
            if file_exists:
                # Update file status based on upload type
                if upload_type == 'report':
                    self._update_report_status(reference_id, s3_key, 'upload_completed')
                else:
                    self._update_attachment_status(reference_id, s3_key, 'upload_completed')
                
                return {
                    'status': 'completed',
                    'message': f'{upload_type.title()} upload completed successfully',
                    's3Key': s3_key,
                    'referenceId': reference_id,
                    'uploadType': upload_type
                }
            else:
                return {
                    'status': 'pending',
                    'message': f'{upload_type.title()} upload still in progress or failed',
                    's3Key': s3_key,
                    'referenceId': reference_id,
                    'uploadType': upload_type
                }
                
        except Exception as e:
            raise BusinessLogicError(f"Failed to validate upload completion: {str(e)}", 500)
    
    def _update_report_status(self, appointment_id, s3_key, status):
        """Update report status in appointment record"""
        try:
            appointment = db.get_appointment(appointment_id)
            if appointment and 'reports' in appointment:
                reports = appointment['reports']
                updated = False
                for report in reports:
                    if report.get('s3Key') == s3_key:
                        report['status'] = status
                        report['completedAt'] = datetime.now(ZoneInfo('Australia/Perth')).isoformat()
                        updated = True
                        break
                
                if updated:
                    update_data = {'reports': reports}
                    db.update_appointment(appointment_id, update_data)
        except Exception as e:
            print(f"Warning: Failed to update report status: {str(e)}")
    
    def _update_attachment_status(self, reference_id, s3_key, status):
        """Update attachment status in record"""
        try:
            # Try appointment first
            appointment = db.get_appointment(reference_id)
            if appointment and 'attachments' in appointment:
                attachments = appointment['attachments']
                updated = False
                for attachment in attachments:
                    if attachment.get('s3Key') == s3_key:
                        attachment['status'] = status
                        attachment['completedAt'] = datetime.now(ZoneInfo('Australia/Perth')).isoformat()
                        updated = True
                        break
                if updated:
                    update_data = {'attachments': attachments}
                    db.update_appointment(reference_id, update_data)
                return
            
            # Try order
            order = db.get_order(reference_id)
            if order and 'attachments' in order:
                attachments = order['attachments']
                updated = False
                for attachment in attachments:
                    if attachment.get('s3Key') == s3_key:
                        attachment['status'] = status
                        attachment['completedAt'] = datetime.now(ZoneInfo('Australia/Perth')).isoformat()
                        updated = True
                        break
                if updated:
                    update_data = {'attachments': attachments}
                    db.update_order(reference_id, update_data)
                return
                
        except Exception as e:
            print(f"Warning: Failed to update attachment status: {str(e)}")


# Factory function
def get_upload_manager():
    """Factory function to get UploadManager instance"""
    return UploadManager()
