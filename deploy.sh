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
    if [[ -z "$FROM_EMAIL" ]]; then
        print_warning "FROM_EMAIL not set, using default: noreply@autolabsolutions.com"
        export FROM_EMAIL="noreply@autolabsolutions.com"
    fi
    
    if [[ -z "$SES_REGION" ]]; then
        print_warning "SES_REGION not set, using default: ap-southeast-2"
        export SES_REGION="ap-southeast-2"
    fi
    
    print_status "SES Configuration:"
    print_status "  From Email: $FROM_EMAIL"
    print_status "  SES Region: $SES_REGION"
    
    # Check SES domain verification status
    local domain="${FROM_EMAIL##*@}"
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
        
        print_success "Firebase configuration validated"
        print_status "  Project ID: $FIREBASE_PROJECT_ID"
        print_status "  Service Account Key: ****[REDACTED]****"
    else
        # Firebase is disabled or not configured
        if [[ -n "$FIREBASE_PROJECT_ID" ]] || [[ -n "$FIREBASE_SERVICE_ACCOUNT_KEY" ]]; then
            print_warning "Firebase credentials detected but Firebase is not enabled"
            print_warning "To enable Firebase notifications: export ENABLE_FIREBASE_NOTIFICATIONS=true"
        else
            print_status "Firebase notifications are DISABLED (default)"
            print_status "To enable Firebase notifications:"
            print_status "  1. Create a Firebase project in Google Console"
            print_status "  2. Enable Firebase Cloud Messaging (FCM)"
            print_status "  3. Set: export ENABLE_FIREBASE_NOTIFICATIONS=true"
            print_status "  4. Set: export FIREBASE_PROJECT_ID='your-firebase-project-id'"
            print_status "  5. Set: export FIREBASE_SERVICE_ACCOUNT_KEY='base64-encoded-json'"
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
        
        # Upload to S3 - use different paths for different lambda types
        if [[ "$lambda_name" == sqs-process-*-notification-queue ]] || [[ "$lambda_name" == "backup-restore" ]] || [[ "$lambda_name" == "api-backup-restore" ]]; then
            # Notification processor lambdas and backup lambdas use lambda-packages/ path
            aws s3 cp "dist/lambda/$lambda_name.zip" "s3://$CLOUDFORMATION_BUCKET/lambda-packages/$lambda_name.zip"
        else
            # Standard lambdas use lambda/ path
            aws s3 cp "dist/lambda/$lambda_name.zip" "s3://$CLOUDFORMATION_BUCKET/lambda/$lambda_name.zip"
        fi
        
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

