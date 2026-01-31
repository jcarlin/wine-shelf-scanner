#!/bin/bash
# One-time GCP setup for Wine Shelf Scanner API
# Run this once to configure secrets, IAM, and Cloud Build triggers
#
# Prerequisites:
#   1. gcloud CLI installed and authenticated
#   2. GCP project with billing enabled
#   3. GitHub repo connected to Cloud Build (manual step - see below)
#
# To connect GitHub to Cloud Build (required before running this script):
#   1. Go to: https://console.cloud.google.com/cloud-build/triggers
#   2. Click "Connect Repository"
#   3. Select "GitHub" and authenticate
#   4. Select the wine-shelf-scanner repository

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
GITHUB_OWNER="${GITHUB_OWNER:-}"
GITHUB_REPO="${GITHUB_REPO:-wine-shelf-scanner}"

if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}Error: No project ID specified and none found in gcloud config${NC}"
    echo "Usage: ./setup.sh <project-id>"
    exit 1
fi

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Wine Shelf Scanner - GCP Setup${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Project ID: $PROJECT_ID"
echo "Region: $REGION"
echo ""

# Get project number for IAM bindings
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format="value(projectNumber)")
COMPUTE_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
CLOUDBUILD_SA="${PROJECT_NUMBER}@cloudbuild.gserviceaccount.com"

echo -e "${YELLOW}Step 1: Enabling required APIs...${NC}"
gcloud services enable \
    secretmanager.googleapis.com \
    cloudbuild.googleapis.com \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    --project "$PROJECT_ID"
echo -e "${GREEN}✓ APIs enabled${NC}"
echo ""

echo -e "${YELLOW}Step 2: Creating Artifact Registry repository...${NC}"
if gcloud artifacts repositories describe "$REPO_NAME" --location="$REGION" --project="$PROJECT_ID" &>/dev/null; then
    echo -e "${GREEN}✓ Repository '$REPO_NAME' already exists${NC}"
else
    gcloud artifacts repositories create "$REPO_NAME" \
        --repository-format=docker \
        --location="$REGION" \
        --project="$PROJECT_ID" \
        --description="Wine Shelf Scanner container images"
    echo -e "${GREEN}✓ Repository '$REPO_NAME' created${NC}"
fi
echo ""

echo -e "${YELLOW}Step 3: Setting up secrets...${NC}"

# Function to create or update a secret
setup_secret() {
    local secret_name=$1
    local prompt_text=$2
    local env_var=$3

    if gcloud secrets describe "$secret_name" --project="$PROJECT_ID" &>/dev/null; then
        echo "Secret '$secret_name' already exists."
        read -p "Do you want to update it? (y/N): " update_secret
        if [ "$update_secret" = "y" ] || [ "$update_secret" = "Y" ]; then
            # Check if env var is set
            if [ -n "${!env_var}" ]; then
                echo "Using value from \$$env_var environment variable"
                echo -n "${!env_var}" | gcloud secrets versions add "$secret_name" --data-file=- --project="$PROJECT_ID"
            else
                read -sp "$prompt_text: " secret_value
                echo ""
                echo -n "$secret_value" | gcloud secrets versions add "$secret_name" --data-file=- --project="$PROJECT_ID"
            fi
            echo -e "${GREEN}✓ Secret '$secret_name' updated${NC}"
        else
            echo "Skipping '$secret_name'"
        fi
    else
        echo "Creating secret '$secret_name'..."
        gcloud secrets create "$secret_name" \
            --replication-policy="automatic" \
            --project="$PROJECT_ID"

        # Check if env var is set
        if [ -n "${!env_var}" ]; then
            echo "Using value from \$$env_var environment variable"
            echo -n "${!env_var}" | gcloud secrets versions add "$secret_name" --data-file=- --project="$PROJECT_ID"
        else
            read -sp "$prompt_text: " secret_value
            echo ""
            if [ -n "$secret_value" ]; then
                echo -n "$secret_value" | gcloud secrets versions add "$secret_name" --data-file=- --project="$PROJECT_ID"
            else
                echo -e "${YELLOW}Warning: Empty secret value. You can add it later with:${NC}"
                echo "  echo -n 'YOUR_KEY' | gcloud secrets versions add $secret_name --data-file=-"
            fi
        fi
        echo -e "${GREEN}✓ Secret '$secret_name' created${NC}"
    fi
}

