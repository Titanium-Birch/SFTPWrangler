#!/bin/bash

PROFILE=$1
PEER_ID=$2
PEER_EVENTS_URL=$3
ENVIRONMENT=$4

if [ -z "$PROFILE" ] || [ -z "$PEER_ID" ] || [ -z "$PEER_EVENTS_URL" ] || [ -z "$ENVIRONMENT" ]; then
  echo "Invalid arguments. Usage: $0 <profile> <peer_id> <peer_events_url> <environment>"
  exit 1
fi

if [ -z "$WISE_TOKEN" ]; then
  echo "Environment variable: WISE_TOKEN is not set."
  exit 1
fi

if [ "$ENVIRONMENT" == "staging" ]; then
  API_HOSTNAME="api.sandbox.transferwise.tech"
else
  API_HOSTNAME="api.transferwise.com"
fi

echo "Running against $API_HOSTNAME"

MAX_RETRIES=5
SLEEP_TIME=1
RETRY_COUNT=0

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
  response=$(curl -X POST "https://$API_HOSTNAME/v3/profiles/$PROFILE/subscriptions" \
    -d "{\"name\": \"Balance updates for $PEER_ID\", \"trigger_on\": \"balances#update\", \"delivery\": {\"version\": \"3.0.0\", \"url\": \"$PEER_EVENTS_URL\"}}" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $WISE_TOKEN")

  id=$(echo "$response" | jq -r '.id // empty')

  if [ -n "$id" ]; then
    echo "Subscription created successfully! ID: $id"
    exit 0
  else
    echo "Attempt $((RETRY_COUNT+1)) failed. Response: $response. Retrying in $SLEEP_TIME seconds..."
    sleep $SLEEP_TIME
    RETRY_COUNT=$((RETRY_COUNT+1))
  fi
done

echo "Failed to create subscription after $MAX_RETRIES attempts."
exit 1
