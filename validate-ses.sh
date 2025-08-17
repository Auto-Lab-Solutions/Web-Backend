#!/bin/bash

# Auto Lab Solutions - SES Validation and Setup Script
# This script validates AWS SES configuration and provides setup guidance

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
    echo "Usage: $0 [ENVIRONMENT] [OPTIONS]"
    echo ""
    echo "Validate AWS SES configuration for Auto Lab Solutions"
    echo ""
    echo "Arguments:"
    echo "  ENVIRONMENT    Target environment (development|dev|production|prod)"
    echo ""
    echo "Options:"
    echo "  --setup        Show detailed setup instructions"
    echo "  --verify       Attempt to verify domain and identity, configure receipt rules"
    echo "  --dns          Show required DNS configuration"
    echo "  --test         Test sending capabilities"
    echo "  --help         Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                    # Validate current/default environment"
    echo "  $0 production         # Validate production environment"
    echo "  $0 dev --setup        # Show setup instructions for development"
    echo "  $0 prod --test        # Test SES in production environment"
}

# Function to check SES service availability
check_ses_service() {
    print_status "Checking AWS SES service availability in region: $SES_REGION"
    
    if aws ses describe-configuration-sets --region "$SES_REGION" &>/dev/null; then
        print_success "AWS SES service is available in region $SES_REGION"
        return 0
    else
        print_error "AWS SES service is not available or accessible in region $SES_REGION"
        print_error "Please check:"
        print_error "  1. AWS credentials are configured correctly"
        print_error "  2. SES_REGION ($SES_REGION) is a valid SES region"
        print_error "  3. Your AWS account has SES access"
        return 1
    fi
}

# Function to check domain verification status
check_domain_verification() {
    local domain="${MAIL_FROM_ADDRESS##*@}"
    print_status "Checking domain verification for: $domain"
    
    local verification_result
    verification_result=$(aws ses get-identity-verification-attributes \
        --identities "$domain" \
        --region "$SES_REGION" \
        --output json 2>/dev/null) || {
        print_warning "Could not check domain verification status"
        return 1
    }
    
    local verification_status
    verification_status=$(echo "$verification_result" | \
        python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('VerificationAttributes', {}).get('$domain', {}).get('VerificationStatus', 'Unknown'))" 2>/dev/null || echo "Unknown")
    
    case "$verification_status" in
        "Success")
            print_success "Domain '$domain' is verified ✓"
            return 0
            ;;
        "Pending")
            print_warning "Domain '$domain' verification is pending"
            print_warning "Please check DNS records and wait for verification to complete"
            return 1
            ;;
        "Failed")
            print_error "Domain '$domain' verification failed"
            print_error "Please check DNS records and re-verify the domain"
            return 1
            ;;
        *)
            print_warning "Domain '$domain' is not yet added to SES or status unknown"
            return 1
            ;;
    esac
}

# Function to check email address verification
check_email_verification() {
    print_status "Checking email address verification for: $MAIL_FROM_ADDRESS"
    
    local verification_result
    verification_result=$(aws ses get-identity-verification-attributes \
        --identities "$MAIL_FROM_ADDRESS" \
        --region "$SES_REGION" \
        --output json 2>/dev/null) || {
        print_warning "Could not check email verification status"
        return 1
    }
    
    local verification_status
    verification_status=$(echo "$verification_result" | \
        python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('VerificationAttributes', {}).get('$MAIL_FROM_ADDRESS', {}).get('VerificationStatus', 'Unknown'))" 2>/dev/null || echo "Unknown")
    
    case "$verification_status" in
        "Success")
            print_success "Email address '$MAIL_FROM_ADDRESS' is verified ✓"
            return 0
            ;;
        "Pending")
            print_warning "Email address '$MAIL_FROM_ADDRESS' verification is pending"
            return 1
            ;;
        "Failed")
            print_error "Email address '$MAIL_FROM_ADDRESS' verification failed"
            return 1
            ;;
        *)
            print_warning "Email address '$MAIL_FROM_ADDRESS' is not yet added to SES"
            return 1
            ;;
    esac
}

