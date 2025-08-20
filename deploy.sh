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
        print_warning "MAIL_FROM_ADDRESS not set, using default: mail@autolabsolutions.com"
        export MAIL_FROM_ADDRESS="mail@autolabsolutions.com"
    fi
    
    if [[ -z "$SES_REGION" ]]; then
        print_warning "SES_REGION not set, using default: ap-southeast-2"
        export SES_REGION="ap-southeast-2"
    fi
    
    # Check Email Storage configuration
    if [[ -z "$NO_REPLY_EMAIL" ]]; then
        if [ "$ENVIRONMENT" = "production" ]; then
            print_warning "NO_REPLY_EMAIL not set, using default: noreply@autolabsolutions.com"
            export NO_REPLY_EMAIL="noreply@autolabsolutions.com"
        else
            print_warning "NO_REPLY_EMAIL not set, using default: noreply@autolabsolutions.com"
            export NO_REPLY_EMAIL="noreply@autolabsolutions.com"
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

# Check if function exists in AWS Lambda
function_exists() {
    local function_name=$1
    aws lambda get-function --function-name "$function_name" &> /dev/null
    return $?
}

# Package Lambda functions
package_lambdas() {
    print_status "Packaging Lambda functions..."
    
    # Create or clean the tmp directory
    mkdir -p lambda/tmp
    rm -rf lambda/tmp/*
    
    # Function to package a single Lambda
    package_lambda() {
        local lambda_dir=$1
        local lambda_name=$(basename "$lambda_dir")
        
        print_status "Packaging $lambda_name..."
        
        # Create temporary working directory
        local temp_dir="lambda/tmp/$lambda_name"
        mkdir -p "$temp_dir"
        
        # Copy Lambda function code
        cp -r "$lambda_dir"/* "$temp_dir/"
        
        # Install dependencies if requirements.txt exists
        if [[ -f "$temp_dir/requirements.txt" ]]; then
            pip3 install -r "$temp_dir/requirements.txt" -t "$temp_dir/" --quiet
        fi
        
        # Copy common library if it exists
        if [[ -d "lambda/common_lib" ]]; then
            cp -r lambda/common_lib "$temp_dir/"
        fi
        
        # Create ZIP file
        cd "$temp_dir"
        zip -r "../${lambda_name}.zip" . > /dev/null
        cd - > /dev/null
        
        print_success "Packaged $lambda_name"
    }
    
    # Package all Lambda functions
    for lambda_dir in lambda/*/; do
        if [[ -d "$lambda_dir" && "$lambda_dir" != "lambda/tmp/" && "$lambda_dir" != "lambda/common_lib/" ]]; then
            package_lambda "$lambda_dir"
        fi
    done
    
    print_success "All Lambda functions packaged"
}

# Update Lambda function code
update_lambda_code() {
    local lambda_name=$1
    local zip_file="lambda/tmp/${lambda_name}.zip"
    local function_name="${lambda_name}-${ENVIRONMENT}"
    
    if [[ ! -f "$zip_file" ]]; then
        print_error "ZIP file not found: $zip_file"
        return 1
    fi
    
    if function_exists "$function_name"; then
        print_status "Updating Lambda function: $function_name"
        aws lambda update-function-code \
            --function-name "$function_name" \
            --zip-file "fileb://$zip_file" > /dev/null
        print_success "Updated Lambda function: $function_name"
    else
        print_warning "Lambda function does not exist (will be created by CloudFormation): $function_name"
    fi
}

