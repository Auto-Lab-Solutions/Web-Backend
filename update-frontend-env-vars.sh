#!/bin/bash
# Script to update environment variables in a GitHub repository environment after deployment

show_usage() {
    echo "Usage: $0 [--help|-h]"
    echo "\nUpdates environment variables in a GitHub repository environment after deployment."
    echo "\nRequired environment variables:"
    echo "  FRONTEND_GITHUB_TOKEN       GitHub token with permissions to update repository environments."
    echo "  FRONTEND_REPO_OWNER                  Owner of the GitHub repository."
    echo "  FRONTEND_REPO_NAME                   Name of the GitHub repository."
    echo "  ENVIRONMENT                 Name of the GitHub environment to update."
    echo "  STACK_NAME                  Name of the deployed CloudFormation stack."
    echo "\nThis script retrieves values from the CloudFormation stack outputs and updates the specified GitHub environment variables."
    echo "\nExample:"
    echo "  FRONTEND_GITHUB_TOKEN=ghp_... FRONTEND_REPO_OWNER=Auto-Lab-Solutions FRONTEND_REPO_NAME=Web-Frontend ENVIRONMENT=production STACK_NAME=your-stack $0"
    echo "\nNote: Ensure that the required environment variables are set before running this script."
}

if [[ "$1" == "--help" || "$1" == "-h" ]]; then
  show_usage
  echo ""
  exit 0
fi

# Load environment configuration
source config/environments.sh

# Load environment configuration
if ! load_environment "$ENVIRONMENT"; then
    exit 1
fi

if [ -z "$FRONTEND_GITHUB_TOKEN" ] || [ -z "$FRONTEND_REPO_OWNER" ] || [ -z "$FRONTEND_REPO_NAME" ] || [ -z "$ENVIRONMENT" ] || [ -z "$STACK_NAME" ] || [ -z "$STRIPE_PUBLISHABLE_KEY" ]; then
  echo "Error: FRONTEND_GITHUB_TOKEN, FRONTEND_REPO_OWNER, FRONTEND_REPO_NAME, ENVIRONMENT, STACK_NAME, or STRIPE_PUBLISHABLE_KEY is not set."
  show_usage
  exit 1
fi

# Retrieve values from CloudFormation stack outputs
STACK_OUTPUTS=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --query "Stacks[0].Outputs" --output json)

API_GATEWAY_BASE_URL=$(echo "$STACK_OUTPUTS" | jq -r '.[] | select(.OutputKey=="RestApiEndpoint") | .OutputValue')
WEB_SOCKET_BASE_URL=$(echo "$STACK_OUTPUTS" | jq -r '.[] | select(.OutputKey=="WebSocketApiEndpoint") | .OutputValue')
CLOUDFRONT_DISTRIBUTION_ID=$(echo "$STACK_OUTPUTS" | jq -r '.[] | select(.OutputKey=="FrontendCloudFrontDistributionId") | .OutputValue')
S3_BUCKET_NAME=$(echo "$STACK_OUTPUTS" | jq -r '.[] | select(.OutputKey=="FrontendBucketName") | .OutputValue')

if [ -z "$API_GATEWAY_BASE_URL" ] || [ -z "$WEB_SOCKET_BASE_URL" ] || [ -z "$CLOUDFRONT_DISTRIBUTION_ID" ] || [ -z "$S3_BUCKET_NAME" ]; then
  echo "Error: One or more required outputs are missing from the CloudFormation stack."
  exit 1
fi

# Prepare environment variable names and values
declare -A ENV_VARS
ENV_VARS=(
  ["API_GATEWAY_BASE_URL"]="$API_GATEWAY_BASE_URL"
  ["WEB_SOCKET_BASE_URL"]="$WEB_SOCKET_BASE_URL"
  ["CLOUDFRONT_DISTRIBUTION_ID"]="$CLOUDFRONT_DISTRIBUTION_ID"
  ["S3_BUCKET_NAME"]="$S3_BUCKET_NAME"
  ["STRIPE_PUBLISHABLE_KEY"]="$STRIPE_PUBLISHABLE_KEY"
)

# Loop through environment variables and set them in the GitHub environment

# Improved: Use variable ID for PATCH, check HTTP status, and stricter error handling
set -euo pipefail

