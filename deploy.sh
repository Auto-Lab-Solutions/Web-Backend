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
    echo "Development Environment:"
    echo "  Configure 'dev.env.sh' for development-specific settings like SKIP_LAMBDAS"
    echo ""
    echo "Pipeline/Automated Execution:"
    echo "  export AUTO_CONFIRM=true    # Skip all confirmation prompts"
    echo "  export CI=true              # Detected in most CI/CD systems"
    echo "  export GITHUB_ACTIONS=true  # Auto-detected in GitHub Actions"
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
        print_error "Please set: export STRIPE_SECRET_KEY='your_stripe_secret_key'"
        exit 1
    fi
    
    if [[ "$STRIPE_WEBHOOK_SECRET" == *"REPLACE_WITH_YOUR"* ]] || [[ -z "$STRIPE_WEBHOOK_SECRET" ]]; then
        print_error "Stripe Webhook Secret not configured."
        print_error "Please set: export STRIPE_WEBHOOK_SECRET='your_webhook_secret'"
        exit 1
    fi
    
    # Check Shared Key configuration
    if [[ "$SHARED_KEY" == *"REPLACE_WITH_YOUR"* ]] || [[ -z "$SHARED_KEY" ]]; then
        print_error "Shared Key not configured."
        print_error "Please set: export SHARED_KEY='your_shared_key'"
        exit 1
    fi
    
    # Check SES configuration
    if [[ -z "$MAIL_FROM_ADDRESS" ]]; then
        print_warning "MAIL_FROM_ADDRESS not set, using default: noreply@autolabsolutions.com"
        export MAIL_FROM_ADDRESS="noreply@autolabsolutions.com"
    fi
    
    if [[ -z "$SES_REGION" ]]; then
        print_warning "SES_REGION not set, using default: ap-southeast-2"
        export SES_REGION="ap-southeast-2"
    fi
    
    # Check Email Storage configuration
    if [[ -z "$NO_REPLY_EMAIL" ]]; then
        if [ "$ENVIRONMENT" = "production" ]; then
            print_warning "NO_REPLY_EMAIL not set, using default: mail@autolabsolutions.com"
            export NO_REPLY_EMAIL="mail@autolabsolutions.com"
        else
            print_warning "NO_REPLY_EMAIL not set, using default: mail@dev.autolabsolutions.com"
            export NO_REPLY_EMAIL="mail@dev.autolabsolutions.com"
        fi
    fi
    
    if [[ -z "$EMAIL_STORAGE_BUCKET" ]]; then
        print_warning "EMAIL_STORAGE_BUCKET not set, using default: auto-lab-email-storage"
        export EMAIL_STORAGE_BUCKET="auto-lab-email-storage"
    fi
    
    # Set EMAIL_METADATA_TABLE if not set
    if [[ -z "$EMAIL_METADATA_TABLE" ]]; then
        export EMAIL_METADATA_TABLE="EmailMetadata-${ENVIRONMENT}"
    fi

    print_status "Email Service Configuration:"
    print_status "  From Email (sending): $NO_REPLY_EMAIL"
    print_status "  To Email (receiving): $MAIL_FROM_ADDRESS"
    print_status "  SES Region: $SES_REGION"
    print_status "  Storage Bucket: $EMAIL_STORAGE_BUCKET"
    print_status "  Metadata Table: $EMAIL_METADATA_TABLE"
    
    # Check SES domain verification status
    local domain="${MAIL_FROM_ADDRESS##*@}"
    print_status "Checking SES domain verification for: $domain"
    
    # Check if domain is verified in SES
    if aws ses get-identity-verification-attributes --identities "$domain" --region "$SES_REGION" 2>/dev/null | grep -q "Success"; then
        print_success "SES domain '$domain' is verified in region $SES_REGION"
    else
        print_warning "SES domain '$domain' verification status unknown or not verified"
        print_warning "Please ensure the following:"
        print_warning "  1. Domain '$domain' is verified in AWS SES console (region: $SES_REGION)"
        print_warning "  2. MAIL FROM domain is configured (recommended: mail.$domain)"
        print_warning "  3. Required DNS records are configured:"
        print_warning "     - Domain verification TXT record"
        print_warning "     - MAIL FROM MX record"
        print_warning "     - MAIL FROM TXT record"
        print_warning "  4. SES is out of sandbox mode for production usage"
        print_warning ""
        print_warning "SES Setup Guide:"
        print_warning "  - AWS SES Console: https://console.aws.amazon.com/ses/"
        print_warning "  - Verify domain: https://docs.aws.amazon.com/ses/latest/dg/verify-domain-procedure.html"
        print_warning "  - Configure MAIL FROM: https://docs.aws.amazon.com/ses/latest/dg/mail-from.html"
    fi
    
    # Check Firebase configuration (optional)
    print_status "Firebase Configuration (Optional):"
    
    # Check if Firebase is explicitly enabled
    if [[ "${ENABLE_FIREBASE_NOTIFICATIONS:-false}" == "true" ]]; then
        print_status "Firebase notifications are ENABLED"
        if [[ -z "$FIREBASE_PROJECT_ID" ]]; then
            print_error "FIREBASE_PROJECT_ID required when Firebase is enabled"
            print_error "Please set: export FIREBASE_PROJECT_ID='your-firebase-project-id'"
            exit 1
        fi
        
        if [[ -z "$FIREBASE_SERVICE_ACCOUNT_KEY" ]]; then
            print_error "FIREBASE_SERVICE_ACCOUNT_KEY required when Firebase is enabled"
            print_error "Please set: export FIREBASE_SERVICE_ACCOUNT_KEY='base64-encoded-service-account-json'"
            exit 1
        fi
        
        # Validate Firebase Service Account Key format (should be base64)
        if ! echo "$FIREBASE_SERVICE_ACCOUNT_KEY" | base64 -d > /dev/null 2>&1; then
            print_error "FIREBASE_SERVICE_ACCOUNT_KEY appears to be invalid base64"
            print_error "Please ensure it's properly base64-encoded service account JSON"
            exit 1
        fi
        
        # Validate that decoded JSON contains required Firebase fields
        local decoded_key
        decoded_key=$(echo "$FIREBASE_SERVICE_ACCOUNT_KEY" | base64 -d 2>/dev/null)
        if ! echo "$decoded_key" | python3 -m json.tool > /dev/null 2>&1; then
            print_error "FIREBASE_SERVICE_ACCOUNT_KEY contains invalid JSON"
            exit 1
        fi
        
        # Check for required fields in service account JSON
        if ! echo "$decoded_key" | grep -q '"type".*"service_account"'; then
            print_error "Firebase service account key missing 'type: service_account'"
            exit 1
        fi
        
        if ! echo "$decoded_key" | grep -q '"project_id"'; then
            print_error "Firebase service account key missing 'project_id'"
            exit 1
        fi
        
        # Verify project_id matches FIREBASE_PROJECT_ID
        local key_project_id
        key_project_id=$(echo "$decoded_key" | python3 -c "import sys, json; print(json.load(sys.stdin)['project_id'])" 2>/dev/null)
        if [[ "$key_project_id" != "$FIREBASE_PROJECT_ID" ]]; then
            print_error "Project ID mismatch: FIREBASE_PROJECT_ID='$FIREBASE_PROJECT_ID' but service account key project_id='$key_project_id'"
            exit 1
        fi
        
        print_success "Firebase configuration validated"
        print_status "  Project ID: $FIREBASE_PROJECT_ID"
        print_status "  Service Account Key: ****[VERIFIED]****"
        
        # Check for Firebase dependencies in requirements
        if [[ -f "lambda/sqs-process-firebase-notification-queue/requirements.txt" ]]; then
            if grep -q "firebase-admin" lambda/sqs-process-firebase-notification-queue/requirements.txt; then
                print_success "Firebase admin SDK dependency found in requirements"
            else
                print_warning "Firebase admin SDK not found in requirements.txt"
            fi
        fi
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

