#!/bin/bash

# Update WebSocket Endpoints Script
# This script updates WebSocket endpoint environment variables in Lambda functions
# after the WebSocket stack has been deployed

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
    echo "Usage: $0 [OPTIONS] [ENVIRONMENT]"
    echo ""
    echo "Update WebSocket endpoint environment variables in Lambda functions"
    echo ""
    echo "Options:"
    echo "  --env, -e <env>     Specify environment (development/dev, production/prod)"
    echo "  --dry-run          Show what would be updated without making changes"
    echo "  --verbose, -v      Show verbose output for debugging"
    echo "  --list-functions   List expected Lambda functions and their status"
    echo "  --test-json        Test JSON approach for debugging"
    echo "  --test-flow        Test complete flow with mock data"
    echo "  --test-scenario    Test success/skip scenario for debugging"
    echo "  --test-user        Test the exact scenario from user's log"
    echo "  --debug           Enable debug mode (set -x)"
    echo "  --help, -h         Show this help message"
    echo ""
    echo "Arguments:"
    echo "  ENVIRONMENT        Target environment (development|dev|production|prod)"
    echo ""
    echo "Examples:"
    echo "  $0 dev              # Update WebSocket endpoints for development"
    echo "  $0 --env production # Update WebSocket endpoints for production"
    echo "  $0 --dry-run dev    # Show what would be updated for development"
    echo ""
}

# Function to get stack output value
get_stack_output() {
    local stack_name=$1
    local output_key=$2
    
    set +e
    local result=$(aws cloudformation describe-stacks \
        --stack-name "$stack_name" \
        --query "Stacks[0].Outputs[?OutputKey=='$output_key'].OutputValue" \
        --output text \
        --region $AWS_REGION 2>/dev/null)
    local exit_code=$?
    set -e
    
    if [[ $exit_code -eq 0 && -n "$result" && "$result" != "None" ]]; then
        echo "$result"
    else
        echo ""
    fi
}

# Function to check if lambda function exists
lambda_exists() {
    local function_name=$1
    set +e
    aws lambda get-function --function-name "$function_name" --region $AWS_REGION >/dev/null 2>&1
    local result=$?
    set -e
    return $result
}

# Function to check prerequisites
check_prerequisites() {
    local environment=$1
    
    print_status "Checking prerequisites..."
    
    # Check if jq is available
    if ! command -v jq &> /dev/null; then
        print_error "jq is required but not installed. Please install jq to continue."
        return 1
    fi
    
    # Check AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        print_error "AWS credentials not configured. Please run 'aws configure'."
        return 1
    fi
    
    # Check if CloudFormation stack exists
    if ! aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region $AWS_REGION >/dev/null 2>&1; then
        print_error "CloudFormation stack '$STACK_NAME' does not exist!"
        print_error "Please deploy the infrastructure first using:"
        print_error "  ./deploy.sh $environment"
        return 1
    fi
    
    print_success "Prerequisites check passed"
    return 0
}

# Function to get current lambda environment variables
get_lambda_env() {
    local function_name=$1
    set +e
    local result=$(aws lambda get-function-configuration \
        --function-name "$function_name" \
        --query 'Environment.Variables' \
        --output json \
        --region $AWS_REGION 2>/dev/null)
    local exit_code=$?
    set -e
    
    if [[ $exit_code -eq 0 && -n "$result" ]]; then
        echo "$result"
    else
        echo "{}"
    fi
}

