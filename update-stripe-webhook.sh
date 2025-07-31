#!/bin/bash
# Script to update Stripe webhook endpoint destination after deployment
# Usage: ./update-stripe-webhook.sh <WEBHOOK_ENDPOINT_ID> <NEW_DESTINATION_URL>
# Or set STRIPE_API_KEY, WEBHOOK_ENDPOINT_ID, and NEW_DESTINATION_URL as environment variables

set -e

# Read from arguments or environment variables
WEBHOOK_ENDPOINT_ID=${1:-$WEBHOOK_ENDPOINT_ID}
NEW_DESTINATION_URL=${2:-$NEW_DESTINATION_URL}
STRIPE_API_KEY=${STRIPE_API_KEY}

if [[ -z "$STRIPE_API_KEY" || -z "$WEBHOOK_ENDPOINT_ID" || -z "$NEW_DESTINATION_URL" ]]; then
  echo "Usage: STRIPE_API_KEY=sk_live_xxx ./update-stripe-webhook.sh <WEBHOOK_ENDPOINT_ID> <NEW_DESTINATION_URL>"
  echo "Or set STRIPE_API_KEY, WEBHOOK_ENDPOINT_ID, and NEW_DESTINATION_URL as environment variables."
  exit 1
fi

# Update the webhook endpoint using Stripe API
response=$(curl -s -X POST https://api.stripe.com/v1/webhook_endpoints/$WEBHOOK_ENDPOINT_ID \
  -u $STRIPE_API_KEY: \
  -d url="$NEW_DESTINATION_URL")

echo "Stripe response: $response"

if echo "$response" | grep -q '"url":'; then
  echo "Webhook endpoint updated successfully."
else
  echo "Failed to update webhook endpoint."
  exit 2
fi
