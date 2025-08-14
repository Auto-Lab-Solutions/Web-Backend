#!/bin/bash

# Environment Configuration for Auto Lab Solutions Backend
# This script defines environment-specific configurations

# Ensure AWS_ACCOUNT_ID is set
if [ -z "$AWS_ACCOUNT_ID" ]; then
    AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null)
    export AWS_ACCOUNT_ID
    if [ -z "$AWS_ACCOUNT_ID" ]; then
        echo "[ERROR] AWS_ACCOUNT_ID is not set and could not be determined automatically."
        exit 1
    fi
fi

# Function to validate environment name
validate_environment() {
    local env=$1
    case $env in
        dev|development)
            echo "development"
            ;;
        prod|production)
            echo "production"
            ;;
        *)
            echo ""
            ;;
    esac
}

# Function to get environment configuration
get_env_config() {
    local env=$1
    
    case $env in
        development)
            # Development Environment Configuration
            export ENVIRONMENT="development"
            export AWS_REGION="ap-southeast-2"
            export STACK_NAME="auto-lab-backend-dev"
            export S3_BUCKET_NAME="auto-lab-reports"
            export CLOUDFORMATION_BUCKET="auto-lab-cloudformation-templates-dev"
            export BACKUP_BUCKET_NAME="auto-lab-backups-dev"
            export LOG_LEVEL="DEBUG"
            export LAMBDA_TIMEOUT="30"
            export LAMBDA_MEMORY="256"
            
            # Frontend Configuration
            export FRONTEND_DOMAIN_NAME="dev.autolabsolutions.com"
            export FRONTEND_HOSTED_ZONE_ID="Z060497817EUO8PSJGQHQ"
            export FRONTEND_ACM_CERTIFICATE_ARN="arn:aws:acm:us-east-1:899704476492:certificate/808b1a88-c14d-46f2-a9d2-e34ac47c0838"
            export ENABLE_CUSTOM_DOMAIN="true"
            export ENABLE_FRONTEND_WEBSITE="true"

            # API Gateway Custom Domain Configuration
            export ENABLE_API_CUSTOM_DOMAINS="true"
            export API_DOMAIN_NAME="api-dev.autolabsolutions.com"
            export WEBSOCKET_DOMAIN_NAME="ws-dev.autolabsolutions.com"
            export API_HOSTED_ZONE_ID="Z060497817EUO8PSJGQHQ"
            export API_ACM_CERTIFICATE_ARN="arn:aws:acm:ap-southeast-2:899704476492:certificate/your-regional-cert-arn"

            # Reports CloudFront Custom Domain Configuration
            export ENABLE_REPORTS_CUSTOM_DOMAIN="true"
            export REPORTS_DOMAIN_NAME="reports-dev.autolabsolutions.com"
            export REPORTS_HOSTED_ZONE_ID="Z060497817EUO8PSJGQHQ"
            export REPORTS_ACM_CERTIFICATE_ARN="arn:aws:acm:us-east-1:899704476492:certificate/808b1a88-c14d-46f2-a9d2-e34ac47c0838"

            # SES Configuration
            export FROM_EMAIL="noreply@dev.autolabsolutions.com"
            export SES_REGION="${AWS_REGION}"
            
            # Firebase Configuration (Optional)
            # Set Firebase enabled/disabled state for development environment
            export ENABLE_FIREBASE_NOTIFICATIONS="false"  # Default disabled for development
            # Firebase credentials passed from CI/CD pipeline or environment variables
            export FIREBASE_PROJECT_ID="${FIREBASE_PROJECT_ID:-}"
            export FIREBASE_SERVICE_ACCOUNT_KEY="${FIREBASE_SERVICE_ACCOUNT_KEY:-}"
            ;;
        production)
            # Production Environment Configuration
            export ENVIRONMENT="production"
            export AWS_REGION="ap-southeast-2"
            export STACK_NAME="auto-lab-backend"
            export S3_BUCKET_NAME="auto-lab-reports"
            export CLOUDFORMATION_BUCKET="auto-lab-cloudformation-templates"
            export BACKUP_BUCKET_NAME="auto-lab-backups"
            export LOG_LEVEL="INFO"
            export LAMBDA_TIMEOUT="30"
            export LAMBDA_MEMORY="256"
            
            # Frontend Configuration
            export FRONTEND_DOMAIN_NAME="autolabsolutions.com"
            export FRONTEND_HOSTED_ZONE_ID="Z060497817EUO8PSJGQHQ"
            export FRONTEND_ACM_CERTIFICATE_ARN="arn:aws:acm:us-east-1:899704476492:certificate/808b1a88-c14d-46f2-a9d2-e34ac47c0838"
            export ENABLE_CUSTOM_DOMAIN="true"
            export ENABLE_FRONTEND_WEBSITE="true"

            # API Gateway Custom Domain Configuration
            export ENABLE_API_CUSTOM_DOMAINS="true"
            export API_DOMAIN_NAME="api.autolabsolutions.com"
            export WEBSOCKET_DOMAIN_NAME="ws.autolabsolutions.com"
            export API_HOSTED_ZONE_ID="Z060497817EUO8PSJGQHQ"
            export API_ACM_CERTIFICATE_ARN="arn:aws:acm:ap-southeast-2:899704476492:certificate/your-regional-cert-arn"

            # Reports CloudFront Custom Domain Configuration
            export ENABLE_REPORTS_CUSTOM_DOMAIN="true"
            export REPORTS_DOMAIN_NAME="reports.autolabsolutions.com"
            export REPORTS_HOSTED_ZONE_ID="Z060497817EUO8PSJGQHQ"
            export REPORTS_ACM_CERTIFICATE_ARN="arn:aws:acm:us-east-1:899704476492:certificate/808b1a88-c14d-46f2-a9d2-e34ac47c0838"

            # SES Configuration
            export FROM_EMAIL="noreply@autolabsolutions.com"
            export SES_REGION="${AWS_REGION}"
            
            # Firebase Configuration (Optional)
            # Set Firebase enabled/disabled state for production environment
            export ENABLE_FIREBASE_NOTIFICATIONS="true"   # Default enabled for production
            # Firebase credentials passed from CI/CD pipeline or environment variables
            export FIREBASE_PROJECT_ID="${FIREBASE_PROJECT_ID:-}"
            export FIREBASE_SERVICE_ACCOUNT_KEY="${FIREBASE_SERVICE_ACCOUNT_KEY:-}"
            ;;
        *)
            echo "Error: Invalid environment '$env'"
            echo "Valid environments: development (dev), production (prod)"
            return 1
            ;;
    esac
    
    # Common configurations
    export PYTHON_VERSION="3.13"
    export NODEJS_VERSION="18.x"
    
    # DynamoDB table names (with environment suffix)
    export STAFF_TABLE="Staff-${ENVIRONMENT}"
    export USERS_TABLE="Users-${ENVIRONMENT}"
    export CONNECTIONS_TABLE="Connections-${ENVIRONMENT}"
    export MESSAGES_TABLE="Messages-${ENVIRONMENT}"
    export UNAVAILABLE_SLOTS_TABLE="UnavailableSlots-${ENVIRONMENT}"
    export APPOINTMENTS_TABLE="Appointments-${ENVIRONMENT}"
    export SERVICE_PRICES_TABLE="ServicePrices-${ENVIRONMENT}"
    export ORDERS_TABLE="Orders-${ENVIRONMENT}"
    export ITEM_PRICES_TABLE="ItemPrices-${ENVIRONMENT}"
    export INQUIRIES_TABLE="Inquiries-${ENVIRONMENT}"
    export PAYMENTS_TABLE="Payments-${ENVIRONMENT}"
    
    # Additional configuration values
    export REPORTS_BUCKET_NAME="${S3_BUCKET_NAME}"
    
    # # SES Configuration
    # export FROM_EMAIL="${FROM_EMAIL:-noreply@autolabsolutions.com}"
    # export SES_REGION="${SES_REGION:-ap-southeast-2}"

    # Auth0 configuration (if needed)
    export AUTH0_DOMAIN="${AUTH0_DOMAIN}"
    export AUTH0_AUDIENCE="${AUTH0_AUDIENCE}"

    # Frontend GitHub Repository Configuration
    FRONTEND_REPO_OWNER="Auto-Lab-Solutions"
    FRONTEND_REPO_NAME="Web-Frontend"
    FRONTEND_GITHUB_TOKEN="${FRONTEND_GITHUB_TOKEN}"

    # Load secrets from environment variables (GitHub environments will provide correct values)
    export STRIPE_WEBHOOK_ENDPOINT_ID="${STRIPE_WEBHOOK_ENDPOINT_ID}"
    export STRIPE_PUBLISHABLE_KEY="${STRIPE_PUBLISHABLE_KEY}"
    export STRIPE_SECRET_KEY="${STRIPE_SECRET_KEY}"
    export STRIPE_WEBHOOK_SECRET="${STRIPE_WEBHOOK_SECRET}"
    export SHARED_KEY="${SHARED_KEY}"
    
    return 0
}

