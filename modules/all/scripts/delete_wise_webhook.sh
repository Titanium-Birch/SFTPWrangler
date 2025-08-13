#!/bin/bash

PROFILE=$1
PEER_ID=$2
ENVIRONMENT=$3

WISE_TOKEN="${WISE_TOKEN:-}"

if [ -z "$PROFILE" ] || [ -z "$PEER_ID" ] || [ -z "$ENVIRONMENT" ]; then
  echo "Invalid arguments. Usage: $0 <profile> <peer_id> <environment>"
  exit 1
fi

if [ "$ENVIRONMENT" == "staging" ]; then
  API_HOSTNAME="api.sandbox.transferwise.tech"
else
  API_HOSTNAME="api.transferwise.com"
fi

echo "Running against $API_HOSTNAME"

response=$(curl -X GET "https://$API_HOSTNAME/v3/profiles/$PROFILE/subscriptions" \
-H "Authorization: Bearer $WISE_TOKEN")

subscription_id=$(echo "$response" | jq -r ".[] | select(.delivery.url | endswith(\"$PEER_ID\")) | .id")

if [ -n "$subscription_id" ]; then
  curl -X DELETE "https://$API_HOSTNAME/v3/profiles/$PROFILE/subscriptions/$subscription_id" \
  -H "Authorization: Bearer $WISE_TOKEN"
  echo "Deleted subscription with ID: $subscription_id"
else
  echo "No webhook subscription found for $PEER_ID"
fi