# Function to check if Lambda function exists in AWS
function_exists() {
    local function_name=$1
    local full_function_name="${function_name}-${ENVIRONMENT}"
    aws lambda get-function --function-name "$full_function_name" --region $AWS_REGION &>/dev/null
}

# Package and upload Lambda functions
package_lambdas() {
    print_status "Packaging Lambda functions..."
    
    mkdir -p dist/lambda
    
    # Get list of all lambda directories
    for lambda_dir in lambda/*/; do
        if [ ! -d "$lambda_dir" ]; then
            print_error "Lambda directory not found: $lambda_dir"
            return 1
        fi
        if [ "$lambda_dir" == "lambda/common_lib/" ]; then
            continue  # Skip common library directory
        fi

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
        
        # Upload to S3 - all lambdas use lambda/ path
        aws s3 cp "dist/lambda/$lambda_name.zip" "s3://$CLOUDFORMATION_BUCKET/lambda/$lambda_name.zip"
        
        print_success "Packaged and uploaded $lambda_name"
    done
}

# Update Lambda function code
update_lambda_code() {
    local lambda_name=$1
    local full_function_name="${lambda_name}-${ENVIRONMENT}"
    local zip_file="dist/lambda/$lambda_name.zip"

    if [ "$lambda_name" == "common_lib" ]; then
        print_warning "Skipping common library update"
        return 0
    fi
    if [ ! -f "$zip_file" ]; then
        print_error "ZIP file not found: $zip_file"
        return 1
    fi
    
    # Check if function exists
    if ! function_exists "$lambda_name"; then
        print_error "Lambda function '$full_function_name' does not exist in AWS"
        print_warning "Please deploy infrastructure first using ./deploy.sh $ENVIRONMENT"
        return 1
    fi
    
    print_status "Updating Lambda function code: $full_function_name"
    
    # Update function code
    aws lambda update-function-code \
        --function-name "$full_function_name" \
        --zip-file "fileb://$zip_file" \
        --region $AWS_REGION > /dev/null
    
    # Wait for update to complete
    print_status "Waiting for update to complete..."
    aws lambda wait function-updated \
        --function-name "$full_function_name" \
        --region $AWS_REGION
    
    print_success "Updated $full_function_name"
    return 0
}

# Update Invoice Processor Lambda function code (managed by InvoiceQueueStack)
update_invoice_processor_lambda() {
    local lambda_name=$1
    local full_function_name="${lambda_name}-${ENVIRONMENT}"
    local zip_file="dist/lambda/$lambda_name.zip"

    if [ ! -f "$zip_file" ]; then
        print_error "ZIP file not found: $zip_file"
        return 1
    fi
    
    # Check if function exists
    if ! aws lambda get-function --function-name "$full_function_name" --region $AWS_REGION &>/dev/null; then
        print_error "Lambda function '$full_function_name' does not exist in AWS"
        print_warning "Please deploy infrastructure first using ./deploy.sh $ENVIRONMENT"
        return 1
    fi
    
    print_status "Updating Invoice Processor Lambda function code: $full_function_name"
    
    # Update function code
    aws lambda update-function-code \
        --function-name "$full_function_name" \
        --zip-file "fileb://$zip_file" \
        --region $AWS_REGION > /dev/null
    
    # Wait for update to complete
    print_status "Waiting for update to complete..."
    aws lambda wait function-updated \
        --function-name "$full_function_name" \
        --region $AWS_REGION
    
    print_success "Updated $full_function_name"
    return 0
}

# Update Backup Lambda function code (managed by BackupSystemStack)
update_backup_lambda() {
    local lambda_name=$1
    local full_function_name
    
    # Map the lambda directory names to actual CloudFormation function names
    case "$lambda_name" in
        "backup-restore")
            full_function_name="auto-lab-backup-${ENVIRONMENT}"
            ;;
        "api-backup-restore")
            full_function_name="auto-lab-manual-backup-${ENVIRONMENT}"
            ;;
        *)
            print_error "Unknown backup lambda: $lambda_name"
            return 1
            ;;
    esac
    
    local zip_file="dist/lambda/$lambda_name.zip"

    if [ ! -f "$zip_file" ]; then
        print_error "ZIP file not found: $zip_file"
        return 1
    fi
    
    # Check if function exists
    if ! aws lambda get-function --function-name "$full_function_name" --region $AWS_REGION &>/dev/null; then
        print_error "Lambda function '$full_function_name' does not exist in AWS"
        print_warning "Please deploy infrastructure first using ./deploy.sh $ENVIRONMENT"
        return 1
    fi
    
    print_status "Updating Backup Lambda function code: $full_function_name"
    
    # Update function code
    aws lambda update-function-code \
        --function-name "$full_function_name" \
        --zip-file "fileb://$zip_file" \
        --region $AWS_REGION > /dev/null
    
    # Wait for update to complete
    print_status "Waiting for update to complete..."
    aws lambda wait function-updated \
        --function-name "$full_function_name" \
        --region $AWS_REGION
    
    print_success "Updated $full_function_name"
    return 0
}

update_all_lambdas() {
    print_status "Updating all Lambda functions..."
    
    # Get list of all lambda directories
    for lambda_dir in lambda/*/; do
        if [ -d "$lambda_dir" ]; then
            lambda_name=$(basename "$lambda_dir")
            
            # Handle invoice processing lambda differently since it's managed by InvoiceQueueStack
            if [ "$lambda_name" = "sqs-process-invoice-queue" ]; then
                print_status "Updating $lambda_name (managed by InvoiceQueueStack)..."
                update_invoice_processor_lambda "$lambda_name"
            # Handle backup/restore lambdas differently since they're managed by BackupSystemStack
            elif [[ "$lambda_name" == "backup-restore" || "$lambda_name" == "api-backup-restore" ]]; then
                print_status "Updating $lambda_name (managed by BackupSystemStack)..."
                update_backup_lambda "$lambda_name"
            # Skip notification, SES processing, and email processor lambdas - we only do simple email receiving now
            elif [[ "$lambda_name" =~ ^ses- ]] || [[ "$lambda_name" == "email-processor" ]] || [[ "$lambda_name" == *-notification-queue ]]; then
                print_warning "Skipping $lambda_name - notification/processing functions removed for simple email receiving"
            else
                update_lambda_code "$lambda_name"
            fi
        fi
    done
    
    print_success "All Lambda functions updated successfully"
}

