#!/bin/bash

# Simple SES verification status checker
# This script only checks status - all SES setup is handled by CloudFormation

set -e

# Load environment configuration
source config/environments.sh

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_status() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Function to show usage
show_usage() {
    echo "Usage: $0 [ENVIRONMENT]"
    echo ""
    echo "Check SES domain verification status"
    echo ""
    echo "Arguments:"
    echo "  ENVIRONMENT    Target environment (development|dev|production|prod)"
    echo ""
    echo "Examples:"
    echo "  $0 dev          # Check development status"
    echo "  $0 production   # Check production status"
    echo ""
    echo "Note: All SES setup is handled by CloudFormation during deployment."
    echo "This script only checks the current verification status."
}

# Load environment configuration
load_environment() {
    local env_arg="$1"
    
    if [ -z "$env_arg" ]; then
        env_arg="development"
    fi
    
    case "$env_arg" in
        "dev"|"development")
            export ENVIRONMENT="development"
            ;;
        "prod"|"production")
            export ENVIRONMENT="production"
            ;;
        *)
            print_error "Invalid environment: $env_arg"
            show_usage
            exit 1
            ;;
    esac
    
    if ! source config/environments.sh; then
        print_error "Failed to load environment configuration"
        exit 1
    fi
    
    set_environment_vars "$ENVIRONMENT"
}

# Check SES verification status
check_ses_status() {
    local domain="$SES_DOMAIN_NAME"
    local ses_stack_name="${STACK_NAME}-SESIdentitiesStack"
    
    print_status "SES Domain Verification Status Check"
    print_status "Environment: $ENVIRONMENT"
    print_status "Domain: $domain"
    print_status "SES Region: $SES_REGION"
    echo ""
    
    # Check if SES stack exists
    if ! aws cloudformation describe-stacks --stack-name "$ses_stack_name" --region "$AWS_REGION" &>/dev/null; then
        print_error "SES stack not found: $ses_stack_name"
        print_error "Run deployment first: ./deploy.sh $ENVIRONMENT"
        exit 1
    fi
    
    # Get CloudFormation outputs
    local dns_created=$(aws cloudformation describe-stacks \
        --stack-name "$ses_stack_name" \
        --region "$AWS_REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`DNSRecordsCreated`].OutputValue' \
        --output text 2>/dev/null || echo "Unknown")
    
    local verification_token=$(aws cloudformation describe-stacks \
        --stack-name "$ses_stack_name" \
        --region "$AWS_REGION" \
        --query 'Stacks[0].Outputs[?OutputKey==`VerificationToken`].OutputValue' \
        --output text 2>/dev/null || echo "Unknown")
    
    print_status "1. CloudFormation Setup:"
    print_status "   DNS Records Created: $dns_created"
    print_status "   Verification Token: ${verification_token:0:20}..."
    echo ""
    
    # Check actual SES verification status
    local domain_status=$(aws ses get-identity-verification-attributes \
        --identities "$domain" \
        --region "$SES_REGION" \
        --output json 2>/dev/null | \
        python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    status = data.get('VerificationAttributes', {}).get('$domain', {}).get('VerificationStatus', 'NotFound')
    print(status)
except:
    print('Error')
" 2>/dev/null || echo "Error")
    
    print_status "2. SES Verification Status:"
    case "$domain_status" in
        "Success")
            print_success "   ✅ Domain is verified and ready!"
            print_success "   📧 You can send and receive emails for @$domain"
            ;;
        "Pending")
            print_warning "   ⏳ Domain verification is pending"
            if [ "$dns_created" = "true" ]; then
                print_status "   DNS records created automatically"
                print_status "   Verification typically completes within 24 hours"
            else
                print_warning "   Manual DNS setup may be required"
                print_status "   Check CloudFormation stack outputs for instructions"
            fi
            ;;
        "Failed")
            print_error "   ❌ Domain verification failed"
            print_error "   Check AWS SES console for detailed error information"
            ;;
        *)
            print_warning "   ❓ Unknown status: $domain_status"
            print_status "   Check AWS SES console manually"
            ;;
    esac
    echo ""
    
    # DNS record check (if hosted zone configured)
    if [ -n "$SES_HOSTED_ZONE_ID" ] && [ "$SES_HOSTED_ZONE_ID" != "" ]; then
        print_status "3. DNS Records (Route53 Zone: $SES_HOSTED_ZONE_ID):"
        
        # Check TXT record
        local txt_record=$(aws route53 list-resource-record-sets \
            --hosted-zone-id "$SES_HOSTED_ZONE_ID" \
            --query "ResourceRecordSets[?Name=='_amazonses.${domain}.' && Type=='TXT'].ResourceRecords[0].Value" \
            --output text 2>/dev/null | tr -d '"' || echo "")
        
        if [ -n "$txt_record" ]; then
            print_success "   ✅ TXT Record: _amazonses.$domain"
            print_status "      Value: ${txt_record:0:40}..."
        else
            print_error "   ❌ TXT Record missing: _amazonses.$domain"
        fi
        
        # Check MX record
        local mx_record=$(aws route53 list-resource-record-sets \
            --hosted-zone-id "$SES_HOSTED_ZONE_ID" \
            --query "ResourceRecordSets[?Name=='${domain}.' && Type=='MX'].ResourceRecords[0].Value" \
            --output text 2>/dev/null || echo "")
        
        if [[ "$mx_record" == *"inbound-smtp"* ]]; then
            print_success "   ✅ MX Record: $domain"
            print_status "      Value: $mx_record"
        else
            print_error "   ❌ MX Record missing or incorrect: $domain"
        fi
    else
        print_status "3. DNS Records: Manual setup (no hosted zone configured)"
        if [ "$verification_token" != "Unknown" ]; then
            print_status "   Required records:"
            print_status "   TXT: _amazonses.$domain = $verification_token"
            print_status "   MX:  $domain = 10 inbound-smtp.$SES_REGION.amazonaws.com"
        fi
    fi
    echo ""
    
    # Summary
    if [ "$domain_status" = "Success" ]; then
        print_success "🎉 SES domain verification is complete!"
    elif [ "$domain_status" = "Pending" ]; then
        print_warning "⏳ Verification is in progress - check again later"
        print_status "Typical verification time: 15 minutes to 24 hours after DNS propagation"
    else
        print_error "❌ Verification needs attention"
        print_status "1. Check AWS SES console for detailed error messages"
        print_status "2. Verify DNS records are correct"
        print_status "3. Re-deploy if needed: ./deploy.sh $ENVIRONMENT"
    fi
}

# Main function
main() {
    if [[ "$1" == "--help" || "$1" == "-h" ]]; then
        show_usage
        exit 0
    fi
    
    if ! load_environment "$1"; then
        exit 1
    fi
    
    check_ses_status
}

main "$@"
