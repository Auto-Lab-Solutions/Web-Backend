
#!/bin/bash
# This script updates only Lambda function code without redeploying infrastructure

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source environment configuration
source "$SCRIPT_DIR/config/environments.sh"

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
    echo "Usage: $0 [OPTIONS] [FUNCTION_NAMES...]"
    echo ""
    echo "Update Lambda function code without redeploying infrastructure"
    echo ""
    echo "Options:"
    echo "  --env, -e <env>        Specify environment (development/dev, production/prod)"
    echo "  --all, -a              Update all Lambda functions"
    echo "  --list, -l             List all available Lambda functions"
    echo "  --help, -h             Show this help message"
    echo ""
    echo "Pipeline/Automated Execution:"
    echo "  export AUTO_CONFIRM=true    # Skip all confirmation prompts"
    echo "  export CI=true              # Detected in most CI/CD systems"
    echo "  export GITHUB_ACTIONS=true  # Auto-detected in GitHub Actions"
    echo ""
    echo "Examples:"
    echo "  $0 --env dev --all                           # Update all functions in dev"
    echo "  $0 --env prod api-get-prices api-get-users   # Update specific functions in prod"
    echo "  $0 --list                                     # List all functions"
    echo ""
}

# Function to list all Lambda functions
list_functions() {
    print_status "Available Lambda functions:"
    echo ""
    echo "API Functions:"
    for lambda_dir in lambda/api-*/; do
        if [ -d "$lambda_dir" ]; then
            lambda_name=$(basename "$lambda_dir")
            echo "  - $lambda_name"
        fi
    done
    echo ""
    echo "WebSocket Functions:"
    for lambda_dir in lambda/ws-*/; do
        if [ -d "$lambda_dir" ]; then
            lambda_name=$(basename "$lambda_dir")
            echo "  - $lambda_name"
        fi
    done
    echo ""
    echo "Authorizer Functions:"
    for lambda_dir in lambda/staff-authorizer*/; do
        if [ -d "$lambda_dir" ]; then
            lambda_name=$(basename "$lambda_dir")
            echo "  - $lambda_name"
        fi
    done
}

