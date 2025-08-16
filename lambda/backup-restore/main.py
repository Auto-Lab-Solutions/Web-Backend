import json
import os
import datetime
import csv
import io
from botocore.exceptions import ClientError

import db_utils as db
import s3_utils as s3
import response_utils as resp

def lambda_handler(event, context):
    """
    Auto Lab Solutions - Enhanced Backup/Restore Lambda Function
    
    This function handles both automated and manual backup requests with cleanup functionality.
    It backs up DynamoDB tables and S3 objects (reports and invoices).
    It also performs data cleanup based on age policies for different tables.
    
    Weekly Schedule:
    - Runs once per week (Sunday at 2 AM UTC)
    - Performs cleanup of old records before backup
    - Backs up deleted records to CSV files in S3
    - Performs regular backup of all remaining data
    
    Cleanup Policies:
    - UnavailableSlots, Connections: Records older than 2 days
    - Other tables (except excluded): Records older than 2 months
    - Excluded from cleanup: EmailSuppression, ItemPrices, ServicePrices, Staff, Users
    
    Event structure:
    {
        "operation": "backup" | "restore" | "cleanup",
        "backup_timestamp": "2025-08-10-14-30-00" (required for restore),
        "tables": ["table1", "table2"] (optional, defaults to all tables),
        "clear_tables": true/false (restore only, default: true),
        "create_backup": true/false (restore only, default: true),
        "manual_trigger": true/false,
        "triggered_by": "username",
        "reason": "Manual backup requested",
        "skip_cleanup": true/false (backup only, default: false)
    }
    """
    try:
        # Log the incoming event
        print(f"Enhanced Backup/Restore Lambda triggered with event: {json.dumps(event, default=str)}")
        
        # Determine operation type
        operation = event.get('operation', 'backup')
        
        if operation == 'backup':
            return handle_backup_with_cleanup(event, context)
        elif operation == 'restore':
            return handle_restore(event, context)
        elif operation == 'cleanup':
            return handle_cleanup_only(event, context)
        elif operation == 'list_backups':
            return handle_list_backups(event, context)
        else:
            return resp.error_response(f"Invalid operation: {operation}. Must be 'backup', 'restore', 'cleanup', or 'list_backups'", 400)
            
    except Exception as e:
        print(f"Error in lambda_handler: {str(e)}")
        return resp.error_response(f"Internal server error: {str(e)}", 500)