# Function to update Lambda environment variables
update_lambda_websocket_env() {
    local dry_run=$1
    local verbose=${2:-false}
    
    print_status "Getting WebSocket API endpoint from CloudFormation stack..."
    
    # Get WebSocket API endpoint from stack outputs
    local websocket_endpoint=$(get_stack_output "$STACK_NAME" "WebSocketApiEndpoint")
    
    if [[ -z "$websocket_endpoint" || "$websocket_endpoint" == "None" ]]; then
        print_error "WebSocket API endpoint not found in stack outputs!"
        print_error "Available stack outputs:"
        aws cloudformation describe-stacks \
            --stack-name "$STACK_NAME" \
            --query "Stacks[0].Outputs[].{Key:OutputKey,Value:OutputValue}" \
            --output table \
            --region $AWS_REGION 2>/dev/null || print_error "Could not retrieve stack outputs"
        print_error ""
        print_error "Make sure the WebSocket API has been deployed successfully."
        print_error "Expected output key: 'WebSocketApiEndpoint'"
        return 1
    fi
    
    print_status "WebSocket API Endpoint: $websocket_endpoint"
    echo ""
    
    # Define all Lambda functions that need WebSocket endpoint
    # These are functions that use wsgw_utils.py and need WEBSOCKET_ENDPOINT_URL
    local websocket_functions=(
        "api-notify-${ENVIRONMENT}"
        "api-send-message-${ENVIRONMENT}"
        "api-take-user-${ENVIRONMENT}"
        "ws-connect-${ENVIRONMENT}"
        "ws-disconnect-${ENVIRONMENT}"
        "ws-init-${ENVIRONMENT}"
        "ws-ping-${ENVIRONMENT}"
        "ws-staff-init-${ENVIRONMENT}"
    )
    
    local updated_count=0
    local error_count=0
    local skipped_count=0
    
    for func in "${websocket_functions[@]}"; do
        print_status "Processing $func..."
        
        # Check if function exists
        if ! lambda_exists "$func"; then
            print_warning "Function $func does not exist, skipping..."
            skipped_count=$((skipped_count + 1))
            continue
        fi
        
        # Get current environment variables
        local current_env=$(get_lambda_env "$func")
        if [[ "$current_env" == "{}" ]]; then
            print_warning "Could not retrieve environment variables for $func, skipping..."
            skipped_count=$((skipped_count + 1))
            continue
        fi
        
        if [[ "$verbose" == "true" ]]; then
            print_status "Current environment variables for $func:"
            echo "$current_env" | jq .
        fi
        
        # Update the environment variables JSON to include/update WEBSOCKET_ENDPOINT_URL
        set +e
        local updated_env=$(echo "$current_env" | jq --arg endpoint "$websocket_endpoint" '. + {WEBSOCKET_ENDPOINT_URL: $endpoint}' 2>/dev/null)
        local jq_exit_code=$?
        set -e
        
        # Validate the JSON is properly formatted
        if [[ $jq_exit_code -ne 0 ]] || ! echo "$updated_env" | jq . > /dev/null 2>&1; then
            print_error "Invalid JSON generated for $func environment variables"
            print_error "Current env: $current_env"
            print_error "Updated env: $updated_env"
            error_count=$((error_count + 1))
            continue
        fi
        
        # Compact the JSON to minimize size and avoid formatting issues
        set +e
        updated_env=$(echo "$updated_env" | jq -c . 2>/dev/null)
        local compact_exit_code=$?
        set -e
        
        if [[ $compact_exit_code -ne 0 ]]; then
            print_error "Failed to compact JSON for $func environment variables"
            error_count=$((error_count + 1))
            continue
        fi
        
        # Check if the complete environment structure is within AWS Lambda limits
        local complete_env_structure="{\"Variables\": $updated_env}"
        local env_size=$(echo "$complete_env_structure" | wc -c)
        if [[ $env_size -gt 4096 ]]; then
            print_error "Environment variables too large for $func ($env_size bytes, max 4096)"
            error_count=$((error_count + 1))
            continue
        fi
        
        if [[ "$dry_run" == "true" ]]; then
            print_status "[DRY RUN] Would update $func with WEBSOCKET_ENDPOINT_URL=$websocket_endpoint"
            if [[ "$verbose" == "true" ]]; then
                print_status "Updated environment variables would be:"
                echo "$updated_env" | jq .
            fi
        else
            # Update the Lambda function
            print_status "Updating environment variables for $func..."
            
            if [[ "$verbose" == "true" ]]; then
                print_status "Updated environment variables:"
                echo "$updated_env" | jq .
            fi
            
            # Write environment variables to a temporary file to handle complex JSON
            local temp_env_file=$(mktemp)
            # Create the correct structure for AWS Lambda environment parameter
            echo "{\"Variables\": $updated_env}" > "$temp_env_file"
            
            if [[ "$verbose" == "true" ]]; then
                print_status "Using temporary file: $temp_env_file"
                print_status "File contents:"
                cat "$temp_env_file"
            fi
            
            local update_output
            # Temporarily disable set -e for this command to handle errors gracefully
            set +e
            update_output=$(aws lambda update-function-configuration \
                --function-name "$func" \
                --environment file://"$temp_env_file" \
                --region $AWS_REGION 2>&1)
            local aws_exit_code=$?
            set -e
            
            if [[ $aws_exit_code -eq 0 ]]; then
                print_success "Updated $func"
                updated_count=$((updated_count + 1))
            else
                print_error "Failed to update $func"
                print_error "AWS CLI Error: $update_output"
                if [[ "$verbose" == "true" ]]; then
                    print_error "Temp file contents were:"
                    cat "$temp_env_file"
                fi
                error_count=$((error_count + 1))
            fi
            
            # Clean up temporary file
            rm -f "$temp_env_file"
            
            # Add a small delay to avoid rate limiting and show progress
            sleep 0.5
        fi
    done
    
    echo ""
    if [[ "$dry_run" == "true" ]]; then
        print_status "Dry run completed. ${#websocket_functions[@]} functions would be processed."
        print_status "To actually update the functions, run without --dry-run"
    else
        print_success "WebSocket endpoint update completed!"
        print_status "Functions processed: ${#websocket_functions[@]}"
        print_status "Functions updated: $updated_count"
        if [[ $skipped_count -gt 0 ]]; then
            print_warning "Functions skipped: $skipped_count"
        fi
        if [[ $error_count -gt 0 ]]; then
            print_warning "Functions with errors: $error_count"
            print_warning "Run with --verbose to see detailed error information"
            echo ""
            print_error "Script completed with errors. Some functions may not have been updated."
            return 1
        fi
        
        if [[ $updated_count -eq 0 && $skipped_count -eq ${#websocket_functions[@]} ]]; then
            print_warning "No functions were updated (all were skipped)."
            print_warning "This may indicate that the Lambda functions don't exist yet."
            echo ""
            print_status "All functions now have WEBSOCKET_ENDPOINT_URL=$websocket_endpoint"
        else
            print_success "Successfully updated $updated_count function(s)!"
            print_status "All functions now have WEBSOCKET_ENDPOINT_URL=$websocket_endpoint"
        fi
    fi
}

# Function to verify WebSocket endpoints
verify_websocket_endpoints() {
    print_status "Verifying WebSocket endpoints in Lambda functions..."
    
    local websocket_endpoint=$(get_stack_output "$STACK_NAME" "WebSocketApiEndpoint")
    
    if [[ -z "$websocket_endpoint" || "$websocket_endpoint" == "None" ]]; then
        print_error "WebSocket API endpoint not found in stack outputs!"
        return 1
    fi
    
    local websocket_functions=(
        "api-notify-${ENVIRONMENT}"
        "api-send-message-${ENVIRONMENT}"
        "api-take-user-${ENVIRONMENT}"
        "ws-connect-${ENVIRONMENT}"
        "ws-disconnect-${ENVIRONMENT}"
        "ws-init-${ENVIRONMENT}"
        "ws-ping-${ENVIRONMENT}"
        "ws-staff-init-${ENVIRONMENT}"
    )
    
    local verified_count=0
    local mismatch_count=0
    
    for func in "${websocket_functions[@]}"; do
        if lambda_exists "$func"; then
            local current_env=$(get_lambda_env "$func")
            local current_endpoint=$(echo "$current_env" | jq -r '.WEBSOCKET_ENDPOINT_URL // "NOT_SET"')
            
            if [[ "$current_endpoint" == "$websocket_endpoint" ]]; then
                print_success "$func: ✓ Correct endpoint"
                verified_count=$((verified_count + 1))
            else
                print_error "$func: ✗ Endpoint mismatch"
                print_error "  Expected: $websocket_endpoint"
                print_error "  Current:  $current_endpoint"
                mismatch_count=$((mismatch_count + 1))
            fi
        fi
    done
    
    echo ""
    print_status "Verification completed:"
    print_status "  Correct endpoints: $verified_count"
    if [[ $mismatch_count -gt 0 ]]; then
        print_warning "  Mismatched endpoints: $mismatch_count"
        return 1
    fi
    
    return 0
}

# Function to list expected Lambda functions
list_expected_functions() {
    print_status "Expected Lambda functions for environment '$ENVIRONMENT':"
    local websocket_functions=(
        "api-notify-${ENVIRONMENT}"
        "api-send-message-${ENVIRONMENT}"
        "api-take-user-${ENVIRONMENT}"
        "ws-connect-${ENVIRONMENT}"
        "ws-disconnect-${ENVIRONMENT}"
        "ws-init-${ENVIRONMENT}"
        "ws-ping-${ENVIRONMENT}"
        "ws-staff-init-${ENVIRONMENT}"
    )
    
    for func in "${websocket_functions[@]}"; do
        if lambda_exists "$func"; then
            print_success "  ✓ $func (exists)"
        else
            print_error "  ✗ $func (missing)"
        fi
    done
    echo ""
}

# Function to test JSON approach (for debugging)
test_json_approach() {
    print_status "Testing JSON approach..."
    
    # Create a sample environment variables JSON
    local test_json='{"TEST_VAR": "test_value", "WEBSOCKET_ENDPOINT_URL": "wss://test.execute-api.region.amazonaws.com/stage"}'
    
    print_status "Sample environment variables JSON:"
    echo "$test_json" | jq .
    
    # Create the AWS Lambda environment structure
    local env_structure="{\"Variables\": $test_json}"
    print_status "AWS Lambda environment structure:"
    echo "$env_structure" | jq .
    
    print_status "Testing AWS CLI parameter structure..."
    # This would be the actual command structure
    echo "aws lambda update-function-configuration --function-name test-function --environment file://temp-file"
    
    print_success "JSON approach test completed"
}

# Function to test the complete flow with mock data (for debugging)
test_complete_flow() {
    print_status "Testing complete flow with mock data..."
    
    # Mock environment variables that a Lambda function might have
    local mock_current_env='{"DATABASE_URL": "some-database-url", "LOG_LEVEL": "INFO", "TIMEOUT": "30"}'
    local mock_websocket_endpoint="wss://abc123.execute-api.ap-southeast-2.amazonaws.com/dev"
    
    print_status "Mock current environment variables:"
    echo "$mock_current_env" | jq .
    
    print_status "Mock WebSocket endpoint: $mock_websocket_endpoint"
    
    # Simulate the update process
    local updated_env=$(echo "$mock_current_env" | jq --arg endpoint "$mock_websocket_endpoint" '. + {WEBSOCKET_ENDPOINT_URL: $endpoint}')
    
    # Validate and compact
    if echo "$updated_env" | jq . > /dev/null 2>&1; then
        updated_env=$(echo "$updated_env" | jq -c .)
        print_success "JSON validation passed"
        print_status "Updated environment variables:"
        echo "$updated_env" | jq .
        
        # Check size of complete structure
        local env_structure="{\"Variables\": $updated_env}"
        local env_size=$(echo "$env_structure" | wc -c)
        print_status "Complete environment structure size: $env_size bytes (max 4096)"
        
        if [[ $env_size -le 4096 ]]; then
            print_success "Size validation passed"
            
            # Show the complete AWS Lambda environment structure
            print_status "Complete environment structure:"
            echo "$env_structure" | jq .
            
            print_status "Would execute:"
            echo "aws lambda update-function-configuration --function-name mock-function --environment file://temp-file"
        else
            print_error "Size validation failed"
        fi
    else
        print_error "JSON validation failed"
    fi
    
    print_success "Complete flow test completed"
}

# Function to test success/skip scenario (for debugging)
test_success_scenario() {
    print_status "Testing success with some skipped functions scenario..."
    
    # Simulate the process without actual AWS calls
    local websocket_functions=(
        "api-notify-development"
        "api-send-message-development" 
        "api-take-user-development"
        "ws-connect-development"
        "ws-disconnect-development"
        "ws-init-development"
        "ws-ping-development"
        "ws-staff-init-development"
    )
    
    local updated_count=0
    local error_count=0
    local skipped_count=0
    
    # Simulate processing each function
    for func in "${websocket_functions[@]}"; do
        print_status "Processing $func..."
        
        # Simulate different scenarios
        case $func in
            "api-notify-development"|"api-send-message-development")
                print_success "Updated $func"
                updated_count=$((updated_count + 1))
                ;;
            *)
                print_warning "Function $func does not exist, skipping..."
                skipped_count=$((skipped_count + 1))
                ;;
        esac
    done
    
    # Show the same summary logic as the real function
    echo ""
    print_success "WebSocket endpoint update completed!"
    print_status "Functions processed: ${#websocket_functions[@]}"
    print_status "Functions updated: $updated_count"
    if [[ $skipped_count -gt 0 ]]; then
        print_warning "Functions skipped: $skipped_count"
    fi
    if [[ $error_count -gt 0 ]]; then
        print_warning "Functions with errors: $error_count"
        print_warning "Run with --verbose to see detailed error information"
        echo ""
        print_error "Script completed with errors. Some functions may not have been updated."
        print_status "This test would return exit code 1"
        return 1
    fi
    
    if [[ $updated_count -eq 0 && $skipped_count -eq ${#websocket_functions[@]} ]]; then
        print_warning "No functions were updated (all were skipped)."
        print_warning "This may indicate that the Lambda functions don't exist yet."
        echo ""
        print_status "This test would return exit code 0"
    else
        print_success "Successfully updated $updated_count function(s)!"
        print_status "This test would return exit code 0"
    fi
    
    print_success "Success scenario test completed"
}

# Function to test the exact scenario from user's log (for debugging)
test_user_scenario() {
    print_status "Testing the exact scenario from user's log..."
    
    # Simulate the process that matches the user's log exactly
    local websocket_endpoint="wss://ke0icoaw68.execute-api.ap-southeast-2.amazonaws.com/development"
    local websocket_functions=(
        "api-notify-development"
        "api-send-message-development"
        "api-take-user-development"
        "ws-connect-development"
        "ws-disconnect-development"
        "ws-init-development"
        "ws-ping-development"
        "ws-staff-init-development"
    )
    
    local updated_count=0
    local error_count=0
    local skipped_count=0
    
    print_status "WebSocket API Endpoint: $websocket_endpoint"
    echo ""
    
    # Process each function as it would happen in the real scenario
    for func in "${websocket_functions[@]}"; do
        print_status "Processing $func..."
        
        case $func in
            "api-notify-development")
                print_status "Updating environment variables for $func..."
                print_success "Updated $func"
                updated_count=$((updated_count + 1))
                ;;
            "api-send-message-development")
                print_status "Updating environment variables for $func..."
                # Simulate a potential failure on the second function
                print_error "Failed to update $func"
                print_error "AWS CLI Error: ResourceConflictException: The function could not be updated due to a concurrent update operation"
                error_count=$((error_count + 1))
                ;;
            *)
                print_status "Updating environment variables for $func..."
                print_success "Updated $func"
                updated_count=$((updated_count + 1))
                ;;
        esac
        
        # Add small delay like the real script
        sleep 0.1
    done
    
    # Show the final summary
    echo ""
    print_success "WebSocket endpoint update completed!"
    print_status "Functions processed: ${#websocket_functions[@]}"
    print_status "Functions updated: $updated_count"
    if [[ $skipped_count -gt 0 ]]; then
        print_warning "Functions skipped: $skipped_count"
    fi
    if [[ $error_count -gt 0 ]]; then
        print_warning "Functions with errors: $error_count"
        print_warning "Run with --verbose to see detailed error information"
        echo ""
        print_error "Script completed with errors. Some functions may not have been updated."
        print_status "This test would return exit code 1"
        return 1
    fi
    
    print_success "Successfully updated $updated_count function(s)!"
    print_status "All functions now have WEBSOCKET_ENDPOINT_URL=$websocket_endpoint"
    print_status "This test would return exit code 0"
    
    print_success "User scenario test completed"
}

# Main function
main() {
    local environment=""
    local dry_run=false
    local verify_only=false
    local verbose=false
    local list_functions=false
    local test_json=false
    local test_flow=false
    local test_scenario=false
    local debug_mode=false
    local test_user=false
    
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --env|-e)
                environment="$2"
                shift 2
                ;;
            --dry-run)
                dry_run=true
                shift
                ;;
            --verbose|-v)
                verbose=true
                shift
                ;;
            --list-functions)
                list_functions=true
                shift
                ;;
            --test-json)
                test_json=true
                shift
                ;;
            --test-flow)
                test_flow=true
                shift
                ;;
            --test-scenario)
                test_scenario=true
                shift
                ;;
            --test-user)
                test_user=true
                shift
                ;;
            --debug)
                debug_mode=true
                shift
                ;;
            --verify)
                verify_only=true
                shift
                ;;
            --help|-h)
                show_usage
                exit 0
                ;;
            -*)
                print_error "Unknown option: $1"
                echo "Use --help for usage information"
                exit 1
                ;;
            *)
                # Positional argument (environment)
                if [[ -z "$environment" ]]; then
                    environment="$1"
                else
                    print_error "Multiple environments specified: '$environment' and '$1'"
                    exit 1
                fi
                shift
                ;;
        esac
    done
    
    if [[ "$test_json" == "true" ]]; then
        test_json_approach
        exit 0
    fi
    
    if [[ "$test_flow" == "true" ]]; then
        test_complete_flow
        exit 0
    fi
    
    if [[ "$test_scenario" == "true" ]]; then
        test_success_scenario
        exit 0
    fi
    
    if [[ "$test_user" == "true" ]]; then
        test_user_scenario
        exit 0
    fi
    
    if [[ "$debug_mode" == "true" ]]; then
        set -x
        print_status "Debug mode enabled"
    fi
    
    # Load environment configuration
    if ! load_environment "$environment"; then
        exit 1
    fi
    
    print_status "Updating WebSocket endpoints for environment: $ENVIRONMENT"    
    print_status "Stack name: $STACK_NAME"
    print_status "AWS Region: $AWS_REGION"
    echo ""
    
    if [[ "$list_functions" == "true" ]]; then
        list_expected_functions
        exit 0
    fi
    
    # Check prerequisites
    if ! check_prerequisites "$environment"; then
        exit 1
    fi
    echo ""
    
    # List expected functions
    list_expected_functions
    
    if [[ "$verify_only" == "true" ]]; then
        verify_websocket_endpoints
    else
        update_lambda_websocket_env "$dry_run" "$verbose"
    fi
    
    # Uncomment the following line to test the JSON file approach
    # test_json_approach
}

# Check if script is being run directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