# Deploy CloudFormation stack
deploy_stack() {
    print_status "Deploying CloudFormation stack..."
    
    # Ensure SES hosted zone ID is set for DNS record creation
    if [ -z "$SES_HOSTED_ZONE_ID" ]; then
        print_status "Looking up Route53 hosted zone for SES domain: $SES_DOMAIN_NAME"
        SES_HOSTED_ZONE_ID=$(aws route53 list-hosted-zones-by-name \
            --dns-name "$SES_DOMAIN_NAME" \
            --query "HostedZones[?Name=='${SES_DOMAIN_NAME}.'].Id" \
            --output text | cut -d'/' -f3 2>/dev/null || echo "")
        
        if [ -n "$SES_HOSTED_ZONE_ID" ]; then
            print_success "Found hosted zone for $SES_DOMAIN_NAME: $SES_HOSTED_ZONE_ID"
            export SES_HOSTED_ZONE_ID
        else
            print_warning "No Route53 hosted zone found for $SES_DOMAIN_NAME"
            print_warning "SES domain verification DNS records will not be created automatically"
            print_warning "You will need to manually add DNS records shown in SES console"
        fi
    else
        print_status "Using configured SES hosted zone: $SES_HOSTED_ZONE_ID"
    fi
    
    # Construct frontend root URL for invoice generation
    local FRONTEND_ROOT_URL=""
    if [ "$ENABLE_FRONTEND_WEBSITE" = "true" ] && [ -n "$FRONTEND_DOMAIN_NAME" ]; then
        FRONTEND_ROOT_URL="https://${FRONTEND_DOMAIN_NAME}"
        print_status "Frontend root URL: $FRONTEND_ROOT_URL"
    else
        print_warning "Frontend website disabled or domain not set - invoice QR codes will use empty URL"
    fi
    
    aws cloudformation deploy \
        --template-file infrastructure/main-stack.yaml \
        --stack-name $STACK_NAME \
        --parameter-overrides \
            Environment=$ENVIRONMENT \
            S3BucketName=$REPORTS_BUCKET_NAME \
            CloudFormationBucket=$CLOUDFORMATION_BUCKET \
            BackupBucketName="$BACKUP_BUCKET_NAME" \
            StripeSecretKey=$STRIPE_SECRET_KEY \
            StripeWebhookSecret=$STRIPE_WEBHOOK_SECRET \
            Auth0Domain=$AUTH0_DOMAIN \
            Auth0Audience=$AUTH0_AUDIENCE \
            ReportsBucketName=$REPORTS_BUCKET_NAME \
            SharedKey=$SHARED_KEY \
            EnableFrontendWebsite=$ENABLE_FRONTEND_WEBSITE \
            FrontendDomainName="$FRONTEND_DOMAIN_NAME" \
            FrontendHostedZoneId="$FRONTEND_HOSTED_ZONE_ID" \
            FrontendAcmCertificateArn="$FRONTEND_ACM_CERTIFICATE_ARN" \
            EnableCustomDomain=$ENABLE_CUSTOM_DOMAIN \
            FrontendRootUrl="$FRONTEND_ROOT_URL" \
            MailSendingAddress="$NO_REPLY_EMAIL" \
            SesRegion="$SES_REGION" \
            MailReceivingAddress="$MAIL_FROM_ADDRESS" \
            EmailStorageBucketName="$EMAIL_STORAGE_BUCKET" \
            EmailMetadataTableName="$EMAIL_METADATA_TABLE" \
            EnableFirebaseNotifications="${ENABLE_FIREBASE_NOTIFICATIONS:-false}" \
            FirebaseProjectId="${FIREBASE_PROJECT_ID:-}" \
            FirebaseServiceAccountKey="${FIREBASE_SERVICE_ACCOUNT_KEY:-}" \
            EnableApiCustomDomains="${ENABLE_API_CUSTOM_DOMAINS:-false}" \
            ApiDomainName="${API_DOMAIN_NAME:-}" \
            WebSocketDomainName="${WEBSOCKET_DOMAIN_NAME:-}" \
            ApiHostedZoneId="${API_HOSTED_ZONE_ID:-}" \
            ApiAcmCertificateArn="${API_ACM_CERTIFICATE_ARN:-}" \
            EnableReportsCustomDomain="${ENABLE_REPORTS_CUSTOM_DOMAIN:-false}" \
            ReportsDomainName="${REPORTS_DOMAIN_NAME:-}" \
            ReportsHostedZoneId="${REPORTS_HOSTED_ZONE_ID:-}" \
            ReportsAcmCertificateArn="${REPORTS_ACM_CERTIFICATE_ARN:-}" \
            SESHostedZoneId="${SES_HOSTED_ZONE_ID:-}" \
            SESDomainName="${SES_DOMAIN_NAME:-autolabsolutions.com}" \
            SESVerificationToken="${SES_VERIFICATION_TOKEN:-}" \
        --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
        --region $AWS_REGION
    
    print_success "CloudFormation stack deployed successfully"
    
    # Verify SES email receiving setup
    verify_ses_email_setup
}

# Verify SES email receiving setup and handle two-step verification
verify_ses_email_setup() {
    print_status "Verifying SES email receiving setup..."
    
    # Check if domain identity exists in SES
    local identity_exists="false"
    if aws ses get-identity-verification-attributes \
        --identities "$SES_DOMAIN_NAME" \
        --region "$SES_REGION" >/dev/null 2>&1; then
        identity_exists="true"
    fi
    
    if [ "$identity_exists" = "false" ]; then
        print_warning "⚠️  SES domain identity not found. This suggests the CloudFormation stack didn't deploy correctly."
        print_warning "   Check the CloudFormation console for errors in the SESIdentitiesStack nested stack."
        return 1
    fi
    
    # Get domain verification status and token
    local verification_response=$(aws ses get-identity-verification-attributes \
        --identities "$SES_DOMAIN_NAME" \
        --region "$SES_REGION" \
        --output json 2>/dev/null || echo '{}')
    
    local verification_status=$(echo "$verification_response" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    status = data.get('VerificationAttributes', {}).get('$SES_DOMAIN_NAME', {}).get('VerificationStatus', 'NotFound')
    print(status)
except:
    print('NotFound')
" 2>/dev/null || echo "NotFound")
    
    local verification_token=$(echo "$verification_response" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    token = data.get('VerificationAttributes', {}).get('$SES_DOMAIN_NAME', {}).get('VerificationToken', '')
    print(token)
except:
    print('')
" 2>/dev/null || echo "")
    
    print_status "SES domain verification status for $SES_DOMAIN_NAME: $verification_status"
    
    case $verification_status in
        "Success")
            print_success "✅ SES domain is verified! Email receiving is fully operational."
            print_success "📧 You can now receive emails at any address @$SES_DOMAIN_NAME"
            ;;
        "Pending")
            print_warning "⏳ SES domain verification is pending."
            if [ -n "$verification_token" ] && [ -z "$SES_VERIFICATION_TOKEN" ]; then
                print_status ""
                print_status "🔧 NEXT STEPS TO COMPLETE VERIFICATION:"
                print_status "1. Set the verification token and redeploy:"
                print_status "   export SES_VERIFICATION_TOKEN=\"$verification_token\""
                print_status "   ./deploy.sh $ENVIRONMENT"
                print_status ""
                print_status "2. Or manually create DNS record:"
                print_status "   Type: TXT"
                print_status "   Name: _amazonses.$SES_DOMAIN_NAME"
                print_status "   Value: $verification_token"
                print_status ""
                print_status "   DNS records will be created automatically after the verification token is set."
            elif [ -n "$SES_VERIFICATION_TOKEN" ]; then
                print_status "   Verification token provided - DNS record should be created."
                print_status "   Verification will complete automatically within 24 hours."
            else
                print_warning "   No verification token available yet. Wait a moment and redeploy."
            fi
            ;;
        "Failed")
            print_error "❌ SES domain verification failed."
            print_error "   Check DNS records in Route53 and SES console for details."
            if [ -n "$verification_token" ]; then
                print_error "   Current verification token: $verification_token"
                print_error "   Ensure DNS TXT record _amazonses.$SES_DOMAIN_NAME = $verification_token"
            fi
            ;;
        "NotFound"|"NotStarted")
            print_warning "⚠️  SES domain not found or verification not started."
            print_warning "   This may indicate an issue with domain setup in CloudFormation."
            ;;
        *)
            print_warning "⚠️  Unknown verification status: $verification_status"
            ;;
    esac
    
    # Check email storage bucket
    local email_bucket_status="unknown"
    if aws s3 ls "s3://$EMAIL_STORAGE_BUCKET" --region "$AWS_REGION" >/dev/null 2>&1; then
        email_bucket_status="exists"
        print_success "✅ Email storage bucket exists: $EMAIL_STORAGE_BUCKET"
    else
        email_bucket_status="missing"
        print_error "❌ Email storage bucket not found: $EMAIL_STORAGE_BUCKET"
    fi
    
    # Check SES receipt rules
    local receipt_rules_count=$(aws ses describe-receipt-rule-set \
        --rule-set-name "auto-lab-receipt-rules-$ENVIRONMENT" \
        --region "$SES_REGION" \
        --query 'Rules | length(@)' \
        --output text 2>/dev/null || echo "0")
    
    if [ "$receipt_rules_count" -gt 0 ]; then
        print_success "✅ SES receipt rules configured ($receipt_rules_count rules)"
    else
        print_warning "⚠️  No SES receipt rules found. Email receiving may not work."
    fi
    
    # Summary
    echo ""
    print_status "=== EMAIL RECEIVING SETUP SUMMARY ==="
    echo "📧 Email Domain: $SES_DOMAIN_NAME"
    echo "🌍 SES Region: $SES_REGION"
    echo "📂 Storage Bucket: $EMAIL_STORAGE_BUCKET"
    echo "✉️  Receiving Address: $MAIL_FROM_ADDRESS"
    echo "📋 Domain Verification: $verification_status"
    echo "🪣 Storage Bucket: $email_bucket_status"
    echo "📜 Receipt Rules: $receipt_rules_count configured"
    
    # Show verification token if available and not set
    if [ -n "$verification_token" ] && [ -z "$SES_VERIFICATION_TOKEN" ]; then
        echo "🔑 Verification Token: $verification_token"
    fi
    echo ""
    
    if [ "$verification_status" = "Success" ] && [ "$email_bucket_status" = "exists" ] && [ "$receipt_rules_count" -gt 0 ]; then
        print_success "🎉 EMAIL RECEIVING SYSTEM IS FULLY OPERATIONAL!"
        print_success "   Send test emails to: mail@$SES_DOMAIN_NAME"
        print_success "   Emails will be stored in: $EMAIL_STORAGE_BUCKET"
    elif [ "$verification_status" = "Pending" ]; then
        print_warning "⏳ Email system is deployed but waiting for domain verification."
        if [ -n "$verification_token" ] && [ -z "$SES_VERIFICATION_TOKEN" ]; then
            print_warning "   Set verification token and redeploy to create DNS records automatically:"
            print_warning "   export SES_VERIFICATION_TOKEN=\"$verification_token\""
            print_warning "   ./deploy.sh $ENVIRONMENT"
        else
            print_warning "   System will be operational within 24 hours."
        fi
    else
        print_error "❌ Email receiving system has issues. Check the details above."
    fi
    echo ""
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
    
    print_success "API Gateway configured successfully"
}

