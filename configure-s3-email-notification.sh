#!/bin/bash

# Auto Lab Solutions - S3 Email Notification Configuration Script
# This script configures S3 bucket notifications to trigger the email processor Lambda function

set -e

# Load environment configuration
source config/environments.sh

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
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

# Function to show usage
show_usage() {
    echo "Usage: $0 [ENVIRONMENT] [OPTIONS]"
    echo ""
    echo "Configure S3 bucket notifications for email processing Lambda trigger"
    echo ""
    echo "Arguments:"
    echo "  ENVIRONMENT    Target environment (development|dev|production|prod)"
    echo ""
    echo "Options:"
    echo "  --remove       Remove S3 bucket notification configuration"
    echo "  --dry-run      Show what would be configured without making changes"
    echo "  --help, -h     Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                    # Configure for default environment"
    echo "  $0 dev               # Configure for development environment"
    echo "  $0 production        # Configure for production environment"
    echo "  $0 dev --dry-run     # Show configuration without applying changes"
    echo "  $0 dev --remove      # Remove notification configuration"
    echo ""
    echo "Prerequisites:"
    echo "  • AWS CLI configured with appropriate permissions"
    echo "  • Email processor Lambda function must exist"
    echo "  • S3 bucket must exist"
    echo "  • CloudFormation stack must be deployed"
    echo ""
}

# Function to get CloudFormation stack output
get_stack_output() {
    local stack_name="$1"
    local output_key="$2"
    
    aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --region "$AWS_REGION" \
        --query "Stacks[0].Outputs[?OutputKey=='$output_key'].OutputValue" \
        --output text 2>/dev/null || echo ""
}

# Function to check if Lambda function exists
check_lambda_function() {
    local function_name="$1"
    
    if aws lambda get-function --function-name "$function_name" --region "$AWS_REGION" >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Function to get Lambda function ARN
get_lambda_arn() {
    local function_name="$1"
    
    aws lambda get-function \
        --function-name "$function_name" \
        --region "$AWS_REGION" \
        --query 'Configuration.FunctionArn' \
        --output text 2>/dev/null || echo ""
}

# Function to check if S3 bucket exists
check_s3_bucket() {
    local bucket_name="$1"
    
    if aws s3 ls "s3://$bucket_name" --region "$AWS_REGION" >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Function to add Lambda permission for S3 trigger
add_lambda_permission() {
    local function_name="$1"
    local bucket_name="$2"
    local statement_id="$3"
    
    print_status "Adding Lambda permission for S3 trigger..."
    
    # Check if permission already exists
    if aws lambda get-policy \
        --function-name "$function_name" \
        --region "$AWS_REGION" \
        --output text 2>/dev/null | grep -q "$statement_id"; then
        print_status "Lambda permission already exists: $statement_id"
        return 0
    fi
    
    # Add permission
    aws lambda add-permission \
        --function-name "$function_name" \
        --statement-id "$statement_id" \
        --action "lambda:InvokeFunction" \
        --principal "s3.amazonaws.com" \
        --source-arn "arn:aws:s3:::$bucket_name" \
        --region "$AWS_REGION" >/dev/null
    
    print_success "✅ Lambda permission added: $statement_id"
}

# Function to remove Lambda permission for S3 trigger
remove_lambda_permission() {
    local function_name="$1"
    local statement_id="$2"
    
    print_status "Removing Lambda permission for S3 trigger..."
    
    if aws lambda remove-permission \
        --function-name "$function_name" \
        --statement-id "$statement_id" \
        --region "$AWS_REGION" >/dev/null 2>&1; then
        print_success "✅ Lambda permission removed: $statement_id"
    else
        print_warning "⚠️ Lambda permission not found or already removed: $statement_id"
    fi
}

# Function to configure S3 bucket notification
configure_s3_notification() {
    local bucket_name="$1"
    local lambda_arn="$2"
    local prefix="$3"
    
    print_status "Configuring S3 bucket notification..."
    
    # Create notification configuration JSON
    local notification_config=$(cat <<EOF
{
    "LambdaConfigurations": [
        {
            "Id": "EmailProcessorNotification",
            "LambdaFunctionArn": "$lambda_arn",
            "Events": ["s3:ObjectCreated:*"],
            "Filter": {
                "Key": {
                    "FilterRules": [
                        {
                            "Name": "prefix",
                            "Value": "$prefix"
                        }
                    ]
                }
            }
        }
    ]
}
EOF
)
    
    # Apply notification configuration
    echo "$notification_config" | aws s3api put-bucket-notification-configuration \
        --bucket "$bucket_name" \
        --notification-configuration file:///dev/stdin \
        --region "$AWS_REGION"
    
    print_success "✅ S3 bucket notification configured for prefix: $prefix"
}

# Function to remove S3 bucket notification
remove_s3_notification() {
    local bucket_name="$1"
    
    print_status "Removing S3 bucket notification configuration..."
    
    # Remove all notifications by setting empty configuration
    aws s3api put-bucket-notification-configuration \
        --bucket "$bucket_name" \
        --notification-configuration '{}' \
        --region "$AWS_REGION"
    
    print_success "✅ S3 bucket notification configuration removed"
}

# Function to show current S3 notification configuration
show_s3_notification() {
    local bucket_name="$1"
    
    print_status "Current S3 bucket notification configuration:"
    
    local config=$(aws s3api get-bucket-notification-configuration \
        --bucket "$bucket_name" \
        --region "$AWS_REGION" \
        --output json 2>/dev/null || echo '{}')
    
    if [[ "$config" == "{}" ]]; then
        print_warning "⚠️ No notification configuration found"
    else
        echo "$config" | python3 -m json.tool 2>/dev/null || echo "$config"
    fi
}

# Parse arguments
environment_arg=""
DRY_RUN=false
REMOVE_CONFIG=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --help|-h)
            show_usage
            exit 0
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --remove)
            REMOVE_CONFIG=true
            shift
            ;;
        *)
            if [ -z "$environment_arg" ]; then
                environment_arg="$1"
            else
                print_error "Unknown argument: $1"
                show_usage
                exit 1
            fi
            shift
            ;;
    esac