# Function to check SES sending quota and limits
check_sending_quota() {
    print_status "Checking SES sending quota and limits"
    
    local quota_result
    quota_result=$(aws ses describe-account-sending-enabled --region "$SES_REGION" --output json 2>/dev/null) || {
        print_warning "Could not retrieve account sending status"
        return 1
    }
    
    local sending_enabled
    sending_enabled=$(echo "$quota_result" | python3 -c "import sys, json; print(json.load(sys.stdin).get('Enabled', False))")
    
    if [ "$sending_enabled" = "True" ]; then
        print_success "SES sending is enabled for this account ✓"
    else
        print_error "SES sending is disabled for this account"
        return 1
    fi
    
    # Get sending statistics
    local stats_result
    stats_result=$(aws ses get-send-quota --region "$SES_REGION" --output json 2>/dev/null) || {
        print_warning "Could not retrieve sending quota information"
        return 1
    }
    
    local max_24_hour
    local max_send_rate
    local sent_last_24_hours
    
    max_24_hour=$(echo "$stats_result" | python3 -c "import sys, json; print(json.load(sys.stdin).get('Max24HourSend', 'Unknown'))")
    max_send_rate=$(echo "$stats_result" | python3 -c "import sys, json; print(json.load(sys.stdin).get('MaxSendRate', 'Unknown'))")
    sent_last_24_hours=$(echo "$stats_result" | python3 -c "import sys, json; print(json.load(sys.stdin).get('SentLast24Hours', 'Unknown'))")
    
    print_status "SES Sending Limits:"
    print_status "  Max emails per 24 hours: $max_24_hour"
    print_status "  Max send rate per second: $max_send_rate"
    print_status "  Sent in last 24 hours: $sent_last_24_hours"
    
    # Check if in sandbox mode
    if [ "$max_24_hour" = "200" ] && [ "$max_send_rate" = "1" ]; then
        print_warning "SES appears to be in SANDBOX mode (200 emails/day, 1 email/second)"
        print_warning "For production usage, request to move out of sandbox mode"
        print_warning "See: https://docs.aws.amazon.com/ses/latest/dg/request-production-access.html"
    else
        print_success "SES appears to be out of sandbox mode"
    fi
}

# Function to automatically verify domain and email
auto_verify_identities() {
    local domain="${MAIL_FROM_ADDRESS##*@}"
    local email_to_verify="$NO_REPLY_EMAIL"
    
    print_status "Attempting to verify SES identities..."
    
    # Verify domain
    print_status "Verifying domain: $domain"
    if aws ses verify-domain-identity --domain "$domain" --region "$SES_REGION" &>/dev/null; then
        print_success "Domain verification initiated for: $domain"
    else
        print_warning "Failed to initiate domain verification for: $domain"
    fi
    
    # Verify email address
    print_status "Verifying email address: $email_to_verify"
    if aws ses verify-email-identity --email-address "$email_to_verify" --region "$SES_REGION" &>/dev/null; then
        print_success "Email verification initiated for: $email_to_verify"
    else
        print_warning "Failed to initiate email verification for: $email_to_verify"
    fi
    
    # Also verify the MAIL_FROM_ADDRESS if different
    if [ "$MAIL_FROM_ADDRESS" != "$email_to_verify" ]; then
        print_status "Verifying email address: $MAIL_FROM_ADDRESS"
        if aws ses verify-email-identity --email-address "$MAIL_FROM_ADDRESS" --region "$SES_REGION" &>/dev/null; then
            print_success "Email verification initiated for: $MAIL_FROM_ADDRESS"
        else
            print_warning "Failed to initiate email verification for: $MAIL_FROM_ADDRESS"
        fi
    fi
}

# Function to check and display DNS requirements
check_dns_requirements() {
    local domain="${MAIL_FROM_ADDRESS##*@}"
    
    print_status "Checking DNS configuration requirements for domain: $domain"
    
    # Get domain verification token
    local verification_token=""
    local verification_result
    verification_result=$(aws ses get-identity-verification-attributes \
        --identities "$domain" \
        --region "$SES_REGION" \
        --output json 2>/dev/null) || {
        print_warning "Could not retrieve domain verification token"
        return 1
    }
    
    verification_token=$(echo "$verification_result" | \
        python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('VerificationAttributes', {}).get('$domain', {}).get('VerificationToken', ''))" 2>/dev/null || echo "")
    
    if [ -n "$verification_token" ]; then
        print_success "Domain verification token retrieved: $verification_token"
        print_status "Required DNS Records for $domain:"
        echo ""
        echo "1. Domain Verification TXT Record:"
        echo "   Name: _amazonses.$domain"
        echo "   Value: $verification_token"
        echo ""
        echo "2. MX Record for Email Receiving:"
        echo "   Name: $domain"
        echo "   Value: 10 inbound-smtp.$SES_REGION.amazonses.com"
        echo ""
        echo "3. Optional MAIL FROM Domain (Recommended):"
        echo "   MX Record:"
        echo "   Name: mail.$domain"
        echo "   Value: 10 feedback-smtp.$SES_REGION.amazonses.com"
        echo ""
        echo "   TXT Record:"
        echo "   Name: mail.$domain"
        echo "   Value: v=spf1 include:amazonses.com ~all"
        echo ""
    else
        print_warning "Could not retrieve verification token. Domain may need to be added to SES first."
    fi
}

