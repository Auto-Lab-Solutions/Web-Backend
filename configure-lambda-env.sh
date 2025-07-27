#!/bin/bash

# Configure Lambda Environment Variables Script
# This script updates Lambda function environment variables after deployment

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
        --region $AWS_REGION
}

# Function to update Lambda environment variables
update_lambda_env() {
    print_status "Updating Lambda function environment variables..."
    
    # Get API Gateway endpoints
    REST_API_ENDPOINT=$(get_stack_output "$STACK_NAME" "RestApiEndpoint")
    WEBSOCKET_API_ENDPOINT=$(get_stack_output "$STACK_NAME" "WebSocketApiEndpoint")
    
    print_status "REST API Endpoint: $REST_API_ENDPOINT"
    print_status "WebSocket API Endpoint: $WEBSOCKET_API_ENDPOINT"
    
    # Update WebSocket-related Lambda functions with the WebSocket API endpoint
    local ws_functions=(
        "ws-connect-${ENVIRONMENT}"
        "ws-disconnect-${ENVIRONMENT}"
        "ws-init-${ENVIRONMENT}"
        "ws-ping-${ENVIRONMENT}"
        "ws-staff-init-${ENVIRONMENT}"
        "api-notify-${ENVIRONMENT}"
        "api-send-message-${ENVIRONMENT}"
    )
    
    for func in "${ws_functions[@]}"; do
        print_status "Updating $func environment variables..."
        
        aws lambda update-function-configuration \
            --function-name "$func" \
            --environment "Variables={WEBSOCKET_API_ENDPOINT=$WEBSOCKET_API_ENDPOINT}" \
            --region $AWS_REGION > /dev/null
        
        print_success "Updated $func"
    done
    
    print_success "All Lambda environment variables updated successfully!"
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
                echo "Configure Lambda environment variables after deployment"
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
    
    print_status "Configuring Lambda environment variables for: $ENVIRONMENT"
    print_status "Stack name: $STACK_NAME"
    print_status "AWS Region: $AWS_REGION"
    echo ""
    
    update_lambda_env
    print_success "Configuration completed successfully!"
}

# Check if script is being run directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
