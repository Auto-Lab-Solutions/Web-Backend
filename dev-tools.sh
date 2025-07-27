#!/bin/bash

# Quick Development Script
# This script provides shortcuts for common development tasks

set -e

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source environment configuration
source "$SCRIPT_DIR/config/environments.sh"

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

# Function to show usage
show_usage() {
    echo "Usage: $0 [--env <environment>] <command> [options]"
    echo ""
    echo "Quick development commands for Auto Lab Solutions backend"
    echo ""
    echo "Options:"
    echo "  --env, -e <env>         Specify environment (development/dev, production/prod)"
    echo ""
    echo "Commands:"
    echo "  logs <function_name>    Show recent CloudWatch logs for a Lambda function"
    echo "  test <function_name>    Test a Lambda function with sample event"
    echo "  env <function_name>     Show environment variables for a Lambda function"
    echo "  status                  Show status of all deployed resources"
    echo "  endpoints               Show API Gateway endpoints"
    echo "  watch <function_name>   Watch CloudWatch logs in real-time"
    echo ""
    echo "Examples:"
    echo "  $0 --env dev logs api-get-prices"
    echo "  $0 --env prod test api-get-users"
    echo "  $0 status"
    echo "  $0 endpoints"
    echo ""
}

# Function to get recent CloudWatch logs
get_logs() {
    local function_name=$1
    local full_function_name="${function_name}-${ENVIRONMENT}"
    local log_group="/aws/lambda/$full_function_name"
    
    print_status "Getting recent logs for $full_function_name..."
    
    # Get logs from the last 10 minutes
    local start_time=$(date -d '10 minutes ago' +%s)000
    
    aws logs filter-log-events \
        --log-group-name "$log_group" \
        --start-time "$start_time" \
        --region $AWS_REGION \
        --query 'events[*].[timestamp,message]' \
        --output table 2>/dev/null || {
        print_error "Failed to get logs for $full_function_name"
        print_warning "Make sure the function exists and has been invoked recently"
    }
}

# Function to watch logs in real-time
watch_logs() {
    local function_name=$1
    local full_function_name="${function_name}-${ENVIRONMENT}"
    local log_group="/aws/lambda/$full_function_name"
    
    print_status "Watching logs for $full_function_name (Press Ctrl+C to stop)..."
    
    # Use AWS CLI to tail logs
    aws logs tail "$log_group" --follow --region $AWS_REGION 2>/dev/null || {
        print_error "Failed to watch logs for $full_function_name"
        print_warning "Make sure the function exists and AWS CLI supports 'logs tail'"
    }
}

# Function to test a Lambda function
test_function() {
    local function_name=$1
    local full_function_name="${function_name}-${ENVIRONMENT}"
    
    print_status "Testing Lambda function: $full_function_name"
    
    # Create a sample test event based on function type
    local test_event='{}'
    
    if [[ $function_name == api-* ]]; then
        test_event='{
            "httpMethod": "GET",
            "path": "/test",
            "headers": {
                "Authorization": "Bearer test-token"
            },
            "queryStringParameters": {},
            "body": null
        }'
    elif [[ $function_name == ws-* ]]; then
        test_event='{
            "requestContext": {
                "connectionId": "test-connection-id",
                "eventType": "MESSAGE"
            },
            "body": "{\"action\":\"test\"}"
        }'
    fi
    
    print_status "Invoking function with test event..."
    
    aws lambda invoke \
        --function-name "$full_function_name" \
        --payload "$test_event" \
        --region $AWS_REGION \
        --cli-binary-format raw-in-base64-out \
        response.json
    
    if [ -f response.json ]; then
        print_success "Function response:"
        cat response.json | python3 -m json.tool 2>/dev/null || cat response.json
        rm response.json
    fi
}

# Function to show function environment variables
show_env() {
    local function_name=$1
    local full_function_name="${function_name}-${ENVIRONMENT}"
    
    print_status "Environment variables for $full_function_name:"
    
    aws lambda get-function-configuration \
        --function-name "$full_function_name" \
        --region $AWS_REGION \
        --query 'Environment.Variables' \
        --output table 2>/dev/null || {
        print_error "Failed to get environment variables for $full_function_name"
    }
}

