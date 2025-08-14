#!/bin/bash

# Deployment Validation Script
# This script validates that all components are deployed correctly

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source environment configuration
source "$SCRIPT_DIR/config/environments.sh"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to get stack output value
get_stack_output() {
    local stack_name=$1
    local output_key=$2
    
    aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --query "Stacks[0].Outputs[?OutputKey=='$output_key'].OutputValue" \
        --output text \
        --region $AWS_REGION 2>/dev/null || echo ""
}

# Function to check if Lambda function exists and is active
check_lambda_function() {
    local function_name=$1
    local full_function_name="${function_name}-${ENVIRONMENT}"
    
    if aws lambda get-function --function-name "$full_function_name" --region $AWS_REGION &>/dev/null; then
        local state=$(aws lambda get-function --function-name "$full_function_name" --region $AWS_REGION --query 'Configuration.State' --output text)
        if [ "$state" = "Active" ]; then
            print_success "✓ Lambda function '$full_function_name' is active"
            return 0
        else
            print_warning "⚠ Lambda function '$full_function_name' exists but is not active (State: $state)"
            return 1
        fi
    else
        print_error "✗ Lambda function '$full_function_name' not found"
        return 1
    fi
}

# Function to check DynamoDB table
check_dynamodb_table() {
    local table_name=$1
    
    if aws dynamodb describe-table --table-name "$table_name" --region $AWS_REGION &>/dev/null; then
        local status=$(aws dynamodb describe-table --table-name "$table_name" --region $AWS_REGION --query 'Table.TableStatus' --output text)
        if [ "$status" = "ACTIVE" ]; then
            print_success "✓ DynamoDB table '$table_name' is active"
            return 0
        else
            print_warning "⚠ DynamoDB table '$table_name' exists but is not active (Status: $status)"
            return 1
        fi
    else
        print_error "✗ DynamoDB table '$table_name' not found"
        return 1
    fi
}

# Function to check API Gateway
check_api_gateway() {
    local api_id=$1
    local api_type=$2
    
    if [ "$api_type" = "rest" ]; then
        if aws apigateway get-rest-api --rest-api-id "$api_id" --region $AWS_REGION &>/dev/null; then
            print_success "✓ REST API Gateway '$api_id' is active"
            return 0
        else
            print_error "✗ REST API Gateway '$api_id' not found"
            return 1
        fi
    elif [ "$api_type" = "websocket" ]; then
        if aws apigatewayv2 get-api --api-id "$api_id" --region $AWS_REGION &>/dev/null; then
            print_success "✓ WebSocket API Gateway '$api_id' is active"
            return 0
        else
            print_error "✗ WebSocket API Gateway '$api_id' not found"
            return 1
        fi
    fi
}

# Function to check S3 bucket
check_s3_bucket() {
    local bucket_name=$1
    
    if aws s3 ls "s3://$bucket_name" --region $AWS_REGION &>/dev/null; then
        print_success "✓ S3 bucket '$bucket_name' is accessible"
        return 0
    else
        print_error "✗ S3 bucket '$bucket_name' not accessible"
        return 1
    fi
}

# Function to check SQS queue
check_sqs_queue() {
    local queue_url=$1
    
    if [ -z "$queue_url" ]; then
        print_warning "⚠ SQS queue URL not provided, skipping SQS validation"
        return 0
    fi
    
    if aws sqs get-queue-attributes --queue-url "$queue_url" --region $AWS_REGION &>/dev/null; then
        print_success "✓ SQS queue '$queue_url' is accessible"
        return 0
    else
        print_error "✗ SQS queue '$queue_url' not accessible"
        return 1
    fi
}