def handle_backup_with_cleanup(event, context):
    """Handle backup operations with data cleanup"""
    try:
        environment = os.environ.get('ENVIRONMENT')
        backup_bucket = os.environ.get('BACKUP_BUCKET')
        reports_bucket = os.environ.get('REPORTS_BUCKET')
        retention_days = int(os.environ.get('RETENTION_DAYS', '30'))
        skip_cleanup = event.get('skip_cleanup', False)
        
        if not backup_bucket:
            return resp.error_response("BACKUP_BUCKET environment variable not set", 500)
        
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
        backup_prefix = f"backups/{environment}/{timestamp}"
        cleanup_prefix = f"cleanup/{environment}/{timestamp}"
        
        results = {
            'operation': 'backup_with_cleanup',
            'timestamp': timestamp,
            'environment': environment,
            'backup_location': f"s3://{backup_bucket}/{backup_prefix}",
            'cleanup_location': f"s3://{backup_bucket}/{cleanup_prefix}",
            'archive_location': f"s3://{backup_bucket}/archive/{environment}",
            'tables_backed_up': [],
            'tables_cleaned_up': {},
            'reports_and_invoices_backed_up': False,
            'errors': [],
            'request_id': context.aws_request_id if context else 'unknown',
            'cleanup_skipped': skip_cleanup
        }
        
        # Get list of DynamoDB tables to backup
        tables = get_dynamodb_tables(environment)
        
        # Perform cleanup before backup (unless skipped)
        if not skip_cleanup:
            print("Starting data cleanup process...")
            for table_name in tables:
                try:
                    cleanup_result = cleanup_old_records(table_name, backup_bucket, cleanup_prefix)
                    if cleanup_result['cleaned_count'] > 0:
                        results['tables_cleaned_up'][table_name] = cleanup_result
                        print(f"Cleaned up {cleanup_result['cleaned_count']} old records from {table_name}")
                except Exception as e:
                    error_msg = f"Failed to cleanup table {table_name}: {str(e)}"
                    print(error_msg)
                    results['errors'].append(error_msg)
        
        # Backup remaining DynamoDB tables
        print("Starting backup process...")
        for table_name in tables:
            try:
                print(f"Backing up table: {table_name}")
                table_backup_key = build_backup_s3_key(backup_prefix, "dynamodb", f"{table_name}.json")
                backup_table_data(table_name, backup_bucket, table_backup_key)
                results['tables_backed_up'].append(table_name)
            except Exception as e:
                error_msg = f"Failed to backup table {table_name}: {str(e)}"
                print(error_msg)
                results['errors'].append(error_msg)
        
        # Backup reports and invoices from S3 bucket if specified
        if reports_bucket:
            try:
                print(f"Backing up reports and invoices from: {reports_bucket}")
                reports_backup_prefix = build_backup_s3_key(backup_prefix, "reports-and-invoices")
                backup_s3_objects(reports_bucket, backup_bucket, reports_backup_prefix)
                results['reports_and_invoices_backed_up'] = True
            except Exception as e:
                error_msg = f"Failed to backup reports and invoices: {str(e)}"
                print(error_msg)
                results['errors'].append(error_msg)
        
        # Clean up old backups (but not archive files)
        try:
            cleanup_old_backups(backup_bucket, build_s3_key("backups", environment), retention_days)
            cleanup_old_backups(backup_bucket, build_s3_key("cleanup", environment), retention_days)
            # Note: Archive files in /archive/{environment}/ are never deleted automatically
        except Exception as e:
            error_msg = f"Failed to cleanup old backups: {str(e)}"
            print(error_msg)
            results['errors'].append(error_msg)
        
        # Save backup manifest
        try:
            manifest_key = build_backup_s3_key(backup_prefix, "backup-manifest.json")
            s3.put_object(backup_bucket, manifest_key, json.dumps(results, indent=2, default=str))
        except Exception as e:
            error_msg = f"Failed to save backup manifest: {str(e)}"
            print(error_msg)
            results['errors'].append(error_msg)
        
        # Return appropriate status
        status_code = 200 if not results['errors'] else 207
        return resp.success_response(results, status_code)
        
    except Exception as e:
        print(f"Error in handle_backup_with_cleanup: {str(e)}")
        return resp.error_response(f"Backup with cleanup failed: {str(e)}", 500)

def handle_restore(event, context):
    """
    Handle restore operations
    
    This function restores both DynamoDB tables and S3 objects (reports and invoices).
    
    Restore options:
    - restore_s3_objects: Set to False to skip S3 restoration (default: True)
    - clear_tables: Clear existing table data before restore (default: True)
    - create_backup: Create pre-restore backup (default: True)
    """
    try:
        environment = os.environ.get('ENVIRONMENT')
        backup_bucket = os.environ.get('BACKUP_BUCKET')
        
        if not backup_bucket:
            return resp.error_response("BACKUP_BUCKET environment variable not set", 500)
        
        # Get restore parameters
        backup_timestamp = event.get('backup_timestamp')
        tables_to_restore = event.get('tables', [])  # Empty list means restore all
        restore_s3_objects = event.get('restore_s3_objects', True)  # Default to restore S3 objects
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
            'reports_and_invoices_restored': False,
            'errors': [],
            'request_id': context.aws_request_id if context else 'unknown'
        }
        
        # Validate backup exists
        manifest_key = build_backup_s3_key(backup_prefix, "backup-manifest.json")
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
                pre_restore_prefix = build_s3_key("backups", environment, f"pre-restore-{pre_restore_timestamp}")
                
                for table_name in tables_to_restore:
                    table_backup_key = build_backup_s3_key(pre_restore_prefix, "dynamodb", f"{table_name}.json")
                    backup_table_data(table_name, backup_bucket, table_backup_key)
                
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
                backup_key = build_backup_s3_key(backup_prefix, "dynamodb", f"{table_name}.json")
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
        
        # Restore S3 objects (reports and invoices) if requested
        if restore_s3_objects:
            reports_bucket = os.environ.get('REPORTS_BUCKET')
            if reports_bucket:
                try:
                    print("Restoring reports and invoices from backup...")
                    restore_s3_objects_from_backup(backup_bucket, backup_prefix, reports_bucket)
                    results['reports_and_invoices_restored'] = True
                except Exception as e:
                    error_msg = f"Failed to restore reports and invoices: {str(e)}"
                    print(error_msg)
                    results['errors'].append(error_msg)
            else:
                error_msg = "REPORTS_BUCKET environment variable not set, cannot restore S3 objects"
                print(error_msg)
                results['errors'].append(error_msg)
        
        # Return appropriate status
        status_code = 200 if not results['errors'] else 207
        return resp.success_response(results, status_code)
        
    except Exception as e:
        print(f"Error in handle_restore: {str(e)}")
        return resp.error_response(f"Restore failed: {str(e)}", 500)

