#!/bin/bash

# Local CI/CD Validation Script
# This script validates the setup locally before pushing to GitHub

set -e

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

print_status "🚀 Local CI/CD Validation"
echo "=========================="

# Check Python syntax in all Lambda functions
print_status "Validating Python syntax..."
error_count=0

find lambda -name "*.py" -exec python3 -m py_compile {} \; || {
    print_error "Python syntax validation failed"
    ((error_count++))
}

if [ $error_count -eq 0 ]; then
    print_success "Python syntax validation passed"
fi

# Check if AWS CLI is available
print_status "Checking AWS CLI..."
if command -v aws &> /dev/null; then
    print_success "AWS CLI is available"
    
    # Validate CloudFormation templates
    print_status "Validating CloudFormation templates..."
    template_errors=0
    
    # Only validate the main stack template since nested stacks have cross-references
    # that can't be resolved during individual template validation
    main_template="infrastructure/main-stack.yaml"
    
    if [ -f "$main_template" ]; then
        echo "  Validating $(basename $main_template) (main stack)..."
        if aws cloudformation validate-template --template-body file://$main_template --region ap-southeast-2 &>/dev/null; then
            print_success "  ✓ $(basename $main_template) is valid"
        else
            print_error "  ✗ $(basename $main_template) validation failed"
            ((template_errors++))
        fi
    else
        print_error "  ✗ Main stack template not found"
        ((template_errors++))
    fi
    
    # Check that nested template files exist and are readable
    print_status "Checking nested template files..."
    nested_templates=("api-gateway.yaml" "dynamodb-tables.yaml" "lambda-functions.yaml" "s3-cloudfront.yaml" "websocket-api.yaml")
    
    for template in "${nested_templates[@]}"; do
        template_path="infrastructure/$template"
        if [ -f "$template_path" ] && [ -r "$template_path" ]; then
            echo "  ✓ $template exists and is readable"
        else
            print_error "  ✗ $template is missing or not readable"
            ((template_errors++))
        fi
    done
    
    if [ $template_errors -eq 0 ]; then
        print_success "CloudFormation template validation passed"
    else
        print_error "$template_errors template validation(s) failed"
        ((error_count++))
    fi
else
    print_warning "AWS CLI not available - skipping template validation"
fi

# Check if all scripts are executable
print_status "Checking script permissions..."
scripts_ok=true

for script in *.sh; do
    if [ -x "$script" ]; then
        echo "  ✓ $script is executable"
    else
        print_error "  ✗ $script is not executable"
        scripts_ok=false
    fi
done

if [ -x "config/environments.sh" ]; then
    echo "  ✓ config/environments.sh is executable"
else
    print_error "  ✗ config/environments.sh is not executable"
    scripts_ok=false
fi

if [ "$scripts_ok" = true ]; then
    print_success "All scripts are executable"
else
    print_error "Some scripts are not executable"
    ((error_count++))
fi

# Check environment configuration
print_status "Testing environment configuration..."
if ./config/environments.sh show development &>/dev/null; then
    print_success "Environment configuration is working"
else
    print_error "Environment configuration failed"
    ((error_count++))
fi

# Check GitHub workflow files
print_status "Checking GitHub workflow files..."
workflow_files=(
    ".github/workflows/deploy-dev.yml"
    ".github/workflows/deploy-prod.yml"
    ".github/workflows/update-lambdas.yml"
    ".github/workflows/cleanup.yml"
)

for workflow in "${workflow_files[@]}"; do
    if [ -f "$workflow" ]; then
        echo "  ✓ $workflow exists"
    else
        print_error "  ✗ $workflow is missing"
        ((error_count++))
    fi
done

# Summary
echo ""
echo "=========================="
if [ $error_count -eq 0 ]; then
    print_success "🎉 All validations passed!"
    print_status "Your CI/CD setup is ready for GitHub Actions"
    echo ""
    print_status "Next steps:"
    echo "  1. Configure GitHub secrets (see .github/SECRETS.md)"
    echo "  2. Push to 'dev' branch for development deployment"
    echo "  3. Push to 'prod' branch for production deployment"
else
    print_error "❌ $error_count validation(s) failed"
    print_status "Please fix the errors above before pushing to GitHub"
    exit 1
fi