# Update Invoice Processor Lambda specifically
update_invoice_processor_lambda() {
    print_status "Updating Invoice Processor Lambda..."
    
    local function_name="invoice-processor-${ENVIRONMENT}"
    local zip_file="lambda/tmp/sqs-process-invoice-queue.zip"
    
    if [[ ! -f "$zip_file" ]]; then
        print_error "Invoice processor ZIP file not found: $zip_file"
        return 1
    fi
    
    if function_exists "$function_name"; then
        print_status "Updating Invoice Processor Lambda function: $function_name"
        aws lambda update-function-code \
            --function-name "$function_name" \
            --zip-file "fileb://$zip_file" > /dev/null
        
        print_success "✅ Invoice Processor Lambda updated successfully"
        print_status "Invoice processing will continue asynchronously via SQS"
    else
        print_warning "Invoice Processor Lambda function does not exist (will be created by CloudFormation): $function_name"
    fi
    
    # Update Email Notification Processor Lambda
    local email_function_name="email-notification-processor-${ENVIRONMENT}"
    local email_zip_file="lambda/tmp/sqs-process-email-notification-queue.zip"
    
    if [[ -f "$email_zip_file" ]]; then
        if function_exists "$email_function_name"; then
            print_status "Updating Email Notification Processor Lambda function: $email_function_name"
            aws lambda update-function-code \
                --function-name "$email_function_name" \
                --zip-file "fileb://$email_zip_file" > /dev/null
            
            print_success "✅ Email Notification Processor Lambda updated successfully"
        else
            print_warning "Email Notification Processor Lambda function does not exist (will be created by CloudFormation): $email_function_name"
        fi
    fi
    
    # Update WebSocket Notification Processor Lambda
    local websocket_function_name="websocket-notification-processor-${ENVIRONMENT}"
    local websocket_zip_file="lambda/tmp/sqs-process-websocket-notification-queue.zip"
    
    if [[ -f "$websocket_zip_file" ]]; then
        if function_exists "$websocket_function_name"; then
            print_status "Updating WebSocket Notification Processor Lambda function: $websocket_function_name"
            aws lambda update-function-code \
                --function-name "$websocket_function_name" \
                --zip-file "fileb://$websocket_zip_file" > /dev/null
            
            print_success "✅ WebSocket Notification Processor Lambda updated successfully"
        else
            print_warning "WebSocket Notification Processor Lambda function does not exist (will be created by CloudFormation): $websocket_function_name"
        fi
    fi
    
    # Update Firebase Notification Processor Lambda if enabled
    if [[ "${ENABLE_FIREBASE_NOTIFICATIONS:-false}" == "true" ]]; then
        local firebase_function_name="firebase-notification-processor-${ENVIRONMENT}"
        local firebase_zip_file="lambda/tmp/sqs-process-firebase-notification-queue.zip"
        
        if [[ -f "$firebase_zip_file" ]]; then
            if function_exists "$firebase_function_name"; then
                print_status "Updating Firebase Notification Processor Lambda function: $firebase_function_name"
                aws lambda update-function-code \
                    --function-name "$firebase_function_name" \
                    --zip-file "fileb://$firebase_zip_file" > /dev/null
                
                print_success "✅ Firebase Notification Processor Lambda updated successfully"
            else
                print_warning "Firebase Notification Processor Lambda function does not exist (will be created by CloudFormation): $firebase_function_name"
            fi
        fi
    fi
}

