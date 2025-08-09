#!/bin/bash

# Firebase Integration Deployment Readiness Checker
# Quick validation of Firebase integration before deployment

set -e

echo "🔥 Firebase Integration Deployment Readiness Check"
echo "=================================================="
echo

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Counters
PASS=0
FAIL=0
WARN=0

check_file() {
    local file_path="$1"
    local description="$2"
    
    if [[ -f "$file_path" ]]; then
        echo -e "  ${GREEN}✅${NC} $description"
        ((PASS++))
        return 0
    else
        echo -e "  ${RED}❌${NC} $description"
        ((FAIL++))
        return 1
    fi
}

check_content() {
    local file_path="$1"
    local search_term="$2" 
    local description="$3"
    
    if [[ -f "$file_path" ]] && grep -q "$search_term" "$file_path"; then
        echo -e "  ${GREEN}✅${NC} $description"
        ((PASS++))
        return 0
    else
        echo -e "  ${RED}❌${NC} $description"
        ((FAIL++))
        return 1
    fi
}

check_env_var() {
    local var_name="$1"
    local description="$2"
    
    if [[ -n "${!var_name}" ]]; then
        echo -e "  ${GREEN}✅${NC} $description: ${!var_name}"
        ((PASS++))
        return 0
    else
        echo -e "  ${YELLOW}⚠️${NC} $description: Not set"
        ((WARN++))
        return 1
    fi
}

echo -e "${BLUE}📁 Infrastructure Files${NC}"
check_file "infrastructure/main-stack.yaml" "Main stack template"
check_content "infrastructure/main-stack.yaml" "FirebaseProjectId" "Firebase parameters in main stack"
check_file "infrastructure/notification-queue.yaml" "Notification queue template"
check_content "infrastructure/notification-queue.yaml" "FirebaseNotificationQueue" "Firebase queue in notification template"
check_file "infrastructure/lambda-functions.yaml" "Lambda functions template"
check_content "infrastructure/lambda-functions.yaml" "FIREBASE_NOTIFICATION_QUEUE_URL" "Firebase environment variables"
echo

echo -e "${BLUE}🔥 Firebase Components${NC}"
check_file "lambda/sqs-process-firebase-notification-queue/main.py" "Firebase processor lambda"
check_file "lambda/sqs-process-firebase-notification-queue/requirements.txt" "Firebase processor requirements"
check_content "lambda/sqs-process-firebase-notification-queue/requirements.txt" "firebase-admin" "Firebase admin SDK dependency"
echo

echo -e "${BLUE}📚 Notification Utilities${NC}"
check_file "lambda/common_lib/notification_utils.py" "Notification utilities"
check_content "lambda/common_lib/notification_utils.py" "queue_firebase_notification" "Firebase notification function"
check_content "lambda/common_lib/notification_utils.py" "queue_order_firebase_notification" "Order Firebase notifications"
check_content "lambda/common_lib/notification_utils.py" "queue_appointment_firebase_notification" "Appointment Firebase notifications"
echo

echo -e "${BLUE}📋 Business Logic Integration${NC}"
check_content "lambda/api-create-appointment/main.py" "queue_appointment_firebase_notification" "Appointment creation Firebase notification"
check_content "lambda/api-create-order/main.py" "queue_order_firebase_notification" "Order creation Firebase notification"
check_content "lambda/api-create-inquiry/main.py" "queue_inquiry_firebase_notification" "Inquiry creation Firebase notification"
check_content "lambda/api-send-message/main.py" "queue_message_firebase_notification" "Message Firebase notification"
echo

echo -e "${BLUE}🚀 Deployment Scripts${NC}"
check_file "deploy.sh" "Main deployment script"
check_content "deploy.sh" "FIREBASE_PROJECT_ID" "Firebase parameter validation in deploy script"
check_file "config/environments.sh" "Environment configuration"
check_content "config/environments.sh" "FIREBASE" "Firebase variables in environment config"
check_file "update-lambdas.sh" "Lambda update script"
echo

echo -e "${BLUE}🔧 Environment Variables${NC}"
if check_env_var "ENABLE_FIREBASE_NOTIFICATIONS" "Firebase Notifications Enable Flag"; then
    if [[ "${ENABLE_FIREBASE_NOTIFICATIONS}" == "true" ]]; then
        check_env_var "FIREBASE_PROJECT_ID" "Firebase Project ID"
        check_env_var "FIREBASE_SERVICE_ACCOUNT_KEY" "Firebase Service Account Key"
    else
        echo -e "  ${YELLOW}⚠️${NC} Firebase notifications are disabled (ENABLE_FIREBASE_NOTIFICATIONS=false)"
        ((WARN++))
    fi
else
    echo -e "  ${YELLOW}⚠️${NC} ENABLE_FIREBASE_NOTIFICATIONS not set - defaulting to disabled"
    ((WARN++))
fi
echo

echo -e "${BLUE}📝 Documentation${NC}"
check_file "FIREBASE_SETUP_GUIDE.md" "Firebase setup guide"
check_file "FIREBASE_INTEGRATION_COMPLETE.md" "Integration completion summary"
check_file "FIREBASE_STATUS_FINAL.md" "Final status and testing guide"
echo

# Summary
echo "🏁 Summary"
echo "=========="
echo -e "✅ Passed: ${GREEN}$PASS${NC}"
echo -e "❌ Failed: ${RED}$FAIL${NC}"
echo -e "⚠️  Warnings: ${YELLOW}$WARN${NC}"
echo

if [[ $FAIL -eq 0 ]]; then
    if [[ $WARN -eq 0 ]]; then
        echo -e "${GREEN}🎉 All checks passed! Ready for deployment.${NC}"
        echo
        echo "Next steps:"
        if [[ "${ENABLE_FIREBASE_NOTIFICATIONS:-false}" == "true" ]]; then
            echo "1. Ensure Firebase project and credentials are configured"
            echo "2. Run: ./deploy.sh"
            echo "3. Test end-to-end Firebase notification flow"
        else
            echo "1. To enable Firebase: export ENABLE_FIREBASE_NOTIFICATIONS=true"
            echo "2. Set Firebase credentials (if enabling)"
            echo "3. Run: ./deploy.sh"
        fi
    else
        echo -e "${YELLOW}⚠️  Ready for deployment with warnings.${NC}"
        if [[ "${ENABLE_FIREBASE_NOTIFICATIONS:-false}" == "true" ]]; then
            echo "Consider fixing Firebase configuration for full functionality."
        else
            echo "Firebase notifications are disabled - this is optional."
        fi
    fi
    exit 0
else
    echo -e "${RED}❌ $FAIL critical issues found. Please fix before deployment.${NC}"
    exit 1
fi