# Function to display current environment configuration
show_env_config() {
    local env=$1
    
    if ! get_env_config "$env"; then
        return 1
    fi
    
    echo "=========================================="
    echo "Environment Configuration: $ENVIRONMENT"
    echo "=========================================="
    # Print all exported environment variables relevant to this script
    echo "All Environment Variables (sorted):"
    env | grep -E '^(AWS_|STACK_NAME|S3_BUCKET_NAME|CLOUDFORMATION_BUCKET|BACKUP_BUCKET_NAME|LOG_LEVEL|LAMBDA_TIMEOUT|LAMBDA_MEMORY|FRONTEND_DOMAIN_NAME|FRONTEND_HOSTED_ZONE_ID|FRONTEND_ACM_CERTIFICATE_ARN|ENABLE_CUSTOM_DOMAIN|ENABLE_FRONTEND_WEBSITE|PYTHON_VERSION|NODEJS_VERSION|STAFF_TABLE|USERS_TABLE|CONNECTIONS_TABLE|MESSAGES_TABLE|UNAVAILABLE_SLOTS_TABLE|APPOINTMENTS_TABLE|SERVICE_PRICES_TABLE|ORDERS_TABLE|ITEM_PRICES_TABLE|INQUIRIES_TABLE|PAYMENTS_TABLE|REPORTS_BUCKET_NAME|AUTH0_DOMAIN|AUTH0_AUDIENCE|FRONTEND_REPO_OWNER|FRONTEND_REPO_NAME|FRONTEND_GITHUB_TOKEN|STRIPE_WEBHOOK_ENDPOINT_ID|STRIPE_PUBLISHABLE_KEY|STRIPE_SECRET_KEY|STRIPE_WEBHOOK_SECRET|SHARED_KEY|FIREBASE_PROJECT_ID|FIREBASE_SERVICE_ACCOUNT_KEY|FROM_EMAIL|SES_REGION)=' | sort
    echo "=========================================="
}

