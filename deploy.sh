#!/bin/bash

# Auto Lab Solutions - Backend Deployment Script
# This script deploys the entire backend architecture from zero

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

# Function to show usage
show_usage() {
    echo "Usage: $0 [ENVIRONMENT]"
    echo ""
    echo "Deploy Auto Lab Solutions backend infrastructure"
    echo ""
    echo "Arguments:"
    echo "  ENVIRONMENT    Target environment (development|dev|production|prod)"
    echo ""
    echo "Examples:"
    echo "  $0              # Deploy to default environment"
    echo "  $0 dev          # Deploy to development"
    echo "  $0 production   # Deploy to production"
    echo ""
    echo "Environment Configuration:"
    echo "  Use 'config/environments.sh show' to view current settings"
    echo "  Use 'config/environments.sh set dev' to change default"
    echo ""
}

# Check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    if ! command -v aws &> /dev/null; then
        print_error "AWS CLI not found. Please install AWS CLI."
        exit 1
    fi
    
    if ! command -v python3 &> /dev/null; then
        print_error "Python3 not found. Please install Python3."
        exit 1
    fi
    
    if ! command -v zip &> /dev/null; then
        print_error "zip not found. Please install zip utility."
        exit 1
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        print_error "AWS credentials not configured. Please run 'aws configure'."
        exit 1
    fi
    
    # Check Stripe configuration
    if [[ "$STRIPE_SECRET_KEY" == *"REPLACE_WITH_YOUR"* ]] || [[ -z "$STRIPE_SECRET_KEY" ]]; then
        print_error "Stripe Secret Key not configured."
        print_error "For development: export STRIPE_SECRET_KEY_DEV='your_test_secret_key'"
        print_error "For production: export STRIPE_SECRET_KEY_PROD='your_live_secret_key'"
        exit 1
    fi
    
    if [[ "$STRIPE_WEBHOOK_SECRET" == *"REPLACE_WITH_YOUR"* ]] || [[ -z "$STRIPE_WEBHOOK_SECRET" ]]; then
        print_error "Stripe Webhook Secret not configured."
        print_error "For development: export STRIPE_WEBHOOK_SECRET_DEV='your_test_webhook_secret'"
        print_error "For production: export STRIPE_WEBHOOK_SECRET_PROD='your_live_webhook_secret'"
        exit 1
    fi
    
    print_success "Prerequisites check passed"
}

# Create S3 bucket for CloudFormation templates if it doesn't exist
create_cf_bucket() {
    print_status "Creating CloudFormation templates bucket..."
    
    if aws s3 ls "s3://$CLOUDFORMATION_BUCKET" 2>&1 | grep -q 'NoSuchBucket'; then
        aws s3 mb s3://$CLOUDFORMATION_BUCKET --region $AWS_REGION
        print_success "Created CloudFormation bucket: $CLOUDFORMATION_BUCKET"
    else
        print_status "CloudFormation bucket already exists: $CLOUDFORMATION_BUCKET"
    fi
}

