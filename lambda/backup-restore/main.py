import json
import os
import sys
import datetime
import boto3
from botocore.exceptions import ClientError

# Add common_lib to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'common_lib'))

import db_utils as db
import s3_utils as s3
import response_utils as resp

def lambda_handler(event, context):
    """
    Auto Lab Solutions - Backup/Restore Lambda Function
    
    This function handles both automated and manual backup requests.
    It can also handle restoration requests based on the event parameters.
    
    Event structure:
    {
        "operation": "backup" | "restore",
        "backup_timestamp": "2025-08-10-14-30-00" (required for restore),
        "tables": ["table1", "table2"] (optional, defaults to all tables),
        "clear_tables": true/false (restore only, default: true),
        "create_backup": true/false (restore only, default: true),
        "manual_trigger": true/false,
        "triggered_by": "username",
        "reason": "Manual backup requested"
    }
    """
    try:
        # Log the incoming event
        print(f"Backup/Restore Lambda triggered with event: {json.dumps(event, default=str)}")
        
        # Determine operation type
        operation = event.get('operation', 'backup')
        
        if operation == 'backup':
            return handle_backup(event, context)
        elif operation == 'restore':
            return handle_restore(event, context)
        elif operation == 'list_backups':
            return handle_list_backups(event, context)
        else:
            return resp.error_response(f"Invalid operation: {operation}. Must be 'backup', 'restore', or 'list_backups'", 400)
            
    except Exception as e:
        print(f"Error in lambda_handler: {str(e)}")
        return resp.error_response(f"Internal server error: {str(e)}", 500)

def handle_backup(event, context):
    """Handle backup operations"""
    try:
        environment = os.environ.get('ENVIRONMENT', 'production')
        backup_bucket = os.environ.get('BACKUP_BUCKET')
        reports_bucket = os.environ.get('REPORTS_BUCKET')
        retention_days = int(os.environ.get('RETENTION_DAYS', '30'))
        
        if not backup_bucket:
            return resp.error_response("BACKUP_BUCKET environment variable not set", 500)
        
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
        backup_prefix = f"backups/{environment}/{timestamp}"
        
        results = {
            'operation': 'backup',
            'timestamp': timestamp,
            'environment': environment,
            'backup_location': f"s3://{backup_bucket}/{backup_prefix}",
            'tables_backed_up': [],
            'reports_backed_up': False,
            'errors': [],
            'request_id': context.aws_request_id if context else 'unknown'
        }
        
        # Get list of DynamoDB tables to backup
        tables = get_dynamodb_tables(environment)
        
        # Backup DynamoDB tables
        for table_name in tables:
            try:
                print(f"Backing up table: {table_name}")
                backup_table_data(table_name, backup_bucket, f"{backup_prefix}/dynamodb/{table_name}.json")
                results['tables_backed_up'].append(table_name)
            except Exception as e:
                error_msg = f"Failed to backup table {table_name}: {str(e)}"
                print(error_msg)
                results['errors'].append(error_msg)
        
        # Backup reports from S3 bucket if specified
        if reports_bucket:
            try:
                print(f"Backing up reports from: {reports_bucket}")
                backup_s3_objects(reports_bucket, backup_bucket, f"{backup_prefix}/reports/")
                results['reports_backed_up'] = True
            except Exception as e:
                error_msg = f"Failed to backup reports: {str(e)}"
                print(error_msg)
                results['errors'].append(error_msg)
        
        # Clean up old backups
        try:
            cleanup_old_backups(backup_bucket, f"backups/{environment}/", retention_days)
        except Exception as e:
            error_msg = f"Failed to cleanup old backups: {str(e)}"
            print(error_msg)
            results['errors'].append(error_msg)
        
        # Save backup manifest
        try:
            manifest_key = f"{backup_prefix}/backup-manifest.json"
            s3.put_object(backup_bucket, manifest_key, json.dumps(results, indent=2))
        except Exception as e:
            error_msg = f"Failed to save backup manifest: {str(e)}"
            print(error_msg)
            results['errors'].append(error_msg)
        
        # Return appropriate status
        status_code = 200 if not results['errors'] else 207
        return resp.success_response(results, status_code)
        
    except Exception as e:
        print(f"Error in handle_backup: {str(e)}")
        return resp.error_response(f"Backup failed: {str(e)}", 500)

