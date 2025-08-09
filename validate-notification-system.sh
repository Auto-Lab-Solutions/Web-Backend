#!/bin/bash

# Notification System Validation Script
# This script validates that the asynchronous notification system is properly deployed

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source environment configuration
source "$SCRIPT_DIR/config/environments.sh"

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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
    echo "Usage: $0 [ENVIRONMENT]"
    echo ""
    echo "Validate Auto Lab Solutions notification system deployment"
    echo ""
    echo "Arguments:"
    echo "  ENVIRONMENT    Target environment (development|dev|production|prod)"
    echo ""
    echo "Examples:"
    echo "  $0              # Validate default environment"
    echo "  $0 dev          # Validate development environment"
    echo "  $0 production   # Validate production environment"
    echo ""
}

# Function to check SQS queues
check_sqs_queues() {
    print_status "Checking SQS queues..."
    
    local email_queue_name="sqs-email-notification-queue-${ENVIRONMENT}"
    local websocket_queue_name="sqs-websocket-notification-queue-${ENVIRONMENT}"
    local email_dlq_name="sqs-email-notification-dlq-${ENVIRONMENT}"
    local websocket_dlq_name="sqs-websocket-notification-dlq-${ENVIRONMENT}"
    
    # Check email notification queue
    if aws sqs get-queue-attributes --queue-url "https://sqs.${AWS_REGION}.amazonaws.com/${AWS_ACCOUNT_ID}/${email_queue_name}" --attribute-names All &>/dev/null; then
        print_success "Email notification queue exists: $email_queue_name"
    else
        print_error "Email notification queue not found: $email_queue_name"
        return 1
    fi
    
    # Check websocket notification queue
    if aws sqs get-queue-attributes --queue-url "https://sqs.${AWS_REGION}.amazonaws.com/${AWS_ACCOUNT_ID}/${websocket_queue_name}" --attribute-names All &>/dev/null; then
        print_success "WebSocket notification queue exists: $websocket_queue_name"
    else
        print_error "WebSocket notification queue not found: $websocket_queue_name"
        return 1
    fi
    
    # Check DLQs
    if aws sqs get-queue-attributes --queue-url "https://sqs.${AWS_REGION}.amazonaws.com/${AWS_ACCOUNT_ID}/${email_dlq_name}" --attribute-names All &>/dev/null; then
        print_success "Email notification DLQ exists: $email_dlq_name"
    else
        print_warning "Email notification DLQ not found: $email_dlq_name"
    fi
    
    if aws sqs get-queue-attributes --queue-url "https://sqs.${AWS_REGION}.amazonaws.com/${AWS_ACCOUNT_ID}/${websocket_dlq_name}" --attribute-names All &>/dev/null; then
        print_success "WebSocket notification DLQ exists: $websocket_dlq_name"
    else
        print_warning "WebSocket notification DLQ not found: $websocket_dlq_name"
    fi
}

# Function to check Lambda functions
check_lambda_functions() {
    print_status "Checking notification processor Lambda functions..."
    
    local email_processor="sqs-process-email-notification-queue-${ENVIRONMENT}"
    local websocket_processor="sqs-process-websocket-notification-queue-${ENVIRONMENT}"
    
    # Check email processor
    if aws lambda get-function --function-name "$email_processor" --region $AWS_REGION &>/dev/null; then
        local state=$(aws lambda get-function --function-name "$email_processor" --query 'Configuration.State' --output text --region $AWS_REGION)
        if [ "$state" = "Active" ]; then
            print_success "Email notification processor is active: $email_processor"
        else
            print_warning "Email notification processor state: $state"
        fi
    else
        print_error "Email notification processor not found: $email_processor"
        return 1
    fi
    
    # Check websocket processor
    if aws lambda get-function --function-name "$websocket_processor" --region $AWS_REGION &>/dev/null; then
        local state=$(aws lambda get-function --function-name "$websocket_processor" --query 'Configuration.State' --output text --region $AWS_REGION)
        if [ "$state" = "Active" ]; then
            print_success "WebSocket notification processor is active: $websocket_processor"
        else
            print_warning "WebSocket notification processor state: $state"
        fi
    else
        print_error "WebSocket notification processor not found: $websocket_processor"
        return 1
    fi
}

