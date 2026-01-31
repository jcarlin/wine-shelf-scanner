#!/bin/bash
# Manual deployment script for Wine Shelf Scanner API
# Builds Docker image, pushes to Artifact Registry, and deploys to Cloud Run
#
# Usage: ./deploy.sh [project-id]

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
REPO_NAME="wine-scanner"
IMAGE_TAG="${IMAGE_TAG:-$(date +%Y%m%d-%H%M%S)}"

if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}Error: No project ID specified and none found in gcloud config${NC}"
    echo "Usage: ./deploy.sh <project-id>"
    exit 1
fi

# Derived values
IMAGE_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${SERVICE_NAME}:${IMAGE_TAG}"
LATEST_URI="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${SERVICE_NAME}:latest"

# Get script directory and backend directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(dirname "$SCRIPT_DIR")"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Wine Shelf Scanner - Manual Deploy${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Project ID: $PROJECT_ID"
echo "Region: $REGION"
echo "Image: $IMAGE_URI"
echo ""

# Configure Docker for Artifact Registry
echo -e "${YELLOW}Step 1: Configuring Docker authentication...${NC}"
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
echo -e "${GREEN}✓ Docker configured${NC}"
echo ""

# Build the Docker image for linux/amd64 (Cloud Run requirement)
echo -e "${YELLOW}Step 2: Building Docker image (linux/amd64)...${NC}"
cd "$BACKEND_DIR"
docker buildx build --platform linux/amd64 -t "$IMAGE_URI" -t "$LATEST_URI" --load .
echo -e "${GREEN}✓ Image built${NC}"
echo ""

# Push to Artifact Registry
echo -e "${YELLOW}Step 3: Pushing to Artifact Registry...${NC}"
docker push "$IMAGE_URI"
docker push "$LATEST_URI"
echo -e "${GREEN}✓ Image pushed${NC}"
echo ""

# Deploy to Cloud Run using service.yaml
echo -e "${YELLOW}Step 4: Deploying to Cloud Run...${NC}"

# Create a temporary service.yaml with the actual image
TEMP_SERVICE_YAML=$(mktemp)
sed "s|IMAGE_PLACEHOLDER|${IMAGE_URI}|g" "$SCRIPT_DIR/service.yaml" > "$TEMP_SERVICE_YAML"

# Deploy using the service definition
gcloud run services replace "$TEMP_SERVICE_YAML" \
    --region "$REGION" \
    --project "$PROJECT_ID"

# Clean up temp file
rm -f "$TEMP_SERVICE_YAML"

echo -e "${GREEN}✓ Service deployed${NC}"
echo ""

# Set IAM policy for public access
echo -e "${YELLOW}Step 5: Setting public access...${NC}"
gcloud run services add-iam-policy-binding "$SERVICE_NAME" \
    --region "$REGION" \
    --project "$PROJECT_ID" \
    --member="allUsers" \
    --role="roles/run.invoker" \
    --quiet
echo -e "${GREEN}✓ Public access configured${NC}"
echo ""

# Get service URL
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
    --region "$REGION" \
    --project "$PROJECT_ID" \
    --format="value(status.url)")

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Service URL: $SERVICE_URL"
echo ""
echo "Test the deployment:"
echo "  curl ${SERVICE_URL}/health"
echo "  curl ${SERVICE_URL}/docs"
echo ""