# Function to configure SES receipt rules
configure_receipt_rules() {
    local domain="${MAIL_FROM_ADDRESS##*@}"
    local email_to_receive="$NO_REPLY_EMAIL"
    
    print_status "Configuring SES receipt rules for email receiving..."
    
    # Create receipt rule set if it doesn't exist
    local rule_set_name="auto-lab-email-rules-${ENVIRONMENT}"
    
    print_status "Creating receipt rule set: $rule_set_name"
    if aws ses create-receipt-rule-set --rule-set-name "$rule_set_name" --region "$SES_REGION" &>/dev/null; then
        print_success "Receipt rule set created: $rule_set_name"
    else
        print_status "Receipt rule set may already exist: $rule_set_name"
    fi
    
    # Set as active rule set
    print_status "Setting active receipt rule set: $rule_set_name"
    if aws ses set-active-receipt-rule-set --rule-set-name "$rule_set_name" --region "$SES_REGION" &>/dev/null; then
        print_success "Receipt rule set activated: $rule_set_name"
    else
        print_warning "Failed to activate receipt rule set: $rule_set_name"
    fi
    
    print_status "Receipt rule configuration completed. Full setup requires CloudFormation deployment."
}

# Function to show detailed setup instructions
show_setup_instructions() {
    local domain="${MAIL_FROM_ADDRESS##*@}"
    
    cat << EOF

========================================
AWS SES Email Receiving Setup Guide
========================================

Environment: $ENVIRONMENT
From Email: $MAIL_FROM_ADDRESS
To Email: $NO_REPLY_EMAIL
Domain: $domain
SES Region: $SES_REGION

Current Status:
- Domain: dev.autolabsolutions.com (Verification pending)
- Email: mail@dev.autolabsolutions.com (Verification pending)

REQUIRED ACTIONS:
================

Step 1: Complete DNS Configuration
----------------------------------

Current Status:
- Domain: dev.autolabsolutions.com (Verification pending)
- Email: mail@dev.autolabsolutions.com (Verification pending)

REQUIRED ACTIONS:
================

Step 1: Complete DNS Configuration
----------------------------------
You need to add these DNS records to dev.autolabsolutions.com:

1. Domain Verification (Get token from SES Console):
   Type: TXT
   Name: _amazonses.dev.autolabsolutions.com
   Value: [Get verification token from AWS SES Console]

2. Email Receiving (MX Record):
   Type: MX
   Name: dev.autolabsolutions.com
   Value: 10 inbound-smtp.ap-southeast-2.amazonses.com
   Priority: 10

3. MAIL FROM Domain (Recommended):
   MX Record:
   Type: MX
   Name: mail.dev.autolabsolutions.com
   Value: 10 feedback-smtp.ap-southeast-2.amazonses.com
   Priority: 10
   
   TXT Record:
   Type: TXT
   Name: mail.dev.autolabsolutions.com
   Value: v=spf1 include:amazonses.com ~all

Step 2: Verify Identities in SES Console
----------------------------------------
1. Go to AWS SES Console: https://console.aws.amazon.com/ses/
2. Select region: ap-southeast-2
3. Navigate to "Verified identities"
4. Check status of:
   - dev.autolabsolutions.com (Domain)
   - mail@dev.autolabsolutions.com (Email)
5. If not verified, click on each and follow verification steps

Step 3: Configure Receipt Rules
-------------------------------
Run the following command after DNS is configured:
   ./validate-ses.sh development --verify

Step 4: Deploy Email Infrastructure
-----------------------------------
Run the main deployment to configure S3 and Lambda functions:
   ./deploy.sh development

Step 5: Test Email Receiving
----------------------------
After completing steps 1-4:
   ./validate-ses.sh development --test

TROUBLESHOOTING:
===============
- DNS propagation can take up to 24-48 hours
- Verify DNS records using: dig TXT _amazonses.dev.autolabsolutions.com
- Check SES sandbox mode if emails aren't being received
- Ensure AWS account has proper SES permissions

For immediate testing, you can:
1. Send a test email to mail@dev.autolabsolutions.com
2. Check CloudWatch logs for the email-processor Lambda function
3. Verify S3 bucket has the stored email

Support Links:
=============
- SES Console: https://console.aws.amazon.com/ses/
- SES Documentation: https://docs.aws.amazon.com/ses/
- DNS Verification: https://docs.aws.amazon.com/ses/latest/dg/verify-domain-procedure.html
   Value: 10 feedback-smtp.$SES_REGION.amazonses.com

3. MAIL FROM TXT Record:
   Name: mail.$domain
   Value: v=spf1 include:amazonses.com ~all

For more details, see:
- https://docs.aws.amazon.com/ses/latest/dg/verify-domain-procedure.html
- https://docs.aws.amazon.com/ses/latest/dg/mail-from.html

========================================
EOF
}