# Function to check environment variables in business lambdas
check_business_lambda_env_vars() {
    print_status "Checking business Lambda functions have notification queue URLs..."
    
    local business_lambdas=(
        "api-create-appointment"
        "api-update-appointment"
        "api-create-order"
        "api-update-order"
        "api-confirm-cash-payment"
        "api-confirm-stripe-payment"
        "api-create-inquiry"
        "api-take-user"
        "api-send-message"
        "api-notify"
        "api-webhook-stripe-payment"
    )
    
    local missing_env_vars=0
    
    for lambda_name in "${business_lambdas[@]}"; do
        local full_function_name="${lambda_name}-${ENVIRONMENT}"
        
        if aws lambda get-function --function-name "$full_function_name" --region $AWS_REGION &>/dev/null; then
            local env_vars=$(aws lambda get-function --function-name "$full_function_name" --query 'Configuration.Environment.Variables' --output json --region $AWS_REGION)
            
            if echo "$env_vars" | grep -q "EMAIL_NOTIFICATION_QUEUE_URL" && echo "$env_vars" | grep -q "WEBSOCKET_NOTIFICATION_QUEUE_URL"; then
                print_success "Environment variables configured: $lambda_name"
            else
                print_error "Missing notification queue environment variables: $lambda_name"
                ((missing_env_vars++))
            fi
        else
            print_warning "Lambda function not found: $full_function_name"
        fi
    done
    
    if [ $missing_env_vars -gt 0 ]; then
        print_error "$missing_env_vars Lambda functions missing notification environment variables"
        return 1
    fi
}

# Function to check CloudFormation stacks
check_cloudformation_stacks() {
    print_status "Checking CloudFormation stacks..."
    
    # Check main stack
    if aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region $AWS_REGION &>/dev/null; then
        local main_status=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --query 'Stacks[0].StackStatus' --output text --region $AWS_REGION)
        print_success "Main stack status: $main_status"
    else
        print_error "Main stack not found: $STACK_NAME"
        return 1
    fi
    
    # Check notification queue stack (nested stack)
    print_status "Notification queue components deployed via nested stack in main stack"
}

# Function to get queue URLs from CloudFormation outputs
get_queue_urls() {
    print_status "Getting queue URLs from CloudFormation outputs..."
    
    local email_queue_url=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --query 'Stacks[0].Outputs[?OutputKey==`EmailNotificationQueueUrl`].OutputValue' \
        --output text \
        --region $AWS_REGION 2>/dev/null)
    
    local websocket_queue_url=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --query 'Stacks[0].Outputs[?OutputKey==`WebSocketNotificationQueueUrl`].OutputValue' \
        --output text \
        --region $AWS_REGION 2>/dev/null)
    
    if [ -n "$email_queue_url" ] && [ "$email_queue_url" != "None" ]; then
        print_success "Email notification queue URL: $email_queue_url"
    else
        print_error "Email notification queue URL not found in stack outputs"
        return 1
    fi
    
    if [ -n "$websocket_queue_url" ] && [ "$websocket_queue_url" != "None" ]; then
        print_success "WebSocket notification queue URL: $websocket_queue_url"
    else
        print_error "WebSocket notification queue URL not found in stack outputs"
        return 1
    fi
}

# Function to get AWS account ID
get_aws_account_id() {
    AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query 'Account' --output text)
    if [ -z "$AWS_ACCOUNT_ID" ]; then
        print_error "Failed to get AWS account ID"
        return 1
    fi
}

# Main validation function
main() {
    # Handle help flag
    if [[ "$1" == "--help" || "$1" == "-h" ]]; then
        show_usage
        exit 0
    fi
    
    # Load environment configuration
    if ! load_environment "$1"; then
        exit 1
    fi
    
    print_status "Validating notification system for environment: $ENVIRONMENT"
    print_status "AWS Region: $AWS_REGION"
    print_status "Stack Name: $STACK_NAME"
    echo ""
    
    # Get AWS account ID
    if ! get_aws_account_id; then
        exit 1
    fi
    
    print_status "AWS Account ID: $AWS_ACCOUNT_ID"
    echo ""
    
    local validation_errors=0
    
    # Run validation checks
    echo "========================================"
    print_status "Starting notification system validation..."
    echo ""
    
    if ! check_cloudformation_stacks; then
        ((validation_errors++))
    fi
    echo ""
    
    if ! get_queue_urls; then
        ((validation_errors++))
    fi
    echo ""
    
    if ! check_sqs_queues; then
        ((validation_errors++))
    fi
    echo ""
    
    if ! check_lambda_functions; then
        ((validation_errors++))
    fi
    echo ""
    
    if ! check_business_lambda_env_vars; then
        ((validation_errors++))
    fi
    echo ""
    
    echo "========================================"
    
    if [ $validation_errors -eq 0 ]; then
        print_success "✅ All notification system components validated successfully!"
        echo ""
        print_status "Notification System Components:"
        echo "  ✅ SQS Email Notification Queue"
        echo "  ✅ SQS WebSocket Notification Queue"
        echo "  ✅ Email Notification Processor Lambda"
        echo "  ✅ WebSocket Notification Processor Lambda"
        echo "  ✅ Business Lambda Environment Variables"
        echo "  ✅ CloudFormation Stack Outputs"
        echo ""
        print_success "Your asynchronous notification system is ready! 🚀"
    else
        print_error "❌ Validation failed with $validation_errors error(s)"
        echo ""
        print_error "Please fix the above issues and run the validation again."
        echo "You may need to run: ./deploy.sh $ENVIRONMENT"
        exit 1
    fi
}

# Check if script is being run directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