# Function to get default environment
get_default_environment() {
    # Check if environment is set via environment variable (for CI/CD)
    if [ -n "$AUTO_LAB_ENV" ]; then
        echo "$AUTO_LAB_ENV"
    elif [ -n "$GITHUB_ACTIONS" ] && [ -n "$ENVIRONMENT" ]; then
        # GitHub Actions environment
        echo "$ENVIRONMENT"
    elif [ -f ".env" ]; then
        # Read from .env file if it exists
        grep "^ENVIRONMENT=" .env 2>/dev/null | cut -d'=' -f2 | tr -d '"' || echo "development"
    else
        echo "development"
    fi
}

# Function to set environment in .env file
set_default_environment() {
    local env=$1
    local normalized_env=$(validate_environment "$env")
    
    if [ -z "$normalized_env" ]; then
        echo "Error: Invalid environment '$env'"
        return 1
    fi
    
    echo "ENVIRONMENT=$normalized_env" > .env
    echo "Default environment set to: $normalized_env"
}

# Function to prompt user for environment if not specified
prompt_for_environment() {
    local default_env=$(get_default_environment)
    
    # Skip prompt in CI/CD environments or if AUTO_CONFIRM is set - use default
    if [ -n "$GITHUB_ACTIONS" ] || [ -n "$CI" ] || [ "$AUTO_CONFIRM" = "true" ]; then
        echo "Running in automated environment - using default environment: $default_env"
        echo "$default_env"
        return
    fi
    
    echo "Available environments:"
    echo "  1) development (dev) - For testing and development"
    echo "  2) production (prod) - For live deployment"
    echo ""
    read -p "Select environment [$default_env]: " env_input
    
    if [ -z "$env_input" ]; then
        env_input="$default_env"
    fi
    
    local normalized_env=$(validate_environment "$env_input")
    if [ -z "$normalized_env" ]; then
        echo "Invalid environment selected. Using default: $default_env"
        normalized_env=$(validate_environment "$default_env")
    fi
    
    echo "$normalized_env"
}

# Function to load environment configuration
load_environment() {
    local env=$1
    
    # If no environment specified, try to get default or prompt
    if [ -z "$env" ]; then
        env=$(get_default_environment)
        # Only prompt if running interactively and not in CI/CD
        if [ "$env" = "development" ] && [ -t 0 ] && [ -z "$GITHUB_ACTIONS" ] && [ -z "$CI" ]; then
            env=$(prompt_for_environment)
        fi
    fi
    
    # Normalize the environment name
    local normalized_env=$(validate_environment "$env")
    if [ -z "$normalized_env" ]; then
        echo "Error: Invalid environment '$env'"
        echo "Valid environments: development (dev), production (prod)"
        return 1
    fi
    
    # Load the configuration
    get_env_config "$normalized_env"
    
    return 0
}

# If script is run directly, show environment configuration
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    case "${1:-}" in
        show|config)
            show_env_config "${2:-$(get_default_environment)}"
            ;;
        set)
            if [ -z "$2" ]; then
                echo "Usage: $0 set <environment>"
                echo "Environments: development (dev), production (prod)"
                exit 1
            fi
            set_default_environment "$2"
            ;;
        list)
            echo "Available environments:"
            echo "  development (dev) - For testing and development"
            echo "  production (prod) - For live deployment"
            echo ""
            echo "Current default: $(get_default_environment)"
            ;;
        *)
            echo "Usage: $0 {show|set|list} [environment]"
            echo ""
            echo "Commands:"
            echo "  show [env]  - Show configuration for environment"
            echo "  set <env>   - Set default environment"
            echo "  list        - List available environments"
            echo ""
            echo "Examples:"
            echo "  $0 show dev"
            echo "  $0 set production"
            echo "  $0 list"
            ;;
    esac
fi
