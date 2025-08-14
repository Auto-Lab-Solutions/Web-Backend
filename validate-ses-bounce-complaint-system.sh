#!/bin/bash

# Auto Lab Solutions - SES Bounce and Complaint System Validation Script
# This script validates that the SES bounce and complaint handling system is properly configured

set -e  # Exit on any error

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

# Function to check CloudFormation stack
check_stack() {
    local stack_name="ses-bounce-complaint-system-${ENVIRONMENT}"
    
    print_status "Checking CloudFormation stack: $stack_name"
    
    if aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --region "$AWS_REGION" &>/dev/null; then
        
        local stack_status=$(aws cloudformation describe-stacks \
            --stack-name "$stack_name" \
            --region "$AWS_REGION" \
            --query "Stacks[0].StackStatus" \
            --output text)
        
        if [ "$stack_status" = "CREATE_COMPLETE" ] || [ "$stack_status" = "UPDATE_COMPLETE" ]; then
            print_success "Stack exists and is in good state: $stack_status"
            return 0
        else
            print_warning "Stack exists but in unexpected state: $stack_status"
            return 1
        fi
    else
        print_error "Stack does not exist or is not accessible"
        return 1
    fi
}

# Function to check DynamoDB tables
check_dynamodb_tables() {
    print_status "Checking DynamoDB tables..."
    
    local tables=("EmailSuppression-${ENVIRONMENT}" "EmailAnalytics-${ENVIRONMENT}")
    local errors=0
    
    for table in "${tables[@]}"; do
        if aws dynamodb describe-table \
            --table-name "$table" \
            --region "$AWS_REGION" &>/dev/null; then
            
            local table_status=$(aws dynamodb describe-table \
                --table-name "$table" \
                --region "$AWS_REGION" \
                --query "Table.TableStatus" \
                --output text)
            
            if [ "$table_status" = "ACTIVE" ]; then
                print_success "Table $table is active"
            else
                print_warning "Table $table status: $table_status"
                ((errors++))
            fi
        else
            print_error "Table $table does not exist or is not accessible"
            ((errors++))
        fi
    done
    
    return $errors
}

# Function to check Lambda functions
check_lambda_functions() {
    print_status "Checking Lambda functions..."
    
    local functions=(
        "ses-bounce-handler-${ENVIRONMENT}"
        "ses-complaint-handler-${ENVIRONMENT}"
        "ses-delivery-handler-${ENVIRONMENT}"
        "api-email-suppression-manager-${ENVIRONMENT}"
    )
    local errors=0
    
    for func in "${functions[@]}"; do
        if aws lambda get-function \
            --function-name "$func" \
            --region "$AWS_REGION" &>/dev/null; then
            
            local func_state=$(aws lambda get-function \
                --function-name "$func" \
                --region "$AWS_REGION" \
                --query "Configuration.State" \
                --output text)
            
            if [ "$func_state" = "Active" ]; then
                print_success "Function $func is active"
            else
                print_warning "Function $func state: $func_state"
                ((errors++))
            fi
        else
            print_error "Function $func does not exist or is not accessible"
            ((errors++))
        fi
    done
    
    return $errors
}

# Function to check SNS topics
check_sns_topics() {
    print_status "Checking SNS topics..."
    
    local topics=(
        "ses-bounce-notifications-${ENVIRONMENT}"
        "ses-complaint-notifications-${ENVIRONMENT}"
        "ses-delivery-notifications-${ENVIRONMENT}"
    )
    local errors=0
    
    for topic in "${topics[@]}"; do
        if aws sns list-topics \
            --region "$AWS_REGION" \
            --query "Topics[?contains(TopicArn, '$topic')].TopicArn" \
            --output text | grep -q "$topic"; then
            print_success "Topic $topic exists"
        else
            print_error "Topic $topic does not exist"
            ((errors++))
        fi
    done
    
    return $errors
}

