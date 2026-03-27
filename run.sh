#!/usr/bin/env bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

banner() {
    echo ""
    echo -e "${CYAN}${BOLD}"
    echo "  ╔═══════════════════════════════════════════════════════╗"
    echo "  ║         SentinelCall — Autonomous SRE Agent          ║"
    echo "  ║     Deep Agents Hackathon | March 27, 2026           ║"
    echo "  ╚═══════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

step() { echo -e "\n${GREEN}▶ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠ $1${NC}"; }
fail() { echo -e "${RED}✗ $1${NC}"; exit 1; }
ok()   { echo -e "${GREEN}✓ $1${NC}"; }

banner

# ------------------------------------------------------------------
# 1. Python check
# ------------------------------------------------------------------
step "Checking Python version..."
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PY_VER=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
        PY_MAJOR=$("$cmd" -c "import sys; print(sys.version_info.major)" 2>/dev/null)
        PY_MINOR=$("$cmd" -c "import sys; print(sys.version_info.minor)" 2>/dev/null)
        if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 10 ] 2>/dev/null; then
            PYTHON="$cmd"
            break
        fi
    fi
done
[ -z "$PYTHON" ] && fail "Python 3.10+ is required. Found: ${PY_VER:-none}"
ok "Python $PY_VER ($PYTHON)"

# ------------------------------------------------------------------
# 2. Virtual environment
# ------------------------------------------------------------------
step "Setting up virtual environment..."
if [ ! -d ".venv" ]; then
    $PYTHON -m venv .venv
    ok "Created .venv"
else
    ok ".venv already exists"
fi

# Activate
source .venv/bin/activate
ok "Activated .venv ($(python3 --version))"

# ------------------------------------------------------------------
# 3. Install dependencies
# ------------------------------------------------------------------
step "Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt
ok "Core dependencies installed"

# Optional: Overmind SDK
if pip install -q overmind 2>/dev/null; then
    ok "Overmind SDK installed"
else
    warn "Overmind SDK not available (optional — in-memory tracing will be used)"
fi

# ------------------------------------------------------------------
# 4. Environment file
# ------------------------------------------------------------------
step "Checking environment configuration..."
if [ ! -f ".env" ]; then
    if [ -f "sentinelcall/.env.example" ]; then
        cp sentinelcall/.env.example .env
        warn "Created .env from template — fill in your API keys for full functionality"
        warn "Edit .env and re-run this script to enable live integrations"
    else
        warn "No .env file found. Running in demo mode (all integrations mocked)"
    fi
else
    ok ".env file found"
fi

# Check which integrations are configured
echo ""
echo -e "${BOLD}  Integration Status:${NC}"

check_key() {
    local key_name="$1"
    local display_name="$2"
    local val=""
    if [ -f ".env" ]; then
        val=$(grep "^${key_name}=" .env 2>/dev/null | cut -d'=' -f2-)
    fi
    if [ -z "$val" ]; then
        val="${!key_name}"
    fi
    if [ -n "$val" ]; then
        echo -e "    ${GREEN}●${NC} $display_name ${GREEN}(live)${NC}"
    else
        echo -e "    ${YELLOW}○${NC} $display_name ${YELLOW}(demo mode)${NC}"
    fi
}

check_key "BLAND_API_KEY"        "Bland AI        — Phone calls"
check_key "AUTH0_DOMAIN"         "Auth0           — CIBA + Token Vault"
check_key "GHOST_URL"            "Ghost CMS       — Incident reports"
check_key "TRUEFOUNDRY_API_KEY"  "TrueFoundry     — AI Gateway"
check_key "OVERMIND_API_KEY"     "Overmind        — LLM tracing"
check_key "ANTHROPIC_API_KEY"    "Anthropic       — LLM fallback"
check_key "GITHUB_TOKEN"        "GitHub          — Macroscope RCA"

# ------------------------------------------------------------------
# 5. Kill any existing instance
# ------------------------------------------------------------------
step "Checking for existing server..."
if lsof -ti:8000 &>/dev/null; then
    warn "Port 8000 in use — stopping existing process"
    kill $(lsof -ti:8000) 2>/dev/null || true
    sleep 1
    ok "Cleared port 8000"
else
    ok "Port 8000 available"
fi

# ------------------------------------------------------------------
# 6. Build frontend (React static export)
# ------------------------------------------------------------------
step "Building frontend..."
if [ -d "frontend" ] && [ -f "frontend/package.json" ]; then
    if ! command -v npm &>/dev/null; then
        warn "npm not found — skipping frontend build (install Node.js for the React landing page)"
    else
        cd frontend
        if npm install --silent 2>/dev/null && npm run build 2>/dev/null; then
            cd ..
            ok "Frontend built (static export in frontend/out/)"
        else
            cd ..
            warn "Frontend build failed — using fallback landing page"
        fi
    fi
else
    warn "Frontend not found — using fallback landing page"
fi

# ------------------------------------------------------------------
# 7. Quick validation
# ------------------------------------------------------------------
step "Validating project..."
python3 -c "
import sys; sys.path.insert(0, '.')
from sentinelcall.agent import SentinelCallAgent
from sentinelcall.dashboard import app
agent = SentinelCallAgent()
routes = [r.path for r in app.routes if hasattr(r, 'path')]
print(f'  Agent: OK | Dashboard: {len(routes)} routes')
" 2>&1 | grep -v "not configured"
ok "All modules loaded successfully"

# ------------------------------------------------------------------
# 8. Launch
# ------------------------------------------------------------------
step "Starting SentinelCall..."
echo ""
echo -e "${BOLD}  Landing:    ${CYAN}http://localhost:8000${NC}"
echo -e "${BOLD}  Dashboard:  ${CYAN}http://localhost:8000/dashboard${NC}"
echo -e "${BOLD}  API Status: ${CYAN}http://localhost:8000/api/status${NC}"
echo -e "${BOLD}  Trigger:    ${CYAN}curl -X POST http://localhost:8000/api/trigger-incident${NC}"
echo -e "${BOLD}  API Docs:   ${CYAN}http://localhost:8000/docs${NC}"
echo ""
echo -e "${GREEN}${BOLD}  Press Ctrl+C to stop the server${NC}"
echo ""

# Open browser (macOS)
if command -v open &>/dev/null; then
    (sleep 2 && open http://localhost:8000) &
fi

# Start server
exec python3 -m uvicorn sentinelcall.dashboard:app --host 0.0.0.0 --port 8000 --reload
