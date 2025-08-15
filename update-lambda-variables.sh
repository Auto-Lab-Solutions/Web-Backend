#!/bin/bash

# Update Lambda Environment Variables Script
# This script updates WebSocket endpoints and notification queue URLs in Lambda functions
# after the infrastructure has been deployed

# Source environment configuration
source "$(dirname "$0")/config/environments.sh"

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

# Function to show usage
show_usage() {
    echo "Usage: $0 [OPTIONS] [ENVIRONMENT]"
    echo ""
    echo "Update Lambda environment variables with WebSocket endpoints and notification queue URLs"
    echo ""
    echo "Options:"
    echo "  --env, -e <env>     Specify environment (development/dev, production/prod)"
    echo "  --dry-run          Show what would be updated without making changes"
    echo "  --verbose, -v      Show verbose output for debugging"
    echo "  --list-functions   List expected Lambda functions and their status"
    echo "  --websocket-only   Update only WebSocket endpoints"
    echo "  --queues-only      Update only notification queue URLs"
    echo "  --verify           Verify current environment variables"
    echo "  --help, -h         Show this help message"
    echo ""
    echo "Arguments:"
    echo "  ENVIRONMENT        Target environment (development|dev|production|prod)"
    echo ""
    echo "Examples:"
    echo "  $0 dev              # Update all environment variables for development"
    echo "  $0 --env production # Update all environment variables for production"
    echo "  $0 --websocket-only dev    # Update only WebSocket endpoints for development"
    echo "  $0 --queues-only prod      # Update only notification queues for production"
    echo "  $0 --dry-run dev    # Show what would be updated for development"
    echo ""
    echo "  --help, -h         Show this help message"
    echo ""
    echo "Arguments:"
    echo "  ENVIRONMENT        Target environment (development|dev|production|prod)"
    echo ""
    echo "Examples:"
    echo "  $0 dev              # Update WebSocket endpoints for development"
    echo "  $0 --env production # Update WebSocket endpoints for production"
    echo "  $0 --dry-run dev    # Show what would be updated for development"
    echo ""
}

# Function to get stack output value
get_stack_output() {
    local stack_name=$1
    local output_key=$2
    
    set +e
    local result=$(aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --query "Stacks[0].Outputs[?OutputKey=='$output_key'].OutputValue" \
        --output text \
        --region $AWS_REGION 2>/dev/null)
    local exit_code=$?
    set -e
    
    if [[ $exit_code -eq 0 && -n "$result" && "$result" != "None" ]]; then
        echo "$result"
    else
        echo ""
    fi
}

# Function to check if lambda function exists
lambda_exists() {
    local function_name=$1
    set +e
    aws lambda get-function --function-name "$function_name" --region $AWS_REGION >/dev/null 2>&1
    local result=$?
    set -e
    return $result
}

# Function to check prerequisites
check_prerequisites() {
    local environment=$1
    
    print_status "Checking prerequisites..."
    
    # Check if jq is available
    if ! command -v jq &> /dev/null; then
        print_error "jq is required but not installed. Please install jq to continue."
        return 1
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        print_error "AWS credentials not configured. Please run 'aws configure'."
        return 1
    fi
    
    # Check if CloudFormation stack exists
    if ! aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region $AWS_REGION >/dev/null 2>&1; then
        print_error "CloudFormation stack '$STACK_NAME' does not exist!"
        print_error "Please deploy the infrastructure first using:"
        print_error "  ./deploy.sh $environment"
        return 1
    fi
    
    print_success "Prerequisites check passed"
    return 0
}

# Function to get current lambda environment variables
get_lambda_env() {
    local function_name=$1
    set +e
    local result=$(aws lambda get-function-configuration \
        --function-name "$function_name" \
        --query 'Environment.Variables' \
        --output json \
        --region $AWS_REGION 2>/dev/null)
    local exit_code=$?
    set -e
    
    if [[ $exit_code -eq 0 && -n "$result" ]]; then
        echo "$result"
    else
        echo "{}"
    fi
}

