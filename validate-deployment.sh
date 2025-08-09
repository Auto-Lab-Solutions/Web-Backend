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
    INVOICE_QUEUE_URL=$(get_stack_output "$STACK_NAME" "InvoiceQueueUrl")
    
    print_status "Stack Outputs:"
    echo "  REST API ID: $REST_API_ID"
    echo "  REST API Endpoint: $REST_API_ENDPOINT"
    echo "  WebSocket API ID: $WEBSOCKET_API_ID"
    echo "  WebSocket API Endpoint: $WEBSOCKET_API_ENDPOINT"
    echo "  CloudFront Domain: $CLOUDFRONT_DOMAIN"
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
    if [ -n "$REST_API_ENDPOINT" ]; then
        # Test a simple endpoint that doesn't require authentication
        if curl -s --max-time 10 "$REST_API_ENDPOINT/get-staff-roles?email=test@example.com" > /dev/null; then
            print_success "✓ REST API endpoint is responding"
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
        echo "  1. Update Auth0 configuration with: $REST_API_ENDPOINT"
        echo "  2. Initialize DynamoDB tables with your data"
        echo "  3. Test your frontend integration"
        echo "  4. Test backup system: ./manage-backups.sh trigger-backup $ENVIRONMENT"
        echo ""
        print_status "Backend services available:"
        echo "  • REST API: $REST_API_ENDPOINT"
        echo "  • WebSocket API: $WEBSOCKET_API_ENDPOINT"
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