# Update backup Lambda specifically
update_backup_lambda() {
    print_status "Updating Backup System Lambda..."
    
    local automated_function_name="backup-automated-${ENVIRONMENT}"
    local manual_function_name="backup-manual-${ENVIRONMENT}"
    local api_function_name="api-backup-restore-${ENVIRONMENT}"
    
    local automated_zip_file="lambda/tmp/backup-restore.zip"
    
    if [[ ! -f "$automated_zip_file" ]]; then
        print_warning "Backup Lambda ZIP file not found: $automated_zip_file"
        return 0
    fi
    
    # Update automated backup function
    if function_exists "$automated_function_name"; then
        print_status "Updating Automated Backup Lambda function: $automated_function_name"
        aws lambda update-function-code \
            --function-name "$automated_function_name" \
            --zip-file "fileb://$automated_zip_file" > /dev/null
        
        print_success "✅ Automated Backup Lambda updated successfully"
    else
        print_warning "Automated Backup Lambda function does not exist (will be created by CloudFormation): $automated_function_name"
    fi
    
    # Update manual backup function
    if function_exists "$manual_function_name"; then
        print_status "Updating Manual Backup Lambda function: $manual_function_name"
        aws lambda update-function-code \
            --function-name "$manual_function_name" \
            --zip-file "fileb://$automated_zip_file" > /dev/null
        
        print_success "✅ Manual Backup Lambda updated successfully"
    else
        print_warning "Manual Backup Lambda function does not exist (will be created by CloudFormation): $manual_function_name"
    fi
    
    # Update API backup/restore function
    local api_zip_file="lambda/tmp/api-backup-restore.zip"
    if [[ -f "$api_zip_file" ]]; then
        if function_exists "$api_function_name"; then
            print_status "Updating API Backup/Restore Lambda function: $api_function_name"
            aws lambda update-function-code \
                --function-name "$api_function_name" \
                --zip-file "fileb://$api_zip_file" > /dev/null
            
            print_success "✅ API Backup/Restore Lambda updated successfully"
        else
            print_warning "API Backup/Restore Lambda function does not exist (will be created by CloudFormation): $api_function_name"
        fi
    fi
}