# Function to check custom domain configuration
check_custom_domain() {
    local domain_name=$1
    local api_type=$2
    
    if [ -z "$domain_name" ]; then
        print_status "✓ Custom domain not configured for $api_type API (using default endpoints)"
        return 0
    fi
    
    print_status "Checking custom domain '$domain_name' for $api_type API..."
    
    # Check if custom domain exists in API Gateway
    if [ "$api_type" = "rest" ]; then
        if aws apigateway get-domain-name --domain-name "$domain_name" --region $AWS_REGION &>/dev/null; then
            local domain_status=$(aws apigateway get-domain-name --domain-name "$domain_name" --region $AWS_REGION --query 'DomainNameStatus' --output text)
            if [ "$domain_status" = "AVAILABLE" ]; then
                print_success "✓ REST API custom domain '$domain_name' is available"
            else
                print_warning "⚠ REST API custom domain '$domain_name' status: $domain_status"
                return 1
            fi
        else
            print_error "✗ REST API custom domain '$domain_name' not found"
            return 1
        fi
    elif [ "$api_type" = "websocket" ]; then
        if aws apigatewayv2 get-domain-name --domain-name "$domain_name" --region $AWS_REGION &>/dev/null; then
            local domain_status=$(aws apigatewayv2 get-domain-name --domain-name "$domain_name" --region $AWS_REGION --query 'DomainNameConfigurations[0].DomainNameStatus' --output text)
            if [ "$domain_status" = "AVAILABLE" ]; then
                print_success "✓ WebSocket API custom domain '$domain_name' is available"
            else
                print_warning "⚠ WebSocket API custom domain '$domain_name' status: $domain_status"
                return 1
            fi
        else
            print_error "✗ WebSocket API custom domain '$domain_name' not found"
            return 1
        fi
    fi
    
    return 0
}

# Function to check DNS resolution
check_dns_resolution() {
    local domain_name=$1
    local api_type=$2
    
    if [ -z "$domain_name" ]; then
        return 0
    fi
    
    print_status "Checking DNS resolution for '$domain_name'..."
    
    # Use nslookup to check if domain resolves
    if command -v nslookup >/dev/null 2>&1; then
        if nslookup "$domain_name" >/dev/null 2>&1; then
            local resolved_ip=$(nslookup "$domain_name" | grep -A1 "Name:" | tail -1 | awk '{print $2}' 2>/dev/null || echo "")
            if [ -n "$resolved_ip" ]; then
                print_success "✓ DNS resolution successful for '$domain_name' (resolves to: $resolved_ip)"
            else
                print_success "✓ DNS resolution successful for '$domain_name'"
            fi
        else
            print_warning "⚠ DNS resolution failed for '$domain_name'"
            print_warning "  Domain may not be fully propagated yet"
            return 1
        fi
    else
        print_warning "⚠ nslookup command not available, skipping DNS resolution check"
    fi
    
    return 0
}

# Function to check Route53 hosted zone
check_hosted_zone() {
    local hosted_zone_id=$1
    local domain_name=$2
    
    if [ -z "$hosted_zone_id" ] || [ -z "$domain_name" ]; then
        print_status "✓ Route53 hosted zone not configured"
        return 0
    fi
    
    print_status "Checking Route53 hosted zone '$hosted_zone_id'..."
    
    # Check if hosted zone exists
    if aws route53 get-hosted-zone --id "$hosted_zone_id" --region $AWS_REGION &>/dev/null; then
        local zone_name=$(aws route53 get-hosted-zone --id "$hosted_zone_id" --region $AWS_REGION --query 'HostedZone.Name' --output text)
        # Remove trailing dot from zone name for comparison
        zone_name=${zone_name%.}
        
        # Check if domain matches hosted zone
        if [[ "$domain_name" == *"$zone_name" ]]; then
            print_success "✓ Route53 hosted zone '$hosted_zone_id' is valid for domain '$domain_name'"
            
            # Check if A record exists for the domain
            local record_sets=$(aws route53 list-resource-record-sets --hosted-zone-id "$hosted_zone_id" --region $AWS_REGION --query "ResourceRecordSets[?Name=='${domain_name}.']" --output text)
            if [ -n "$record_sets" ]; then
                print_success "✓ DNS record found for '$domain_name' in hosted zone"
            else
                print_warning "⚠ No DNS record found for '$domain_name' in hosted zone '$hosted_zone_id'"
                return 1
            fi
        else
            print_error "✗ Domain '$domain_name' does not match hosted zone '$zone_name'"
            return 1
        fi
    else
        print_error "✗ Route53 hosted zone '$hosted_zone_id' not found"
        return 1
    fi
    
    return 0
}