def handle_cleanup_only(event, context):
    """Handle cleanup operations only without backup"""
    try:
        environment = os.environ.get('ENVIRONMENT')
        backup_bucket = os.environ.get('BACKUP_BUCKET')
        
        if not backup_bucket:
            return resp.error_response("BACKUP_BUCKET environment variable not set", 500)
        
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d-%H-%M-%S')
        cleanup_prefix = f"cleanup/{environment}/{timestamp}"
        
        results = {
            'operation': 'cleanup_only',
            'timestamp': timestamp,
            'environment': environment,
            'cleanup_location': f"s3://{backup_bucket}/{cleanup_prefix}",
            'archive_location': f"s3://{backup_bucket}/archive/{environment}",
            'tables_cleaned_up': {},
            'errors': [],
            'request_id': context.aws_request_id if context else 'unknown'
        }
        
        # Get list of DynamoDB tables to cleanup
        tables = get_dynamodb_tables(environment)
        
        # Perform cleanup on all tables
        print("Starting cleanup-only process...")
        for table_name in tables:
            try:
                cleanup_result = cleanup_old_records(table_name, backup_bucket, cleanup_prefix)
                if cleanup_result['cleaned_count'] > 0:
                    results['tables_cleaned_up'][table_name] = cleanup_result
                    print(f"Cleaned up {cleanup_result['cleaned_count']} old records from {table_name}")
            except Exception as e:
                error_msg = f"Failed to cleanup table {table_name}: {str(e)}"
                print(error_msg)
                results['errors'].append(error_msg)
        
        # Save cleanup manifest
        try:
            manifest_key = build_cleanup_s3_key(cleanup_prefix, "cleanup-manifest.json")
            s3.put_object(backup_bucket, manifest_key, json.dumps(results, indent=2, default=str))
        except Exception as e:
            error_msg = f"Failed to save cleanup manifest: {str(e)}"
            print(error_msg)
            results['errors'].append(error_msg)
        
        # Return appropriate status
        status_code = 200 if not results['errors'] else 207
        return resp.success_response(results, status_code)
        
    except Exception as e:
        print(f"Error in handle_cleanup_only: {str(e)}")
        return resp.error_response(f"Cleanup failed: {str(e)}", 500)

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
        f'Invoices-{environment}',
        f'EmailSuppression-{environment}',
        f'EmailMetadata-{environment}',
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
        report_count = 0
        invoice_count = 0
        
        for obj_key in objects:
            backup_key = build_s3_key(backup_prefix, obj_key)
            s3.copy_object(source_bucket, obj_key, backup_bucket, backup_key)
            object_count += 1
            
            # Count different types of files for better reporting
            if obj_key.startswith('reports/'):
                report_count += 1
            elif obj_key.startswith('invoices/'):
                invoice_count += 1
        
        print(f"Backed up {object_count} objects from {source_bucket}")
        print(f"  - {report_count} report files")
        print(f"  - {invoice_count} invoice files")
        print(f"  - {object_count - report_count - invoice_count} other files")
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchBucket':
            print(f"Source bucket {source_bucket} not found, skipping...")
        else:
            raise

