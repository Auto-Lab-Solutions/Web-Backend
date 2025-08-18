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
        # First, remove all objects including versions and delete markers
        aws s3api delete-objects --bucket "$bucket_name" \
            --delete "$(aws s3api list-object-versions --bucket "$bucket_name" \
                --query '{Objects: Versions[?Key].{Key: Key, VersionId: VersionId}}' \
                --output json)" 2>/dev/null || true
        
        aws s3api delete-objects --bucket "$bucket_name" \
            --delete "$(aws s3api list-object-versions --bucket "$bucket_name" \
                --query '{Objects: DeleteMarkers[?Key].{Key: Key, VersionId: VersionId}}' \
                --output json)" 2>/dev/null || true
        
        # Then remove all current objects
        aws s3 rm "s3://$bucket_name" --recursive 2>/dev/null || true
        print_success "Emptied S3 bucket: $bucket_name"
    else
        print_warning "S3 bucket does not exist: $bucket_name"
    fi
}

# Function to delete CloudFormation stack
delete_stack() {
    print_status "Deleting CloudFormation stack: $STACK_NAME"
    
    if aws cloudformation describe-stacks --stack-name "$STACK_NAME" &> /dev/null; then
        # First attempt normal deletion
        aws cloudformation delete-stack --stack-name "$STACK_NAME" --region $AWS_REGION
        
        print_status "Waiting for stack deletion to complete..."
        if aws cloudformation wait stack-delete-complete --stack-name "$STACK_NAME" --region $AWS_REGION; then
            print_success "Stack deleted successfully: $STACK_NAME"
        else
            print_warning "Stack deletion failed or timed out. Checking for failed resources..."
            
            # Get deletion failure reasons
            local failed_resources
            failed_resources=$(aws cloudformation describe-stack-events \
                --stack-name "$STACK_NAME" \
                --query 'StackEvents[?ResourceStatus==`DELETE_FAILED`].[LogicalResourceId,ResourceStatusReason]' \
                --output table)
            
            if [ -n "$failed_resources" ]; then
                print_error "Failed to delete the following resources:"
                echo "$failed_resources"
                
                print_status "Attempting to force deletion by emptying S3 buckets and retrying..."
                
                # Empty all possible S3 buckets
                empty_all_buckets
                
                # Retry stack deletion
                print_status "Retrying stack deletion..."
                aws cloudformation delete-stack --stack-name "$STACK_NAME" --region $AWS_REGION
                
                if aws cloudformation wait stack-delete-complete --stack-name "$STACK_NAME" --region $AWS_REGION; then
                    print_success "Stack deleted successfully on retry: $STACK_NAME"
                else
                    print_error "Stack deletion failed even after cleanup. Manual intervention may be required."
                    print_status "Check the CloudFormation console for specific error details."
                    exit 1
                fi
            fi
        fi
    else
        print_warning "Stack does not exist: $STACK_NAME"
    fi
}

# Function to empty all S3 buckets that might exist
empty_all_buckets() {
    print_status "Emptying all possible S3 buckets..."
    
    # Get AWS Account ID
    local account_id
    account_id=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "unknown")
    
    # List of possible bucket names
    local buckets=(
        "$REPORTS_BUCKET_NAME"
        "$CLOUDFORMATION_BUCKET"
        "${EMAIL_STORAGE_BUCKET}-${account_id}-${ENVIRONMENT}"
        "auto-lab-email-storage-${account_id}-${ENVIRONMENT}"
        "auto-lab-reports-${ENVIRONMENT}"
        "auto-lab-cloudformation-templates"
    )
    
    for bucket in "${buckets[@]}"; do
        if [ -n "$bucket" ] && [ "$bucket" != "unknown" ]; then
            empty_s3_bucket "$bucket"
        fi
    done
    
    # Also check for any buckets with our naming pattern
    print_status "Checking for additional buckets with auto-lab pattern..."
    aws s3 ls | grep "auto-lab" | while read -r line; do
        local bucket_name
        bucket_name=$(echo "$line" | awk '{print $3}')
        if [[ "$bucket_name" == *"$ENVIRONMENT"* ]] || [[ "$bucket_name" == *"auto-lab"* ]]; then
            print_status "Found additional bucket: $bucket_name"
            empty_s3_bucket "$bucket_name"
        fi
    done
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

# Function to check stack deletion status and show helpful error information
check_stack_deletion_status() {
    local stack_name="$1"
    
    print_status "Checking stack deletion status for: $stack_name"
    
    local stack_status
    stack_status=$(aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --query 'Stacks[0].StackStatus' \
        --output text 2>/dev/null || echo "DELETED")
    
    if [ "$stack_status" = "DELETE_FAILED" ]; then
        print_error "Stack deletion failed: $stack_name"
        
        # Get detailed error information
        print_status "Getting detailed error information..."
        aws cloudformation describe-stack-events \
            --stack-name "$stack_name" \
            --query 'StackEvents[?ResourceStatus==`DELETE_FAILED`].[LogicalResourceId,ResourceType,ResourceStatusReason]' \
            --output table
        
        # Show resources that are still in the stack
        print_status "Remaining stack resources:"
        aws cloudformation describe-stack-resources \
            --stack-name "$stack_name" \
            --query 'StackResources[*].[LogicalResourceId,ResourceType,ResourceStatus]' \
            --output table
            
        return 1
    elif [ "$stack_status" = "DELETED" ]; then
        print_success "Stack has been deleted successfully: $stack_name"
        return 0
    else
        print_status "Stack status: $stack_status"
        return 1
    fi
}

# Function to deactivate SES rule sets
deactivate_ses_rule_sets() {
    print_status "Deactivating SES rule sets..."
    
    local rule_set_name="auto-lab-email-rules-${ENVIRONMENT}"
    
    # Check if the rule set exists and is active
    local active_rule_set
    active_rule_set=$(aws ses describe-active-receipt-rule-set --query 'RuleSet.Name' --output text 2>/dev/null || echo "None")
    
    if [ "$active_rule_set" = "$rule_set_name" ]; then
        print_status "Deactivating active SES rule set: $rule_set_name"
        aws ses set-active-receipt-rule-set 2>/dev/null || true
        print_success "Deactivated SES rule set: $rule_set_name"
    elif [ "$active_rule_set" = "None" ]; then
        print_status "No active SES rule set found"
    else
        print_status "Active rule set '$active_rule_set' is not from this environment"
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
    
    # Step 1: Deactivate SES rule sets before stack deletion
    deactivate_ses_rule_sets
    
    # Step 2: Empty all S3 buckets first (this is critical for stack deletion)
    print_status "Pre-emptying S3 buckets to ensure clean stack deletion..."
    empty_all_buckets
    
    # Step 3: Delete the main stack
    delete_stack
    
    # Step 4: Clean up any remaining S3 resources
    cleanup_s3_buckets
    
    # Step 5: Clean up local artifacts
    cleanup_local
    
    print_success "Cleanup completed successfully!"
    print_status "All Auto Lab Solutions Backend resources have been removed from $ENVIRONMENT environment."
}

# Check if script is being run directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
