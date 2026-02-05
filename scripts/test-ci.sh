#!/usr/bin/env bash
#
# Local CI test runner — mirrors .github/workflows/test.yml
#
# Run this before pushing to catch the same failures CI would catch.
#
# Usage:
#   ./scripts/test-ci.sh           # run all checks
#   ./scripts/test-ci.sh backend   # backend only (pytest + docker build)
#   ./scripts/test-ci.sh expo      # expo only
#   ./scripts/test-ci.sh nextjs    # nextjs only
#   ./scripts/test-ci.sh docker    # docker build + startup only

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
FILTER="${1:-all}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
NC='\033[0m'

FAILED=()

step() {
  echo ""
  echo -e "${BOLD}━━━ $1 ━━━${NC}"
}

pass() {
  echo -e "${GREEN}✓ $1${NC}"
}

fail() {
  echo -e "${RED}✗ $1${NC}"
  FAILED+=("$1")
}

# ─── Backend Tests ───────────────────────────────────────────────────────────
run_backend() {
  step "Backend: Install dependencies"
  cd "$ROOT_DIR/backend"

  if [ ! -d "venv" ]; then
    echo "Creating virtualenv..."
    python3 -m venv venv
  fi

  source venv/bin/activate

  pip install -q -r requirements-dev.txt && pass "Backend deps installed" || fail "Backend dep install"

  step "Backend: Install Playwright browsers"
  playwright install chromium > /dev/null 2>&1 && pass "Playwright chromium installed" || fail "Playwright install"

  step "Backend: Run pytest (same filters as CI)"
  # Matches: pytest tests/ -v --tb=short -k "not (test_scan_returns_valid_response or test_accepts_jpeg or test_accepts_png)"
  # Env:     USE_MOCKS=true USE_SQLITE=true
  if USE_MOCKS=true USE_SQLITE=true \
    pytest tests/ -v --tb=short \
    -k "not (test_scan_returns_valid_response or test_accepts_jpeg or test_accepts_png)"; then
    pass "Backend tests"
  else
    fail "Backend tests"
  fi

  deactivate
  cd "$ROOT_DIR"
}

# ─── Backend Docker Build & Startup ─────────────────────────────────────────
run_docker() {
  if ! command -v docker &> /dev/null; then
    echo -e "${YELLOW}⚠ Docker not available — skipping Docker build check${NC}"
    echo -e "${YELLOW}  CI will still run this check. Install Docker to test locally.${NC}"
    return
  fi

  step "Backend Docker: Build image"
  cd "$ROOT_DIR/backend"

  if docker build -t wine-scanner-api:test .; then
    pass "Docker build"
  else
    fail "Docker build"
    cd "$ROOT_DIR"
    return
  fi

  step "Backend Docker: Verify container starts and /health responds"
  docker rm -f wine-test 2>/dev/null || true
  docker run -d --name wine-test \
    -p 8080:8080 \
    -e USE_MOCKS=true \
    -e USE_SQLITE=true \
    wine-scanner-api:test

  HEALTH_OK=false
  for i in $(seq 1 15); do
    if curl -sf http://localhost:8080/health > /dev/null 2>&1; then
      HEALTH_OK=true
      break
    fi
    sleep 2
  done

  if $HEALTH_OK; then
    pass "Docker health check (/health responded)"
  else
    echo "Container logs:"
    docker logs wine-test
    fail "Docker health check (container failed to start)"
  fi

  docker stop wine-test > /dev/null 2>&1 || true
  docker rm wine-test > /dev/null 2>&1 || true
  cd "$ROOT_DIR"
}

# ─── Expo Tests ──────────────────────────────────────────────────────────────
run_expo() {
  step "Expo: Install dependencies"
  cd "$ROOT_DIR/expo"

  npm ci --silent && pass "Expo deps installed" || fail "Expo dep install"

  step "Expo: Type check"
  if npm run type-check; then
    pass "Expo type-check"
  else
    fail "Expo type-check"
  fi

  step "Expo: Tests"
  if npm test; then
    pass "Expo tests"
  else
    fail "Expo tests"
  fi

  cd "$ROOT_DIR"
}

# ─── Next.js Tests ───────────────────────────────────────────────────────────
run_nextjs() {
  step "Next.js: Install dependencies"
  cd "$ROOT_DIR/nextjs"

  npm ci --silent && pass "Next.js deps installed" || fail "Next.js dep install"

  step "Next.js: Type check"
  if npm run type-check; then
    pass "Next.js type-check"
  else
    fail "Next.js type-check"
  fi

  step "Next.js: Lint"
  if npm run lint; then
    pass "Next.js lint"
  else
    fail "Next.js lint"
  fi

  step "Next.js: Build"
  # Mirrors Vercel's build step — catches SSR/import/type errors that tsc alone misses
  if NEXT_PUBLIC_API_BASE_URL="http://localhost:8000" npm run build; then
    pass "Next.js build"
  else
    fail "Next.js build"
  fi

  cd "$ROOT_DIR"
}

# ─── Main ────────────────────────────────────────────────────────────────────
echo -e "${BOLD}Wine Shelf Scanner — Local CI${NC}"
echo "Mirrors .github/workflows/test.yml"
echo "─────────────────────────────────"

case "$FILTER" in
  backend)
    run_backend
    run_docker
    ;;
  docker)  run_docker ;;
  expo)    run_expo ;;
  nextjs)  run_nextjs ;;
  all)
    run_backend
    run_docker
    run_expo
    run_nextjs
    ;;
  *)
    echo "Usage: $0 [all|backend|docker|expo|nextjs]"
    exit 1
    ;;
esac

# ─── Summary ─────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}═══════════════════════════════════${NC}"
if [ ${#FAILED[@]} -eq 0 ]; then
  echo -e "${GREEN}${BOLD}All checks passed — safe to push.${NC}"
  exit 0
else
  echo -e "${RED}${BOLD}${#FAILED[@]} check(s) failed:${NC}"
  for f in "${FAILED[@]}"; do
    echo -e "  ${RED}• $f${NC}"
  done
  echo ""
  echo -e "${YELLOW}Fix these before pushing — CI will fail on the same checks.${NC}"
  exit 1
fi