def handle_restore(event, context):
    """Handle restore operations"""
    try:
        environment = os.environ.get('ENVIRONMENT', 'production')
        backup_bucket = os.environ.get('BACKUP_BUCKET')
        
        if not backup_bucket:
            return resp.error_response("BACKUP_BUCKET environment variable not set", 500)
        
        # Get restore parameters
        backup_timestamp = event.get('backup_timestamp')
        tables_to_restore = event.get('tables', [])  # Empty list means restore all
        clear_tables = event.get('clear_tables', True)
        create_pre_restore_backup = event.get('create_backup', True)
        
        if not backup_timestamp:
            return resp.error_response("backup_timestamp is required for restore operation", 400)
        
        backup_prefix = f"backups/{environment}/{backup_timestamp}"
        
        results = {
            'operation': 'restore',
            'timestamp': datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S'),
            'environment': environment,
            'backup_timestamp': backup_timestamp,
            'backup_location': f"s3://{backup_bucket}/{backup_prefix}",
            'tables_restored': [],
            'errors': [],
            'request_id': context.aws_request_id if context else 'unknown'
        }
        
        # Validate backup exists
        manifest_key = f"{backup_prefix}/backup-manifest.json"
        try:
            manifest_content = s3.get_object(backup_bucket, manifest_key)
            backup_manifest = json.loads(manifest_content)
            print(f"Found backup manifest: {backup_manifest.get('timestamp')}")
        except Exception as e:
            return resp.error_response(f"Backup not found or invalid: {str(e)}", 404)
        
        # Get tables to restore
        if not tables_to_restore:
            tables_to_restore = backup_manifest.get('tables_backed_up', [])
        
        # Create pre-restore backup if requested
        if create_pre_restore_backup:
            try:
                pre_restore_timestamp = datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
                pre_restore_prefix = f"backups/{environment}/pre-restore-{pre_restore_timestamp}"
                
                for table_name in tables_to_restore:
                    backup_table_data(table_name, backup_bucket, f"{pre_restore_prefix}/dynamodb/{table_name}.json")
                
                print(f"Created pre-restore backup at: {pre_restore_prefix}")
            except Exception as e:
                error_msg = f"Failed to create pre-restore backup: {str(e)}"
                print(error_msg)
                results['errors'].append(error_msg)
        
        # Restore tables
        for table_name in tables_to_restore:
            try:
                print(f"Restoring table: {table_name}")
                
                # Get backup data
                backup_key = f"{backup_prefix}/dynamodb/{table_name}.json"
                backup_data_str = s3.get_object(backup_bucket, backup_key)
                backup_data = json.loads(backup_data_str)
                
                # Clear table if requested
                if clear_tables:
                    clear_table(table_name)
                
                # Restore data
                restore_table_data(table_name, backup_data)
                results['tables_restored'].append(table_name)
                
            except Exception as e:
                error_msg = f"Failed to restore table {table_name}: {str(e)}"
                print(error_msg)
                results['errors'].append(error_msg)
        
        # Return appropriate status
        status_code = 200 if not results['errors'] else 207
        return resp.success_response(results, status_code)
        
    except Exception as e:
        print(f"Error in handle_restore: {str(e)}")
        return resp.error_response(f"Restore failed: {str(e)}", 500)

def get_dynamodb_tables(environment):
    """Get list of DynamoDB tables for the environment"""
    return [
        f'Staff-{environment}',
        f'Users-{environment}',
        f'Connections-{environment}',
        f'Messages-{environment}',
        f'UnavailableSlots-{environment}',
        f'Appointments-{environment}',
        f'ServicePrices-{environment}',
        f'Orders-{environment}',
        f'ItemPrices-{environment}',
        f'Inquiries-{environment}',
        f'Payments-{environment}',
        f'Invoices-{environment}'
    ]

def backup_table_data(table_name, bucket, s3_key):
    """Backup DynamoDB table data to S3"""
    try:
        # Get all items from table
        items = db.scan_all_items(table_name)
        
        backup_data = {
            'table_name': table_name,
            'backup_timestamp': datetime.datetime.now().isoformat(),
            'item_count': len(items),
            'items': items
        }
        
        # Upload to S3
        s3.put_object(bucket, s3_key, json.dumps(backup_data, indent=2, default=str))
        
        print(f"Backed up {len(items)} items from {table_name}")
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            print(f"Table {table_name} not found, skipping...")
        else:
            raise

