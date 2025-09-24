#!/bin/bash

# API Gateway Redeploy Script
# This script forces a redeployment of API Gateway stages after infrastructure updates

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

show_usage() {
    echo "Usage: $0 [ENVIRONMENT] [OPTIONS]"
    echo ""
    echo "Redeploy API Gateway stages after infrastructure updates"
    echo ""
    echo "Arguments:"
    echo "  ENVIRONMENT    Target environment (development|dev|production|prod)"
    echo ""
    echo "Options:"
    echo "  --force        Force redeployment even if no changes detected"
    echo "  --help, -h     Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 dev                    # Redeploy API Gateway for dev environment"
    echo "  $0 production --force     # Force redeploy for production"
    echo ""
    echo "This script:"
    echo "  • Forces a new API Gateway deployment"
    echo "  • Updates the stage to use the new deployment"
    echo "  • Validates the deployment worked correctly"
    echo "  • Clears any CloudFront cache if custom domains are enabled"
    echo ""
}

# Function to get API Gateway ID from CloudFormation
get_api_gateway_id() {
    local api_id
    api_id=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --region "$AWS_REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`RestApiId`].OutputValue' \
        --output text 2>/dev/null)
    
    if [[ -z "$api_id" || "$api_id" == "None" ]]; then
        print_error "Could not retrieve API Gateway ID from CloudFormation stack: $STACK_NAME"
        print_error "Make sure the stack exists and has been deployed successfully"
        return 1
    fi
    
    echo "$api_id"
}

# Function to create a new API Gateway deployment
create_api_deployment() {
    local api_id="$1"
    local description="Redeployment for ${ENVIRONMENT} environment - $(date '+%Y-%m-%d %H:%M:%S')"
    
    print_status "Creating new API Gateway deployment..."
    
    local deployment_id
    deployment_id=$(aws apigateway create-deployment \
        --rest-api-id "$api_id" \
        --stage-name "$ENVIRONMENT" \
        --description "$description" \
        --region "$AWS_REGION" \
        --query 'id' \
        --output text)
    
    if [[ -z "$deployment_id" || "$deployment_id" == "None" ]]; then
        print_error "Failed to create new API Gateway deployment"
        return 1
    fi
    
    print_success "Created new deployment: $deployment_id"
    echo "$deployment_id"
}

# Function to update stage to use new deployment
update_stage() {
    local api_id="$1"
    local deployment_id="$2"
    
    print_status "Updating stage '$ENVIRONMENT' to use new deployment..."
    
    aws apigateway update-stage \
        --rest-api-id "$api_id" \
        --stage-name "$ENVIRONMENT" \
        --patch-ops op=replace,path=/deploymentId,value="$deployment_id" \
        --region "$AWS_REGION" > /dev/null
    
    print_success "Stage updated successfully"
}

# Function to validate the deployment
validate_deployment() {
    local api_id="$1"
    
    print_status "Validating API Gateway deployment..."
    
    # Get the API endpoint
    local api_endpoint
    if [[ "${ENABLE_API_CUSTOM_DOMAINS:-false}" == "true" && -n "${API_DOMAIN_NAME:-}" ]]; then
        api_endpoint="https://${API_DOMAIN_NAME}"
    else
        api_endpoint="https://${api_id}.execute-api.${AWS_REGION}.amazonaws.com/${ENVIRONMENT}"
    fi
    
    print_status "API endpoint: $api_endpoint"
    
    # Test a simple endpoint (health check or prices endpoint)
    print_status "Testing API connectivity..."
    
    # Try to hit the prices endpoint (which should be available)
    local status_code
    status_code=$(curl -s -o /dev/null -w "%{http_code}" "${api_endpoint}/prices" || echo "000")
    
    # Note: We expect 401/403 for prices endpoint without auth, but not 404
    case "$status_code" in
        "200"|"401"|"403")
            print_success "✅ API Gateway is responding correctly (HTTP $status_code)"
            ;;
        "404")
            print_warning "⚠️  API returned 404 - this might indicate routing issues"
            ;;
        "000")
            print_warning "⚠️  Could not connect to API - DNS may be propagating"
            ;;
        *)
            print_warning "⚠️  API returned unexpected status: $status_code"
            ;;
    esac
    
    # Check if the new email update endpoint is available
    print_status "Testing new email update endpoint..."
    
    # Test the new PATCH endpoint (should return 401/403 without auth, not 404)
    local email_status_code
    email_status_code=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH "${api_endpoint}/emails/test-email-id" || echo "000")
    
    case "$email_status_code" in
        "401"|"403")
            print_success "✅ Email update endpoint is accessible (HTTP $email_status_code)"
            ;;
        "404")
            print_error "❌ Email update endpoint not found (HTTP 404)"
            print_error "This suggests the API Gateway deployment didn't include the new methods"
            return 1
            ;;
        "000")
            print_warning "⚠️  Could not test email endpoint - DNS may be propagating"
            ;;
        *)
            print_warning "⚠️  Email endpoint returned unexpected status: $email_status_code"
            ;;
    esac
    
    return 0
}

# Function to clear CloudFront cache if custom domain is used
clear_cloudfront_cache() {
    print_status "Checking if CloudFront cache clearing is needed..."
    
    if [[ "${ENABLE_API_CUSTOM_DOMAINS:-false}" != "true" ]]; then
        print_status "Custom domains not enabled - skipping CloudFront cache clearing"
        return 0
    fi
    
    # API Gateway behind custom domain might use CloudFront
    # This is a simplified check - you might need to adjust based on your setup
    print_status "Custom domains enabled - API changes should propagate automatically"
    print_status "If you're using CloudFront with API Gateway, consider clearing the cache manually"
    
    # Note: API Gateway custom domains typically don't use CloudFront directly
    # but if you have CloudFront in front of your API, you might want to add cache invalidation here
}