# Function to check SES notification configuration
check_ses_notifications() {
    print_status "Checking SES notification configuration..."
    
    local domain="${FROM_EMAIL##*@}"
    local errors=0
    
    # Check domain notifications
    print_status "Checking domain notifications for: $domain"
    
    local domain_config
    domain_config=$(aws ses get-identity-notification-attributes \
        --identities "$domain" \
        --region "$SES_REGION" \
        --output json 2>/dev/null)
    
    if [ $? -eq 0 ]; then
        # Check bounce notifications
        local bounce_enabled=$(echo "$domain_config" | \
            python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('NotificationAttributes', {}).get('$domain', {}).get('BounceTopic', 'None'))")
        
        if [ "$bounce_enabled" != "None" ] && [ "$bounce_enabled" != "null" ]; then
            print_success "Bounce notifications configured for domain"
        else
            print_error "Bounce notifications not configured for domain"
            ((errors++))
        fi
        
        # Check complaint notifications
        local complaint_enabled=$(echo "$domain_config" | \
            python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('NotificationAttributes', {}).get('$domain', {}).get('ComplaintTopic', 'None'))")
        
        if [ "$complaint_enabled" != "None" ] && [ "$complaint_enabled" != "null" ]; then
            print_success "Complaint notifications configured for domain"
        else
            print_error "Complaint notifications not configured for domain"
            ((errors++))
        fi
    else
        print_error "Could not retrieve domain notification configuration"
        ((errors++))
    fi
    
    # Check email notifications if different from domain
    if [ "$FROM_EMAIL" != "$domain" ]; then
        print_status "Checking email notifications for: $FROM_EMAIL"
        
        local email_config
        email_config=$(aws ses get-identity-notification-attributes \
            --identities "$FROM_EMAIL" \
            --region "$SES_REGION" \
            --output json 2>/dev/null)
        
        if [ $? -eq 0 ]; then
            print_success "Email notifications configured"
        else
            print_warning "Could not retrieve email notification configuration"
        fi
    fi
    
    return $errors
}

# Function to check email suppression integration
check_suppression_integration() {
    print_status "Checking email suppression integration..."
    
    # Check if email utils has suppression table environment variable
    if grep -q "EMAIL_SUPPRESSION_TABLE_NAME" lambda/common_lib/email_utils.py; then
        print_success "Email utils has suppression integration"
    else
        print_error "Email utils missing suppression integration"
        return 1
    fi
    
    # Check if Lambda functions have the environment variable
    local stack_name="auto-lab-lambda-functions-${ENVIRONMENT}"
    
    if aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --region "$AWS_REGION" \
        --query "Stacks[0].Parameters[?ParameterKey=='EmailSuppressionTableName'].ParameterValue" \
        --output text | grep -q "EmailSuppression"; then
        print_success "Lambda functions have suppression table parameter"
    else
        print_warning "Lambda functions may not have suppression table parameter"
    fi
    
    return 0
}

# Function to perform end-to-end test
perform_e2e_test() {
    print_status "Performing end-to-end test..."
    
    # Test with SES simulator
    print_status "Testing bounce simulation..."
    
    local test_result
    test_result=$(aws ses send-email \
        --source "$FROM_EMAIL" \
        --destination "ToAddresses=bounce@simulator.amazonses.com" \
        --message "Subject={Data='E2E Test - Bounce',Charset=UTF-8},Body={Text={Data='This is an end-to-end test for bounce handling.',Charset=UTF-8}}" \
        --region "$SES_REGION" \
        --output json 2>/dev/null)
    
    if [ $? -eq 0 ]; then
        local message_id=$(echo "$test_result" | python3 -c "import sys, json; print(json.load(sys.stdin)['MessageId'])")
        print_success "Test email sent successfully. MessageId: $message_id"
        print_status "Check CloudWatch logs in a few minutes for bounce processing"
    else
        print_error "Failed to send test email"
        return 1
    fi
    
    return 0
}

