#!/bin/bash

# SES Email Receiving Infrastructure Deployment Script
# This script deploys the CloudFormation stack for SES email receiving

set -e  # Exit on any error

# Default values
STACK_NAME="auto-lab-ses-email-receiving"
TEMPLATE_FILE="ses-email-receiving.yaml"
REGION="ap-southeast-2"
ENVIRONMENT="dev"
DOMAIN_NAME="autolabsolutions.com"  # Default domain
S3_BUCKET_NAME=""  # Will be auto-generated based on environment
LAMBDA_FUNCTION_NAME="auto-lab-email-processor"

# Colors for output
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
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -e, --environment ENVIRONMENT    Environment (dev/staging/prod) [default: dev]"
    echo "  -d, --domain DOMAIN             Domain name for email receiving (optional - uses env default)"
    echo "  -b, --bucket BUCKET_NAME        S3 bucket name for email storage (optional - auto-generated)"
    echo "  -l, --lambda LAMBDA_NAME        Lambda function name [default: auto-lab-email-processor]"
    echo "  -r, --region REGION             AWS region [default: us-east-1]"
    echo "  -s, --stack-name STACK_NAME     CloudFormation stack name (optional - auto-generated)"
    echo "  --validate-only                 Only validate the template without deploying"
    echo "  --delete                        Delete the stack"
    echo "  -h, --help                      Show this help message"
    echo ""
    echo "Environment-specific defaults:"
    echo "  dev:     Domain: dev.autolabsolutions.com,     Stack: auto-lab-ses-email-receiving-dev"
    echo "  staging: Domain: staging.autolabsolutions.com, Stack: auto-lab-ses-email-receiving-staging"
    echo "  prod:    Domain: autolabsolutions.com,         Stack: auto-lab-ses-email-receiving-prod"
    echo ""
    echo "Examples:"
    echo "  $0 -e dev"
    echo "  $0 -e prod"
    echo "  $0 -e dev -d custom.domain.com"
    echo "  $0 -e prod -b custom-bucket-name"
}

# Function to validate AWS CLI is configured
validate_aws_cli() {
    if ! command -v aws &> /dev/null; then
        print_error "AWS CLI is not installed or not in PATH"
        exit 1
    fi

    if ! aws sts get-caller-identity &> /dev/null; then
        print_error "AWS CLI is not configured or credentials are invalid"
        exit 1
    fi

    print_status "AWS CLI validation passed"
}

# Function to validate template
validate_template() {
    print_status "Validating CloudFormation template..."
    
    if aws cloudformation validate-template \
        --template-body file://"$TEMPLATE_FILE" \
        --region "$REGION" > /dev/null; then
        print_success "Template validation passed"
    else
        print_error "Template validation failed"
        exit 1
    fi
}

# Function to check if stack exists
stack_exists() {
    aws cloudformation describe-stacks \
        --stack-name "$1" \
        --region "$REGION" \
        --query 'Stacks[0].StackStatus' \
        --output text 2>/dev/null || echo "DOES_NOT_EXIST"
}

# Function to wait for stack operation to complete
wait_for_stack() {
    local stack_name=$1
    local operation=$2
    
    print_status "Waiting for stack $operation to complete..."
    
    if aws cloudformation wait "stack-${operation}-complete" \
        --stack-name "$stack_name" \
        --region "$REGION"; then
        print_success "Stack $operation completed successfully"
    else
        print_error "Stack $operation failed or timed out"
        
        # Show stack events for debugging
        print_status "Recent stack events:"
        aws cloudformation describe-stack-events \
            --stack-name "$stack_name" \
            --region "$REGION" \
            --query 'StackEvents[0:10].[Timestamp,ResourceStatus,ResourceType,LogicalResourceId,ResourceStatusReason]' \
            --output table
        exit 1
    fi
}

# Function to deploy stack
deploy_stack() {
    local stack_name="$1"
    local stack_status
    
    # Build parameters
    local parameters="ParameterKey=Environment,ParameterValue=$ENVIRONMENT"
    parameters="$parameters ParameterKey=DomainName,ParameterValue=$DOMAIN_NAME"
    parameters="$parameters ParameterKey=LambdaFunctionName,ParameterValue=$LAMBDA_FUNCTION_NAME"
    
    if [ -n "$S3_BUCKET_NAME" ]; then
        parameters="$parameters ParameterKey=S3BucketName,ParameterValue=$S3_BUCKET_NAME"
    fi
    
    stack_status=$(stack_exists "$stack_name")
    
    if [ "$stack_status" = "DOES_NOT_EXIST" ]; then
        print_status "Creating new stack: $stack_name"
        
        aws cloudformation create-stack \
            --stack-name "$stack_name" \
            --template-body file://"$TEMPLATE_FILE" \
            --parameters $parameters \
            --capabilities CAPABILITY_NAMED_IAM \
            --region "$REGION" \
            --tags Key=Environment,Value="$ENVIRONMENT" Key=Project,Value="AutoLabSolutions" Key=Component,Value="EmailReceiving"
        
        wait_for_stack "$stack_name" "create"
    else
        print_status "Updating existing stack: $stack_name (current status: $stack_status)"
        
        if aws cloudformation update-stack \
            --stack-name "$stack_name" \
            --template-body file://"$TEMPLATE_FILE" \
            --parameters $parameters \
            --capabilities CAPABILITY_NAMED_IAM \
            --region "$REGION" 2>/dev/null; then
            wait_for_stack "$stack_name" "update"
        else
            print_warning "No updates to perform on stack $stack_name"
        fi
    fi
}