done

# Load environment configuration
if ! load_environment "$environment_arg"; then
    exit 1
fi

print_status "S3 Email Notification Configuration"
print_status "Environment: $ENVIRONMENT"
print_status "AWS Region: $AWS_REGION"

if [[ "$DRY_RUN" == "true" ]]; then
    print_warning "DRY RUN MODE - No changes will be made"
fi

if [[ "$REMOVE_CONFIG" == "true" ]]; then
    print_warning "REMOVE MODE - Configuration will be removed"
fi

echo ""

# Configuration variables
EMAIL_PROCESSOR_FUNCTION="email-processor-$ENVIRONMENT"
EMAIL_STORAGE_BUCKET="${EMAIL_STORAGE_BUCKET:-auto-lab-email-storage}"
S3_PREFIX="emails/$ENVIRONMENT/"
PERMISSION_STATEMENT_ID="EmailProcessorS3Trigger-$ENVIRONMENT"

print_status "Configuration Details:"
print_status "  Lambda Function: $EMAIL_PROCESSOR_FUNCTION"
print_status "  S3 Bucket: $EMAIL_STORAGE_BUCKET"
print_status "  S3 Prefix: $S3_PREFIX"
print_status "  Permission ID: $PERMISSION_STATEMENT_ID"

echo ""

# Validate prerequisites
print_status "Validating prerequisites..."

# Check if Lambda function exists
if ! check_lambda_function "$EMAIL_PROCESSOR_FUNCTION"; then
    print_error "❌ Email processor Lambda function not found: $EMAIL_PROCESSOR_FUNCTION"
    print_error "Please ensure the CloudFormation stack is deployed and Lambda function exists"
    exit 1
fi