# Update Notification Processor Lambda function code (managed by NotificationQueueStack)
update_notification_processor_lambda() {
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
    
    print_status "Updating Notification Processor Lambda function code: $full_function_name"
    
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
            
            # Handle notification processing lambdas differently since they're managed by NotificationQueueStack
            if [[ "$lambda_name" == sqs-process-*-notification-queue ]]; then
                print_status "Updating $lambda_name (managed by NotificationQueueStack)..."
                update_notification_processor_lambda "$lambda_name"
            # Handle invoice processing lambda differently since it's managed by InvoiceQueueStack
            elif [ "$lambda_name" = "sqs-process-invoice-queue" ]; then
                print_status "Updating $lambda_name (managed by InvoiceQueueStack)..."
                update_invoice_processor_lambda "$lambda_name"
            # Handle backup/restore lambdas differently since they're managed by BackupSystemStack
            elif [[ "$lambda_name" == "backup-restore" || "$lambda_name" == "api-backup-restore" ]]; then
                print_status "Updating $lambda_name (managed by BackupSystemStack)..."
                update_backup_lambda "$lambda_name"
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
            S3BucketName=$S3_BUCKET_NAME \
            CloudFormationBucket=$CLOUDFORMATION_BUCKET \
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
            FromEmail="$FROM_EMAIL" \
            SesRegion="$SES_REGION" \
            EnableFirebaseNotifications="${ENABLE_FIREBASE_NOTIFICATIONS:-false}" \
            FirebaseProjectId="${FIREBASE_PROJECT_ID:-}" \
            FirebaseServiceAccountKey="${FIREBASE_SERVICE_ACCOUNT_KEY:-}" \
            EnableApiCustomDomains="${ENABLE_API_CUSTOM_DOMAINS:-false}" \
            ApiDomainName="${API_DOMAIN_NAME:-}" \
            WebSocketDomainName="${WEBSOCKET_DOMAIN_NAME:-}" \
            ApiHostedZoneId="${API_HOSTED_ZONE_ID:-}" \
            ApiAcmCertificateArn="${API_ACM_CERTIFICATE_ARN:-}" \
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

# Deploy backup system
deploy_backup_system() {
    print_status "Deploying backup system infrastructure..."
    
    # Note: Backup Lambda packages should already be uploaded by package_lambdas function
    # This function focuses on deploying the backup system CloudFormation stack
    
    local backup_stack_name="auto-lab-backup-system-${ENVIRONMENT}"
    
    # Check if backup Lambda packages exist in S3
    print_status "Verifying backup Lambda packages in S3..."
    
    if ! aws s3 ls "s3://$CLOUDFORMATION_BUCKET/lambda-packages/backup-restore.zip" --region "$AWS_REGION" &>/dev/null; then
        print_warning "Backup Lambda package not found in S3. This should have been uploaded by package_lambdas."
        print_warning "Backup system deployment may fail if packages are missing."
    fi
    
    if ! aws s3 ls "s3://$CLOUDFORMATION_BUCKET/lambda-packages/api-backup-restore.zip" --region "$AWS_REGION" &>/dev/null; then
        print_warning "API Backup Lambda package not found in S3. This should have been uploaded by package_lambdas."
        print_warning "Backup system deployment may fail if packages are missing."
    fi
    
    # Deploy backup system CloudFormation stack
    print_status "Deploying backup system CloudFormation stack..."
    
    aws cloudformation deploy \
        --template-file infrastructure/backup-system.yaml \
        --stack-name "$backup_stack_name" \
        --parameter-overrides \
            Environment="$ENVIRONMENT" \
            CloudFormationBucket="$CLOUDFORMATION_BUCKET" \
            ReportsBucketName="$REPORTS_BUCKET_NAME" \
        --capabilities CAPABILITY_NAMED_IAM \
        --region "$AWS_REGION"
    
    if [ $? -eq 0 ]; then
        print_success "Backup system deployed successfully"
        
        # Show backup system information
        print_status "Backup system components:"
        aws cloudformation describe-stacks \
            --stack-name "$backup_stack_name" \
            --query 'Stacks[0].Outputs[?OutputKey==`BackupLambdaFunctionArn`||OutputKey==`BackupScheduleRuleArn`||OutputKey==`BackupBucket`].[OutputKey,OutputValue]' \
            --output table --region "$AWS_REGION" 2>/dev/null || print_warning "Could not retrieve backup system outputs"
    else
        print_error "Failed to deploy backup system"
        return 1
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
    
    package_lambdas
    deploy_stack
    
    # Deploy backup system
    print_status "Deploying backup system..."
    deploy_backup_system
    
    update_all_lambdas
    configure_api_gateway
    
    # Update WebSocket endpoints in Lambda functions
    print_status "Updating WebSocket endpoints in Lambda functions..."
    ./update-websocket-endpoints.sh --env "$ENVIRONMENT"
    
    update_auth0_config
    
    # Initialize DynamoDB tables with required data
    print_status "Initializing DynamoDB tables with default data..."
    ./initialize-dynamodb-data.sh "$ENVIRONMENT"

    print_success "Deployment completed successfully!"

    # Print important endpoints
    print_status "Important endpoints:"
    aws cloudformation describe-stacks \
        --stack-name $STACK_NAME \
        --query 'Stacks[0].Outputs[?OutputKey==`RestApiEndpoint`||OutputKey==`WebSocketApiEndpoint`||OutputKey==`InvoiceQueueUrl`||OutputKey==`EmailNotificationQueueUrl`||OutputKey==`WebSocketNotificationQueueUrl`||OutputKey==`FirebaseNotificationQueueUrl`].[OutputKey,OutputValue]' \
        --output table

    # Print async processing status
    echo ""
    print_success "Async Processing Components Deployed:"
    echo "  ✓ SQS Invoice Queue for asynchronous invoice generation"
    echo "  ✓ Invoice Processor Lambda (sqs-process-invoice-queue)"
    echo "  ✓ SQS Email Notification Queue for asynchronous email processing"
    echo "  ✓ Email Notification Processor Lambda (sqs-process-email-notification-queue)"
    echo "  ✓ SQS WebSocket Notification Queue for asynchronous WebSocket processing"
    echo "  ✓ WebSocket Notification Processor Lambda (sqs-process-websocket-notification-queue)"
    
    # Show Firebase status
    if [[ "${ENABLE_FIREBASE_NOTIFICATIONS:-false}" == "true" ]]; then
        echo "  ✓ Firebase notifications ENABLED"
        echo "    - SQS Firebase Notification Queue for asynchronous Firebase processing"
        echo "    - Firebase Notification Processor Lambda (sqs-process-firebase-notification-queue)"
        echo "    - Project ID: ${FIREBASE_PROJECT_ID}"
    else
        echo "  • Firebase notifications DISABLED"
        echo "    - No Firebase resources deployed"
        echo "    - Firebase calls will be gracefully skipped"
    fi
    
    echo "  ✓ Payment confirmation Lambdas updated with async support"
    echo "  ✓ All business logic Lambdas updated to use notification queues"
    echo "  ✓ Shared notification_utils library deployed to all functions"
    echo ""
    print_status "All notification processing is now asynchronous via SQS queues!"
    
    echo ""
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
}

# Check if script is being run directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
