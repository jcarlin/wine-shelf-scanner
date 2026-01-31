#!/bin/bash
# Update Cloud Run environment variables without rebuilding
# Reads from env.production.yaml and applies to the running service
#
# Usage: ./update-env.sh [project-id]
#
# Prerequisites: yq (brew install yq)

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
PROJECT_ID=${1:-$(gcloud config get-value project 2>/dev/null)}
REGION="us-central1"
SERVICE_NAME="wine-scanner-api"

if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}Error: No project ID specified and none found in gcloud config${NC}"
    echo "Usage: ./update-env.sh <project-id>"
    exit 1
fi

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/env.production.yaml"

# Check for yq
if ! command -v yq &> /dev/null; then
    echo -e "${RED}Error: yq is required but not installed${NC}"
    echo "Install with: brew install yq"
    exit 1
fi

# Check env file exists
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}Error: $ENV_FILE not found${NC}"
    exit 1
fi

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Updating Environment Variables${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Project ID: $PROJECT_ID"
echo "Service: $SERVICE_NAME"
echo "Region: $REGION"
echo ""

# Parse env.production.yaml and build env var string
echo -e "${YELLOW}Reading environment variables from env.production.yaml...${NC}"

# Extract env vars and format as KEY=VALUE,KEY=VALUE
ENV_VARS=$(yq -r '.env | to_entries | map("\(.key)=\(.value)") | join(",")' "$ENV_FILE")

if [ -z "$ENV_VARS" ]; then
    echo -e "${RED}Error: No environment variables found in $ENV_FILE${NC}"
    exit 1
fi

echo "Variables to set:"
yq -r '.env | to_entries | .[] | "  \(.key)=\(.value)"' "$ENV_FILE"
echo ""

# Update the Cloud Run service
echo -e "${YELLOW}Applying to Cloud Run service...${NC}"
gcloud run services update "$SERVICE_NAME" \
    --region "$REGION" \
    --project "$PROJECT_ID" \
    --set-env-vars "$ENV_VARS"

echo ""
echo -e "${GREEN}✓ Environment variables updated${NC}"
echo ""

# Verify the update
echo -e "${YELLOW}Current service configuration:${NC}"
gcloud run services describe "$SERVICE_NAME" \
    --region "$REGION" \
    --project "$PROJECT_ID" \
    --format="yaml(spec.template.spec.containers[0].env)"
echo ""