# Update all Lambda functions
update_all_lambdas() {
    print_status "Updating all Lambda functions..."
    
    # Update specific system functions first
    update_invoice_processor_lambda
    update_backup_lambda
    
    # Update all other Lambda functions
    for zip_file in lambda/tmp/*.zip; do
        if [[ -f "$zip_file" ]]; then
            local lambda_name=$(basename "$zip_file" .zip)
            
            # Skip functions already handled by specific update functions
            if [[ "$lambda_name" == "sqs-process-invoice-queue" ]] || \
               [[ "$lambda_name" == "sqs-process-email-notification-queue" ]] || \
               [[ "$lambda_name" == "sqs-process-websocket-notification-queue" ]] || \
               [[ "$lambda_name" == "sqs-process-firebase-notification-queue" ]] || \
               [[ "$lambda_name" == "backup-restore" ]] || \
               [[ "$lambda_name" == "api-backup-restore" ]]; then
                continue
            fi
            
            update_lambda_code "$lambda_name"
        fi
    done
    
    print_success "All Lambda functions updated"
}

# Deploy CloudFormation stack
deploy_stack() {
    print_status "Deploying CloudFormation stack..."
    
    # Prepare CloudFormation parameters
    local cf_params=""
    
    # Core Environment Configuration
    cf_params="$cf_params ParameterKey=Environment,ParameterValue=$ENVIRONMENT"
    cf_params="$cf_params ParameterKey=SharedKey,ParameterValue=$SHARED_KEY"
    
    # S3 Bucket Configuration
    cf_params="$cf_params ParameterKey=S3BucketName,ParameterValue=$REPORTS_BUCKET_NAME"
    cf_params="$cf_params ParameterKey=CloudFormationBucket,ParameterValue=$CLOUDFORMATION_BUCKET"
    cf_params="$cf_params ParameterKey=BackupBucketName,ParameterValue=$BACKUP_BUCKET_NAME"
    cf_params="$cf_params ParameterKey=ReportsBucketName,ParameterValue=$REPORTS_BUCKET_NAME"
    
    # Payment Integration (Stripe)
    cf_params="$cf_params ParameterKey=StripeSecretKey,ParameterValue=$STRIPE_SECRET_KEY"
    cf_params="$cf_params ParameterKey=StripeWebhookSecret,ParameterValue=$STRIPE_WEBHOOK_SECRET"
    
    # Authentication (Auth0)
    cf_params="$cf_params ParameterKey=Auth0Domain,ParameterValue=$AUTH0_DOMAIN"
    cf_params="$cf_params ParameterKey=Auth0Audience,ParameterValue=$AUTH0_AUDIENCE"
    
    # Frontend Website Configuration
    cf_params="$cf_params ParameterKey=EnableFrontendWebsite,ParameterValue=$ENABLE_FRONTEND_WEBSITE"
    cf_params="$cf_params ParameterKey=FrontendDomainName,ParameterValue=$FRONTEND_DOMAIN_NAME"
    cf_params="$cf_params ParameterKey=FrontendHostedZoneId,ParameterValue=$FRONTEND_HOSTED_ZONE_ID"
    cf_params="$cf_params ParameterKey=FrontendAcmCertificateArn,ParameterValue=$FRONTEND_ACM_CERTIFICATE_ARN"
    cf_params="$cf_params ParameterKey=EnableCustomDomain,ParameterValue=$ENABLE_CUSTOM_DOMAIN"
    cf_params="$cf_params ParameterKey=FrontendRootUrl,ParameterValue=$FRONTEND_ROOT_URL"
    
    # Email Service (SES) Configuration
    cf_params="$cf_params ParameterKey=MailSendingAddress,ParameterValue=$NO_REPLY_EMAIL"
    cf_params="$cf_params ParameterKey=SesRegion,ParameterValue=$SES_REGION"
    cf_params="$cf_params ParameterKey=MailReceivingAddress,ParameterValue=$MAIL_FROM_ADDRESS"
    cf_params="$cf_params ParameterKey=EmailStorageBucketName,ParameterValue=$EMAIL_STORAGE_BUCKET"
    cf_params="$cf_params ParameterKey=EmailMetadataTableName,ParameterValue=$EMAIL_METADATA_TABLE"
    cf_params="$cf_params ParameterKey=SESHostedZoneId,ParameterValue=${SES_HOSTED_ZONE_ID:-}"
    cf_params="$cf_params ParameterKey=SESDomainName,ParameterValue=${SES_DOMAIN_NAME:-autolabsolutions.com}"
    
    # Firebase Notifications (Optional)
    cf_params="$cf_params ParameterKey=EnableFirebaseNotifications,ParameterValue=${ENABLE_FIREBASE_NOTIFICATIONS:-false}"
    cf_params="$cf_params ParameterKey=FirebaseProjectId,ParameterValue=${FIREBASE_PROJECT_ID:-}"
    cf_params="$cf_params ParameterKey=FirebaseServiceAccountKey,ParameterValue=${FIREBASE_SERVICE_ACCOUNT_KEY:-}"
    
    # API Custom Domains (Optional)
    cf_params="$cf_params ParameterKey=EnableApiCustomDomains,ParameterValue=${ENABLE_API_CUSTOM_DOMAINS:-false}"
    cf_params="$cf_params ParameterKey=ApiDomainName,ParameterValue=${API_DOMAIN_NAME:-}"
    cf_params="$cf_params ParameterKey=WebSocketDomainName,ParameterValue=${WEBSOCKET_DOMAIN_NAME:-}"
    cf_params="$cf_params ParameterKey=ApiHostedZoneId,ParameterValue=${API_HOSTED_ZONE_ID:-}"
    cf_params="$cf_params ParameterKey=ApiAcmCertificateArn,ParameterValue=${API_ACM_CERTIFICATE_ARN:-}"
    
    # Reports Custom Domain (Optional)
    cf_params="$cf_params ParameterKey=EnableReportsCustomDomain,ParameterValue=${ENABLE_REPORTS_CUSTOM_DOMAIN:-false}"
    cf_params="$cf_params ParameterKey=ReportsDomainName,ParameterValue=${REPORTS_DOMAIN_NAME:-}"
    cf_params="$cf_params ParameterKey=ReportsHostedZoneId,ParameterValue=${REPORTS_HOSTED_ZONE_ID:-}"
    cf_params="$cf_params ParameterKey=ReportsAcmCertificateArn,ParameterValue=${REPORTS_ACM_CERTIFICATE_ARN:-}"
    
    # Check if stack exists
    if aws cloudformation describe-stacks --stack-name "$STACK_NAME" &> /dev/null; then
        print_status "Updating existing CloudFormation stack: $STACK_NAME"
        aws cloudformation update-stack \
            --stack-name "$STACK_NAME" \
            --template-url "https://$CLOUDFORMATION_BUCKET.s3.$AWS_REGION.amazonaws.com/main-stack.yaml" \
            --parameters $cf_params \
            --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
            --region "$AWS_REGION"
    else
        print_status "Creating new CloudFormation stack: $STACK_NAME"
        aws cloudformation create-stack \
            --stack-name "$STACK_NAME" \
            --template-url "https://$CLOUDFORMATION_BUCKET.s3.$AWS_REGION.amazonaws.com/main-stack.yaml" \
            --parameters $cf_params \
            --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
            --region "$AWS_REGION"
    fi
    
    print_status "Waiting for CloudFormation stack operation to complete..."
    aws cloudformation wait stack-update-complete --stack-name "$STACK_NAME" --region "$AWS_REGION" 2>/dev/null || \
    aws cloudformation wait stack-create-complete --stack-name "$STACK_NAME" --region "$AWS_REGION"
    
    print_success "CloudFormation stack deployed successfully"
}

# Check SES verification status
check_ses_verification_status() {
    print_status "Checking SES verification status..."
    
    local domain="$SES_DOMAIN_NAME"
    
    # Check domain verification status
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
    
    print_status "SES Verification Status:"
    print_status "  Domain ($domain): $domain_status"
    
    # Check DNS records if hosted zone is configured
    if [ -n "$SES_HOSTED_ZONE_ID" ]; then
        print_status "  DNS Records: Managed by CloudFormation (Route53 Hosted Zone: $SES_HOSTED_ZONE_ID)"
        
        # Check if verification DNS record exists
        local verification_record_exists="false"
        if aws route53 list-resource-record-sets \
            --hosted-zone-id "$SES_HOSTED_ZONE_ID" \
            --query "ResourceRecordSets[?Name=='_amazonses.${domain}.' && Type=='TXT']" \
            --output text 2>/dev/null | grep -q .; then
            verification_record_exists="true"
            print_status "  DNS TXT Record: ✅ Created (_amazonses.$domain)"
        else
            print_warning "  DNS TXT Record: ⚠️ Not found (_amazonses.$domain)"
        fi
        
        # Check if MX record exists
        local mx_record_exists="false"
        if aws route53 list-resource-record-sets \
            --hosted-zone-id "$SES_HOSTED_ZONE_ID" \
            --query "ResourceRecordSets[?Name=='${domain}.' && Type=='MX']" \
            --output text 2>/dev/null | grep -q "inbound-smtp"; then
            mx_record_exists="true"
            print_status "  DNS MX Record: ✅ Created ($domain)"
        else
            print_warning "  DNS MX Record: ⚠️ Not found ($domain)"
        fi
    else
        print_warning "  DNS Records: Manual configuration required (no hosted zone configured)"
        print_warning "  Set SES_HOSTED_ZONE_ID for automatic DNS management"
    fi
    
    # Provide status assessment and guidance
    case $domain_status in
        "Success")
            print_success "✅ SES domain is verified and ready for email receiving!"
            print_success "📧 You can send and receive emails for @$domain"
            return 0
            ;;
        "Pending")
            print_warning "⏳ SES domain verification is pending."
            if [ -n "$SES_HOSTED_ZONE_ID" ]; then
                print_status "   DNS records are managed by CloudFormation."
                print_status "   Verification typically completes within 30 minutes to 24 hours."
            else
                print_warning "   Manual DNS configuration required:"
                print_warning "   1. Create TXT record: _amazonses.$domain"
                print_warning "   2. Create MX record: $domain -> 10 inbound-smtp.$SES_REGION.amazonses.com"
                print_warning "   3. Check AWS SES console for verification token value"
            fi
            return 0
            ;;
        "Failed")
            print_error "❌ SES domain verification failed."
            print_error "   Check DNS records and SES console for details."
            return 1
            ;;
        "Unknown"|"NotFound")
            print_warning "⚠️ SES domain not found or verification not started."
            print_warning "   This may indicate an issue with CloudFormation SES identity creation."
            return 1
            ;;
        *)
            print_warning "⚠️ Unknown verification status: $domain_status"
            print_warning "   Check AWS SES Console for detailed verification status."
            return 1
            ;;
    esac
}

# Verify SES email setup
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
    
    # Get domain verification status
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
    
    print_status "SES domain verification status for $SES_DOMAIN_NAME: $verification_status"
    
    case $verification_status in
        "Success")
            print_success "✅ SES domain is verified! Email receiving is fully operational."
            print_success "📧 You can now receive emails at any address @$SES_DOMAIN_NAME"
            ;;
        "Pending")
            print_warning "⏳ SES domain verification is pending."
            print_status "   DNS records have been created automatically by CloudFormation."
            print_status "   Verification will complete automatically within 24 hours."
            ;;
        "Failed")
            print_error "❌ SES domain verification failed."
            print_error "   Check DNS records in Route53 and SES console for details."
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
    echo "🤖 DNS Management: Automated via CloudFormation (Native Resources)"
    echo ""
    
    if [ "$verification_status" = "Success" ] && [ "$email_bucket_status" = "exists" ] && [ "$receipt_rules_count" -gt 0 ]; then
        print_success "🎉 EMAIL RECEIVING SYSTEM IS FULLY OPERATIONAL!"
        print_success "   Send test emails to: mail@$SES_DOMAIN_NAME"
        print_success "   Emails will be stored in: $EMAIL_STORAGE_BUCKET"
    elif [ "$verification_status" = "Pending" ]; then
        print_warning "⏳ Email system is deployed and DNS records were created automatically."
        print_warning "   System will be operational within 24 hours."
    else
        print_error "❌ Email receiving system has issues. Check the details above."
    fi
    echo ""
}

# Configure API Gateway
configure_api_gateway() {
    print_status "Configuring API Gateway..."
    
    # API Gateway configuration is handled by CloudFormation
    print_success "✅ API Gateway configured by CloudFormation"
    
    # Get API Gateway ID from CloudFormation outputs
    local api_id=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --query 'Stacks[0].Outputs[?OutputKey==`RestApiId`].OutputValue' \
        --output text 2>/dev/null)
    
    if [ -n "$api_id" ]; then
        print_success "API Gateway ID: $api_id"
    else
        print_warning "Could not retrieve API Gateway ID from stack outputs"
    fi
}

# Update Auth0 configuration
update_auth0_config() {
    print_status "Updating Auth0 configuration..."
    
    # Get API Gateway endpoint from CloudFormation outputs
    local api_endpoint=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --query 'Stacks[0].Outputs[?OutputKey==`RestApiEndpoint`].OutputValue' \
        --output text 2>/dev/null)
    
    if [ -n "$api_endpoint" ]; then
        print_success "API endpoint: $api_endpoint"
        print_status "Update your Auth0 configuration to use this endpoint"
    else
        print_warning "Could not retrieve API endpoint from stack outputs"
    fi
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

    # Conditionally update Lambda functions
    if [[ "${SKIP_LAMBDAS:-false}" == "true" ]]; then
        print_warning "Skipping Lambda function code updates as requested"
    else
        update_all_lambdas
    fi
    
    configure_api_gateway
    
    # SES email receiving verification (all managed by CloudFormation)
    print_status "Verifying SES email receiving setup..."
    print_success "✅ SES identities, DNS records, and receipt rules are managed by CloudFormation"
    print_success "✅ S3 bucket notifications are managed by CloudFormation"
    print_success "✅ Bounce/complaint notifications are managed by CloudFormation"
    
    # Check verification status
    check_ses_verification_status
    verify_ses_email_setup
    
    # Always update Lambda environment variables (even when SKIP_LAMBDAS=true)
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
    
    # Print final summary
    print_status "=========================================="
    print_status "SES Email System Configuration Summary"
    print_status "=========================================="
    
    local domain="${MAIL_FROM_ADDRESS##*@}"
    
    print_status "Environment: $ENVIRONMENT"
    print_status "Domain: $domain"
    print_status "Email receiving address: $MAIL_FROM_ADDRESS"
    print_status "SES Region: $SES_REGION"
    print_status "DNS Management: Automated via CloudFormation"
    
    # Quick verification status check
    local domain_status="Unknown"
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
    
    if [ "$domain_status" = "Success" ]; then
        print_success "✅ SES domain is verified - Email receiving is ready!"
    elif [ "$domain_status" = "Pending" ]; then
        print_warning "⏳ SES verification is pending - Email receiving will work once verified"
        print_warning "DNS propagation can take up to 30 minutes"
    else
        print_warning "⚠ SES verification status unknown - Check AWS SES Console"
    fi
    
    print_status "To test email receiving:"
    print_status "  1. Wait for SES verification to complete"
    print_status "  2. Send test email to: $MAIL_FROM_ADDRESS"
    print_status "  3. Check S3 bucket and DynamoDB for stored email"
    print_status "=========================================="

    # Print important endpoints
    print_status "Important endpoints:"
    aws cloudformation describe-stacks \
        --stack-name $STACK_NAME \
        --query 'Stacks[0].Outputs[?OutputKey==`RestApiEndpoint`||OutputKey==`WebSocketApiEndpoint`||OutputKey==`InvoiceQueueUrl`||OutputKey==`EmailNotificationQueueUrl`||OutputKey==`WebSocketNotificationQueueUrl`||OutputKey==`FirebaseNotificationQueueUrl`||OutputKey==`SESBounceTopicArn`||OutputKey==`SESComplaintTopicArn`||OutputKey==`EmailSuppressionTableName`||OutputKey==`EmailAnalyticsTableName`].[OutputKey,OutputValue]' \
        --output table

    # Print deployment summary
    echo ""
    if [[ "${SKIP_LAMBDAS:-false}" == "true" ]]; then
        print_warning "System Components (Lambda functions skipped):"
        echo "  ⚠ SQS Queues for async processing (created)"
        echo "  ⚠ Lambda function code (not updated)"
        echo "  ✓ Lambda environment variables (updated)"
        echo "  ✓ Infrastructure and configuration (deployed)"
        echo ""
        print_warning "Set SKIP_LAMBDAS=false in dev.env.sh and run deployment again to update Lambda function code."
    else
        print_success "✅ EMAIL RECEIVING SYSTEM FULLY DEPLOYED:"
        echo "  ✓ SES domain identity configured for $SES_DOMAIN_NAME"
        echo "  ✓ DNS records created automatically for domain verification"
        echo "  ✓ Email storage bucket with proper permissions"
        echo "  ✓ SES receipt rules configured for email processing"
        echo "  ✓ Email processor Lambda function"
        echo "  ✓ Bounce/complaint handlers for email deliverability"
        echo ""
        print_success "📧 EMAIL RECEIVING IS NOW OPERATIONAL:"
        echo "  📨 Send emails to: any-address@$SES_DOMAIN_NAME"
        echo "  📂 Emails stored automatically in S3"
        echo "  📊 Metadata tracked in DynamoDB"
        echo "  🔔 Notifications via SNS topics"
        echo ""
        print_success "✅ ASYNC PROCESSING SYSTEM DEPLOYED:"
        echo "  ✓ SQS queues for invoice, email, and WebSocket notifications"
        echo "  ✓ Lambda processors for all async operations"
        echo "  ✓ Firebase notifications (if enabled)"
        echo "  ✓ Automated backup system with scheduling"
        echo ""
        print_success "✅ BOUNCE/COMPLAINT HANDLING DEPLOYED:"
        echo "  ✓ SES bounce/complaint handlers"
        echo "  ✓ Email suppression list management"
        echo "  ✓ Delivery tracking and analytics"
    fi
}

# Check if script is being run directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
