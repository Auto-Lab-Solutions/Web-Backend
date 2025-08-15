#!/bin/bash

# Cleanup Script for Auto Lab Solutions Backend
# This script removes all deployed resources

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

# Function to empty S3 bucket
empty_s3_bucket() {
    local bucket_name=$1
    print_status "Emptying S3 bucket: $bucket_name"
    
    if aws s3 ls "s3://$bucket_name" &> /dev/null; then
        aws s3 rm "s3://$bucket_name" --recursive
        print_success "Emptied S3 bucket: $bucket_name"
    else
        print_warning "S3 bucket does not exist: $bucket_name"
    fi
}

# Function to delete CloudFormation stack
delete_stack() {
    print_status "Deleting CloudFormation stack: $STACK_NAME"
    
    if aws cloudformation describe-stacks --stack-name "$STACK_NAME" &> /dev/null; then
        aws cloudformation delete-stack --stack-name "$STACK_NAME" --region $AWS_REGION
        
        print_status "Waiting for stack deletion to complete..."
        aws cloudformation wait stack-delete-complete --stack-name "$STACK_NAME" --region $AWS_REGION
        
        print_success "Stack deleted successfully: $STACK_NAME"
    else
        print_warning "Stack does not exist: $STACK_NAME"
    fi
}

# Function to clean up S3 buckets
cleanup_s3_buckets() {
    print_status "Cleaning up S3 buckets..."
    
    # Empty and delete reports bucket
    empty_s3_bucket "$REPORTS_BUCKET_NAME"
    
    # Empty CloudFormation templates bucket
    empty_s3_bucket "$CLOUDFORMATION_BUCKET"
    
    # Delete CloudFormation bucket
    if aws s3 ls "s3://$CLOUDFORMATION_BUCKET" &> /dev/null; then
        aws s3 rb "s3://$CLOUDFORMATION_BUCKET"
        print_success "Deleted S3 bucket: $CLOUDFORMATION_BUCKET"
    fi
}

# Function to clean up local build artifacts
cleanup_local() {
    print_status "Cleaning up local build artifacts..."
    
    if [ -d "dist" ]; then
        rm -rf dist
        print_success "Removed dist directory"
    fi
    
    if [ -d "lambda/tmp" ]; then
        rm -rf lambda/tmp
        print_success "Removed lambda/tmp directory"
    fi
}

# Main cleanup function
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
                echo "Clean up Auto Lab Solutions backend deployment"
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
    
    print_status "Cleaning up environment: $ENVIRONMENT"
    print_status "Stack name: $STACK_NAME"
    print_status "AWS Region: $AWS_REGION"
    echo ""
    
    print_warning "This will delete ALL deployed resources for Auto Lab Solutions Backend ($ENVIRONMENT environment)."
    
    # Skip confirmation prompt in CI/CD environments or if AUTO_CONFIRM is set
    if [ -n "$GITHUB_ACTIONS" ] || [ -n "$CI" ] || [ "$AUTO_CONFIRM" = "true" ]; then
        print_status "Running in automated environment - proceeding with cleanup"
    else
        read -p "Are you sure you want to continue? (y/N): " -n 1 -r
        echo
        
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_status "Cleanup cancelled."
            exit 0
        fi
    fi
    
    print_status "Starting cleanup process..."
    
    # First empty S3 buckets (required before stack deletion)
    empty_s3_bucket "$REPORTS_BUCKET_NAME"
    
    # Delete the main stack
    delete_stack
    
    # Clean up remaining S3 resources
    cleanup_s3_buckets
    
    # Clean up local artifacts
    cleanup_local
    
    print_success "Cleanup completed successfully!"
    print_status "All Auto Lab Solutions Backend resources have been removed from $ENVIRONMENT environment."
}

# Check if script is being run directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