# Function to update Lambda environment variables with WebSocket endpoints and notification queues
update_lambda_environment_vars() {
    local dry_run=$1
    local verbose=${2:-false}
    local websocket_only=${3:-false}
    local queues_only=${4:-false}
    
    local websocket_endpoint=""
    local email_queue_url=""
    local websocket_queue_url=""
    local firebase_queue_url=""
    
    # Get WebSocket API endpoint if needed
    if [[ "$queues_only" != "true" ]]; then
        print_status "Getting WebSocket API endpoint from CloudFormation stack..."
        websocket_endpoint=$(get_stack_output "$STACK_NAME" "WebSocketApiEndpoint")
        
        if [[ -z "$websocket_endpoint" || "$websocket_endpoint" == "None" ]]; then
            print_error "WebSocket API endpoint not found in stack outputs!"
            return 1
        fi
        
        print_status "WebSocket API Endpoint: $websocket_endpoint"
        # Convert wss:// to https:// for WEBSOCKET_ENDPOINT_URL environment variable
        websocket_endpoint="${websocket_endpoint//wss:\/\//https:\/\/}"
        print_status "HTTPS Endpoint for environment variable: $websocket_endpoint"
    fi
    
    # Get notification queue URLs if needed
    if [[ "$websocket_only" != "true" ]]; then
        print_status "Getting notification queue URLs from CloudFormation stack..."
        
        email_queue_url=$(get_stack_output "$STACK_NAME" "EmailNotificationQueueUrl")
        websocket_queue_url=$(get_stack_output "$STACK_NAME" "WebSocketNotificationQueueUrl")
        firebase_queue_url=$(get_stack_output "$STACK_NAME" "FirebaseNotificationQueueUrl")
        
        print_status "📦 Retrieved queue URLs:"
        print_status "  Email: ${email_queue_url:-'Not found'}"
        print_status "  WebSocket: ${websocket_queue_url:-'Not found'}"
        print_status "  Firebase: ${firebase_queue_url:-'Not found or disabled'}"
    fi
    
    echo ""
    
    # Define all Lambda functions that need environment variable updates
    local lambda_functions=(
        "api-notify-${ENVIRONMENT}"
        "api-send-message-${ENVIRONMENT}"
        "api-take-user-${ENVIRONMENT}"
        "api-webhook-stripe-payment-${ENVIRONMENT}"
        "api-confirm-cash-payment-${ENVIRONMENT}"
        "api-confirm-stripe-payment-${ENVIRONMENT}"
        "api-create-appointment-${ENVIRONMENT}"
        "api-create-order-${ENVIRONMENT}"
        "api-update-appointment-${ENVIRONMENT}"
        "api-update-order-${ENVIRONMENT}"
        "api-create-inquiry-${ENVIRONMENT}"
        "api-generate-invoice-${ENVIRONMENT}"
    )
    
    local updated_count=0
    local error_count=0
    local skipped_count=0
    
    for func in "${lambda_functions[@]}"; do
        print_status "Processing $func..."
        
        # Check if function exists
        if ! lambda_exists "$func"; then
            print_warning "Function $func does not exist, skipping..."
            skipped_count=$((skipped_count + 1))
            continue
        fi
        
        # Get current environment variables
        local current_env=$(get_lambda_env "$func")
        if [[ "$current_env" == "{}" ]]; then
            print_warning "Could not retrieve environment variables for $func, skipping..."
            skipped_count=$((skipped_count + 1))
            continue
        fi
        
        if [[ "$verbose" == "true" ]]; then
            print_status "Current environment variables for $func:"
            echo "$current_env" | jq .
        fi
        
        # Build the jq update expression based on what we're updating
        local jq_expression="."
        local update_description=""
        
        if [[ "$queues_only" != "true" && -n "$websocket_endpoint" ]]; then
            jq_expression="$jq_expression | .WEBSOCKET_ENDPOINT_URL = \$websocket_endpoint"
            update_description="WebSocket endpoint"
        fi
        
        if [[ "$websocket_only" != "true" ]]; then
            if [[ -n "$email_queue_url" ]]; then
                jq_expression="$jq_expression | .EMAIL_NOTIFICATION_QUEUE_URL = \$email_url"
                update_description="${update_description:+$update_description, }email queue"
            fi
            if [[ -n "$websocket_queue_url" ]]; then
                jq_expression="$jq_expression | .WEBSOCKET_NOTIFICATION_QUEUE_URL = \$websocket_url"
                update_description="${update_description:+$update_description, }WebSocket queue"
            fi
            if [[ -n "$firebase_queue_url" ]]; then
                jq_expression="$jq_expression | .FIREBASE_NOTIFICATION_QUEUE_URL = \$firebase_url"
                update_description="${update_description:+$update_description, }Firebase queue"
            fi
        fi
        
        # Update the environment variables JSON
        set +e
        local updated_env=$(echo "$current_env" | jq \
            --arg websocket_endpoint "$websocket_endpoint" \
            --arg email_url "$email_queue_url" \
            --arg websocket_url "$websocket_queue_url" \
            --arg firebase_url "$firebase_queue_url" \
            "$jq_expression" 2>/dev/null)
        local jq_exit_code=$?
        set -e
        
        # Validate the JSON is properly formatted
        if [[ $jq_exit_code -ne 0 ]] || ! echo "$updated_env" | jq . > /dev/null 2>&1; then
            print_error "Invalid JSON generated for $func environment variables"
            error_count=$((error_count + 1))
            continue
        fi
        
        # Compact the JSON to minimize size and avoid formatting issues
        set +e
        updated_env=$(echo "$updated_env" | jq -c . 2>/dev/null)
        local compact_exit_code=$?
        set -e
        
        if [[ $compact_exit_code -ne 0 ]]; then
            print_error "Failed to compact JSON for $func environment variables"
            error_count=$((error_count + 1))
            continue
        fi
        
        # Check if the complete environment structure is within AWS Lambda limits
        local complete_env_structure="{\"Variables\": $updated_env}"
        local env_size=$(echo "$complete_env_structure" | wc -c)
        if [[ $env_size -gt 4096 ]]; then
            print_error "Environment variables too large for $func ($env_size bytes, max 4096)"
            error_count=$((error_count + 1))
            continue
        fi
        
        if [[ "$dry_run" == "true" ]]; then
            print_status "[DRY RUN] Would update $func with: $update_description"
            if [[ "$verbose" == "true" ]]; then
                print_status "Updated environment variables would be:"
                echo "$updated_env" | jq .
            fi
        else
            # Update the Lambda function
            print_status "Updating $func with: $update_description"
            
            if [[ "$verbose" == "true" ]]; then
                print_status "Updated environment variables:"
                echo "$updated_env" | jq .
            fi
            
            # Write environment variables to a temporary file to handle complex JSON
            local temp_env_file=$(mktemp)
            echo "{\"Variables\": $updated_env}" > "$temp_env_file"
            
            local update_output
            set +e
            update_output=$(aws lambda update-function-configuration \
                --function-name "$func" \
                --environment file://"$temp_env_file" \
                --region $AWS_REGION 2>&1)
            local aws_exit_code=$?
            set -e
            
            if [[ $aws_exit_code -eq 0 ]]; then
                print_success "✅ Updated $func"
                updated_count=$((updated_count + 1))
            else
                print_error "Failed to update $func"
                print_error "AWS CLI Error: $update_output"
                error_count=$((error_count + 1))
            fi
            
            # Clean up temporary file
            rm -f "$temp_env_file"
            
            # Add a small delay to avoid rate limiting
            sleep 0.5
        fi
    done
    
    echo ""
    if [[ "$dry_run" == "true" ]]; then
        print_status "Dry run completed. ${#lambda_functions[@]} functions would be processed."
        print_status "To actually update the functions, run without --dry-run"
    else
        print_success "🎉 Lambda environment variable update completed!"
        print_status "Functions processed: ${#lambda_functions[@]}"
        print_status "Functions updated: $updated_count"
        if [[ $skipped_count -gt 0 ]]; then
            print_warning "Functions skipped: $skipped_count"
        fi
        if [[ $error_count -gt 0 ]]; then
            print_warning "Functions with errors: $error_count"
            return 1
        fi
        
        if [[ $updated_count -eq 0 && $skipped_count -eq ${#lambda_functions[@]} ]]; then
            print_warning "No functions were updated (all were skipped)."
            print_warning "This may indicate that the Lambda functions don't exist yet."
        else
            print_success "🔗 Successfully updated $updated_count function(s)!"
            if [[ "$queues_only" != "true" ]]; then
                print_status "All functions now have WEBSOCKET_ENDPOINT_URL=$websocket_endpoint"
            fi
            if [[ "$websocket_only" != "true" ]]; then
                print_status "All functions now have notification queue URLs configured"
            fi
        fi
    fi
}

# Function to verify WebSocket endpoints
verify_websocket_endpoints() {
    print_status "Verifying WebSocket endpoints in Lambda functions..."
    
    local websocket_endpoint=$(get_stack_output "$STACK_NAME" "WebSocketApiEndpoint")
    
    if [[ -z "$websocket_endpoint" || "$websocket_endpoint" == "None" ]]; then
        print_error "WebSocket API endpoint not found in stack outputs!"
        return 1
    fi
    
    # Convert wss:// to https:// for comparison with environment variables
    local https_endpoint="${websocket_endpoint//wss:\/\//https:\/\/}"
    
    local websocket_functions=(
        "api-notify-${ENVIRONMENT}"
        "api-send-message-${ENVIRONMENT}"
        "api-take-user-${ENVIRONMENT}"
        "api-webhook-stripe-payment-${ENVIRONMENT}"
        "api-confirm-cash-payment-${ENVIRONMENT}"
        "api-confirm-stripe-payment-${ENVIRONMENT}"
        "api-create-appointment-${ENVIRONMENT}"
        "api-create-order-${ENVIRONMENT}"
        "api-update-appointment-${ENVIRONMENT}"
        "api-update-order-${ENVIRONMENT}"
        "api-create-inquiry-${ENVIRONMENT}"
    )
    
    local verified_count=0
    local mismatch_count=0
    
    for func in "${websocket_functions[@]}"; do
        if lambda_exists "$func"; then
            local current_env=$(get_lambda_env "$func")
            local current_endpoint=$(echo "$current_env" | jq -r '.WEBSOCKET_ENDPOINT_URL // "NOT_SET"')
            
            if [[ "$current_endpoint" == "$https_endpoint" ]]; then
                print_success "$func: ✓ Correct endpoint"
                verified_count=$((verified_count + 1))
            else
                print_error "$func: ✗ Endpoint mismatch"
                print_error "  Expected: $https_endpoint"
                print_error "  Current:  $current_endpoint"
                mismatch_count=$((mismatch_count + 1))
            fi
        fi
    done
    
    echo ""
    print_status "Verification completed:"
    print_status "  Correct endpoints: $verified_count"
    if [[ $mismatch_count -gt 0 ]]; then
        print_warning "  Mismatched endpoints: $mismatch_count"
        return 1
    fi
    
    return 0
}

# Function to list expected Lambda functions
list_expected_functions() {
    print_status "Expected Lambda functions for environment '$ENVIRONMENT':"
    local lambda_functions=(
        "api-notify-${ENVIRONMENT}"
        "api-send-message-${ENVIRONMENT}"
        "api-take-user-${ENVIRONMENT}"
        "api-webhook-stripe-payment-${ENVIRONMENT}"
        "api-confirm-cash-payment-${ENVIRONMENT}"
        "api-confirm-stripe-payment-${ENVIRONMENT}"
        "api-create-appointment-${ENVIRONMENT}"
        "api-create-order-${ENVIRONMENT}"
        "api-update-appointment-${ENVIRONMENT}"
        "api-update-order-${ENVIRONMENT}"
        "api-create-inquiry-${ENVIRONMENT}"
        "api-generate-invoice-${ENVIRONMENT}"
    )
    
    for func in "${lambda_functions[@]}"; do
        if lambda_exists "$func"; then
            print_success "  ✓ $func (exists)"
        else
            print_error "  ✗ $func (missing)"
        fi
    done
    echo ""
}

# Main function
main() {
    local environment=""
    local dry_run=false
    local verify_only=false
    local verbose=false
    local list_functions=false
    local websocket_only=false
    local queues_only=false
    
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --env|-e)
                environment="$2"
                shift 2
                ;;
            --dry-run)
                dry_run=true
                shift
                ;;
            --verbose|-v)
                verbose=true
                shift
                ;;
            --list-functions)
                list_functions=true
                shift
                ;;
            --websocket-only)
                websocket_only=true
                shift
                ;;
            --queues-only)
                queues_only=true
                shift
                ;;
            --verify)
                verify_only=true
                shift
                ;;
            --help|-h)
                show_usage
                exit 0
                ;;
            -*)
                print_error "Unknown option: $1"
                echo "Use --help for usage information"
                exit 1
                ;;
            *)
                # Positional argument (environment)
                if [[ -z "$environment" ]]; then
                    environment="$1"
                else
                    print_error "Multiple environments specified: '$environment' and '$1'"
                    exit 1
                fi
                shift
                ;;
        esac
    done
    
    # Validate mutually exclusive options
    if [[ "$websocket_only" == "true" && "$queues_only" == "true" ]]; then
        print_error "Options --websocket-only and --queues-only are mutually exclusive"
        exit 1
    fi
    
    # Load environment configuration
    if ! load_environment "$environment"; then
        exit 1
    fi
    
    local update_description="WebSocket endpoints and notification queues"
    if [[ "$websocket_only" == "true" ]]; then
        update_description="WebSocket endpoints only"
    elif [[ "$queues_only" == "true" ]]; then
        update_description="notification queues only"
    fi
    
    print_status "Updating Lambda environment variables for environment: $ENVIRONMENT"
    print_status "Update scope: $update_description"
    print_status "Stack name: $STACK_NAME"
    print_status "AWS Region: $AWS_REGION"
    echo ""
    
    if [[ "$list_functions" == "true" ]]; then
        list_expected_functions
        exit 0
    fi
    
    # Check prerequisites
    if ! check_prerequisites "$environment"; then
        exit 1
    fi
    echo ""
    
    if [[ "$verify_only" == "true" ]]; then
        verify_websocket_endpoints
    else
        update_lambda_environment_vars "$dry_run" "$verbose" "$websocket_only" "$queues_only"
    fi
}

# Check if script is being run directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