# Function to show recommendations
show_recommendations() {
    print_status "Recommendations:"
    echo ""
    
    print_status "1. Monitor CloudWatch logs for Lambda functions"
    print_status "2. Set up CloudWatch alarms for bounce/complaint rates"
    print_status "3. Review DynamoDB tables periodically"
    print_status "4. Test with SES simulator addresses regularly"
    print_status "5. Keep bounce rate < 5% and complaint rate < 0.1%"
    echo ""
    
    print_status "Quick Commands:"
    print_status "  # Check bounce handler logs"
    print_status "  aws logs tail /aws/lambda/ses-bounce-handler-${ENVIRONMENT} --follow"
    print_status ""
    print_status "  # Check suppression list"
    print_status "  aws dynamodb scan --table-name EmailSuppression-${ENVIRONMENT} --select COUNT"
    print_status ""
    print_status "  # Check SES statistics"
    print_status "  aws ses get-send-statistics --region ${SES_REGION}"
}

# Main validation function
main() {
    local environment=""
    local e2e_test=false
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --e2e-test)
                e2e_test=true
                shift
                ;;
            --help|-h)
                echo "Usage: $0 [ENVIRONMENT] [--e2e-test]"
                echo "Validate SES bounce and complaint handling system"
                exit 0
                ;;
            -*)
                print_error "Unknown option: $1"
                exit 1
                ;;
            *)
                environment="$1"
                shift
                ;;
        esac
    done
    
    # Set environment
    if [ -n "$environment" ]; then
        case "$environment" in
            development|dev)
                ENVIRONMENT="development"
                ;;
            production|prod)
                ENVIRONMENT="production"
                ;;
            *)
                print_error "Invalid environment: $environment"
                exit 1
                ;;
        esac
    fi
    
    if [ -z "$ENVIRONMENT" ]; then
        ENVIRONMENT="production"
    fi
    
    # Load environment configuration
    load_environment "$ENVIRONMENT"
    
    print_status "Validating SES bounce and complaint handling system for environment: $ENVIRONMENT"
    print_status "Configuration:"
    print_status "  FROM_EMAIL: $FROM_EMAIL"
    print_status "  SES_REGION: $SES_REGION"
    print_status "  AWS_REGION: $AWS_REGION"
    echo ""
    
    local total_errors=0
    
    # Run validations
    print_status "=== Validation Results ==="
    echo ""
    
    if ! check_stack; then
        ((total_errors++))
    fi
    echo ""
    
    if ! check_dynamodb_tables; then
        ((total_errors++))
    fi
    echo ""
    
    if ! check_lambda_functions; then
        ((total_errors++))
    fi
    echo ""
    
    if ! check_sns_topics; then
        ((total_errors++))
    fi
    echo ""
    
    if ! check_ses_notifications; then
        ((total_errors++))
    fi
    echo ""
    
    if ! check_suppression_integration; then
        ((total_errors++))
    fi
    echo ""
    
    # Optional end-to-end test
    if [ "$e2e_test" = true ]; then
        if ! perform_e2e_test; then
            ((total_errors++))
        fi
        echo ""
    fi
    
    # Show final results
    print_status "=== Validation Summary ==="
    echo ""
    
    if [ $total_errors -eq 0 ]; then
        print_success "✓ All validations passed! SES bounce and complaint handling system is properly configured."
        if [ "$e2e_test" = false ]; then
            print_status "Run with --e2e-test to perform end-to-end testing"
        fi
    else
        print_error "✗ Validation failed with $total_errors errors"
        print_error "Please review the errors above and fix them before proceeding"
        
        if [ $total_errors -le 2 ]; then
            print_status "You can try running the configuration script:"
            print_status "  ./setup-ses-notifications.sh $ENVIRONMENT --configure"
        fi
    fi
    
    echo ""
    show_recommendations
    
    exit $total_errors
}

# Run main function
main "$@"