# Function to show deployment status
show_status() {
    print_status "Checking deployment status for environment: $ENVIRONMENT..."
    
    # Check CloudFormation stack
    local stack_status=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --query 'Stacks[0].StackStatus' \
        --output text \
        --region $AWS_REGION 2>/dev/null || echo "NOT_FOUND")
    
    echo ""
    print_status "CloudFormation Stack ($STACK_NAME): $stack_status"
    
    # Check Lambda functions
    print_status "Lambda Functions:"
    local function_count=0
    local active_count=0
    
    for lambda_dir in lambda/*/; do
        if [ -d "$lambda_dir" ] && [ "$(basename "$lambda_dir")" != "common_lib" ] && [ "$(basename "$lambda_dir")" != "tmp" ]; then
            local function_name=$(basename "$lambda_dir")
            local full_function_name="${function_name}-${ENVIRONMENT}"
            
            # Temporarily disable exit on error for AWS command
            set +e
            local state=$(aws lambda get-function \
                --function-name "$full_function_name" \
                --query 'Configuration.State' \
                --output text \
                --region $AWS_REGION 2>/dev/null)
            local aws_exit_code=$?
            set -e
            
            # Handle the result
            if [ $aws_exit_code -ne 0 ] || [ -z "$state" ]; then
                state="NOT_FOUND"
            fi
            
            ((function_count++))
            if [ "$state" = "Active" ]; then
                ((active_count++))
                echo "  ✅ $full_function_name: $state"
            else
                echo "  ❌ $full_function_name: $state"
            fi
        fi
    done
    
    print_status "Functions Status: $active_count/$function_count active"
    
    # Check DynamoDB tables
    print_status "DynamoDB Tables:"
    local tables=("$STAFF_TABLE" "$USERS_TABLE" "$CONNECTIONS_TABLE" "$MESSAGES_TABLE" "$UNAVAILABLE_SLOTS_TABLE" "$APPOINTMENTS_TABLE" "$SERVICE_PRICES_TABLE" "$ORDERS_TABLE" "$ITEM_PRICES_TABLE" "$INQUIRIES_TABLE")
    local table_count=0
    local active_tables=0
    
    for table in "${tables[@]}"; do
        # Temporarily disable exit on error for AWS command
        set +e
        local status=$(aws dynamodb describe-table \
            --table-name "$table" \
            --query 'Table.TableStatus' \
            --output text \
            --region $AWS_REGION 2>/dev/null)
        local aws_exit_code=$?
        set -e
        
        # Handle the result
        if [ $aws_exit_code -ne 0 ] || [ -z "$status" ]; then
            status="NOT_FOUND"
        fi
        
        ((table_count++))
        if [ "$status" = "ACTIVE" ]; then
            ((active_tables++))
            echo "  ✅ $table: $status"
        else
            echo "  ❌ $table: $status"
        fi
    done
    
    print_status "Tables Status: $active_tables/$table_count active"
}

# Function to show API endpoints
show_endpoints() {
    print_status "Getting API Gateway endpoints for environment: $ENVIRONMENT..."
    
    # Get REST API endpoint
    local rest_endpoint=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --query 'Stacks[0].Outputs[?OutputKey==`RestApiEndpoint`].OutputValue' \
        --output text \
        --region $AWS_REGION 2>/dev/null || echo "NOT_FOUND")
    
    # Get WebSocket endpoint
    local ws_endpoint=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --query 'Stacks[0].Outputs[?OutputKey==`WebSocketApiEndpoint`].OutputValue' \
        --output text \
        --region $AWS_REGION 2>/dev/null || echo "NOT_FOUND")
    
    # Get CloudFront domain
    local cf_domain=$(aws cloudformation describe-stacks \
        --stack-name "$STACK_NAME" \
        --query 'Stacks[0].Outputs[?OutputKey==`CloudFrontDomainName`].OutputValue' \
        --output text \
        --region $AWS_REGION 2>/dev/null || echo "NOT_FOUND")
    
    echo ""
    print_success "API Endpoints:"
    echo "  🌐 REST API: $rest_endpoint"
    echo "  🔌 WebSocket API: $ws_endpoint"
    echo "  📁 CloudFront CDN: https://$cf_domain"
    echo ""
    
    print_status "Sample API calls:"
    echo "  curl \"$rest_endpoint/get-staff-roles?email=test@example.com\""
    echo "  curl \"$rest_endpoint/prices\" -H \"Authorization: Bearer YOUR_TOKEN\""
}

# Main function
main() {
    local environment=""
    
    # Parse environment option first
    while [[ $# -gt 0 ]]; do
        case $1 in
            --env|-e)
                environment="$2"
                shift 2
                ;;
            *)
                break
                ;;
        esac
    done
    
    # Load environment configuration
    if ! load_environment "$environment"; then
        exit 1
    fi
    
    print_status "Using environment: $ENVIRONMENT"
    echo ""
    
    if [ $# -eq 0 ]; then
        show_usage
        exit 1
    fi
    
    local command=$1
    shift
    
    case $command in
        logs)
            if [ $# -eq 0 ]; then
                print_error "Function name required"
                echo "Usage: $0 logs <function_name>"
                exit 1
            fi
            get_logs "$1"
            ;;
        watch)
            if [ $# -eq 0 ]; then
                print_error "Function name required"
                echo "Usage: $0 watch <function_name>"
                exit 1
            fi
            watch_logs "$1"
            ;;
        test)
            if [ $# -eq 0 ]; then
                print_error "Function name required"
                echo "Usage: $0 test <function_name>"
                exit 1
            fi
            test_function "$1"
            ;;
        env)
            if [ $# -eq 0 ]; then
                print_error "Function name required"
                echo "Usage: $0 env <function_name>"
                exit 1
            fi
            show_env "$1"
            ;;
        status)
            show_status
            ;;
        endpoints)
            show_endpoints
            ;;
        help|--help|-h)
            show_usage
            ;;
        *)
            print_error "Unknown command: $command"
            show_usage
            exit 1
            ;;
    esac
}

# Check if script is being run directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