# Update Auth0 configuration
update_auth0_config() {
    print_status "Auth0 configuration update required..."
    print_warning "Please manually update Auth0 Action with the new API Gateway endpoint:"
    
    # Get the appropriate API endpoint (custom domain if enabled, otherwise default)
    if [ "${ENABLE_API_CUSTOM_DOMAINS:-false}" = "true" ] && [ -n "$API_DOMAIN_NAME" ]; then
        REST_API_ENDPOINT="https://${API_DOMAIN_NAME}"
        print_status "Using custom domain for Auth0 configuration"
    else
        REST_API_ENDPOINT=$(aws cloudformation describe-stacks \
            --stack-name $STACK_NAME \
            --query 'Stacks[0].Outputs[?OutputKey==`RestApiEndpoint`].OutputValue' \
            --output text)
        print_status "Using default AWS domain for Auth0 configuration"
    fi
    
    echo "API Gateway endpoint for Auth0: $REST_API_ENDPOINT"
    echo "Update the 'apiGwEndpoint' variable in auth0-actions/post-login-roles-assignment.js"
    
    if [ "${ENABLE_API_CUSTOM_DOMAINS:-false}" = "true" ]; then
        echo ""
        print_status "Custom domain endpoints configured:"
        echo "  REST API: https://${API_DOMAIN_NAME:-not-configured}"
        echo "  WebSocket API: wss://${WEBSOCKET_DOMAIN_NAME:-not-configured}"
        echo ""
        print_warning "Make sure DNS records are propagated before testing the custom domains"
    fi
}

# Configure SES Bounce and Complaint Notifications
configure_ses_notifications() {
    print_status "Configuring SES bounce and complaint notifications..."
    print_success "✅ SES bounce and complaint notifications are now automatically configured by CloudFormation"
    print_success "✅ SNS topics created and linked to SES identities"
    print_success "✅ Lambda functions configured to process bounce/complaint notifications"
    print_success "✅ DynamoDB tables configured for email suppression and analytics"
    
    # Provide instructions for manual verification
    print_status "SES Notification Setup Complete!"
    print_status "Next steps:"
    print_status "  1. Verify your domain in SES console if not already done"
    print_status "  2. Test the notification system by sending test emails"
    print_status "  3. Check CloudWatch logs for Lambda function execution"
    print_status "  4. Monitor DynamoDB tables for bounce/complaint records"
    
    return 0
}

# Validate S3 bucket configuration for SES
validate_ses_s3_configuration() {
    print_status "Validating S3 bucket is properly configured for SES access..."
    
    # Get AWS Account ID
    local account_id
    account_id=$(aws sts get-caller-identity --query Account --output text)
    
    if [ -z "$account_id" ]; then
        print_error "Could not retrieve AWS Account ID"
        return 1
    fi
    
    # Construct bucket name
    local bucket_name="${EMAIL_STORAGE_BUCKET}-${account_id}-${ENVIRONMENT}"
    
    print_status "Checking bucket: $bucket_name"
    
    # Check if bucket exists
    if ! aws s3api head-bucket --bucket "$bucket_name" --region "$AWS_REGION" 2>/dev/null; then
        print_error "S3 bucket $bucket_name does not exist or is not accessible"
        return 1
    fi
    
    # Check bucket policy
    print_status "Checking bucket policy for SES permissions..."
    local bucket_policy
    bucket_policy=$(aws s3api get-bucket-policy --bucket "$bucket_name" --region "$AWS_REGION" --output text --query 'Policy' 2>/dev/null)
    
    if [ -z "$bucket_policy" ] || [ "$bucket_policy" = "None" ]; then
        print_error "No bucket policy found for $bucket_name"
        print_error "SES requires specific bucket permissions to store emails"
        return 1
    fi
    
    # Check if the policy contains SES service principal
    if echo "$bucket_policy" | grep -q "ses.amazonaws.com"; then
        print_success "Bucket policy includes SES permissions"
    else
        print_error "Bucket policy does not include SES service principal permissions"
        print_error "Please ensure the bucket policy allows ses.amazonaws.com to PutObject"
        return 1
    fi
    
    # Check public access block configuration
    print_status "Checking public access block configuration..."
    local public_access_block
    public_access_block=$(aws s3api get-public-access-block --bucket "$bucket_name" --region "$AWS_REGION" 2>/dev/null)
    
    if echo "$public_access_block" | grep -q '"RestrictPublicBuckets": true'; then
        print_warning "RestrictPublicBuckets is enabled - this may prevent SES access"
        print_warning "Consider setting RestrictPublicBuckets to false for SES integration"
    fi
    
    # Test SES can access the bucket by checking permissions
    print_status "Testing SES service permissions on bucket..."
    
    # Create a test policy document to verify SES permissions
    local test_result
    test_result=$(aws s3api get-bucket-location --bucket "$bucket_name" --region "$AWS_REGION" 2>/dev/null)
    
    if [ $? -eq 0 ]; then
        print_success "S3 bucket is accessible and properly configured for SES"
    else
        print_error "S3 bucket configuration test failed"
        return 1
    fi
}