def cleanup_old_backups(bucket, prefix, retention_days):
    """Delete backups older than retention_days (but preserve archive CSV files)"""
    cutoff_date = datetime.datetime.now() - datetime.timedelta(days=retention_days)
    
    objects = s3.list_objects_with_metadata(bucket, prefix)
    deleted_count = 0
    
    for obj in objects:
        # Never delete archive CSV files (they contain cumulative deleted records)
        if '/archive/' in obj['Key'] and obj['Key'].endswith('_archive.csv'):
            print(f"Preserving archive file: {obj['Key']}")
            continue
        
        if obj['LastModified'].replace(tzinfo=None) < cutoff_date:
            s3.delete_object(bucket, obj['Key'])
            deleted_count += 1
    
    print(f"Cleaned up {deleted_count} old backup files (preserved archive CSV files)")

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

def restore_s3_objects_from_backup(backup_bucket, backup_prefix, target_bucket):
    """Restore S3 objects from backup to target bucket"""
    try:
        backup_s3_prefix = build_backup_s3_key(backup_prefix, "reports-and-invoices")
        
        # List all objects in the backup S3 location
        objects = s3.list_objects_with_metadata(backup_bucket, backup_s3_prefix)
        
        if not objects:
            print(f"No S3 objects found in backup location: {backup_s3_prefix}")
            return
        
        restored_count = 0
        report_count = 0
        invoice_count = 0
        
        for obj in objects:
            # Get the original object key by removing the backup prefix
            # Add trailing slash to ensure proper prefix matching
            prefix_with_slash = backup_s3_prefix + ('/' if not backup_s3_prefix.endswith('/') else '')
            original_key = obj['Key'][len(prefix_with_slash):] if obj['Key'].startswith(prefix_with_slash) else obj['Key']
            
            if not original_key:  # Skip if the key is empty after prefix removal
                continue
            
            try:
                # Copy object from backup location to target bucket
                s3.copy_object(backup_bucket, obj['Key'], target_bucket, original_key)
                restored_count += 1
                
                # Count different types of restored files
                if original_key.startswith('reports/'):
                    report_count += 1
                elif original_key.startswith('invoices/'):
                    invoice_count += 1
                
                print(f"Restored: {original_key}")
                
            except Exception as e:
                print(f"Failed to restore {original_key}: {str(e)}")
                raise
        
        print(f"Successfully restored {restored_count} S3 objects to {target_bucket}")
        print(f"  - {report_count} report files")
        print(f"  - {invoice_count} invoice files")
        print(f"  - {restored_count - report_count - invoice_count} other files")
        
    except Exception as e:
        print(f"Error restoring S3 objects: {str(e)}")
        raise