# Package and upload Lambda functions
package_lambdas() {
    print_status "Packaging Lambda functions..."
    
    mkdir -p dist/lambda
    
    # Get list of all lambda directories
    for lambda_dir in lambda/*/; do
        if [ -d "$lambda_dir" ]; then
            lambda_name=$(basename "$lambda_dir")
            print_status "Packaging $lambda_name..."
            
            # Create temp directory
            temp_dir="dist/lambda/$lambda_name"
            mkdir -p "$temp_dir"
            
            # Copy function code
            cp "$lambda_dir"*.py "$temp_dir/"
            
            # Copy common library
            if [ -d "lambda/common_lib" ]; then
                cp lambda/common_lib/*.py "$temp_dir/"
            fi
            
            # Install requirements if requirements.txt exists
            if [ -f "$lambda_dir/requirements.txt" ]; then
                pip3 install -r "$lambda_dir/requirements.txt" -t "$temp_dir/"
            fi
            
            # Create ZIP file
            cd "$temp_dir"
            zip -r "../$lambda_name.zip" . -q
            cd - > /dev/null
            
            # Upload to S3
            aws s3 cp "dist/lambda/$lambda_name.zip" "s3://$CLOUDFORMATION_BUCKET/lambda/$lambda_name.zip"
            
            print_success "Packaged and uploaded $lambda_name"
        fi
    done
}

# Deploy CloudFormation stack
deploy_stack() {
    print_status "Deploying CloudFormation stack..."
    
    aws cloudformation deploy \
        --template-file infrastructure/main-stack.yaml \
        --stack-name $STACK_NAME \
        --parameter-overrides \
            Environment=$ENVIRONMENT \
            S3BucketName=$S3_BUCKET_NAME \
            CloudFormationBucket=$CLOUDFORMATION_BUCKET \
            StripeSecretKey=$STRIPE_SECRET_KEY \
            StripeWebhookSecret=$STRIPE_WEBHOOK_SECRET \
        --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
        --region $AWS_REGION
    
    print_success "CloudFormation stack deployed successfully"
}

# Configure API Gateway
configure_api_gateway() {
    print_status "Configuring API Gateway..."
    
    # Get stack outputs
    REST_API_ID=$(aws cloudformation describe-stacks \
        --stack-name $STACK_NAME \
        --query 'Stacks[0].Outputs[?OutputKey==`RestApiId`].OutputValue' \
        --output text)
    
    WEBSOCKET_API_ID=$(aws cloudformation describe-stacks \
        --stack-name $STACK_NAME \
        --query 'Stacks[0].Outputs[?OutputKey==`WebSocketApiId`].OutputValue' \
        --output text)
    
    print_status "REST API ID: $REST_API_ID"
    print_status "WebSocket API ID: $WEBSOCKET_API_ID"
    
    # Deploy REST API
    aws apigateway create-deployment \
        --rest-api-id $REST_API_ID \
        --stage-name production \
        --region $AWS_REGION
    
    # Deploy WebSocket API
    aws apigatewayv2 create-deployment \
        --api-id $WEBSOCKET_API_ID \
        --stage-name production \
        --region $AWS_REGION
    
    print_success "API Gateway configured successfully"
}

# Update Auth0 configuration
update_auth0_config() {
    print_status "Auth0 configuration update required..."
    print_warning "Please manually update Auth0 Action with the new API Gateway endpoint:"
    
    REST_API_ENDPOINT=$(aws cloudformation describe-stacks \
        --stack-name $STACK_NAME \
        --query 'Stacks[0].Outputs[?OutputKey==`RestApiEndpoint`].OutputValue' \
        --output text)
    
    echo "New API Gateway endpoint: $REST_API_ENDPOINT"
    echo "Update the 'apiGwEndpoint' variable in auth0-actions/post-login-roles-assignment.js"
}

# Main deployment function
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
    
    print_status "Starting Auto Lab Solutions Backend Deployment..."
    print_status "Target Environment: $ENVIRONMENT"
    print_status "AWS Region: $AWS_REGION"
    print_status "Stack Name: $STACK_NAME"
    echo ""
    
    # Show environment configuration
    show_env_config "$ENVIRONMENT"
    echo ""
    
    # Confirm deployment
    print_warning "This will deploy/update the backend infrastructure for '$ENVIRONMENT' environment."
    read -p "Continue? (y/N): " -n 1 -r
    echo ""
    
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_status "Deployment cancelled."
        exit 0
    fi
    
    check_prerequisites
    create_cf_bucket
    
    # Upload CloudFormation templates
    print_status "Uploading CloudFormation templates..."
    ./upload-templates.sh "$ENVIRONMENT"
    
    package_lambdas
    deploy_stack
    configure_api_gateway
    
    # Configure Lambda environment variables
    print_status "Configuring Lambda environment variables..."
    ./configure-lambda-env.sh "$ENVIRONMENT"
    
    update_auth0_config
    
    print_success "Deployment completed successfully!"
    
    # Print important endpoints
    print_status "Important endpoints:"
    aws cloudformation describe-stacks \
        --stack-name $STACK_NAME \
        --query 'Stacks[0].Outputs[?OutputKey==`RestApiEndpoint`||OutputKey==`WebSocketApiEndpoint`].[OutputKey,OutputValue]' \
        --output table
}

# Check if script is being run directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
