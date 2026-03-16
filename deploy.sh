#!/usr/bin/env bash
# deploy.sh — Deploy Clarity Studio to Google Cloud Run
set -euo pipefail

# ── Config (override via env or edit here) ────────────────────────────────────
PROJECT_ID="${GCP_PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${GCP_REGION:-us-central1}"
SERVICE_NAME="clarity-studio"
SECRET_NAME="GEMINI_API_KEY_SECRET"

# ── Colours ───────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()    { echo -e "${CYAN}[deploy]${NC} $*"; }
success() { echo -e "${GREEN}[deploy]${NC} $*"; }
warn()    { echo -e "${YELLOW}[deploy]${NC} $*"; }
die()     { echo -e "${RED}[deploy] ERROR:${NC} $*" >&2; exit 1; }

# ── Pre-flight ────────────────────────────────────────────────────────────────
[[ -z "$PROJECT_ID" ]] && die "GCP_PROJECT_ID not set. Run: export GCP_PROJECT_ID=your-project-id"
command -v gcloud &>/dev/null || die "gcloud CLI not found. Install: https://cloud.google.com/sdk/"
command -v docker  &>/dev/null || warn "docker not found — Cloud Run source deploy will be used instead"

info "Project  : $PROJECT_ID"
info "Region   : $REGION"
info "Service  : $SERVICE_NAME"

# ── Ensure Secret Exists ──────────────────────────────────────────────────────
info "Checking for Secret Manager secret: $SECRET_NAME"
if ! gcloud secrets describe "$SECRET_NAME" --project="$PROJECT_ID" &>/dev/null; then
  if [[ -z "${GEMINI_API_KEY:-}" ]]; then
    die "Secret '$SECRET_NAME' not found and GEMINI_API_KEY env var not set.\n  Create the secret first:\n  echo -n 'YOUR_KEY' | gcloud secrets create $SECRET_NAME --data-file=- --project=$PROJECT_ID"
  fi
  info "Creating secret $SECRET_NAME from GEMINI_API_KEY env var..."
  echo -n "$GEMINI_API_KEY" | gcloud secrets create "$SECRET_NAME" \
    --data-file=- \
    --project="$PROJECT_ID" \
    --replication-policy=automatic
  success "Secret created."
else
  success "Secret $SECRET_NAME exists."
fi

# ── Deploy to Cloud Run ───────────────────────────────────────────────────────
info "Deploying backend to Cloud Run (source-based build)..."
gcloud run deploy "$SERVICE_NAME" \
  --source ./backend \
  --platform managed \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --allow-unauthenticated \
  --set-secrets="GEMINI_API_KEY=${SECRET_NAME}:latest" \
  --memory 512Mi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 10 \
  --timeout 300 \
  --port 8080

# ── Get Service URL ───────────────────────────────────────────────────────────
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" \
  --region "$REGION" \
  --project "$PROJECT_ID" \
  --format="value(status.url)")

success "Backend deployed: $SERVICE_URL"

# ── Update frontend config ────────────────────────────────────────────────────
FRONTEND_CONFIG="frontend/index.html"
if [[ -f "$FRONTEND_CONFIG" ]]; then
  info "Patching backend URL in frontend/index.html..."
  sed -i "s|value=\"http://localhost:8080\"|value=\"$SERVICE_URL\"|g" "$FRONTEND_CONFIG"
  success "Frontend patched with live URL: $SERVICE_URL"
fi

echo ""
success "=== Deployment complete ==="
echo -e "  Backend URL : ${CYAN}$SERVICE_URL${NC}"
echo -e "  Health check: ${CYAN}$SERVICE_URL/health${NC}"
echo ""
echo -e "  To test locally:"
echo -e "    ${YELLOW}cd backend && pip install -r requirements.txt${NC}"
echo -e "    ${YELLOW}GEMINI_API_KEY=your_key uvicorn main:app --reload --port 8080${NC}"
echo -e "  Then open frontend/index.html in your browser."