def handle_list_backups(event, context):
    """Handle listing available backups"""
    try:
        environment = os.environ.get('ENVIRONMENT')
        backup_bucket = os.environ.get('BACKUP_BUCKET')
        
        if not backup_bucket:
            return resp.error_response("BACKUP_BUCKET environment variable not set", 500)
        
        # List backups for the environment
        backup_prefix = build_s3_key("backups", environment)
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
                manifest_key = build_backup_s3_key(backup_prefix, timestamp, "backup-manifest.json")
                try:
                    manifest_content = s3.get_object(backup_bucket, manifest_key)
                    manifest = json.loads(manifest_content)
                    backups.append({
                        'timestamp': timestamp,
                        'tables_backed_up': manifest.get('tables_backed_up', []),
                        'reports_and_invoices_backed_up': manifest.get('reports_and_invoices_backed_up', manifest.get('reports_backed_up', False)),  # Support old format
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

def cleanup_old_records(table_name, backup_bucket, cleanup_prefix):
    """
    Clean up old records from DynamoDB table based on table-specific policies.
    Returns dict with cleanup results.
    """
    try:
        # Extract base table name (remove environment suffix)
        base_table_name = table_name.split('-')[0]
        
        # Tables that should be excluded from cleanup
        excluded_tables = {'EmailSuppression', 'ItemPrices', 'ServicePrices', 'Staff', 'Users'}
        
        if base_table_name in excluded_tables:
            print(f"Skipping cleanup for excluded table: {table_name}")
            return {
                'cleaned_count': 0,
                'archive_key': '',
                'reason': 'excluded_table'
            }
        
        # Determine cleanup age policy
        if base_table_name in ['UnavailableSlots', 'Connections']:
            cutoff_days = 2
        else:
            cutoff_days = 60  # 2 months
        
        cutoff_date = datetime.datetime.now() - datetime.timedelta(days=cutoff_days)
        cutoff_timestamp = int(cutoff_date.timestamp())
        
        print(f"Cleaning up records older than {cutoff_days} days ({cutoff_date.isoformat()}) from {table_name}")
        
        # Get old records to cleanup
        old_records = get_old_records(table_name, base_table_name, cutoff_timestamp)
        
        if not old_records:
            print(f"No old records found in {table_name}")
            return {
                'cleaned_count': 0,
                'archive_key': '',
                'reason': 'no_old_records'
            }
        
        # Backup old records to CSV before deletion (append to existing file)
        # Include environment in archive path: archive/{environment}/TableName_archive.csv
        environment = os.environ.get('ENVIRONMENT')
        csv_key = build_cleanup_s3_key("archive", environment, f"{base_table_name}_archive.csv")
        append_records_to_csv(old_records, backup_bucket, csv_key, table_name)
        
        # Delete old records
        deleted_count = delete_old_records(table_name, old_records)
        
        print(f"Successfully cleaned up {deleted_count} records from {table_name}")
        
        return {
            'cleaned_count': deleted_count,
            'archive_key': csv_key,
            'cutoff_date': cutoff_date.isoformat(),
            'cutoff_days': cutoff_days,
            'archive_type': 'cumulative'
        }
        
    except Exception as e:
        print(f"Error during cleanup of {table_name}: {str(e)}")
        raise

def get_old_records(table_name, base_table_name, cutoff_timestamp):
    """Get records that are older than the cutoff timestamp"""
    try:
        # Get all items from table
        items = db.scan_all_items(table_name)
        
        if not items:
            return []
        
        old_records = []
        
        for item in items:
            # Deserialize the item for easier processing
            record = db.deserialize_item_json_safe(item)
            if not record:
                continue
            
            # Determine the timestamp field based on table type
            timestamp_field = get_timestamp_field(base_table_name)
            
            if timestamp_field and timestamp_field in record:
                record_timestamp = parse_timestamp(record[timestamp_field])
                
                if record_timestamp and record_timestamp < cutoff_timestamp:
                    old_records.append(record)
            else:
                # If no timestamp field, check common fields
                for common_field in ['createdAt', 'updatedAt', 'timestamp', 'created_at', 'updated_at']:
                    if common_field in record:
                        record_timestamp = parse_timestamp(record[common_field])
                        if record_timestamp and record_timestamp < cutoff_timestamp:
                            old_records.append(record)
                            break
        
        print(f"Found {len(old_records)} old records in {table_name}")
        return old_records
        
    except Exception as e:
        print(f"Error getting old records from {table_name}: {str(e)}")
        raise

def get_timestamp_field(base_table_name):
    """Get the primary timestamp field for each table type"""
    timestamp_fields = {
        'Messages': 'timestamp',
        'Appointments': 'createdAt',
        'Orders': 'createdAt',
        'Inquiries': 'createdAt',
        'Payments': 'createdAt',
        'Invoices': 'createdAt',
        'UnavailableSlots': 'date',  # Special handling needed
        'EmailMetadata': 'timestamp',
        'Connections': 'connectedAt'
    }
    return timestamp_fields.get(base_table_name)

def parse_timestamp(timestamp_value):
    """Parse various timestamp formats to Unix timestamp"""
    try:
        if isinstance(timestamp_value, (int, float)):
            # Already a Unix timestamp
            return int(timestamp_value)
        elif isinstance(timestamp_value, str):
            # Try parsing ISO format
            try:
                dt = datetime.datetime.fromisoformat(timestamp_value.replace('Z', '+00:00'))
                return int(dt.timestamp())
            except:
                # Try parsing date format (YYYY-MM-DD)
                try:
                    dt = datetime.datetime.strptime(timestamp_value, '%Y-%m-%d')
                    return int(dt.timestamp())
                except:
                    return None
        return None
    except Exception:
        return None

def append_records_to_csv(records, bucket, s3_key, table_name):
    """Append records to existing CSV file in S3, creating cumulative archive"""
    try:
        if not records:
            return
        
        # Check if CSV file already exists
        existing_records = []
        existing_fieldnames = set()
        file_exists = False
        
        try:
            # Try to download existing CSV
            existing_csv_content = s3.get_object(bucket, s3_key)
            if existing_csv_content:
                file_exists = True
                # Parse existing CSV
                csv_reader = csv.DictReader(io.StringIO(existing_csv_content))
                existing_fieldnames = set(csv_reader.fieldnames or [])
                existing_records = list(csv_reader)
                print(f"Found existing archive with {len(existing_records)} records for {table_name}")
        except Exception as e:
            # File doesn't exist or is empty, start fresh
            print(f"No existing archive found for {table_name}, creating new one")
            file_exists = False
        
        # Get all unique keys from both existing and new records
        all_keys = existing_fieldnames.copy()
        for record in records:
            all_keys.update(record.keys())
        
        # Add timestamp for when record was archived
        all_keys.add('archived_at')
        
        fieldnames = sorted(list(all_keys))
        
        # Create new CSV content with all records (existing + new)
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        
        # Write header
        writer.writeheader()
        
        # Write existing records first (if any)
        for existing_record in existing_records:
            # Ensure all fields are present
            csv_record = {}
            for key in fieldnames:
                csv_record[key] = existing_record.get(key, '')
            writer.writerow(csv_record)
        
        # Write new records with archive timestamp
        archive_timestamp = datetime.datetime.now().isoformat()
        for record in records:
            # Convert complex objects to strings for CSV
            csv_record = {'archived_at': archive_timestamp}
            for key in fieldnames:
                if key == 'archived_at':
                    continue  # Already set
                value = record.get(key, '')
                if isinstance(value, (dict, list)):
                    csv_record[key] = json.dumps(value)
                else:
                    csv_record[key] = str(value) if value is not None else ''
            writer.writerow(csv_record)
        
        # Upload updated CSV to S3
        csv_content = output.getvalue()
        s3.put_object(bucket, s3_key, csv_content)
        
        total_records = len(existing_records) + len(records)
        print(f"Updated archive for {table_name}: {len(records)} new records added, {total_records} total records in {s3_key}")
        
    except Exception as e:
        print(f"Error appending records to CSV archive: {str(e)}")
        raise

def delete_old_records(table_name, records):
    """Delete old records from DynamoDB table"""
    try:
        if not records:
            return 0
        
        # Get table key schema to identify primary keys
        key_schema = db.get_table_key_schema(table_name)
        key_names = [key['AttributeName'] for key in key_schema]
        
        deleted_count = 0
        
        # Delete records one by one (could be optimized with batch operations)
        for record in records:
            try:
                # Build key for deletion
                key = {}
                for key_name in key_names:
                    if key_name in record:
                        # Convert to DynamoDB format if needed
                        value = record[key_name]
                        if not db.is_dynamodb_format({key_name: value}):
                            key[key_name] = db.convert_to_dynamodb_format(value)
                        else:
                            key[key_name] = value
                
                if len(key) == len(key_names):
                    db.delete_item(table_name, key)
                    deleted_count += 1
                else:
                    print(f"Skipping record with incomplete key: {key}")
                
            except Exception as e:
                print(f"Error deleting individual record: {str(e)}")
                continue
        
        print(f"Successfully deleted {deleted_count} old records from {table_name}")
        return deleted_count
        
    except Exception as e:
        print(f"Error deleting old records from {table_name}: {str(e)}")
        raise

def build_s3_key(*parts):
    """Build standardized S3 key from parts, ensuring proper path separators"""
    # Filter out empty parts and ensure no leading/trailing slashes
    clean_parts = [str(part).strip('/') for part in parts if part and str(part).strip()]
    return '/'.join(clean_parts)

def build_backup_s3_key(backup_prefix, *path_parts):
    """Build standardized backup S3 key"""
    return build_s3_key(backup_prefix, *path_parts)

def build_cleanup_s3_key(cleanup_prefix, *path_parts):
    """Build standardized cleanup S3 key"""
    return build_s3_key(cleanup_prefix, *path_parts)
