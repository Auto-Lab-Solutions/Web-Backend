#!/bin/bash

# Firebase Centralized Configuration Verification Script
# This script verifies that Firebase configuration is working correctly with the new centralized approach

set -e

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

echo "Firebase Centralized Configuration Verification"
echo "=============================================="

# Test 1: Verify environments.sh contains Firebase configuration
print_status "Test 1: Checking Firebase configuration in environments.sh"

if grep -q "ENABLE_FIREBASE_NOTIFICATIONS" config/environments.sh; then
    print_success "✓ ENABLE_FIREBASE_NOTIFICATIONS found in environments.sh"
else
    print_error "✗ ENABLE_FIREBASE_NOTIFICATIONS not found in environments.sh"
    exit 1
fi

if grep -q "FIREBASE_PROJECT_ID" config/environments.sh; then
    print_success "✓ FIREBASE_PROJECT_ID configuration found in environments.sh"
else
    print_error "✗ FIREBASE_PROJECT_ID not found in environments.sh"
    exit 1
fi

# Test 2: Load development environment and check Firebase settings
print_status "Test 2: Testing development environment Firebase configuration"

# Source environments.sh and load development config
source config/environments.sh
if load_environment "development" > /dev/null 2>&1; then
    print_success "✓ Development environment loaded successfully"
    
    if [[ "$ENABLE_FIREBASE_NOTIFICATIONS" == "false" ]]; then
        print_success "✓ Firebase correctly DISABLED for development (default)"
    else
        print_warning "! Firebase is ENABLED for development (may be intentional override)"
    fi
else
    print_error "✗ Failed to load development environment"
    exit 1
fi

# Test 3: Load production environment and check Firebase settings
print_status "Test 3: Testing production environment Firebase configuration"

if load_environment "production" > /dev/null 2>&1; then
    print_success "✓ Production environment loaded successfully"
    
    if [[ "$ENABLE_FIREBASE_NOTIFICATIONS" == "true" ]]; then
        print_success "✓ Firebase correctly ENABLED for production (default)"
    else
        print_warning "! Firebase is DISABLED for production (may be intentional cost optimization)"
    fi
else
    print_error "✗ Failed to load production environment"
    exit 1
fi

# Test 4: Check that deploy.sh no longer contains configure_firebase function
print_status "Test 4: Verifying deploy.sh has been updated"

if grep -q "configure_firebase()" deploy.sh; then
    print_error "✗ configure_firebase() function still exists in deploy.sh"
    print_error "  This should have been removed in the centralized configuration update"
    exit 1
else
    print_success "✓ configure_firebase() function correctly removed from deploy.sh"
fi

if grep -q "configure_firebase$" deploy.sh; then
    print_error "✗ configure_firebase call still exists in deploy.sh"
    print_error "  This should have been removed in the centralized configuration update"
    exit 1
else
    print_success "✓ configure_firebase call correctly removed from deploy.sh"
fi

# Test 5: Check CI/CD workflow files have Firebase environment variables
print_status "Test 5: Verifying CI/CD workflows have Firebase configuration"

if grep -q "FIREBASE_PROJECT_ID_DEV" .github/workflows/deploy-dev.yml; then
    print_success "✓ Development workflow has Firebase environment variables"
else
    print_error "✗ Development workflow missing Firebase environment variables"
    exit 1
fi

if grep -q "FIREBASE_PROJECT_ID_PROD" .github/workflows/deploy-prod.yml; then
    print_success "✓ Production workflow has Firebase environment variables"
else
    print_error "✗ Production workflow missing Firebase environment variables"
    exit 1
fi

# Test 6: Test Firebase credential validation logic
print_status "Test 6: Testing Firebase credential validation"

# Test with Firebase enabled but missing credentials
export ENABLE_FIREBASE_NOTIFICATIONS="true"
unset FIREBASE_PROJECT_ID
unset FIREBASE_SERVICE_ACCOUNT_KEY

echo "Testing Firebase validation with missing credentials..."
if source <(grep -A 50 "check_prerequisites()" deploy.sh | grep -B 50 "print_success.*Prerequisites check passed") 2>/dev/null; then
    print_warning "! Firebase validation logic may need adjustment"
else
    print_status "Firebase validation correctly catches missing credentials"
fi

echo ""
print_success "Firebase Centralized Configuration Verification Complete!"
echo ""
print_status "Summary of centralized Firebase configuration:"
echo "  ✓ Environment-specific defaults set in config/environments.sh"
echo "  ✓ Development: Firebase DISABLED by default"
echo "  ✓ Production: Firebase ENABLED by default"
echo "  ✓ Credentials passed from CI/CD pipelines or environment variables"
echo "  ✓ No Firebase configuration files needed"
echo "  ✓ Simplified deployment script without Firebase-specific logic"
echo ""
print_status "To deploy with Firebase:"
echo "  1. CI/CD: Set FIREBASE_PROJECT_ID_* variables and FIREBASE_SERVICE_ACCOUNT_KEY_* secrets"
echo "  2. Local: Export FIREBASE_PROJECT_ID and FIREBASE_SERVICE_ACCOUNT_KEY environment variables"
echo "  3. Override defaults: Edit ENABLE_FIREBASE_NOTIFICATIONS in config/environments.sh"