for VAR_NAME in "${!ENV_VARS[@]}"; do
  VAR_VALUE="${ENV_VARS[$VAR_NAME]}"
  if [ -z "$VAR_VALUE" ]; then
    echo "Error: Environment variable $VAR_NAME is not set."
    exit 1
  fi

  echo "Setting environment variable $VAR_NAME in $FRONTEND_REPO_OWNER/$FRONTEND_REPO_NAME/$ENVIRONMENT..."

  # Get all variables and try to find the variable ID for this name
  VARS_JSON=$(curl -s -H "Authorization: Bearer $FRONTEND_GITHUB_TOKEN" \
    "https://api.github.com/repos/$FRONTEND_REPO_OWNER/$FRONTEND_REPO_NAME/environments/$ENVIRONMENT/variables")
  VAR_ID=$(echo "$VARS_JSON" | jq -r ".variables[] | select(.name == \"$VAR_NAME\") | .id" || true)

  if [ -z "$VAR_ID" ] || [ "$VAR_ID" == "null" ]; then
    # Try to create variable in environment
    RESP=$(curl -s -w "%{http_code}" -o /tmp/gh_var_resp.json -X POST \
      -H "Authorization: Bearer $FRONTEND_GITHUB_TOKEN" \
      -H "Content-Type: application/json" \
      -d "{\"name\":\"$VAR_NAME\",\"value\":\"$VAR_VALUE\"}" \
      "https://api.github.com/repos/$FRONTEND_REPO_OWNER/$FRONTEND_REPO_NAME/environments/$ENVIRONMENT/variables")
    if [ "$RESP" -ge 200 ] && [ "$RESP" -lt 300 ]; then
      echo "Created environment variable $VAR_NAME in $FRONTEND_REPO_NAME/$ENVIRONMENT."
    else
      # Check if error is 409 (already exists), then update instead
      HTTP_STATUS=$(tail -c 3 /tmp/gh_var_resp.json | tr -d '\n')
      if grep -q '"status": "409"' /tmp/gh_var_resp.json || grep -q 'Already exists' /tmp/gh_var_resp.json; then
        # Get variable ID and update
        VARS_JSON=$(curl -s -H "Authorization: Bearer $FRONTEND_GITHUB_TOKEN" \
          "https://api.github.com/repos/$FRONTEND_REPO_OWNER/$FRONTEND_REPO_NAME/environments/$ENVIRONMENT/variables")
        VAR_ID=$(echo "$VARS_JSON" | jq -r ".variables[] | select(.name == \"$VAR_NAME\") | .id" || true)
        if [ -z "$VAR_ID" ] || [ "$VAR_ID" == "null" ]; then
          echo "Error: Could not retrieve variable ID for $VAR_NAME after 409 conflict."
          cat /tmp/gh_var_resp.json
          exit 1
        fi
        RESP=$(curl -s -w "%{http_code}" -o /tmp/gh_var_resp.json -X PATCH \
          -H "Authorization: Bearer $FRONTEND_GITHUB_TOKEN" \
          -H "Content-Type: application/json" \
          -d "{\"name\":\"$VAR_NAME\",\"value\":\"$VAR_VALUE\"}" \
          "https://api.github.com/repos/$FRONTEND_REPO_OWNER/$FRONTEND_REPO_NAME/environments/$ENVIRONMENT/variables/$VAR_ID")
        if [ "$RESP" -ge 200 ] && [ "$RESP" -lt 300 ]; then
          echo "Updated environment variable $VAR_NAME in $FRONTEND_REPO_NAME/$ENVIRONMENT (after 409 conflict)."
        else
          echo "Error: Failed to update environment variable $VAR_NAME after 409 conflict. Response:"
          cat /tmp/gh_var_resp.json
          exit 1
        fi
      else
        echo "Error: Failed to create environment variable $VAR_NAME. Response:"
        cat /tmp/gh_var_resp.json
        exit 1
      fi
    fi
  else
    # Update variable in environment using variable ID
    RESP=$(curl -s -w "%{http_code}" -o /tmp/gh_var_resp.json -X PATCH \
      -H "Authorization: Bearer $FRONTEND_GITHUB_TOKEN" \
      -H "Content-Type: application/json" \
      -d "{\"name\":\"$VAR_NAME\",\"value\":\"$VAR_VALUE\"}" \
      "https://api.github.com/repos/$FRONTEND_REPO_OWNER/$FRONTEND_REPO_NAME/environments/$ENVIRONMENT/variables/$VAR_ID")
    if [ "$RESP" -ge 200 ] && [ "$RESP" -lt 300 ]; then
      echo "Updated environment variable $VAR_NAME in $FRONTEND_REPO_NAME/$ENVIRONMENT."
    else
      echo "Error: Failed to update environment variable $VAR_NAME. Response:"
      cat /tmp/gh_var_resp.json
      exit 1
    fi
  fi
done

echo "All environment variables have been set successfully in $FRONTEND_REPO_NAME/$ENVIRONMENT."
