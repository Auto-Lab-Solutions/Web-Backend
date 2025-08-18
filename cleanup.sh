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
                    print_error "Stack deletion failed even after cleanup. Performing comprehensive diagnostics..."
                    
                    # Comprehensive failure analysis
                    print_status "=== FAILURE ANALYSIS ==="
                    
                    # 1. Show all DELETE_FAILED resources with details
                    print_status "Resources that failed to delete:"
                    aws cloudformation describe-stack-events \
                        --stack-name "$STACK_NAME" \
                        --query 'StackEvents[?ResourceStatus==`DELETE_FAILED`].[Timestamp,LogicalResourceId,ResourceType,ResourceStatusReason]' \
                        --output table
                    
                    # 2. Show current stack resources
                    print_status "Current stack resources:"
                    aws cloudformation describe-stack-resources \
                        --stack-name "$STACK_NAME" \
                        --query 'StackResources[*].[LogicalResourceId,ResourceType,ResourceStatus]' \
                        --output table
                    
                    # 3. Try to identify specific issues
                    print_status "Checking for common issues..."
                    
                    # Check for Lambda functions with ENIs
                    print_status "Checking Lambda functions..."
                    aws lambda list-functions --query "Functions[?contains(FunctionName, 'auto-lab-') || contains(FunctionName, '${ENVIRONMENT}')].FunctionName" --output text | tr '\t' '\n' | while read -r func; do
                        if [ -n "$func" ]; then
                            print_status "Found Lambda function: $func"
                        fi
                    done
                    
                    # Check for active SES rule sets
                    local active_ses=$(aws ses describe-active-receipt-rule-set --query 'RuleSet.Name' --output text 2>/dev/null || echo "None")
                    if [ "$active_ses" != "None" ] && [ "$active_ses" != "null" ]; then
                        print_warning "Active SES rule set found: $active_ses"
                        print_status "Deactivating SES rule set..."
                        aws ses set-active-receipt-rule-set 2>/dev/null || true
                    fi
                    
                    # Check for remaining S3 buckets
                    print_status "Checking for remaining S3 objects..."
                    aws s3 ls | grep -E "(auto-lab|${ENVIRONMENT})" | while read -r line; do
                        local bucket=$(echo "$line" | awk '{print $3}')
                        if [ -n "$bucket" ]; then
                            local obj_count=$(aws s3 ls "s3://$bucket" --recursive | wc -l)
                            if [ "$obj_count" -gt 0 ]; then
                                print_warning "Bucket $bucket still has $obj_count objects"
                                # Force empty the bucket
                                empty_s3_bucket "$bucket"
                            fi
                        fi
                    done
                    
                    # Try additional cleanup steps
                    cleanup_additional_resources
                    
                    # Final retry with more specific error handling
                    print_status "Final retry of stack deletion..."
                    aws cloudformation delete-stack --stack-name "$STACK_NAME" --region $AWS_REGION
                    
                    # Wait longer for final deletion
                    print_status "Waiting for final deletion (this may take several minutes)..."
                    if timeout 1800 aws cloudformation wait stack-delete-complete --stack-name "$STACK_NAME" --region $AWS_REGION; then
                        print_success "Stack deleted successfully after comprehensive cleanup: $STACK_NAME"
                    else
                        print_error "Stack deletion failed completely. Manual intervention required."
                        print_status "=== MANUAL CLEANUP REQUIRED ==="
                        print_status "Please check the CloudFormation console for specific error details."
                        print_status ""
                        print_status "Common manual steps required:"
                        print_status "1. Check for Lambda functions with VPC ENIs that need time to detach"
                        print_status "2. Check for security groups with active dependencies"
                        print_status "3. Check for IAM roles that are still in use by other resources"
                        print_status "4. Empty any remaining S3 buckets manually in the AWS console"
                        print_status "5. Delete the stack manually through the AWS console"
                        print_status ""
                        print_status "Debug commands to run:"
                        print_status "aws cloudformation describe-stack-events --stack-name $STACK_NAME --region $AWS_REGION --query 'StackEvents[?ResourceStatus==\\\`DELETE_FAILED\\\`].[LogicalResourceId,ResourceStatusReason]' --output table"
                        exit 1
                    fi
            fi
        fi
    else
        print_warning "Stack does not exist: $STACK_NAME"
    fi
}