print_success "✅ Lambda function exists: $EMAIL_PROCESSOR_FUNCTION"

# Get Lambda function ARN
LAMBDA_ARN=$(get_lambda_arn "$EMAIL_PROCESSOR_FUNCTION")
if [[ -z "$LAMBDA_ARN" ]]; then
    print_error "❌ Could not get Lambda function ARN"
    exit 1
fi

print_status "Lambda ARN: $LAMBDA_ARN"

# Check if S3 bucket exists
if ! check_s3_bucket "$EMAIL_STORAGE_BUCKET"; then
    print_error "❌ S3 bucket not found: $EMAIL_STORAGE_BUCKET"
    print_error "Please ensure the CloudFormation stack is deployed and S3 bucket exists"
    exit 1
fi

print_success "✅ S3 bucket exists: $EMAIL_STORAGE_BUCKET"

echo ""

# Show current configuration
show_s3_notification "$EMAIL_STORAGE_BUCKET"

echo ""

# Execute configuration based on mode
if [[ "$REMOVE_CONFIG" == "true" ]]; then
    # Remove configuration mode
    print_status "=== REMOVING S3 NOTIFICATION CONFIGURATION ==="
    
    if [[ "$DRY_RUN" == "true" ]]; then
        print_warning "DRY RUN: Would remove S3 notification configuration"
        print_warning "DRY RUN: Would remove Lambda permission: $PERMISSION_STATEMENT_ID"
    else
        remove_s3_notification "$EMAIL_STORAGE_BUCKET"
        remove_lambda_permission "$EMAIL_PROCESSOR_FUNCTION" "$PERMISSION_STATEMENT_ID"
        
        print_success "🎉 S3 notification configuration removed successfully!"
        print_status "Email processing via S3 triggers is now disabled"
    fi
    
else
    # Configure mode
    print_status "=== CONFIGURING S3 NOTIFICATION ==="
    
    if [[ "$DRY_RUN" == "true" ]]; then
        print_warning "DRY RUN: Would add Lambda permission for S3 trigger"
        print_warning "DRY RUN: Would configure S3 bucket notification:"
        print_warning "  Bucket: $EMAIL_STORAGE_BUCKET"
        print_warning "  Lambda: $LAMBDA_ARN"
        print_warning "  Prefix: $S3_PREFIX"
        print_warning "  Events: s3:ObjectCreated:*"
    else
        # Add Lambda permission
        add_lambda_permission "$EMAIL_PROCESSOR_FUNCTION" "$EMAIL_STORAGE_BUCKET" "$PERMISSION_STATEMENT_ID"
        
        # Configure S3 notification
        configure_s3_notification "$EMAIL_STORAGE_BUCKET" "$LAMBDA_ARN" "$S3_PREFIX"
        
        print_success "🎉 S3 notification configuration completed successfully!"
        print_success "📧 Email processing flow:"
        print_success "  1. Email sent to mail@domain → SES"
        print_success "  2. SES stores email in S3: $EMAIL_STORAGE_BUCKET/$S3_PREFIX"
        print_success "  3. S3 ObjectCreated event triggers Lambda: $EMAIL_PROCESSOR_FUNCTION"
        print_success "  4. Lambda processes email and stores metadata in DynamoDB"
        
        echo ""
        print_status "Verification:"
        print_status "  1. Send test email to verify end-to-end processing"
        print_status "  2. Check Lambda logs: aws logs tail /aws/lambda/$EMAIL_PROCESSOR_FUNCTION --follow"
        print_status "  3. Check S3 objects: aws s3 ls s3://$EMAIL_STORAGE_BUCKET/$S3_PREFIX"
        print_status "  4. Run validation: ./validate-email-processing.sh $ENVIRONMENT"
    fi
fi

echo ""

# Show final configuration
if [[ "$DRY_RUN" != "true" ]]; then
    print_status "Final S3 bucket notification configuration:"
    show_s3_notification "$EMAIL_STORAGE_BUCKET"
fi

print_status "Configuration completed!"
