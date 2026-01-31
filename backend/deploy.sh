#!/bin/bash
# Quick deploy script for Wine Shelf Scanner API
# Usage: ./deploy.sh [project-id]

set -e

PROJECT_ID=${1:-$(gcloud config get-value project)}

if [ -z "$PROJECT_ID" ]; then
    echo "Error: No project ID specified and none found in gcloud config"
    echo "Usage: ./deploy.sh <project-id>"
    exit 1
fi

echo "Deploying to project: $PROJECT_ID"
echo "Region: us-central1"
echo ""

# Deploy directly from source (simpler than Cloud Build for small projects)
gcloud run deploy wine-scanner-api \
    --source . \
    --project "$PROJECT_ID" \
    --region us-central1 \
    --platform managed \
    --allow-unauthenticated \
    --memory 1Gi \
    --min-instances 0 \
    --max-instances 10 \
    --set-env-vars "USE_MOCKS=false,DEV_MODE=true,LOG_LEVEL=DEBUG"

echo ""
echo "Deployment complete!"
echo "Run 'gcloud run services describe wine-scanner-api --region us-central1' to see the URL"