# Function to cleanup additional resources that might prevent stack deletion
cleanup_additional_resources() {
    print_status "Performing comprehensive resource cleanup..."
    
    # 1. Clean up Lambda ENIs (wait for them to be removed)
    print_status "Waiting for Lambda ENIs to be cleaned up..."
    sleep 30  # Give Lambda ENIs time to be removed
    
    # 2. Force deactivate any SES rule sets
    print_status "Ensuring SES rule sets are deactivated..."
    aws ses set-active-receipt-rule-set 2>/dev/null || true
    
    # 3. Try to delete any custom Lambda functions that might be stuck
    print_status "Checking for custom Lambda functions..."
    local lambda_functions
    lambda_functions=$(aws lambda list-functions --query "Functions[?contains(FunctionName, 'ses-notification-configurator') || contains(FunctionName, 'ses-ruleset-activator') || contains(FunctionName, 's3-notification-configurator')].FunctionName" --output text 2>/dev/null || echo "")
    
    if [ -n "$lambda_functions" ]; then
        echo "$lambda_functions" | tr '\t' '\n' | while read -r func_name; do
            if [ -n "$func_name" ]; then
                print_status "Attempting to delete Lambda function: $func_name"
                aws lambda delete-function --function-name "$func_name" 2>/dev/null || true
            fi
        done
    fi
    
    # 4. Clean up any remaining SES configurations more aggressively
    print_status "Cleaning up SES configurations..."
    
    # Try to delete any remaining receipt rule sets
    local rule_sets
    rule_sets=$(aws ses list-receipt-rule-sets --query "RuleSets[?contains(Name, 'auto-lab-email-rules')].Name" --output text 2>/dev/null || echo "")
    
    if [ -n "$rule_sets" ]; then
        echo "$rule_sets" | tr '\t' '\n' | while read -r rule_set; do
            if [ -n "$rule_set" ]; then
                print_status "Attempting to delete SES rule set: $rule_set"
                # First deactivate if active
                aws ses set-active-receipt-rule-set 2>/dev/null || true
                # Then try to delete
                aws ses delete-receipt-rule-set --rule-set-name "$rule_set" 2>/dev/null || true
            fi
        done
    fi
    
    # 5. Force empty any remaining buckets
    print_status "Final S3 bucket cleanup..."
    aws s3 ls | grep -E "(auto-lab|${ENVIRONMENT})" | while read -r line; do
        local bucket_name=$(echo "$line" | awk '{print $3}')
        if [ -n "$bucket_name" ]; then
            print_status "Force emptying bucket: $bucket_name"
            # Delete all versions and delete markers
            aws s3api delete-objects --bucket "$bucket_name" \
                --delete "$(aws s3api list-object-versions --bucket "$bucket_name" \
                --query '{Objects: Versions[].{Key: Key, VersionId: VersionId}}' \
                --output json)" 2>/dev/null || true
            
            aws s3api delete-objects --bucket "$bucket_name" \
                --delete "$(aws s3api list-object-versions --bucket "$bucket_name" \
                --query '{Objects: DeleteMarkers[].{Key: Key, VersionId: VersionId}}' \
                --output json)" 2>/dev/null || true
            
            # Remove any remaining objects
            aws s3 rm "s3://$bucket_name" --recursive 2>/dev/null || true
        fi
    done
    
    # 6. Wait longer for AWS to process all the changes
    print_status "Waiting for AWS to process all resource changes..."
    sleep 90
}

# Function to empty all S3 buckets that might exist
empty_all_buckets() {
    print_status "Emptying all possible S3 buckets..."
    
    # Get AWS Account ID
    local account_id
    account_id=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "unknown")
    
    # Get all buckets and filter for ones that might be related to our project
    print_status "Scanning all S3 buckets for project-related buckets..."
    local all_buckets
    all_buckets=$(aws s3 ls | awk '{print $3}' || true)
    
    if [ -n "$all_buckets" ]; then
        echo "$all_buckets" | while IFS= read -r bucket_name; do
            if [ -n "$bucket_name" ]; then
                # Check if bucket matches our naming patterns
                if [[ "$bucket_name" == *"auto-lab"* ]] || \
                   [[ "$bucket_name" == *"$ENVIRONMENT"* ]] || \
                   [[ "$bucket_name" == *"cloudformation"* ]] || \
                   [[ "$bucket_name" == *"reports"* ]] || \
                   [[ "$bucket_name" == *"email-storage"* ]]; then
                    print_status "Found project bucket: $bucket_name"
                    empty_s3_bucket "$bucket_name"
                fi
            fi
        done
    fi
    
    # Also try specific bucket patterns that might exist
    local possible_buckets=(
        "$REPORTS_BUCKET_NAME"
        "$CLOUDFORMATION_BUCKET"
        "${EMAIL_STORAGE_BUCKET}-${account_id}-${ENVIRONMENT}"
        "auto-lab-email-storage-${account_id}-${ENVIRONMENT}"
        "auto-lab-reports-${ENVIRONMENT}"
        "auto-lab-cloudformation-templates"
        "auto-lab-cloudformation-templates-${ENVIRONMENT}"
        "auto-lab-reports"
    )
    
    for bucket in "${possible_buckets[@]}"; do
        if [ -n "$bucket" ] && [ "$bucket" != "unknown" ]; then
            empty_s3_bucket "$bucket"
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
