#!/bin/bash

# Upload CloudFormation Templates Script
# This script uploads all CloudFormation templates to S3

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

# Function to upload CloudFormation templates
upload_templates() {
    print_status "Uploading CloudFormation templates to S3 bucket: $CLOUDFORMATION_BUCKET"
    
    # Upload all CloudFormation templates
    aws s3 cp infrastructure/dynamodb-tables.yaml s3://$CLOUDFORMATION_BUCKET/dynamodb-tables.yaml --region $AWS_REGION
    aws s3 cp infrastructure/invoice-queue.yaml s3://$CLOUDFORMATION_BUCKET/invoice-queue.yaml --region $AWS_REGION
    aws s3 cp infrastructure/notification-queue.yaml s3://$CLOUDFORMATION_BUCKET/notification-queue.yaml --region $AWS_REGION
    aws s3 cp infrastructure/lambda-functions.yaml s3://$CLOUDFORMATION_BUCKET/lambda-functions.yaml --region $AWS_REGION
    aws s3 cp infrastructure/api-gateway.yaml s3://$CLOUDFORMATION_BUCKET/api-gateway.yaml --region $AWS_REGION
    aws s3 cp infrastructure/websocket-api.yaml s3://$CLOUDFORMATION_BUCKET/websocket-api.yaml --region $AWS_REGION
    aws s3 cp infrastructure/s3-cloudfront.yaml s3://$CLOUDFORMATION_BUCKET/s3-cloudfront.yaml --region $AWS_REGION
    aws s3 cp infrastructure/frontend-website.yaml s3://$CLOUDFORMATION_BUCKET/frontend-website.yaml --region $AWS_REGION
    aws s3 cp infrastructure/backup-system.yaml s3://$CLOUDFORMATION_BUCKET/backup-system.yaml --region $AWS_REGION
    aws s3 cp infrastructure/ses-bounce-complaint-system.yaml s3://$CLOUDFORMATION_BUCKET/ses-bounce-complaint-system.yaml --region $AWS_REGION
    
    print_success "All CloudFormation templates uploaded successfully!"
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
                echo "Upload CloudFormation templates to S3"
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
    
    print_status "Uploading templates for environment: $ENVIRONMENT"
    print_status "CloudFormation bucket: $CLOUDFORMATION_BUCKET"
    print_status "AWS Region: $AWS_REGION"
    echo ""
    
    upload_templates
    print_success "Upload completed successfully!"
}

# Check if script is being run directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
