"""
Report Upload Manager for API operations

This module provides managers for report upload operations,
including validation and S3 presigned URL generation.
"""

from datetime import datetime

import db_utils as db
import s3_utils as s3
import request_utils as req
from exceptions import BusinessLogicError
from data_access_utils import DataAccessManager


class ReportUploadManager(DataAccessManager):
    """Manager for report upload operations"""
    
    def __init__(self):
        super().__init__()
        self.permitted_roles = ['MECHANIC', 'CLERK']
        self.max_file_size = 10 * 1024 * 1024  # 10MB
        self.allowed_file_types = ['application/pdf', 'pdf']
    
    def generate_upload_url(self, event, staff_context):
        """
        Generate presigned URL for report upload
        
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
        appointment_id = req.get_body_param(event, 'appointmentId')
        file_name = req.get_body_param(event, 'fileName')
        file_type = req.get_body_param(event, 'fileType')
        file_size = req.get_body_param(event, 'fileSize')
        
        # Validate required parameters
        if not appointment_id or not file_name or not file_type:
            raise BusinessLogicError("appointmentId, fileName, and fileType are required", 400)
        
        # Validate appointment exists
        existing_appointment = db.get_appointment(appointment_id)
        if not existing_appointment:
            raise BusinessLogicError("Appointment not found", 404)
        
        # Validate file type
        if file_type.lower() not in self.allowed_file_types:
            raise BusinessLogicError("Only PDF files are allowed for reports", 400)
        
        # Validate file size
        if file_size and int(file_size) > self.max_file_size:
            max_size_mb = self.max_file_size // (1024 * 1024)
            raise BusinessLogicError(f"File size exceeds maximum limit of {max_size_mb}MB", 400)
        
        # Generate S3 key and presigned URL
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        s3_key = f"reports/{appointment_id}/{timestamp}_{file_name}"
        
        try:
            upload_url_data = s3.generate_presigned_upload_url(
                s3_key=s3_key,
                file_type=file_type,
                expiration_seconds=3600  # 1 hour
            )
            
            # Update appointment record with report metadata
            report_metadata = {
                's3Key': s3_key,
                'fileName': file_name,
                'fileType': file_type,
                'fileSize': file_size,
                'uploadedBy': staff_context['staff_user_id'],
                'uploadedAt': datetime.utcnow().isoformat(),
                'status': 'pending_upload'
            }
            
            # Add report to appointment's reports list
            self._add_report_to_appointment(appointment_id, report_metadata)
            
            return {
                'uploadUrl': upload_url_data['upload_url'],
                'uploadFields': upload_url_data.get('fields', {}),
                's3Key': s3_key,
                'appointmentId': appointment_id,
                'reportMetadata': report_metadata,
                'expiresIn': 3600,
                'instructions': {
                    'method': 'POST',
                    'note': 'Use the uploadUrl and fields for multipart form upload'
                }
            }
            
        except Exception as e:
            raise BusinessLogicError(f"Failed to generate upload URL: {str(e)}", 500)
    
    def _add_report_to_appointment(self, appointment_id, report_metadata):
        """Add report metadata to appointment record"""
        try:
            # Get current appointment
            appointment = db.get_appointment(appointment_id)
            if not appointment:
                raise BusinessLogicError("Appointment not found", 404)
            
            # Add report to reports list
            reports = appointment.get('reports', [])
            reports.append(report_metadata)
            
            # Update appointment
            db.update_appointment_field(appointment_id, 'reports', reports)
            db.update_appointment_field(appointment_id, 'updatedAt', datetime.utcnow().isoformat())
            
        except Exception as e:
            print(f"Warning: Failed to update appointment with report metadata: {str(e)}")
            # Don't fail the entire operation if this fails
    
    def validate_upload_completion(self, appointment_id, s3_key, staff_context):
        """
        Validate that a report upload was completed successfully
        
        Args:
            appointment_id: Appointment ID
            s3_key: S3 key of uploaded file
            staff_context: Staff context
            
        Returns:
            dict: Validation result
        """
        try:
            # Check if file exists in S3
            file_exists = s3.object_exists(s3_key)
            
            if file_exists:
                # Update report status to completed
                appointment = db.get_appointment(appointment_id)
                if appointment and 'reports' in appointment:
                    reports = appointment['reports']
                    for report in reports:
                        if report.get('s3Key') == s3_key:
                            report['status'] = 'upload_completed'
                            report['completedAt'] = datetime.utcnow().isoformat()
                            break
                    
                    db.update_appointment_field(appointment_id, 'reports', reports)
                
                return {
                    'status': 'completed',
                    'message': 'Report upload completed successfully',
                    's3Key': s3_key,
                    'appointmentId': appointment_id
                }
            else:
                return {
                    'status': 'pending',
                    'message': 'Report upload still in progress or failed',
                    's3Key': s3_key,
                    'appointmentId': appointment_id
                }
                
        except Exception as e:
            raise BusinessLogicError(f"Failed to validate upload completion: {str(e)}", 500)


def get_report_upload_manager():
    """Factory function to get ReportUploadManager instance"""
    return ReportUploadManager()
