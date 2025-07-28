#!/bin/bash

# Update WebSocket Endpoints Script
# This script updates WebSocket endpoint environment variables in Lambda functions
# after the WebSocket stack has been deployed

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
    echo "Update WebSocket endpoint environment variables in Lambda functions"
    echo ""
    echo "Options:"
    echo "  --env, -e <env>     Specify environment (development/dev, production/prod)"
    echo "  --dry-run          Show what would be updated without making changes"
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
    
    aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --query "Stacks[0].Outputs[?OutputKey=='$output_key'].OutputValue" \
        --output text \
        --region $AWS_REGION 2>/dev/null || echo ""
}

# Function to check if lambda function exists
lambda_exists() {
    local function_name=$1
    aws lambda get-function --function-name "$function_name" --region $AWS_REGION >/dev/null 2>&1
}

# Function to get current lambda environment variables
get_lambda_env() {
    local function_name=$1
    aws lambda get-function-configuration \
        --function-name "$function_name" \
        --query 'Environment.Variables' \
        --output json \
        --region $AWS_REGION 2>/dev/null || echo "{}"
}

# Function to update Lambda environment variables
update_lambda_websocket_env() {
    local dry_run=$1
    
    print_status "Getting WebSocket API endpoint from CloudFormation stack..."
    
    # Get WebSocket API endpoint from stack outputs
    local websocket_endpoint=$(get_stack_output "$STACK_NAME" "WebSocketApiEndpoint")
    
    if [[ -z "$websocket_endpoint" || "$websocket_endpoint" == "None" ]]; then
        print_error "WebSocket API endpoint not found in stack outputs!"
        print_error "Make sure the WebSocket stack has been deployed successfully."
        return 1
    fi
    
    print_status "WebSocket API Endpoint: $websocket_endpoint"
    echo ""
    
    # Define all Lambda functions that need WebSocket endpoint
    # These are functions that use wsgw_utils.py and need WEBSOCKET_ENDPOINT_URL
    local websocket_functions=(
        "api-notify-${ENVIRONMENT}"
        "api-send-message-${ENVIRONMENT}"
        "api-take-user-${ENVIRONMENT}"
        "ws-connect-${ENVIRONMENT}"
        "ws-disconnect-${ENVIRONMENT}"
        "ws-init-${ENVIRONMENT}"
        "ws-ping-${ENVIRONMENT}"
        "ws-staff-init-${ENVIRONMENT}"
    )
    
    local updated_count=0
    local error_count=0
    
    for func in "${websocket_functions[@]}"; do
        print_status "Processing $func..."
        
        # Check if function exists
        if ! lambda_exists "$func"; then
            print_warning "Function $func does not exist, skipping..."
            continue
        fi
        
        # Get current environment variables
        local current_env=$(get_lambda_env "$func")
        if [[ "$current_env" == "{}" ]]; then
            print_warning "Could not retrieve environment variables for $func, skipping..."
            continue
        fi
        
        # Update the environment variables JSON to include/update WEBSOCKET_ENDPOINT_URL
        local updated_env=$(echo "$current_env" | jq --arg endpoint "$websocket_endpoint" '. + {WEBSOCKET_ENDPOINT_URL: $endpoint}')
        
        if [[ "$dry_run" == "true" ]]; then
            print_status "[DRY RUN] Would update $func with WEBSOCKET_ENDPOINT_URL=$websocket_endpoint"
        else
            # Update the Lambda function
            if aws lambda update-function-configuration \
                --function-name "$func" \
                --environment "Variables=$updated_env" \
                --region $AWS_REGION > /dev/null 2>&1; then
                print_success "Updated $func"
                ((updated_count++))
            else
                print_error "Failed to update $func"
                ((error_count++))
            fi
        fi
    done
    
    echo ""
    if [[ "$dry_run" == "true" ]]; then
        print_status "Dry run completed. ${#websocket_functions[@]} functions would be processed."
    else
        print_success "WebSocket endpoint update completed!"
        print_status "Functions updated: $updated_count"
        if [[ $error_count -gt 0 ]]; then
            print_warning "Functions with errors: $error_count"
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
    
    local websocket_functions=(
        "api-notify-${ENVIRONMENT}"
        "api-send-message-${ENVIRONMENT}"
        "api-take-user-${ENVIRONMENT}"
        "ws-connect-${ENVIRONMENT}"
        "ws-disconnect-${ENVIRONMENT}"
        "ws-init-${ENVIRONMENT}"
        "ws-ping-${ENVIRONMENT}"
        "ws-staff-init-${ENVIRONMENT}"
    )
    
    local verified_count=0
    local mismatch_count=0
    
    for func in "${websocket_functions[@]}"; do
        if lambda_exists "$func"; then
            local current_env=$(get_lambda_env "$func")
            local current_endpoint=$(echo "$current_env" | jq -r '.WEBSOCKET_ENDPOINT_URL // "NOT_SET"')
            
            if [[ "$current_endpoint" == "$websocket_endpoint" ]]; then
                print_success "$func: ✓ Correct endpoint"
                ((verified_count++))
            else
                print_error "$func: ✗ Endpoint mismatch"
                print_error "  Expected: $websocket_endpoint"
                print_error "  Current:  $current_endpoint"
                ((mismatch_count++))
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

# Main function
main() {
    local environment=""
    local dry_run=false
    local verify_only=false
    
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
    
    # Load environment configuration
    if ! load_environment "$environment"; then
        exit 1
    fi
    
    print_status "Updating WebSocket endpoints for environment: $ENVIRONMENT"    
    print_status "Stack name: $STACK_NAME"
    print_status "AWS Region: $AWS_REGION"
    echo ""
    
    # Check if jq is available
    if ! command -v jq &> /dev/null; then
        print_error "jq is required but not installed. Please install jq to continue."
        exit 1
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        print_error "AWS credentials not configured. Please run 'aws configure'."
        exit 1
    fi
    
    if [[ "$verify_only" == "true" ]]; then
        verify_websocket_endpoints
    else
        update_lambda_websocket_env "$dry_run"
    fi
}

# Check if script is being run directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
