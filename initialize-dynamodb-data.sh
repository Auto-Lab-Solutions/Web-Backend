#!/bin/bash
# Script to initialize DynamoDB tables: ServicePrices, ItemPrices, Staff
# Usage: ./scripts/initialize-dynamodb-data.sh [ENVIRONMENT]

set -e

# Load environment configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$SCRIPT_DIR"
source "$ROOT_DIR/config/environments.sh"

# Accept environment as argument
if [ -n "$1" ]; then
  ENVIRONMENT="$1"
  load_environment "$ENVIRONMENT"
fi


# Load data from JSON files
SEED_DATA_DIR="$ROOT_DIR/dynamodb-seed-data"
SERVICE_PRICES_DATA=$(cat "$SEED_DATA_DIR/ServicePrices.json")
ITEM_PRICES_DATA=$(cat "$SEED_DATA_DIR/ItemPrices.json")
STAFF_DATA=$(cat "$SEED_DATA_DIR/Staff.json")


# Insert data into ServicePrices
echo "$SERVICE_PRICES_DATA" | jq -c '.[]' | while read -r row; do
  aws dynamodb put-item --table-name "$SERVICE_PRICES_TABLE" --item "$row" --region $AWS_REGION
  echo "Inserted into $SERVICE_PRICES_TABLE: $row"
done

# Insert data into ItemPrices
echo "$ITEM_PRICES_DATA" | jq -c '.[]' | while read -r row; do
  aws dynamodb put-item --table-name "$ITEM_PRICES_TABLE" --item "$row" --region $AWS_REGION
  echo "Inserted into $ITEM_PRICES_TABLE: $row"
done

# Insert data into Staff
echo "$STAFF_DATA" | jq -c '.[]' | while read -r row; do
  aws dynamodb put-item --table-name "$STAFF_TABLE" --item "$row" --region $AWS_REGION
  echo "Inserted into $STAFF_TABLE: $row"
done

echo "DynamoDB initialization complete."