# Function to check ACM certificate
check_acm_certificate() {
    local cert_arn=$1
    local domain_name=$2
    
    if [ -z "$cert_arn" ]; then
        print_status "✓ ACM certificate not configured"
        return 0
    fi
    
    print_status "Checking ACM certificate..."
    
    # Extract certificate ARN region
    local cert_region=$(echo "$cert_arn" | cut -d: -f4)
    
    # Check if certificate exists
    if aws acm describe-certificate --certificate-arn "$cert_arn" --region "$cert_region" &>/dev/null; then
        local cert_status=$(aws acm describe-certificate --certificate-arn "$cert_arn" --region "$cert_region" --query 'Certificate.Status' --output text)
        local cert_domain=$(aws acm describe-certificate --certificate-arn "$cert_arn" --region "$cert_region" --query 'Certificate.DomainName' --output text)
        
        if [ "$cert_status" = "ISSUED" ]; then
            print_success "✓ ACM certificate is issued and valid"
            
            # Check if certificate covers the domain
            if [ -n "$domain_name" ]; then
                if [ "$cert_domain" = "$domain_name" ] || [[ "$cert_domain" == "*."* && "$domain_name" == *"${cert_domain#*.}" ]]; then
                    print_success "✓ ACM certificate covers domain '$domain_name'"
                else
                    print_warning "⚠ ACM certificate domain '$cert_domain' may not cover '$domain_name'"
                    return 1
                fi
            fi
        else
            print_error "✗ ACM certificate status: $cert_status"
            return 1
        fi
    else
        print_error "✗ ACM certificate not found: $cert_arn"
        return 1
    fi
    
    return 0
}

# Function to check external backup bucket
check_external_backup_bucket() {
    local bucket_name="$1"
    
    if [ -z "$bucket_name" ]; then
        print_warning "No backup bucket name provided"
        return 1
    fi
    
    print_status "Checking external backup bucket '$bucket_name'..."
    
    # Check if bucket exists and is accessible
    if aws s3api head-bucket --bucket "$bucket_name" 2>/dev/null; then
        print_success "Backup bucket '$bucket_name' exists and is accessible"
        
        # Check bucket versioning
        local versioning_status=$(aws s3api get-bucket-versioning --bucket "$bucket_name" --query 'Status' --output text 2>/dev/null)
        if [ "$versioning_status" = "Enabled" ]; then
            print_success "Bucket versioning is enabled"
        else
            print_warning "Bucket versioning is not enabled (recommended for backups)"
        fi
        
        # Check if backup folder structure exists
        if aws s3 ls "s3://$bucket_name/backups/" >/dev/null 2>&1; then
            print_success "Backup folder structure exists"
        else
            print_warning "Backup folder structure not found (will be created on first backup)"
        fi
        
        return 0
    else
        print_error "Backup bucket '$bucket_name' does not exist or is not accessible"
        print_error "Please run: ./initialize-external-backup-bucket.sh $ENVIRONMENT"
        return 1
    fi
}

# Function to check reports domain resolution
check_reports_domain() {
    local reports_domain="$1"
    local cloudfront_domain="$2"
    
    if [ -z "$reports_domain" ]; then
        print_warning "No reports domain configured, using CloudFront domain"
        return 0
    fi
    
    print_status "Checking reports domain '$reports_domain'..."
    
    # Check DNS resolution
    if command -v nslookup >/dev/null 2>&1; then
        if nslookup "$reports_domain" >/dev/null 2>&1; then
            print_success "Reports domain '$reports_domain' resolves correctly"
            
            # Check if it points to CloudFront
            local resolved_target=$(nslookup "$reports_domain" | grep -A1 "canonical name" | tail -1 | awk '{print $NF}' | sed 's/\.$//')
            if [[ "$resolved_target" == *"cloudfront.net" ]]; then
                print_success "Reports domain points to CloudFront distribution"
            else
                print_warning "Reports domain may not be pointing to CloudFront distribution"
            fi
            
            return 0
        else
            print_error "Reports domain '$reports_domain' does not resolve"
            print_error "Check Route53 configuration and DNS propagation"
            return 1
        fi
    else
        print_warning "nslookup command not available, skipping DNS resolution check"
        return 0
    fi
}