# Function to test SES sending capability
test_ses_sending() {
    print_status "Testing SES sending capability"
    
    # Create a test email
    local test_email_file="/tmp/ses-test-email.json"
    cat > "$test_email_file" << EOF
{
    "Source": "$MAIL_FROM_ADDRESS",
    "Destination": {
        "ToAddresses": ["$MAIL_FROM_ADDRESS"]
    },
    "Message": {
        "Subject": {
            "Data": "Auto Lab Solutions - SES Test Email",
            "Charset": "UTF-8"
        },
        "Body": {
            "Text": {
                "Data": "This is a test email from Auto Lab Solutions SES integration.\\n\\nEnvironment: $ENVIRONMENT\\nTimestamp: $(date)\\n\\nIf you receive this email, SES is working correctly.",
                "Charset": "UTF-8"
            },
            "Html": {
                "Data": "<html><body><h2>Auto Lab Solutions - SES Test</h2><p>This is a test email from Auto Lab Solutions SES integration.</p><ul><li><strong>Environment:</strong> $ENVIRONMENT</li><li><strong>Timestamp:</strong> $(date)</li></ul><p>If you receive this email, SES is working correctly.</p></body></html>",
                "Charset": "UTF-8"
            }
        }
    }
}
EOF
    
    print_status "Sending test email from $MAIL_FROM_ADDRESS to $MAIL_FROM_ADDRESS"
    
    if aws ses send-email --cli-input-json "file://$test_email_file" --region "$SES_REGION" &>/dev/null; then
        print_success "Test email sent successfully!"
        print_status "Check the inbox for $MAIL_FROM_ADDRESS to confirm delivery"
    else
        print_error "Failed to send test email"
        print_error "This could be due to:"
        print_error "  1. Domain/email not verified"
        print_error "  2. SES in sandbox mode (can only send to verified addresses)"
        print_error "  3. Insufficient permissions"
        print_error "  4. SES sending disabled"
    fi
    
    # Clean up
    rm -f "$test_email_file"
}

# Main validation function
validate_ses() {
    print_status "Starting AWS SES validation for environment: $ENVIRONMENT"
    print_status "Configuration:"
    print_status "  MAIL_FROM_ADDRESS: $MAIL_FROM_ADDRESS"
    print_status "  SES_REGION: $SES_REGION"
    echo ""
    
    local validation_passed=true
    
    # Check SES service availability
    if ! check_ses_service; then
        validation_passed=false
    fi
    
    # Check domain verification
    if ! check_domain_verification; then
        validation_passed=false
    fi
    
    # Check email verification
    if ! check_email_verification; then
        validation_passed=false
    fi
    
    # Check sending quota and limits
    if ! check_sending_quota; then
        validation_passed=false
    fi
    
    echo ""
    if [ "$validation_passed" = true ]; then
        print_success "✓ SES validation passed! Email sending should work correctly."
    else
        print_warning "⚠ SES validation found issues. Please review the warnings above."
        print_status "Run '$0 $ENVIRONMENT --setup' for detailed setup instructions"
    fi
    
    return 0
}

# Main function
main() {
    local setup_mode=false
    local verify_mode=false
    local test_mode=false
    local environment=""
    
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --setup)
                setup_mode=true
                shift
                ;;
            --verify)
                verify_mode=true
                auto_verify_identities
                configure_receipt_rules
                shift
                ;;
            --dns)
                check_dns_requirements
                exit 0
                ;;
            --test)
                test_mode=true
                shift
                ;;
            --help|-h)
                show_usage
                exit 0
                ;;
            -*)
                print_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
            *)
                if [ -z "$environment" ]; then
                    environment="$1"
                else
                    print_error "Multiple environments specified"
                    show_usage
                    exit 1
                fi
                shift
                ;;
        esac
    done
    
    # Load environment configuration
    if ! load_environment "$environment"; then
        exit 1
    fi
    
    print_status "AWS SES Validation Tool - Auto Lab Solutions"
    print_status "Environment: $ENVIRONMENT"
    echo ""
    
    # Execute based on mode
    if [ "$setup_mode" = true ]; then
        show_setup_instructions
    elif [ "$test_mode" = true ]; then
        validate_ses
        echo ""
        test_ses_sending
    else
        validate_ses
    fi
}

# Check if script is being run directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