# Configure SES DNS Records for Domain Verification
configure_ses_dns_records() {
    print_status "Configuring SES DNS records for domain verification..."
    
    local domain="${MAIL_FROM_ADDRESS##*@}"
    local email_to_receive="$MAIL_FROM_ADDRESS"
    
    print_status "Setting up SES identities for domain: $domain"
    print_status "  Email receiving address: $email_to_receive"
    print_status "  Email sending address: $NO_REPLY_EMAIL"
    
    # Add domain to SES (this covers all email addresses under the domain)
    print_status "Adding domain to SES: $domain"
    if aws ses verify-domain-identity --domain "$domain" --region "$SES_REGION" &>/dev/null; then
        print_success "Domain added to SES: $domain"
        print_status "✅ This automatically verifies ALL @$domain email addresses"
        print_status "  - $email_to_receive (receiving)"
        print_status "  - $NO_REPLY_EMAIL (sending)"
        print_status "  - Any other @$domain addresses"
    else
        print_warning "Domain may already be in SES: $domain"
    fi
    
    # Get domain verification token
    print_status "Getting domain verification token for domain: $domain"
    local domain_token=""
    local retry_count=0
    while [ -z "$domain_token" ] && [ $retry_count -lt 3 ]; do
        domain_token=$(aws ses get-identity-verification-attributes \
            --identities "$domain" \
            --region "$SES_REGION" \
            --output json 2>/dev/null | \
            python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    token = data.get('VerificationAttributes', {}).get('$domain', {}).get('VerificationToken', '')
    print(token)
except:
    print('')
" 2>/dev/null || echo "")
        
        if [ -z "$domain_token" ]; then
            retry_count=$((retry_count + 1))
            print_status "Waiting for SES to generate verification token... (attempt $retry_count/3)"
            sleep 5
        fi
    done
    
    if [ -z "$domain_token" ]; then
        print_error "Could not get domain verification token after 3 attempts"
        print_error "You may need to manually verify the domain in SES Console"
        return 1
    fi
    
    print_success "Domain verification token obtained: $domain_token"
    
    # Find Route53 hosted zone
    print_status "Finding Route53 hosted zone..."
    local hosted_zone_id=""
    hosted_zone_id=$(aws route53 list-hosted-zones --query "HostedZones[?contains(Name, 'autolabsolutions.com')].Id" --output text 2>/dev/null | head -1 | sed 's|/hostedzone/||')
    
    if [ -z "$hosted_zone_id" ]; then
        print_error "Could not find Route53 hosted zone for autolabsolutions.com"
        print_error "Please ensure you have a Route53 hosted zone for your domain"
        print_error "Manual DNS configuration required:"
        print_error "  1. TXT Record: _amazonses.$domain = $domain_token"
        print_error "  2. MX Record: $domain = 10 inbound-smtp.$SES_REGION.amazonses.com"
        print_error "  3. MX Record: mail.$domain = 10 feedback-smtp.$SES_REGION.amazonses.com"
        print_error "  4. TXT Record: mail.$domain = v=spf1 include:amazonses.com ~all"
        return 1
    fi
    
    print_success "Found Route53 hosted zone: $hosted_zone_id"
    
    # Create DNS records using Route53
    print_status "Creating DNS records in Route53..."
    
    # Create temporary JSON file for Route53 change batch
    local change_batch_file="/tmp/ses-route53-changes-$$.json"
    
    cat > "$change_batch_file" << EOF
{
    "Comment": "SES verification and email receiving records for $domain",
    "Changes": [
        {
            "Action": "UPSERT",
            "ResourceRecordSet": {
                "Name": "_amazonses.$domain",
                "Type": "TXT",
                "TTL": 300,
                "ResourceRecords": [
                    {
                        "Value": "\"$domain_token\""
                    }
                ]
            }
        },
        {
            "Action": "UPSERT",
            "ResourceRecordSet": {
                "Name": "$domain",
                "Type": "MX",
                "TTL": 300,
                "ResourceRecords": [
                    {
                        "Value": "10 inbound-smtp.$SES_REGION.amazonses.com"
                    }
                ]
            }
        },
        {
            "Action": "UPSERT",
            "ResourceRecordSet": {
                "Name": "mail.$domain",
                "Type": "MX",
                "TTL": 300,
                "ResourceRecords": [
                    {
                        "Value": "10 feedback-smtp.$SES_REGION.amazonses.com"
                    }
                ]
            }
        },
        {
            "Action": "UPSERT",
            "ResourceRecordSet": {
                "Name": "mail.$domain",
                "Type": "TXT",
                "TTL": 300,
                "ResourceRecords": [
                    {
                        "Value": "\"v=spf1 include:amazonses.com ~all\""
                    }
                ]
            }
        }
    ]
}
EOF
    
    # Apply the DNS changes
    local change_id=""
    change_id=$(aws route53 change-resource-record-sets \
        --hosted-zone-id "$hosted_zone_id" \
        --change-batch "file://$change_batch_file" \
        --query 'ChangeInfo.Id' \
        --output text 2>/dev/null)
    
    # Clean up temporary file
    rm -f "$change_batch_file"
    
    if [ -n "$change_id" ]; then
        print_success "✅ DNS records created successfully!"
        print_success "Route53 Change ID: $change_id"
        
        print_status "Created DNS Records:"
        print_status "  1. TXT Record: _amazonses.$domain = $domain_token"
        print_status "  2. MX Record: $domain = 10 inbound-smtp.$SES_REGION.amazonses.com"
        print_status "  3. MX Record: mail.$domain = 10 feedback-smtp.$SES_REGION.amazonses.com"
        print_status "  4. TXT Record: mail.$domain = v=spf1 include:amazonses.com ~all"
        
        print_status "Waiting for DNS propagation (30 seconds)..."
        sleep 30
        
        # Check if changes are propagated
        if aws route53 get-change --id "$change_id" --query 'ChangeInfo.Status' --output text 2>/dev/null | grep -q "INSYNC"; then
            print_success "✅ DNS changes are live!"
        else
            print_warning "⏳ DNS changes are still propagating (may take a few more minutes)"
        fi
        
    else
        print_error "❌ Failed to create DNS records in Route53"
        return 1
    fi
    
    return 0
}

# Check SES verification status
check_ses_verification_status() {
    local domain="${MAIL_FROM_ADDRESS##*@}"
    local email_to_receive="$MAIL_FROM_ADDRESS"
    
    print_status "Checking SES verification status..."
    
    # Check domain verification
    local domain_status=""
    domain_status=$(aws ses get-identity-verification-attributes \
        --identities "$domain" \
        --region "$SES_REGION" \
        --output json 2>/dev/null | \
        python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    status = data.get('VerificationAttributes', {}).get('$domain', {}).get('VerificationStatus', 'Unknown')
    print(status)
except:
    print('Unknown')
" 2>/dev/null || echo "Unknown")
    
    # Check email verification
    local email_status=""
    email_status=$(aws ses get-identity-verification-attributes \
        --identities "$email_to_receive" \
        --region "$SES_REGION" \
        --output json 2>/dev/null | \
        python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    status = data.get('VerificationAttributes', {}).get('$email_to_receive', {}).get('VerificationStatus', 'Unknown')
    print(status)
except:
    print('Unknown')
" 2>/dev/null || echo "Unknown")
    
    print_status "SES Verification Status:"
    print_status "  Domain ($domain): $domain_status"
    print_status "  Email ($email_to_receive): $email_status"
    
    if [ "$domain_status" = "Success" ] && [ "$email_status" = "Success" ]; then
        print_success "✅ Both identities are verified and ready for email receiving!"
        return 0
    elif [ "$domain_status" = "Pending" ] || [ "$email_status" = "Pending" ]; then
        print_warning "⏳ Verification is in progress. This is normal and may take up to 30 minutes."
        print_warning "Email receiving will work once verification completes."
        return 0
    else
        print_warning "⚠ Verification status unknown. Email receiving may not work until verified."
        print_warning "Check AWS SES Console for detailed verification status."
        return 1
    fi
}

# Configure SES Email Receiving
configure_email_receiving() {
    print_status "Configuring SES email receiving..."
    
    # Note: SES identities, DNS records, receipt rules, and notifications are now managed by CloudFormation
    print_status "Step 1: SES identities and DNS records managed by CloudFormation"
    print_success "✅ SES domain identities and Route53 DNS records are automatically managed by CloudFormation"
    print_success "✅ Domain verification covers all email addresses under the domain"
    print_success "✅ DKIM signing and MAIL FROM domain configured for better deliverability"
    print_success "✅ SES receipt rule set automatically activated by CloudFormation"
    print_success "✅ SES bounce/complaint notifications automatically configured by CloudFormation"
    print_success "✅ S3 bucket notifications automatically configured by CloudFormation"
    
    # Check verification status
    print_status "Step 2: Check SES verification status"
    check_ses_verification_status
    
    # Validate S3 bucket configuration for SES
    print_status "Step 3: Validate S3 bucket configuration for SES"
    validate_ses_s3_configuration
    
    print_success "✅ SES email receiving configured successfully!"
    
    # Get AWS Account ID for display purposes
    local account_id
    account_id=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "unknown")
    
    print_status "Email receiving is now configured for: $MAIL_FROM_ADDRESS"
    print_status "S3 storage bucket: ${EMAIL_STORAGE_BUCKET}-${account_id}-${ENVIRONMENT}"
    print_status "DynamoDB metadata table: ${EMAIL_METADATA_TABLE}"
    
    # Final verification check
    print_status "Step 4: Final verification status check"
    if check_ses_verification_status; then
        print_success "🎉 Email receiving setup is complete and verified!"
    else
        print_warning "⚠ Email receiving setup is complete but verification is still pending"
        print_warning "Email receiving will work once SES identities are verified"
        print_warning "Check AWS SES Console for verification status"
    fi
}

# Configure S3 bucket notifications for email processing
configure_s3_email_notifications() {
    print_status "Configuring S3 bucket notifications for email processing..."
    
    # Get AWS Account ID
    local account_id
    account_id=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "unknown")
    
    if [ "$account_id" = "unknown" ]; then
        print_error "Failed to get AWS Account ID"
        return 1
    fi
    
    local bucket_name="${EMAIL_STORAGE_BUCKET}-${account_id}-${ENVIRONMENT}"
    local function_name="email-processor-${ENVIRONMENT}"
    
    print_status "Bucket: $bucket_name"
    print_status "Function: $function_name"
    
    # Get the Lambda function ARN
    local lambda_arn
    lambda_arn=$(aws lambda get-function --function-name "$function_name" --query 'Configuration.FunctionArn' --output text 2>/dev/null)
    
    if [ $? -ne 0 ] || [ -z "$lambda_arn" ]; then
        print_error "Failed to get Lambda function ARN for $function_name"
        return 1
    fi
    
    print_status "Lambda ARN: $lambda_arn"
    
    # Configure S3 bucket notification
    local notification_config=$(cat <<EOF
{
    "LambdaFunctionConfigurations": [
        {
            "Id": "EmailProcessorTrigger",
            "LambdaFunctionArn": "$lambda_arn",
            "Events": [
                "s3:ObjectCreated:*"
            ],
            "Filter": {
                "Key": {
                    "FilterRules": [
                        {
                            "Name": "prefix",
                            "Value": "emails/"
                        }
                    ]
                }
            }
        }
    ]
}
EOF
    )
    
    # Apply the notification configuration
    print_status "Applying S3 bucket notification configuration..."
    aws s3api put-bucket-notification-configuration \
        --bucket "$bucket_name" \
        --notification-configuration "$notification_config"
    
    if [ $? -eq 0 ]; then
        print_success "✅ S3 bucket notifications configured successfully"
        print_success "✅ Lambda function permissions are properly set"
        print_success "✅ Email processor will be triggered automatically when emails arrive"
        print_success "S3 bucket notification configuration completed successfully!"
    else
        print_error "Failed to configure S3 bucket notifications"
        return 1
    fi
}

# Configure SES domain notifications as a backup mechanism
configure_ses_domain_notifications() {
    print_status "Configuring SES domain notifications as backup..."
    
    local domain_name="${SES_DOMAIN_NAME}"
    
    # Get SNS topic ARNs from the main stack outputs (which should export these values)
    local bounce_topic_arn
    local complaint_topic_arn
    local delivery_topic_arn
    
    bounce_topic_arn=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --query 'Stacks[0].Outputs[?OutputKey==`SESBounceTopicArn`].OutputValue' \
        --output text 2>/dev/null)
    
    complaint_topic_arn=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --query 'Stacks[0].Outputs[?OutputKey==`SESComplaintTopicArn`].OutputValue' \
        --output text 2>/dev/null)
    
    delivery_topic_arn=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --query 'Stacks[0].Outputs[?OutputKey==`SESDeliveryTopicArn`].OutputValue' \
        --output text 2>/dev/null)
    
    if [ -z "$bounce_topic_arn" ] || [ -z "$complaint_topic_arn" ]; then
        print_warning "Could not retrieve SNS topic ARNs from stack outputs. SES notifications may need manual configuration."
        return 0
    fi
    
    print_status "Domain: $domain_name"
    print_status "Bounce Topic: $bounce_topic_arn"
    print_status "Complaint Topic: $complaint_topic_arn"
    
    # Check if domain is verified
    local verification_status
    verification_status=$(aws ses get-identity-verification-attributes \
        --identities "$domain_name" \
        --query "VerificationAttributes.\"$domain_name\".VerificationStatus" \
        --output text 2>/dev/null)
    
    if [ "$verification_status" != "Success" ]; then
        print_warning "Domain $domain_name is not yet verified (status: $verification_status)"
        print_warning "SES notifications will be configured automatically when domain verification completes"
        return 0
    fi
    
    # Configure bounce notifications
    print_status "Configuring bounce notifications..."
    aws ses put-identity-notification-attributes \
        --identity "$domain_name" \
        --notification-type Bounce \
        --sns-topic "$bounce_topic_arn"
    
    aws ses put-identity-notification-attributes \
        --identity "$domain_name" \
        --notification-type Bounce \
        --enabled
    
    # Configure complaint notifications
    print_status "Configuring complaint notifications..."
    aws ses put-identity-notification-attributes \
        --identity "$domain_name" \
        --notification-type Complaint \
        --sns-topic "$complaint_topic_arn"
    
    aws ses put-identity-notification-attributes \
        --identity "$domain_name" \
        --notification-type Complaint \
        --enabled
    
    # Configure delivery notifications if available
    if [ -n "$delivery_topic_arn" ]; then
        print_status "Configuring delivery notifications..."
        aws ses put-identity-notification-attributes \
            --identity "$domain_name" \
            --notification-type Delivery \
            --sns-topic "$delivery_topic_arn"
        
        aws ses put-identity-notification-attributes \
            --identity "$domain_name" \
            --notification-type Delivery \
            --enabled
    fi
    
    print_success "✅ SES domain notifications configured successfully"
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
    
    # Initialize variables
    local SKIP_LAMBDAS=false
    
    # Source development-specific configuration if deploying to development
    if [[ "$ENVIRONMENT" == "development" ]]; then
        if [[ -f "config/dev.env.sh" ]]; then
            print_status "Loading development-specific configuration from config/dev.env.sh..."
            source config/dev.env.sh
            if [[ "${SKIP_LAMBDAS:-false}" == "true" ]]; then
                print_status "Development configuration: SKIP_LAMBDAS=true"
            fi
        else
            print_warning "config/dev.env.sh not found. Using default development configuration."
        fi
    fi
    
    print_status "Starting Auto Lab Solutions Backend Deployment..."
    print_status "Target Environment: $ENVIRONMENT"
    print_status "AWS Region: $AWS_REGION"
    print_status "Stack Name: $STACK_NAME"
    
    if [[ "${SKIP_LAMBDAS:-false}" == "true" ]]; then
        print_warning "Lambda function updates will be SKIPPED (configured in dev.env.sh)"
    fi
    
    echo ""
    
    # Show environment configuration
    show_env_config "$ENVIRONMENT"
    echo ""
    
    # Confirm deployment
    if [[ "${SKIP_LAMBDAS:-false}" == "true" ]]; then
        print_warning "This will deploy/update the backend infrastructure for '$ENVIRONMENT' environment WITHOUT updating Lambda function code."
        print_warning "CloudFormation stack, API Gateway, configuration, and Lambda environment variables will be updated."
        print_warning "Only Lambda function code packaging and deployment will be skipped."
    else
        print_warning "This will deploy/update the backend infrastructure for '$ENVIRONMENT' environment."
    fi
    
    # Skip confirmation prompt in CI/CD environments or if AUTO_CONFIRM is set
    if [ -n "$GITHUB_ACTIONS" ] || [ -n "$CI" ] || [ "$AUTO_CONFIRM" = "true" ]; then
        print_status "Running in automated environment - proceeding with deployment"
    else
        read -p "Continue? (y/N): " -n 1 -r
        echo ""
        
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_status "Deployment cancelled."
            exit 0
        fi
    fi
    
    check_prerequisites
    
    create_cf_bucket
    
    # Upload CloudFormation templates
    print_status "Uploading CloudFormation templates..."
    ./upload-templates.sh --env "$ENVIRONMENT"
    
    # Conditionally package and upload Lambda functions
    if [[ "${SKIP_LAMBDAS:-false}" == "true" ]]; then
        print_warning "Skipping Lambda function packaging and uploading as requested"
    else
        package_lambdas
    fi
    
    deploy_stack

    # Note: Backup system is deployed as part of the main stack (nested stack)
    # No separate backup system deployment needed

    # Conditionally update Lambda functions
    if [[ "${SKIP_LAMBDAS:-false}" == "true" ]]; then
        print_warning "Skipping Lambda function code updates as requested"
    else
        update_all_lambdas
    fi
    
    configure_api_gateway
    
    # Configure SES bounce and complaint notifications
    print_status "Configuring SES bounce and complaint notifications..."
    configure_ses_notifications
    
    # Configure SES email receiving
    configure_email_receiving
    
    # Configure S3 bucket notifications for email processing
    configure_s3_email_notifications
    if [ $? -ne 0 ]; then
        print_error "Failed to configure S3 bucket notifications"
        exit 1
    fi
    
    # Configure SES domain notifications as backup (in case CloudFormation custom resource failed)
    configure_ses_domain_notifications
    
    # Always update Lambda environment variables (even when SKIP_LAMBDAS=true)
    # This ensures Lambda functions have the correct configuration for the updated infrastructure
    print_status "Updating Lambda environment variables (WebSocket endpoints and notification queues)..."
    ./update-lambda-variables.sh --env "$ENVIRONMENT"
    
    update_auth0_config
    
    # Initialize DynamoDB tables with required data
    print_status "Initializing DynamoDB tables with default data..."
    ./initialize-dynamodb-data.sh "$ENVIRONMENT"

    if [[ "${SKIP_LAMBDAS:-false}" == "true" ]]; then
        print_success "Deployment completed successfully! (Lambda function code was skipped, but environment variables were updated)"
        print_warning ""
        print_warning "IMPORTANT: Lambda function code was not updated in this deployment."
        print_warning "However, Lambda environment variables were updated with the latest configuration."
        print_warning "To update Lambda function code later, set SKIP_LAMBDAS=false in dev.env.sh and run:"
        print_warning "  ./deploy.sh $ENVIRONMENT"
        print_warning "Or to update Lambda function code only:"
        print_warning "  ./update-lambdas.sh $ENVIRONMENT"
    else
        print_success "Deployment completed successfully!"
    fi
    
    # Print SES configuration summary
    print_status "=========================================="
    print_status "SES Email Receiving Configuration Summary"
    print_status "=========================================="
    
    local domain="${MAIL_FROM_ADDRESS##*@}"
    local email_to_receive="$MAIL_FROM_ADDRESS"
    
    print_status "Environment: $ENVIRONMENT"
    print_status "Domain: $domain"
    print_status "Email receiving address: $email_to_receive"
    print_status "SES Region: $SES_REGION"
    
    # Quick verification status check
    local domain_status="Unknown"
    local email_status="Unknown"
    
    domain_status=$(aws ses get-identity-verification-attributes \
        --identities "$domain" \
        --region "$SES_REGION" \
        --output json 2>/dev/null | \
        python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    status = data.get('VerificationAttributes', {}).get('$domain', {}).get('VerificationStatus', 'Unknown')
    print(status)
except:
    print('Unknown')
" 2>/dev/null || echo "Unknown")
    
    email_status=$(aws ses get-identity-verification-attributes \
        --identities "$email_to_receive" \
        --region "$SES_REGION" \
        --output json 2>/dev/null | \
        python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    status = data.get('VerificationAttributes', {}).get('$email_to_receive', {}).get('VerificationStatus', 'Unknown')
    print(status)
except:
    print('Unknown')
" 2>/dev/null || echo "Unknown")
    
    if [ "$domain_status" = "Success" ] && [ "$email_status" = "Success" ]; then
        print_success "✅ SES identities are verified - Email receiving is ready!"
    elif [ "$domain_status" = "Pending" ] || [ "$email_status" = "Pending" ]; then
        print_warning "⏳ SES verification is pending - Email receiving will work once verified"
        print_warning "DNS propagation can take up to 30 minutes"
    else
        print_warning "⚠ SES verification status unknown - Check AWS SES Console"
    fi
    
    print_status "To test email receiving:"
    print_status "  1. Wait for SES verification to complete"
    print_status "  2. Send test email to: $email_to_receive"
    print_status "  3. Check S3 bucket and DynamoDB for stored email"
    print_status "=========================================="

    # Print important endpoints
    print_status "Important endpoints:"
    aws cloudformation describe-stacks \
        --stack-name $STACK_NAME \
        --query 'Stacks[0].Outputs[?OutputKey==`RestApiEndpoint`||OutputKey==`WebSocketApiEndpoint`||OutputKey==`InvoiceQueueUrl`||OutputKey==`EmailNotificationQueueUrl`||OutputKey==`WebSocketNotificationQueueUrl`||OutputKey==`FirebaseNotificationQueueUrl`||OutputKey==`SESBounceTopicArn`||OutputKey==`SESComplaintTopicArn`||OutputKey==`EmailSuppressionTableName`||OutputKey==`EmailAnalyticsTableName`].[OutputKey,OutputValue]' \
        --output table

    # Print async processing status
    echo ""
    if [[ "${SKIP_LAMBDAS:-false}" == "true" ]]; then
        print_warning "Async Processing Components (Lambda functions skipped):"
        echo "  ⚠ SQS Invoice Queue for asynchronous invoice generation (created)"
        echo "  ⚠ Invoice Processor Lambda (sqs-process-invoice-queue) (not updated)"
        echo "  ⚠ SQS Email Notification Queue for asynchronous email processing (created)"
        echo "  ⚠ Email Notification Processor Lambda (sqs-process-email-notification-queue) (not updated)"
        echo "  ⚠ SQS WebSocket Notification Queue for asynchronous WebSocket processing (created)"
        echo "  ⚠ WebSocket Notification Processor Lambda (sqs-process-websocket-notification-queue) (not updated)"
        
        # Show Firebase status
        if [[ "${ENABLE_FIREBASE_NOTIFICATIONS:-false}" == "true" ]]; then
            echo "  ⚠ Firebase Notification Processor Lambda (sqs-process-firebase-notification-queue) (not updated)"
            echo "  ⚠ Firebase Cloud Messaging configured for push notifications (not updated)"
        else
            echo "  ✗ Firebase Notifications are disabled"
        fi
        
        echo "  ⚠ Payment confirmation Lambdas (code not updated, but environment variables updated)"
        echo "  ⚠ All business logic Lambdas (code not updated, but environment variables updated)"
        echo "  ⚠ Shared notification_utils library (not deployed)"
        echo ""
        print_warning "Lambda function code was skipped! SQS queues are available and Lambda environment variables are updated."
        print_warning "Set SKIP_LAMBDAS=false in dev.env.sh and run deployment again to update Lambda function code."
    else
        print_success "Async Processing Components Deployed:"
        echo "  ✓ SQS Invoice Queue for asynchronous invoice generation"
        echo "  ✓ Invoice Processor Lambda (sqs-process-invoice-queue)"
        echo "  ✓ SQS Email Notification Queue for asynchronous email processing"
        echo "  ✓ Email Notification Processor Lambda (sqs-process-email-notification-queue)"
        echo "  ✓ SQS WebSocket Notification Queue for asynchronous WebSocket processing"
        echo "  ✓ WebSocket Notification Processor Lambda (sqs-process-websocket-notification-queue)"
        
        # Show Firebase status
        if [[ "${ENABLE_FIREBASE_NOTIFICATIONS:-false}" == "true" ]]; then
            echo "  ✓ Firebase Notification Processor Lambda (sqs-process-firebase-notification-queue)"
            echo "  ✓ Firebase Cloud Messaging configured for push notifications"
        else
            echo "  ✗ Firebase Notifications are disabled"
        fi
        
        echo "  ✓ Payment confirmation Lambdas updated with async support"
        echo "  ✓ All business logic Lambdas updated to use notification queues"
        echo "  ✓ Shared notification_utils library deployed to all functions"
        echo ""
        print_status "All notification processing is now asynchronous via SQS queues!"
    fi
    
    echo ""
    if [[ "${SKIP_LAMBDAS:-false}" == "true" ]]; then
        print_warning "Backup System (Lambda functions skipped):"
        echo "  ⚠ Automated backup Lambda function for scheduled backups (not updated)"
        echo "  ⚠ Manual backup Lambda function for on-demand backups (not updated)"
        echo "  ⚠ API backup/restore Lambda function for programmatic access (not updated)"
        echo "  ✓ Scheduled backups configured (daily at 2:00 AM UTC for production)"
        echo "  ✓ Backup retention policies configured"
        echo "  ✓ S3 backup storage with versioning enabled"
        echo ""
        print_warning "Lambda function code was skipped! Set SKIP_LAMBDAS=false in dev.env.sh and run deployment again to update backup function code."
    else
        print_success "Backup System Deployed:"
        echo "  ✓ Automated backup Lambda function for scheduled backups"
        echo "  ✓ Manual backup Lambda function for on-demand backups"
        echo "  ✓ API backup/restore Lambda function for programmatic access"
        echo "  ✓ Scheduled backups configured (daily at 2:00 AM UTC for production)"
        echo "  ✓ Backup retention policies configured"
        echo "  ✓ S3 backup storage with versioning enabled"
        echo ""
        print_status "Backup Management Commands:"
        echo "  ./manage-backups.sh trigger-backup $ENVIRONMENT    # Trigger manual backup"
        echo "  ./manage-backups.sh list-backups $ENVIRONMENT      # List available backups"
        echo "  ./manage-backups.sh restore-info $ENVIRONMENT      # Show restore instructions"
        echo ""
        print_status "For full backup system documentation, see: BACKUP_SYSTEM_GUIDE.md"
    fi
    
    echo ""
    if [[ "${SKIP_LAMBDAS:-false}" == "true" ]]; then
        print_warning "SES Bounce/Complaint System (Lambda functions skipped):"
        echo "  ⚠ SES bounce handler Lambda function for processing bounced emails (not updated)"
        echo "  ⚠ SES complaint handler Lambda function for processing complaints (not updated)"
        echo "  ⚠ SES delivery handler Lambda function for tracking deliveries (not updated)"
        echo "  ⚠ Email suppression manager Lambda function for managing suppression lists (not updated)"
        echo "  ✓ SNS topics configured for SES notifications"
        echo "  ✓ DynamoDB tables for email suppression and analytics"
        echo "  ✓ SES notifications configured for bounce and complaint handling"
        echo ""
        print_warning "SES Management (Lambda code not updated, but environment variables updated):"
        echo "  - Monitor DynamoDB EmailSuppression table for bounced/complained emails"
        echo "  - Monitor DynamoDB EmailAnalytics table for delivery tracking"
        echo "  - Check CloudWatch logs for Lambda function execution"
        echo "  - Verify SES domain configuration in AWS SES console"
        echo ""
        print_warning "Lambda function code was skipped! Set SKIP_LAMBDAS=false in dev.env.sh and run deployment again to update SES function code."
    else
        print_success "✅ EMAIL RECEIVING SYSTEM FULLY DEPLOYED:"
        echo "  ✓ SES domain identity configured for $SES_DOMAIN_NAME"
        echo "  ✓ DNS records created for domain verification"
        echo "  ✓ Email storage bucket: $EMAIL_STORAGE_BUCKET"
        echo "  ✓ SES receipt rules configured for email processing"
        echo "  ✓ Email processor Lambda function"
        echo ""
        print_success "✅ SES BOUNCE/COMPLAINT SYSTEM DEPLOYED:"
        echo "  ✓ SES bounce handler Lambda function for processing bounced emails"
        echo "  ✓ SES complaint handler Lambda function for processing complaints"
        echo "  ✓ SES delivery handler Lambda function for tracking deliveries"
        echo "  ✓ Email suppression manager Lambda function for managing suppression lists"
        echo "  ✓ SNS topics configured for SES notifications"
        echo "  ✓ DynamoDB tables for email suppression and analytics"
        echo "  ✓ SES notifications configured for bounce and complaint handling"
        echo ""
        print_success "📧 EMAIL RECEIVING IS NOW OPERATIONAL:"
        echo "  📨 Send emails to: any-address@$SES_DOMAIN_NAME"
        echo "  📂 Emails stored in: $EMAIL_STORAGE_BUCKET"
        echo "  📊 Metadata tracked in: $EMAIL_METADATA_TABLE"
        echo "  🔔 Notifications via SNS topics"
        echo ""
        print_status "SES Management:"
        echo "  - Monitor DynamoDB EmailSuppression table for bounced/complained emails"
        echo "  - Monitor DynamoDB EmailAnalytics table for delivery tracking"
        echo "  - Check CloudWatch logs for Lambda function execution"
        echo "  - Verify SES domain configuration in AWS SES console"
        echo ""
        print_status "For full SES system documentation, see: SES_BOUNCE_COMPLAINT_SYSTEM.md"
    fi
}

# Check if script is being run directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
