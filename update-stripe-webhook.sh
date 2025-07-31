#!/bin/bash
# Script to update Stripe webhook endpoint destination after deployment
set -e

# Show usage
show_usage() {
  echo "Usage: $0 [--help|-h]"
  echo "\nUpdates the Stripe webhook endpoint destination URL after deployment."
  echo "\nRequired environment variables:"
  echo "  STACK_NAME                Name of the deployed CloudFormation stack."
  echo "  AWS_REGION                AWS region where the stack is deployed."
  echo "  STRIPE_SECRET_KEY         Stripe secret key (starts with sk_)."
  echo "  STRIPE_WEBHOOK_ENDPOINT_ID  The Stripe webhook endpoint ID to update."
  echo "\nThis script fetches the new webhook URL from CloudFormation outputs and updates the Stripe webhook endpoint."
  echo "\nExample:"
  echo "  STACK_NAME=your-stack AWS_REGION=us-east-1 STRIPE_SECRET_KEY=sk_test_... STRIPE_WEBHOOK_ENDPOINT_ID=we_... $0"
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

STRIPE_WEBHOOK_DESTINATION_URL=$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$AWS_REGION" \
  --query 'Stacks[0].Outputs[?OutputKey==`ApiWebhookStripePaymentUrl`].OutputValue' \
  --output text)

if [[ -z "$STRIPE_SECRET_KEY" || -z "$STRIPE_WEBHOOK_ENDPOINT_ID" || -z "$STRIPE_WEBHOOK_DESTINATION_URL" || "$STRIPE_WEBHOOK_DESTINATION_URL" == "None" ]]; then
  show_usage
  echo "\nError: STRIPE_SECRET_KEY, STRIPE_WEBHOOK_ENDPOINT_ID, and STRIPE_WEBHOOK_DESTINATION_URL (or STACK_NAME) are required."
  exit 1
fi

# Update the webhook endpoint using Stripe API
response=$(curl -s -X POST https://api.stripe.com/v1/webhook_endpoints/$STRIPE_WEBHOOK_ENDPOINT_ID \
  -u $STRIPE_SECRET_KEY: \
  -d url="$STRIPE_WEBHOOK_DESTINATION_URL")

echo "Stripe response: $response"

if echo "$response" | grep -q '"url":'; then
  echo "Webhook endpoint updated successfully."
  exit 0
else
  echo "Failed to update webhook endpoint."
  exit 2
fi

set -e

