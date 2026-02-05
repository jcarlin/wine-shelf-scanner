# Backend Deployment

This directory contains deployment configuration for the Wine Shelf Scanner API on Google Cloud Run.

## Deployment Methods

### Automatic (GitHub Actions)

Pushing to `main` branch triggers automatic deployment via `.github/workflows/deploy.yml`.

### Manual

```bash
cd backend/deploy
./deploy.sh [project-id]
```

## GitHub Secrets

The following secrets must be configured in GitHub repository settings for CI/CD:

| Secret | Description | Example |
|--------|-------------|---------|
| `GCP_PROJECT_ID` | Google Cloud project ID | `wine-shelf-scanner` |
| `GCP_SERVICE_ACCOUNT` | Service account email for Workload Identity | `github-actions@project.iam.gserviceaccount.com` |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | Full Workload Identity Provider resource name | `projects/123/locations/global/workloadIdentityPools/github/providers/github` |

## Workload Identity Federation Setup

GitHub Actions uses Workload Identity Federation (keyless auth) instead of service account keys.

### 1. Create a Workload Identity Pool

```bash
gcloud iam workload-identity-pools create "github" \
  --location="global" \
  --display-name="GitHub Actions"
```

### 2. Create a Provider for GitHub

```bash
gcloud iam workload-identity-pools providers create-oidc "github" \
  --location="global" \
  --workload-identity-pool="github" \
  --display-name="GitHub" \
  --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository" \
  --issuer-uri="https://token.actions.githubusercontent.com"
```

### 3. Create a Service Account for GitHub Actions

```bash
gcloud iam service-accounts create "github-actions" \
  --display-name="GitHub Actions"
```

### 4. Grant Permissions to the Service Account

```bash
PROJECT_ID=$(gcloud config get-value project)

# Cloud Run deployment
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:github-actions@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/run.admin"

# Artifact Registry (push images)
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:github-actions@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"

# Act as compute service account (for Cloud Run)
gcloud iam service-accounts add-iam-policy-binding \
  $PROJECT_ID-compute@developer.gserviceaccount.com \
  --member="serviceAccount:github-actions@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"
```

### 5. Allow GitHub to Impersonate the Service Account

```bash
PROJECT_ID=$(gcloud config get-value project)
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")
REPO="your-github-username/wine-shelf-scanner"

gcloud iam service-accounts add-iam-policy-binding \
  "github-actions@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github/attribute.repository/$REPO"
```

### 6. Get the Provider Resource Name

```bash
PROJECT_NUMBER=$(gcloud projects describe $(gcloud config get-value project) --format="value(projectNumber)")
echo "projects/$PROJECT_NUMBER/locations/global/workloadIdentityPools/github/providers/github"
```

Use this value for the `GCP_WORKLOAD_IDENTITY_PROVIDER` secret.

## Cloud Run Service Account Permissions

The Cloud Run service uses the default Compute Engine service account. It requires:

- `storage.objects.get` - Download database from GCS
- `secretmanager.versions.access` - Access API keys from Secret Manager

## Secret Manager Secrets

API keys are stored in Secret Manager and referenced in `service.yaml`:

| Secret Name | Description |
|-------------|-------------|
| `google-api-key` | Google API key (Vision API, Gemini) |
| `anthropic-api-key` | Anthropic API key (Claude) |

Create secrets:

```bash
echo -n "your-api-key" | gcloud secrets create google-api-key --data-file=-
echo -n "your-api-key" | gcloud secrets create anthropic-api-key --data-file=-
```

Grant access to the compute service account:

```bash
PROJECT_ID=$(gcloud config get-value project)
PROJECT_NUMBER=$(gcloud projects describe $PROJECT_ID --format="value(projectNumber)")

gcloud secrets add-iam-policy-binding google-api-key \
  --member="serviceAccount:$PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud secrets add-iam-policy-binding anthropic-api-key \
  --member="serviceAccount:$PROJECT_NUMBER-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

## Files

| File | Purpose |
|------|---------|
| `service.yaml` | Cloud Run service definition (source of truth) |
| `env.production.yaml` | Documentation of non-secret env vars |
| `deploy.sh` | Manual deployment script |
| `setup.sh` | One-time GCP infrastructure setup |
| `update-env.sh` | Update env vars without rebuild (use cautiously) |