# Main validation function
validate_deployment() {
    print_status "Starting deployment validation..."
    
    local errors=0
    
    # Check CloudFormation stack
    print_status "Checking CloudFormation stack..."
    if aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region $AWS_REGION &>/dev/null; then
        local stack_status=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region $AWS_REGION --query 'Stacks[0].StackStatus' --output text)
        if [ "$stack_status" = "CREATE_COMPLETE" ] || [ "$stack_status" = "UPDATE_COMPLETE" ]; then
            print_success "✓ CloudFormation stack '$STACK_NAME' is in good state ($stack_status)"
        else
            print_error "✗ CloudFormation stack '$STACK_NAME' is in bad state ($stack_status)"
            ((errors++))
        fi
    else
        print_error "✗ CloudFormation stack '$STACK_NAME' not found"
        ((errors++))
        return $errors
    fi
    
    # Get stack outputs
    print_status "Retrieving stack outputs..."
    REST_API_ID=$(get_stack_output "$STACK_NAME" "RestApiId")
    REST_API_ENDPOINT=$(get_stack_output "$STACK_NAME" "RestApiEndpoint")
    WEBSOCKET_API_ID=$(get_stack_output "$STACK_NAME" "WebSocketApiId")
    WEBSOCKET_API_ENDPOINT=$(get_stack_output "$STACK_NAME" "WebSocketApiEndpoint")
    CLOUDFRONT_DOMAIN=$(get_stack_output "$STACK_NAME" "CloudFrontDomainName")
    REPORTS_DOMAIN=$(get_stack_output "$STACK_NAME" "ReportsDomainName")
    REPORTS_BASE_URL=$(get_stack_output "$STACK_NAME" "ReportsBaseUrl")
    INVOICE_QUEUE_URL=$(get_stack_output "$STACK_NAME" "InvoiceQueueUrl")
    BACKUP_BUCKET_NAME=$(get_stack_output "$STACK_NAME" "BackupBucketName")
    
    # Get custom domain outputs (may be empty if not configured)
    REST_API_CUSTOM_DOMAIN=$(get_stack_output "$STACK_NAME" "RestApiCustomDomainName")
    WEBSOCKET_API_CUSTOM_DOMAIN=$(get_stack_output "$STACK_NAME" "WebSocketApiCustomDomainName")
    
    print_status "Stack Outputs:"
    echo "  REST API ID: $REST_API_ID"
    echo "  REST API Endpoint: $REST_API_ENDPOINT"
    if [ -n "$REST_API_CUSTOM_DOMAIN" ]; then
        echo "  REST API Custom Domain: $REST_API_CUSTOM_DOMAIN"
    fi
    echo "  WebSocket API ID: $WEBSOCKET_API_ID"
    echo "  WebSocket API Endpoint: $WEBSOCKET_API_ENDPOINT"
    if [ -n "$WEBSOCKET_API_CUSTOM_DOMAIN" ]; then
        echo "  WebSocket API Custom Domain: $WEBSOCKET_API_CUSTOM_DOMAIN"
    fi
    echo "  CloudFront Domain: $CLOUDFRONT_DOMAIN"
    echo "  Reports Domain: $REPORTS_DOMAIN"
    echo "  Reports Base URL: $REPORTS_BASE_URL"
    echo "  Backup Bucket: $BACKUP_BUCKET_NAME"
    echo "  Invoice Queue URL: $INVOICE_QUEUE_URL"
    echo
    
    # Check DynamoDB tables
    print_status "Checking DynamoDB tables..."
    local tables=("$STAFF_TABLE" "$USERS_TABLE" "$CONNECTIONS_TABLE" "$MESSAGES_TABLE" "$UNAVAILABLE_SLOTS_TABLE" "$APPOINTMENTS_TABLE" "$SERVICE_PRICES_TABLE" "$ORDERS_TABLE" "$ITEM_PRICES_TABLE" "$INQUIRIES_TABLE")
    for table in "${tables[@]}"; do
        check_dynamodb_table "$table" || ((errors++))
    done
    echo
    
    # Check Lambda functions
    print_status "Checking Lambda functions..."
    local functions=(
        "staff-authorizer" "staff-authorizer-optional"
        "api-get-prices" "api-get-users" "api-get-appointments" "api-create-appointment" "api-update-appointment"
        "api-get-unavailable-slots" "api-update-unavailable-slots"
        "api-get-orders" "api-create-order" "api-update-order" 
        "api-confirm-cash-payment" "api-create-payment-intent" "api-confirm-stripe-payment"
        "api-webhook-stripe-payment" "api-get-invoices" "api-generate-invoice"
        "api-get-inquiries" "api-create-inquiry"
        "api-get-report-upload-url" "api-get-analytics" "api-get-staff-roles"
        "api-notify" "api-take-user" "api-get-connections" "api-get-messages" "api-get-last-messages" "api-send-message"
        "ws-connect" "ws-disconnect" "ws-init" "ws-ping" "ws-staff-init"
        "sqs-process-invoice-queue"
    )
    
    for func in "${functions[@]}"; do
        check_lambda_function "$func" || ((errors++))
    done
    echo
    
    # Check API Gateways
    print_status "Checking API Gateways..."
    if [ -n "$REST_API_ID" ]; then
        check_api_gateway "$REST_API_ID" "rest" || ((errors++))
    else
        print_error "✗ REST API ID not found in stack outputs"
        ((errors++))
    fi
    
    if [ -n "$WEBSOCKET_API_ID" ]; then
        check_api_gateway "$WEBSOCKET_API_ID" "websocket" || ((errors++))
    else
        print_error "✗ WebSocket API ID not found in stack outputs"
        ((errors++))
    fi
    echo
    
    # Check custom domains and DNS configuration
    print_status "Checking custom domain configuration..."
    
    # Check ACM certificate (if configured)
    if [ -n "$API_CERTIFICATE_ARN" ]; then
        check_acm_certificate "$API_CERTIFICATE_ARN" "$API_DOMAIN_NAME" || ((errors++))
    fi
    
    # Check Route53 hosted zone (if configured)
    if [ -n "$HOSTED_ZONE_ID" ] && [ -n "$API_DOMAIN_NAME" ]; then
        check_hosted_zone "$HOSTED_ZONE_ID" "$API_DOMAIN_NAME" || ((errors++))
    fi
    
    # Check REST API custom domain
    check_custom_domain "$REST_API_CUSTOM_DOMAIN" "rest" || ((errors++))
    if [ -n "$REST_API_CUSTOM_DOMAIN" ]; then
        check_dns_resolution "$REST_API_CUSTOM_DOMAIN" "rest" || ((errors++))
    fi
    
    # Check WebSocket API custom domain  
    check_custom_domain "$WEBSOCKET_API_CUSTOM_DOMAIN" "websocket" || ((errors++))
    if [ -n "$WEBSOCKET_API_CUSTOM_DOMAIN" ]; then
        check_dns_resolution "$WEBSOCKET_API_CUSTOM_DOMAIN" "websocket" || ((errors++))
    fi
    echo
    
    # Check S3 bucket
    print_status "Checking S3 bucket..."
    check_s3_bucket "${S3_BUCKET_NAME}-${AWS_ACCOUNT_ID}-${ENVIRONMENT}" || ((errors++))
    echo
    
    # Check SQS queues
    print_status "Checking SQS queues..."
    check_sqs_queue "$INVOICE_QUEUE_URL" || ((errors++))
    
    # Check notification queues
    EMAIL_QUEUE_URL=$(get_stack_output "$STACK_NAME" "EmailNotificationQueueUrl")
    WEBSOCKET_QUEUE_URL=$(get_stack_output "$STACK_NAME" "WebSocketNotificationQueueUrl")
    FIREBASE_QUEUE_URL=$(get_stack_output "$STACK_NAME" "FirebaseNotificationQueueUrl")
    
    check_sqs_queue "$EMAIL_QUEUE_URL" || ((errors++))
    check_sqs_queue "$WEBSOCKET_QUEUE_URL" || ((errors++))
    
    # Only check Firebase queue if Firebase is enabled
    if [ "${ENABLE_FIREBASE_NOTIFICATIONS:-false}" == "true" ]; then
        check_sqs_queue "$FIREBASE_QUEUE_URL" || ((errors++))
    fi
    echo
    
    # Check Firebase notification system (optional)
    print_status "Checking Firebase notification system..."
    if [ "${ENABLE_FIREBASE_NOTIFICATIONS:-false}" == "true" ]; then
        if [ -n "$FIREBASE_QUEUE_URL" ]; then
            # Check Firebase processor lambda
            check_lambda_function "sqs-process-firebase-notification-queue" || ((errors++))
            
            # Check Firebase configuration
            if [ -n "$FIREBASE_PROJECT_ID" ]; then
                print_success "✓ Firebase project ID configured: $FIREBASE_PROJECT_ID"
            else
                print_error "✗ Firebase project ID required when Firebase is enabled"
                ((errors++))
            fi
            
            if [ -n "$FIREBASE_SERVICE_ACCOUNT_KEY" ]; then
                print_success "✓ Firebase service account key configured"
            else
                print_error "✗ Firebase service account key required when Firebase is enabled"
                ((errors++))
            fi
        else
            print_error "✗ Firebase notification queue not found (required when Firebase is enabled)"
            ((errors++))
        fi
    else
        print_status "✓ Firebase notifications are disabled (ENABLE_FIREBASE_NOTIFICATIONS=false)"
        if [ -n "$FIREBASE_QUEUE_URL" ]; then
            print_warning "⚠ Firebase queue exists but Firebase is disabled"
        fi
    fi
    echo
    
    # Check SES configuration
    print_status "Checking SES configuration..."
    if ./validate-ses.sh "$ENVIRONMENT" 2>/dev/null; then
        print_success "✓ SES configuration validated successfully"
    else
        print_warning "⚠ SES configuration validation failed"
        print_warning "Email sending may not work correctly"
        print_warning "Run './validate-ses.sh $ENVIRONMENT --setup' for setup instructions"
        ((errors++))
    fi
    echo
    
    # Test API endpoints (optional)
    print_status "Testing API endpoints..."
    local api_endpoint_to_test=""
    if [ -n "$REST_API_CUSTOM_DOMAIN" ]; then
        api_endpoint_to_test="https://$REST_API_CUSTOM_DOMAIN"
    elif [ -n "$REST_API_ENDPOINT" ]; then
        api_endpoint_to_test="$REST_API_ENDPOINT"
    fi
    
    if [ -n "$api_endpoint_to_test" ]; then
        # Test a simple endpoint that doesn't require authentication
        if curl -s --max-time 10 "$api_endpoint_to_test/get-staff-roles?email=test@example.com" > /dev/null; then
            print_success "✓ REST API endpoint is responding ($api_endpoint_to_test)"
        else
            print_warning "⚠ REST API endpoint test failed (may require authentication)"
        fi
    fi
    
    # Check backup system
    print_status "Checking backup system..."
    local backup_stack_name="auto-lab-backup-system-${ENVIRONMENT}"
    if aws cloudformation describe-stacks --stack-name "$backup_stack_name" --region $AWS_REGION &>/dev/null; then
        local backup_stack_status=$(aws cloudformation describe-stacks --stack-name "$backup_stack_name" --region $AWS_REGION --query 'Stacks[0].StackStatus' --output text)
        if [ "$backup_stack_status" = "CREATE_COMPLETE" ] || [ "$backup_stack_status" = "UPDATE_COMPLETE" ]; then
            print_success "✓ Backup system stack '$backup_stack_name' is in good state ($backup_stack_status)"
            
            # Check backup Lambda functions
            local backup_functions=("backup-restore" "api-backup-restore")
            for func in "${backup_functions[@]}"; do
                check_lambda_function "$func" || ((errors++))
            done
            
            # Check backup system outputs
            local backup_function_arn=$(get_stack_output "$backup_stack_name" "BackupLambdaFunctionArn")
            local manual_backup_arn=$(get_stack_output "$backup_stack_name" "ManualBackupLambdaFunctionArn")
            local backup_bucket=$(get_stack_output "$backup_stack_name" "BackupBucket")
            local backup_schedule_arn=$(get_stack_output "$backup_stack_name" "BackupScheduleRuleArn")
            
            if [ -n "$backup_function_arn" ]; then
                print_success "✓ Automated backup function deployed: $(basename "$backup_function_arn")"
            else
                print_error "✗ Automated backup function not found"
                ((errors++))
            fi
            
            if [ -n "$manual_backup_arn" ]; then
                print_success "✓ Manual backup function deployed: $(basename "$manual_backup_arn")"
            else
                print_error "✗ Manual backup function not found"
                ((errors++))
            fi
            
            if [ -n "$backup_bucket" ]; then
                # Check if backup bucket exists
                if aws s3 ls "s3://$backup_bucket" &>/dev/null; then
                    print_success "✓ Backup S3 bucket exists: $backup_bucket"
                else
                    print_error "✗ Backup S3 bucket not accessible: $backup_bucket"
                    ((errors++))
                fi
            else
                print_error "✗ Backup S3 bucket not found in outputs"
                ((errors++))
            fi
            
            if [ -n "$backup_schedule_arn" ]; then
                print_success "✓ Backup schedule configured: $(basename "$backup_schedule_arn")"
                # Show schedule details based on environment
                case $ENVIRONMENT in
                    "development"|"dev")
                        print_status "  Schedule: Daily at 4:00 AM UTC (dev environment)"
                        ;;
                    "production"|"prod")
                        print_status "  Schedule: Daily at 2:00 AM UTC (production environment)"
                        ;;
                esac
            else
                print_error "✗ Backup schedule not found"
                ((errors++))
            fi
            
        else
            print_error "✗ Backup system stack '$backup_stack_name' is in bad state ($backup_stack_status)"
            ((errors++))
        fi
    else
        print_warning "⚠ Backup system stack '$backup_stack_name' not found"
        print_warning "Backup functionality is not available"
        # Don't increment errors as backup system might be optional
    fi
    echo
    
    # Summary
    echo
    print_status "=== VALIDATION SUMMARY ==="
    if [ $errors -eq 0 ]; then
        print_success "🎉 All components validated successfully!"
        print_status "Your Auto Lab Solutions backend is ready for use."
        echo
        print_status "Next steps:"
        if [ -n "$REST_API_CUSTOM_DOMAIN" ]; then
            echo "  1. Update Auth0 configuration with: https://$REST_API_CUSTOM_DOMAIN"
        else
            echo "  1. Update Auth0 configuration with: $REST_API_ENDPOINT"
        fi
        echo "  2. Initialize DynamoDB tables with your data"
        echo "  3. Test your frontend integration"
        echo "  4. Test backup system: ./manage-backups.sh trigger-backup $ENVIRONMENT"
        echo ""
        print_status "Backend services available:"
        if [ -n "$REST_API_CUSTOM_DOMAIN" ]; then
            echo "  • REST API: https://$REST_API_CUSTOM_DOMAIN (custom domain)"
        else
            echo "  • REST API: $REST_API_ENDPOINT"
        fi
        if [ -n "$WEBSOCKET_API_CUSTOM_DOMAIN" ]; then
            echo "  • WebSocket API: wss://$WEBSOCKET_API_CUSTOM_DOMAIN (custom domain)"
        else
            echo "  • WebSocket API: $WEBSOCKET_API_ENDPOINT"
        fi
        if [ -n "$CLOUDFRONT_DOMAIN" ]; then
            echo "  • CloudFront CDN: https://$CLOUDFRONT_DOMAIN"
        fi
        echo "  • Async processing via SQS queues"
        echo "  • Automated backups (if backup system deployed)"
    else
        print_error "❌ Validation completed with $errors error(s)"
        print_status "Please check the errors above and re-run deployment if needed."
        echo ""
        print_status "Common fixes:"
        echo "  • Re-run deployment: ./deploy.sh $ENVIRONMENT"
        echo "  • Check AWS credentials and permissions"
    fi
    
    return $errors
}

# Main function
main() {
    local environment=""
    
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --env|-e)
                environment="$2"
                shift 2
                ;;
            --help|-h)
                echo "Usage: $0 [--env <environment>]"
                echo ""
                echo "Validate Auto Lab Solutions backend deployment"
                echo ""
                echo "Options:"
                echo "  --env, -e <env>     Specify environment (development/dev, production/prod)"
                echo "  --help, -h          Show this help message"
                echo ""
                echo "Examples:"
                echo "  $0 --env dev"
                echo "  $0 --env production"
                exit 0
                ;;
            *)
                echo "Unknown option: $1"
                echo "Use --help for usage information"
                exit 1
                ;;
        esac
    done
    
    # Load environment configuration
    if ! load_environment "$environment"; then
        exit 1
    fi
    
    print_status "Validating deployment for environment: $ENVIRONMENT"
    print_status "Stack name: $STACK_NAME"
    print_status "AWS Region: $AWS_REGION"
    echo ""
    
    validate_deployment
}

# Check if script is being run directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
