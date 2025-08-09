#!/bin/bash

# Firebase Notification Integration Validation Script
# This script validates that Firebase Cloud Messaging integration is properly configured

set -e

echo "🔥 Validating Firebase Notification Integration"
echo "=============================================="

# Check if main infrastructure files exist
echo "✅ Checking infrastructure files..."

if [[ ! -f "infrastructure/notification-queue.yaml" ]]; then
    echo "❌ notification-queue.yaml not found"
    exit 1
fi

if [[ ! -f "infrastructure/lambda-functions.yaml" ]]; then
    echo "❌ lambda-functions.yaml not found"
    exit 1
fi

if [[ ! -f "infrastructure/main-stack.yaml" ]]; then
    echo "❌ main-stack.yaml not found"
    exit 1
fi

echo "✅ Infrastructure files exist"

# Check Firebase processor lambda
echo "✅ Checking Firebase processor lambda..."

if [[ ! -f "lambda/sqs-process-firebase-notification-queue/main.py" ]]; then
    echo "❌ Firebase processor lambda not found"
    exit 1
fi

if [[ ! -f "lambda/sqs-process-firebase-notification-queue/requirements.txt" ]]; then
    echo "❌ Firebase processor requirements.txt not found"
    exit 1
fi

echo "✅ Firebase processor lambda exists"

# Check notification utilities
echo "✅ Checking notification utilities..."

if [[ ! -f "lambda/common_lib/notification_utils.py" ]]; then
    echo "❌ notification_utils.py not found"
    exit 1
fi

# Check for Firebase functions in notification_utils.py
if ! grep -q "queue_firebase_notification" lambda/common_lib/notification_utils.py; then
    echo "❌ queue_firebase_notification function not found in notification_utils.py"
    exit 1
fi

if ! grep -q "queue_order_firebase_notification" lambda/common_lib/notification_utils.py; then
    echo "❌ queue_order_firebase_notification function not found"
    exit 1
fi

if ! grep -q "queue_appointment_firebase_notification" lambda/common_lib/notification_utils.py; then
    echo "❌ queue_appointment_firebase_notification function not found"
    exit 1
fi

if ! grep -q "queue_inquiry_firebase_notification" lambda/common_lib/notification_utils.py; then
    echo "❌ queue_inquiry_firebase_notification function not found"
    exit 1
fi

if ! grep -q "queue_message_firebase_notification" lambda/common_lib/notification_utils.py; then
    echo "❌ queue_message_firebase_notification function not found"
    exit 1
fi

if ! grep -q "queue_payment_firebase_notification" lambda/common_lib/notification_utils.py; then
    echo "❌ queue_payment_firebase_notification function not found"
    exit 1
fi

if ! grep -q "queue_user_assignment_firebase_notification" lambda/common_lib/notification_utils.py; then
    echo "❌ queue_user_assignment_firebase_notification function not found"
    exit 1
fi

echo "✅ All Firebase notification functions found in notification_utils.py"

# Check infrastructure components
echo "✅ Checking infrastructure components..."

# Check for Firebase queue in notification-queue.yaml
if ! grep -q "FirebaseNotificationQueue" infrastructure/notification-queue.yaml; then
    echo "❌ Firebase notification queue not found in notification-queue.yaml"
    exit 1
fi

if ! grep -q "FirebaseNotificationDLQ" infrastructure/notification-queue.yaml; then
    echo "❌ Firebase notification DLQ not found in notification-queue.yaml"
    exit 1
fi

if ! grep -q "SqsProcessFirebaseNotificationQueue" infrastructure/notification-queue.yaml; then
    echo "❌ Firebase processor lambda not found in notification-queue.yaml"
    exit 1
fi

echo "✅ Firebase queue infrastructure found"

# Check for Firebase parameters in main-stack.yaml
if ! grep -q "FirebaseProjectId" infrastructure/main-stack.yaml; then
    echo "❌ Firebase project ID parameter not found in main-stack.yaml"
    exit 1
fi

if ! grep -q "FirebaseServiceAccountKey" infrastructure/main-stack.yaml; then
    echo "❌ Firebase service account key parameter not found in main-stack.yaml"
    exit 1
fi

echo "✅ Firebase parameters found in main-stack.yaml"

# Check lambda environment variables
echo "✅ Checking lambda environment variables..."

# Count how many lambdas have Firebase environment variables
firebase_env_count=$(grep -c "FIREBASE_NOTIFICATION_QUEUE_URL" infrastructure/lambda-functions.yaml || echo "0")

if [[ $firebase_env_count -lt 8 ]]; then
    echo "❌ Only $firebase_env_count lambdas have Firebase environment variables (expected at least 8)"
    exit 1
fi

echo "✅ $firebase_env_count lambdas have Firebase environment variables"

# Check business logic lambdas for Firebase integration
echo "✅ Checking business logic lambdas for Firebase integration..."

# List of lambdas that should have Firebase notifications
declare -a firebase_lambdas=(
    "api-create-appointment"
    "api-update-appointment" 
    "api-create-order"
    "api-update-order"
    "api-create-inquiry"
    "api-send-message"
    "api-take-user"
    "api-confirm-cash-payment"
    "api-confirm-stripe-payment"
    "api-webhook-stripe-payment"
)

missing_integration=false

for lambda_name in "${firebase_lambdas[@]}"; do
    lambda_file="lambda/$lambda_name/main.py"
    
    if [[ ! -f "$lambda_file" ]]; then
        echo "⚠️  Warning: $lambda_file not found"
        continue
    fi
    
    if ! grep -q "firebase" "$lambda_file"; then
        echo "❌ $lambda_name missing Firebase notification integration"
        missing_integration=true
    else
        echo "✅ $lambda_name has Firebase integration"
    fi
done

if [[ "$missing_integration" == true ]]; then
    echo "❌ Some lambdas are missing Firebase integration"
    exit 1
fi

echo "✅ All business logic lambdas have Firebase integration"

# Check requirements.txt for Firebase processor
echo "✅ Checking Firebase processor dependencies..."

if ! grep -q "firebase-admin" lambda/sqs-process-firebase-notification-queue/requirements.txt; then
    echo "❌ firebase-admin not found in Firebase processor requirements.txt"
    exit 1
fi

if ! grep -q "boto3" lambda/sqs-process-firebase-notification-queue/requirements.txt; then
    echo "❌ boto3 not found in Firebase processor requirements.txt"
    exit 1
fi

echo "✅ Firebase processor dependencies are correct"

# Summary
echo ""
echo "🎉 Firebase Notification Integration Validation Complete!"
echo "======================================================="
echo "✅ All infrastructure components are in place"
echo "✅ Firebase processor lambda is configured"
echo "✅ Notification utilities have all Firebase functions"
echo "✅ $firebase_env_count lambdas have Firebase environment variables"
echo "✅ All business logic lambdas have Firebase integration"
echo "✅ Firebase processor dependencies are correct"
echo ""
echo "🚀 Ready for deployment!"
echo ""
echo "Next steps:"
echo "1. Set Firebase project ID and service account key in CloudFormation parameters"
echo "2. Deploy the infrastructure stacks"
echo "3. Test Firebase notifications end-to-end"
echo "4. Monitor Firebase notification queue and processor logs"