# Function to delete stack
delete_stack() {
    local stack_name="$1"
    local stack_status
    
    stack_status=$(stack_exists "$stack_name")
    
    if [ "$stack_status" = "DOES_NOT_EXIST" ]; then
        print_warning "Stack $stack_name does not exist"
        return 0
    fi
    
    print_status "Deleting stack: $stack_name"
    
    aws cloudformation delete-stack \
        --stack-name "$stack_name" \
        --region "$REGION"
    
    wait_for_stack "$stack_name" "delete"
}

# Function to show stack outputs
show_outputs() {
    local stack_name="$1"
    
    print_status "Stack outputs for $stack_name:"
    aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --region "$REGION" \
        --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue,Description]' \
        --output table
}

# Parse command line arguments
VALIDATE_ONLY=false
DELETE_STACK=false

while [[ $# -gt 0 ]]; do
    case $1 in
        -e|--environment)
            ENVIRONMENT="$2"
            shift 2
            ;;
        -d|--domain)
            DOMAIN_NAME="$2"
            shift 2
            ;;
        -b|--bucket)
            S3_BUCKET_NAME="$2"
            shift 2
            ;;
        -l|--lambda)
            LAMBDA_FUNCTION_NAME="$2"
            shift 2
            ;;
        -r|--region)
            REGION="$2"
            shift 2
            ;;
        -s|--stack-name)
            STACK_NAME="$2"
            shift 2
            ;;
        --validate-only)
            VALIDATE_ONLY=true
            shift
            ;;
        --delete)
            DELETE_STACK=true
            shift
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Main execution
print_status "Starting SES Email Receiving Infrastructure deployment"

# Change to script directory
cd "$(dirname "$0")"

# Set environment-specific defaults
set_environment_defaults "$ENVIRONMENT"

print_status "Region: $REGION"

# Validate AWS CLI
validate_aws_cli

# Validate template
validate_template

if [ "$VALIDATE_ONLY" = true ]; then
    print_success "Template validation completed successfully"
    exit 0
fi

if [ "$DELETE_STACK" = true ]; then
    delete_stack "$STACK_NAME"
    print_success "Stack deletion completed"
    exit 0
fi

# Function to set environment-specific defaults
set_environment_defaults() {
    local env=$1
    
    case $env in
        dev)
            DOMAIN_NAME="dev.autolabsolutions.com"
            STACK_NAME="auto-lab-ses-email-receiving-dev"
            ;;
        staging)
            DOMAIN_NAME="staging.autolabsolutions.com"
            STACK_NAME="auto-lab-ses-email-receiving-staging"
            ;;
        prod)
            DOMAIN_NAME="autolabsolutions.com"
            STACK_NAME="auto-lab-ses-email-receiving-prod"
            ;;
        *)
            print_warning "Unknown environment: $env. Using default values."
            ;;
    esac
    
    # Generate default bucket name if not provided
    if [ -z "$S3_BUCKET_NAME" ]; then
        S3_BUCKET_NAME="auto-lab-$env-email-storage"
    fi
    
    print_status "Environment: $env"
    print_status "Domain: $DOMAIN_NAME"
    print_status "S3 Bucket: $S3_BUCKET_NAME"
    print_status "Stack Name: $STACK_NAME"
}

# Deploy the stack
deploy_stack "$STACK_NAME"

# Show outputs
show_outputs "$STACK_NAME"

print_success "SES Email Receiving Infrastructure deployment completed successfully!"

# Important notes
echo ""
print_warning "IMPORTANT NOTES:"
echo "1. SES email receiving rules must be deployed in us-east-1 region"
echo "2. You need to verify the domain '$DOMAIN_NAME' in SES before emails can be received"
echo "3. Make sure to set the receipt rule set as active in the SES console"
echo "4. Configure your domain's MX records to point to the SES inbound mail servers"
echo ""
echo "Next steps:"
echo "1. Verify domain in SES: aws ses verify-domain-identity --domain $DOMAIN_NAME"
echo "2. Set rule set as active: aws ses set-active-receipt-rule-set --rule-set-name ${ENVIRONMENT}-${DOMAIN_NAME}-ReceiptRuleSet"
echo "3. Update MX records to point to: inbound-smtp.us-east-1.amazonaws.com"
