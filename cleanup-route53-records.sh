#!/bin/bash

# Script to cleanup old Route53 records for API Gateway domains
# This helps resolve issues where old DNS records exist

set -e

# Load environment configuration
source config/environments.sh

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

# Function to list Route53 records for a domain
list_records() {
    local hosted_zone_id=$1
    local domain_name=$2
    
    print_status "Checking existing records for $domain_name..."
    
    aws route53 list-resource-record-sets \
        --hosted-zone-id "$hosted_zone_id" \
        --query "ResourceRecordSets[?Name=='${domain_name}.'].[Name,Type,AliasTarget.DNSName,ResourceRecords[0].Value]" \
        --output table
}

# Function to get current API Gateway custom domain info
get_api_domain_info() {
    local domain_name=$1
    
    print_status "Getting current API Gateway domain configuration for $domain_name..."
    
    local domain_info=$(aws apigateway get-domain-name --domain-name "$domain_name" 2>/dev/null || echo "")
    
    if [ -n "$domain_info" ]; then
        echo "$domain_info" | jq -r '.regionalDomainName, .regionalHostedZoneId'
    else
        print_warning "API Gateway custom domain '$domain_name' not found"
        return 1
    fi
}

# Function to get current WebSocket API custom domain info
get_websocket_domain_info() {
    local domain_name=$1
    
    print_status "Getting current WebSocket API domain configuration for $domain_name..."
    
    local domain_info=$(aws apigatewayv2 get-domain-name --domain-name "$domain_name" 2>/dev/null || echo "")
    
    if [ -n "$domain_info" ]; then
        echo "$domain_info" | jq -r '.DomainNameConfigurations[0].TargetDomainName, .DomainNameConfigurations[0].HostedZoneId'
    else
        print_warning "WebSocket API custom domain '$domain_name' not found"
        return 1
    fi
}

# Function to delete old Route53 record
delete_old_record() {
    local hosted_zone_id=$1
    local domain_name=$2
    local record_type=$3
    local old_value=$4
    
    print_warning "Deleting old Route53 record: $domain_name ($record_type) -> $old_value"
    
    # Create change batch to delete the old record
    local change_batch=$(cat <<EOF
{
    "Changes": [
        {
            "Action": "DELETE",
            "ResourceRecordSet": {
                "Name": "${domain_name}",
                "Type": "${record_type}",
                "AliasTarget": {
                    "DNSName": "${old_value}",
                    "EvaluateTargetHealth": false,
                    "HostedZoneId": "Z2FDTNDATAQYW2"
                }
            }
        }
    ]
}
EOF
)
    
    aws route53 change-resource-record-sets \
        --hosted-zone-id "$hosted_zone_id" \
        --change-batch "$change_batch"
    
    print_success "Old record deletion initiated"
}

# Main cleanup function
cleanup_api_records() {
    local environment=$1
    
    if ! load_environment "$environment"; then
        print_error "Failed to load environment configuration"
        exit 1
    fi
    
    if [[ "${ENABLE_API_CUSTOM_DOMAINS}" != "true" ]]; then
        print_warning "API custom domains are not enabled for this environment"
        return 0
    fi
    
    print_status "=== Cleaning up Route53 records for API domains ==="
    print_status "Environment: $ENVIRONMENT"
    print_status "Hosted Zone ID: $API_HOSTED_ZONE_ID"
    print_status "REST API Domain: $API_DOMAIN_NAME"
    print_status "WebSocket Domain: $WEBSOCKET_DOMAIN_NAME"
    echo ""
    
    # Check REST API domain
    if [ -n "$API_DOMAIN_NAME" ]; then
        print_status "=== REST API Domain: $API_DOMAIN_NAME ==="
        list_records "$API_HOSTED_ZONE_ID" "$API_DOMAIN_NAME"
        echo ""
        
        # Get current domain info
        print_status "Current API Gateway configuration:"
        if get_api_domain_info "$API_DOMAIN_NAME"; then
            print_success "API Gateway domain is correctly configured"
        else
            print_warning "API Gateway domain may need to be recreated"
        fi
        echo ""
    fi
    
    # Check WebSocket API domain
    if [ -n "$WEBSOCKET_DOMAIN_NAME" ]; then
        print_status "=== WebSocket API Domain: $WEBSOCKET_DOMAIN_NAME ==="
        list_records "$API_HOSTED_ZONE_ID" "$WEBSOCKET_DOMAIN_NAME"
        echo ""
        
        # Get current domain info
        print_status "Current WebSocket API configuration:"
        if get_websocket_domain_info "$WEBSOCKET_DOMAIN_NAME"; then
            print_success "WebSocket API domain is correctly configured"
        else
            print_warning "WebSocket API domain may need to be recreated"
        fi
        echo ""
    fi
    
    print_status "=== Manual Actions Required ==="
    print_warning "If you see duplicate or incorrect records above, you have these options:"
    echo ""
    echo "1. Delete incorrect records manually in AWS Route53 console"
    echo "2. Update the CloudFormation stack to recreate the domains"
    echo "3. Use this script with --delete-old option (coming soon)"
    echo ""
    print_status "To force recreation of API Gateway domains:"
    print_status "  1. Set ENABLE_API_CUSTOM_DOMAINS=false in config"
    print_status "  2. Deploy the stack (this removes the domains)"
    print_status "  3. Set ENABLE_API_CUSTOM_DOMAINS=true in config"
    print_status "  4. Deploy the stack again (this recreates the domains)"
}

# Show usage
show_usage() {
    echo "Usage: $0 [ENVIRONMENT]"
    echo ""
    echo "Check and cleanup Route53 records for API Gateway domains"
    echo ""
    echo "Arguments:"
    echo "  ENVIRONMENT    Target environment (development|dev|production|prod)"
    echo ""
    echo "Examples:"
    echo "  $0 dev          # Check development environment"
    echo "  $0 production   # Check production environment"
    echo ""
}

# Main execution
main() {
    local environment_arg="$1"
    
    if [[ "$1" == "--help" || "$1" == "-h" ]]; then
        show_usage
        exit 0
    fi
    
    # Check prerequisites
    if ! command -v aws &> /dev/null; then
        print_error "AWS CLI not found. Please install AWS CLI."
        exit 1
    fi
    
    if ! command -v jq &> /dev/null; then
        print_error "jq not found. Please install jq for JSON parsing."
        exit 1
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        print_error "AWS credentials not configured. Please run 'aws configure'."
        exit 1
    fi
    
    cleanup_api_records "$environment_arg"
}

# Run main function if script is executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