def backup_s3_objects(source_bucket, backup_bucket, backup_prefix):
    """Backup S3 objects from source bucket to backup location"""
    try:
        objects = s3.list_objects(source_bucket)
        object_count = 0
        
        for obj_key in objects:
            backup_key = f"{backup_prefix}{obj_key}"
            s3.copy_object(source_bucket, obj_key, backup_bucket, backup_key)
            object_count += 1
        
        print(f"Backed up {object_count} objects from {source_bucket}")
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchBucket':
            print(f"Source bucket {source_bucket} not found, skipping...")
        else:
            raise

def cleanup_old_backups(bucket, prefix, retention_days):
    """Delete backups older than retention_days"""
    cutoff_date = datetime.datetime.now() - datetime.timedelta(days=retention_days)
    
    objects = s3.list_objects_with_metadata(bucket, prefix)
    deleted_count = 0
    
    for obj in objects:
        if obj['LastModified'].replace(tzinfo=None) < cutoff_date:
            s3.delete_object(bucket, obj['Key'])
            deleted_count += 1
    
    print(f"Cleaned up {deleted_count} old backup files")

def clear_table(table_name):
    """Clear all items from a DynamoDB table"""
    try:
        print(f"Clearing table: {table_name}")
        
        # Get table key schema
        key_schema = db.get_table_key_schema(table_name)
        key_names = [key['AttributeName'] for key in key_schema]
        
        # Get all items (keys only)
        items = db.scan_table_keys_only(table_name, key_names)
        
        # Delete items in batches
        deleted_count = 0
        for item in items:
            key = {attr: item[attr] for attr in key_names if attr in item}
            db.delete_item(table_name, key)
            deleted_count += 1
        
        print(f"Cleared {deleted_count} items from {table_name}")
        
    except Exception as e:
        print(f"Error clearing table {table_name}: {str(e)}")
        raise

def restore_table_data(table_name, backup_data):
    """Restore data to a DynamoDB table"""
    try:
        items = backup_data.get('items', [])
        print(f"Restoring {len(items)} items to {table_name}")
        
        # Restore items in batches
        batch_size = 25
        restored_count = 0
        
        for i in range(0, len(items), batch_size):
            batch = items[i:i + batch_size]
            
            # Write batch to table
            db.batch_write_items(table_name, batch)
            restored_count += len(batch)
            
            print(f"Progress: {restored_count}/{len(items)} items restored")
        
        print(f"Restoration completed: {restored_count} items restored")
        
    except Exception as e:
        print(f"Error restoring table data: {str(e)}")
        raise

def handle_list_backups(event, context):
    """Handle listing available backups"""
    try:
        environment = os.environ.get('ENVIRONMENT', 'production')
        backup_bucket = os.environ.get('BACKUP_BUCKET')
        
        if not backup_bucket:
            return resp.error_response("BACKUP_BUCKET environment variable not set", 500)
        
        # List backups for the environment
        backup_prefix = f"backups/{environment}/"
        backups = []
        
        try:
            objects = s3.list_objects_with_metadata(backup_bucket, backup_prefix)
            
            # Group by backup timestamp
            backup_timestamps = set()
            for obj in objects:
                parts = obj['Key'].split('/')
                if len(parts) >= 3 and parts[2] != '':
                    backup_timestamps.add(parts[2])
            
            # Get details for each backup
            for timestamp in sorted(backup_timestamps, reverse=True):
                manifest_key = f"{backup_prefix}{timestamp}/backup-manifest.json"
                try:
                    manifest_content = s3.get_object(backup_bucket, manifest_key)
                    manifest = json.loads(manifest_content)
                    backups.append({
                        'timestamp': timestamp,
                        'tables_backed_up': manifest.get('tables_backed_up', []),
                        'reports_backed_up': manifest.get('reports_backed_up', False),
                        'errors': manifest.get('errors', []),
                        'backup_location': manifest.get('backup_location', ''),
                        'environment': manifest.get('environment', environment)
                    })
                except Exception as e:
                    print(f"Error reading manifest for backup {timestamp}: {e}")
                    backups.append({
                        'timestamp': timestamp,
                        'error': f"Could not read backup manifest: {str(e)}"
                    })
        
        except Exception as e:
            print(f"Error listing backups: {e}")
            return resp.error_response(f"Failed to list backups: {str(e)}", 500)
        
        return resp.success_response({
            'environment': environment,
            'backup_count': len(backups),
            'backups': backups
        })
        
    except Exception as e:
        print(f"Error in handle_list_backups: {str(e)}")
        return resp.error_response(f"Failed to list backups: {str(e)}", 500)