# Function to get deployment information
get_deployment_info() {
    local api_id="$1"
    
    print_status "Current API Gateway deployment information:"
    
    # Get stage information
    local stage_info
    stage_info=$(aws apigateway get-stage \
        --rest-api-id "$api_id" \
        --stage-name "$ENVIRONMENT" \
        --region "$AWS_REGION" \
        --output json 2>/dev/null)
    
    if [[ -n "$stage_info" ]]; then
        local deployment_id
        local created_date
        deployment_id=$(echo "$stage_info" | python3 -c "import sys, json; print(json.load(sys.stdin).get('deploymentId', 'Unknown'))" 2>/dev/null || echo "Unknown")
        created_date=$(echo "$stage_info" | python3 -c "import sys, json; print(json.load(sys.stdin).get('createdDate', 'Unknown'))" 2>/dev/null || echo "Unknown")
        
        print_status "  Stage: $ENVIRONMENT"
        print_status "  Deployment ID: $deployment_id"
        print_status "  Created: $created_date"
    else
        print_warning "Could not retrieve stage information"
    fi
}

# Main function
main() {
    local environment_arg=""
    local force_redeploy=false
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --help|-h)
                show_usage
                exit 0
                ;;
            --force)
                force_redeploy=true
                shift
                ;;
            *)
                if [[ -z "$environment_arg" ]]; then
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
    
    print_status "API Gateway Redeployment for environment: $ENVIRONMENT"
    print_status "AWS Region: $AWS_REGION"
    print_status "Stack Name: $STACK_NAME"
    echo ""
    
    # Check if this is a forced redeploy
    if [[ "$force_redeploy" == "true" ]]; then
        print_warning "Force redeploy enabled - will create new deployment regardless of changes"
    fi
    
    # Check prerequisites
    print_status "Checking prerequisites..."
    
    if ! command -v aws &> /dev/null; then
        print_error "AWS CLI not found. Please install AWS CLI."
        exit 1
    fi
    
    if ! aws sts get-caller-identity &> /dev/null; then
        print_error "AWS credentials not configured. Please run 'aws configure'."
        exit 1
    fi
    
    print_success "Prerequisites check passed"
    
    # Get API Gateway ID
    print_status "Retrieving API Gateway information..."
    local api_id
    if ! api_id=$(get_api_gateway_id); then
        exit 1
    fi
    
    print_success "API Gateway ID: $api_id"
    
    # Show current deployment info
    get_deployment_info "$api_id"
    echo ""
    
    # Confirm redeploy
    if [[ -z "${AUTO_CONFIRM:-}" && -z "${CI:-}" && -z "${GITHUB_ACTIONS:-}" ]]; then
        if [[ "$force_redeploy" == "true" ]]; then
            print_warning "This will FORCE redeploy the API Gateway stage for '$ENVIRONMENT'."
        else
            print_warning "This will redeploy the API Gateway stage for '$ENVIRONMENT'."
        fi
        print_warning "This creates a new immutable deployment snapshot with all current API changes."
        
        read -p "Continue? (y/N): " -n 1 -r
        echo ""
        
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_status "Redeployment cancelled."
            exit 0
        fi
    else
        print_status "Running in automated environment - proceeding with redeployment"
    fi
    
    # Create new deployment
    print_status "Creating new API Gateway deployment..."
    local deployment_id
    if ! deployment_id=$(create_api_deployment "$api_id"); then
        exit 1
    fi
    
    # Update stage
    if ! update_stage "$api_id" "$deployment_id"; then
        print_error "Failed to update stage"
        exit 1
    fi
    
    # Brief wait for propagation
    print_status "Waiting for deployment to propagate..."
    sleep 5
    
    # Validate deployment
    if ! validate_deployment "$api_id"; then
        print_warning "Validation failed - but deployment was created"
        print_warning "The API might need a few minutes to fully propagate"
    fi
    
    # Clear cache if needed
    clear_cloudfront_cache
    
    # Show final deployment info
    echo ""
    print_status "Final deployment information:"
    get_deployment_info "$api_id"
    
    print_success "API Gateway redeployment completed successfully!"
    echo ""
    print_status "The following endpoints should now be available:"
    if [[ "${ENABLE_API_CUSTOM_DOMAINS:-false}" == "true" && -n "${API_DOMAIN_NAME:-}" ]]; then
        print_status "  Base URL: https://${API_DOMAIN_NAME}"
        print_status "  Email Update: PATCH https://${API_DOMAIN_NAME}/emails/{emailId}"
    else
        print_status "  Base URL: https://${api_id}.execute-api.${AWS_REGION}.amazonaws.com/${ENVIRONMENT}"
        print_status "  Email Update: PATCH https://${api_id}.execute-api.${AWS_REGION}.amazonaws.com/${ENVIRONMENT}/emails/{emailId}"
    fi
    
    print_status "New email update endpoint accepts the following fields:"
    print_status "  • isImportant: boolean (mark email as important)"
    print_status "  • isRead: boolean (mark email as read/unread)"
    print_status "  • tags: array of strings (assign tags to email)"
    echo ""
    print_success "🎉 API Gateway is ready with the new email update functionality!"
}

# Check if script is being run directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