# Function to get all Lambda function names
get_all_functions() {
    local functions=()
    for lambda_dir in lambda/*/; do
        if [ -d "$lambda_dir" ] && [ "$(basename "$lambda_dir")" != "common_lib" ] && [ "$(basename "$lambda_dir")" != "tmp" ]; then
            functions+=($(basename "$lambda_dir"))
        fi
    done
    echo "${functions[@]}"
}

# Function to check if Lambda function exists in AWS
function_exists() {
    local function_name=$1
    local full_function_name="${function_name}-${ENVIRONMENT}"
    aws lambda get-function --function-name "$full_function_name" --region $AWS_REGION &>/dev/null
}

# Function to package a single Lambda function
package_lambda() {
    local lambda_name=$1
    local lambda_dir="lambda/$lambda_name"
    
    if [ ! -d "$lambda_dir" ]; then
        print_error "Lambda directory not found: $lambda_dir"
        return 1
    fi
    if [ "$lambda_dir" == "lambda/common_lib/" ]; then
        continue  # Skip common library directory
    fi
    
    print_status "Packaging $lambda_name..."
    
    # Create temp directory
    local temp_dir="dist/lambda/$lambda_name"
    mkdir -p "$temp_dir"
    
    # Copy function code
    cp "$lambda_dir"/*.py "$temp_dir/" 2>/dev/null || {
        print_error "No Python files found in $lambda_dir"
        return 1
    }
    
    # Copy common library
    if [ -d "lambda/common_lib" ]; then
        cp lambda/common_lib/*.py "$temp_dir/"
    fi
    
    # Install requirements if requirements.txt exists
    if [ -f "$lambda_dir/requirements.txt" ]; then
        print_status "Installing dependencies for $lambda_name..."
        pip3 install -r "$lambda_dir/requirements.txt" -t "$temp_dir/" -q
    fi
    
    # Create ZIP file
    cd "$temp_dir"
    zip -r "../$lambda_name.zip" . -q
    cd - > /dev/null

    # Upload to S3
    aws s3 cp "dist/lambda/$lambda_name.zip" "s3://$CLOUDFORMATION_BUCKET/lambda/$lambda_name.zip"
    
    print_success "Packaged $lambda_name"
    return 0
}

# Function to update Lambda function code
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

# Function to update multiple Lambda functions
update_functions() {
    local functions=("$@")
    local success_count=0
    local error_count=0
    
    print_status "Updating ${#functions[@]} Lambda function(s)..."
    echo ""
    
    # Create dist directory
    mkdir -p dist/lambda
    
    for lambda_name in "${functions[@]}"; do
        echo "----------------------------------------"
        
        # Package the function
        if package_lambda "$lambda_name"; then
            # Update the function
            if update_lambda_code "$lambda_name"; then
                ((success_count++))
            else
                ((error_count++))
            fi
        else
            ((error_count++))
        fi
        
        echo ""
    done
    
    echo "========================================"
    print_status "Update Summary:"
    print_success "Successfully updated: $success_count function(s)"
    if [ $error_count -gt 0 ]; then
        print_error "Failed to update: $error_count function(s)"
    fi
    echo ""
    
    return $error_count
}

# Function to validate function names
validate_functions() {
    local functions=("$@")
    local invalid_functions=()
    
    for func in "${functions[@]}"; do
        if [ ! -d "lambda/$func" ]; then
            invalid_functions+=("$func")
        fi
    done
    
    if [ ${#invalid_functions[@]} -gt 0 ]; then
        print_error "Invalid function names:"
        for func in "${invalid_functions[@]}"; do
            echo "  - $func"
        done
        echo ""
        print_status "Use --list to see available functions"
        return 1
    fi
    
    return 0
}

# Function to confirm update
confirm_update() {
    local functions=("$@")
    
    echo ""
    print_warning "About to update the following Lambda function(s):"
    for func in "${functions[@]}"; do
        echo "  - $func"
    done
    echo ""
    
    # Skip confirmation prompt in CI/CD environments or if AUTO_CONFIRM is set
    if [ -n "$GITHUB_ACTIONS" ] || [ -n "$CI" ] || [ "$AUTO_CONFIRM" = "true" ]; then
        print_status "Running in automated environment - proceeding with update"
    else
        read -p "Continue? (y/N): " -n 1 -r
        echo ""
        
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            print_status "Update cancelled."
            exit 0
        fi
    fi
}

# Main function
main() {
    local update_all=false
    local show_list=false
    local environment=""
    local functions_to_update=()
    
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --env|-e)
                environment="$2"
                shift 2
                ;;
            --all|-a)
                update_all=true
                shift
                ;;
            --list|-l)
                show_list=true
                shift
                ;;
            --help|-h)
                show_usage
                exit 0
                ;;
            -*)
                print_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
            *)
                functions_to_update+=("$1")
                shift
                ;;
        esac
    done
    
    # Load environment configuration
    if ! load_environment "$environment"; then
        exit 1
    fi
    
    print_status "Using environment: $ENVIRONMENT"
    print_status "Stack name: $STACK_NAME"
    print_status "AWS Region: $AWS_REGION"
    echo ""
    
    # Handle list option
    if [ "$show_list" = true ]; then
        list_functions
        exit 0
    fi
    
    # Handle all functions option
    if [ "$update_all" = true ]; then
        readarray -t functions_to_update < <(get_all_functions | tr ' ' '\n')
    fi
    
    # Check if no functions specified
    if [ ${#functions_to_update[@]} -eq 0 ]; then
        print_error "No Lambda functions specified"
        echo ""
        show_usage
        exit 1
    fi
    
    # Validate function names
    if ! validate_functions "${functions_to_update[@]}"; then
        exit 1
    fi
    
    # Check prerequisites
    if ! command -v aws &> /dev/null; then
        print_error "AWS CLI not found. Please install AWS CLI."
        exit 1
    fi
    
    if ! command -v python3 &> /dev/null; then
        print_error "Python3 not found. Please install Python3."
        exit 1
    fi
    
    if ! aws sts get-caller-identity &> /dev/null; then
        print_error "AWS credentials not configured. Please run 'aws configure'."
        exit 1
    fi
    
    # Confirm update
    confirm_update "${functions_to_update[@]}"
    
    # Update functions
    print_status "Starting Lambda function updates..."
    update_functions "${functions_to_update[@]}"
    
    local exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        print_success "All Lambda functions updated successfully! 🚀"
    else
        print_warning "Some Lambda functions failed to update. Check the output above."
    fi

    exit $exit_code
}

# Check if script is being run directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