setup_secret "google-api-key" "Enter your Google API Key (for Vision API)" "GOOGLE_API_KEY"
setup_secret "anthropic-api-key" "Enter your Anthropic API Key (for Claude)" "ANTHROPIC_API_KEY"
echo ""

echo -e "${YELLOW}Step 4: Granting IAM permissions...${NC}"

# Grant Cloud Run service account access to secrets
echo "Granting secret access to Cloud Run service account..."
for secret in "google-api-key" "anthropic-api-key"; do
    gcloud secrets add-iam-policy-binding "$secret" \
        --member="serviceAccount:$COMPUTE_SA" \
        --role="roles/secretmanager.secretAccessor" \
        --project="$PROJECT_ID" \
        --quiet
done

# Grant Cloud Build service account permission to deploy to Cloud Run
echo "Granting Cloud Run Admin to Cloud Build service account..."
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
    --member="serviceAccount:$CLOUDBUILD_SA" \
    --role="roles/run.admin" \
    --quiet

# Grant Cloud Build permission to act as the compute service account
echo "Granting Service Account User to Cloud Build..."
gcloud iam service-accounts add-iam-policy-binding "$COMPUTE_SA" \
    --member="serviceAccount:$CLOUDBUILD_SA" \
    --role="roles/iam.serviceAccountUser" \
    --project="$PROJECT_ID" \
    --quiet

echo -e "${GREEN}✓ IAM permissions configured${NC}"
echo ""

echo -e "${YELLOW}Step 5: Setting up Cloud Build trigger...${NC}"

# Check if GitHub is connected
if [ -z "$GITHUB_OWNER" ]; then
    echo -e "${YELLOW}Note: GITHUB_OWNER not set. Skipping Cloud Build trigger creation.${NC}"
    echo ""
    echo "To create the trigger manually:"
    echo "  1. Ensure GitHub is connected at https://console.cloud.google.com/cloud-build/triggers"
    echo "  2. Run this command:"
    echo ""
    echo "  gcloud builds triggers create github \\"
    echo "      --repo-name=$GITHUB_REPO \\"
    echo "      --repo-owner=YOUR_GITHUB_USERNAME \\"
    echo "      --branch-pattern='^main\$' \\"
    echo "      --build-config=backend/cloudbuild.yaml \\"
    echo "      --name=deploy-wine-scanner-api \\"
    echo "      --project=$PROJECT_ID"
    echo ""
else
    # Check if trigger already exists
    if gcloud builds triggers describe "deploy-wine-scanner-api" --project="$PROJECT_ID" &>/dev/null; then
        echo -e "${GREEN}✓ Trigger 'deploy-wine-scanner-api' already exists${NC}"
    else
        gcloud builds triggers create github \
            --repo-name="$GITHUB_REPO" \
            --repo-owner="$GITHUB_OWNER" \
            --branch-pattern="^main$" \
            --build-config="backend/cloudbuild.yaml" \
            --name="deploy-wine-scanner-api" \
            --project="$PROJECT_ID"
        echo -e "${GREEN}✓ Cloud Build trigger created${NC}"
    fi
fi
echo ""

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Next steps:"
echo "  1. Deploy manually: ./deploy/deploy.sh"
echo "  2. Or push to main branch to trigger auto-deploy"
echo ""
echo "Useful commands:"
echo "  - View secrets: gcloud secrets list --project=$PROJECT_ID"
echo "  - Update a secret: echo -n 'VALUE' | gcloud secrets versions add SECRET_NAME --data-file=-"
echo "  - View Cloud Build history: gcloud builds list --project=$PROJECT_ID"
echo "  - View Cloud Run service: gcloud run services describe $SERVICE_NAME --region=$REGION"
echo ""
