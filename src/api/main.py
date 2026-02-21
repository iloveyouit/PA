"""
FastAPI REST API — Exposes agent services as HTTP endpoints.

Provides authenticated REST endpoints for:
- General orchestrator queries
- Runbook generation
- Terraform module building
- Security audit reports
- Usage statistics and health checks

Includes:
- API key authentication
- Rate limiting
- Request/response logging
- Stripe webhook handler for billing
- CORS support

Usage:
    # Development
    uvicorn src.api.main:app --reload --port 8000

    # Production
    uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --workers 4
"""
import os
import time
import logging
import secrets
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

logger = logging.getLogger("api")

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
try:
    from fastapi import FastAPI, HTTPException, Depends, Header, Request, BackgroundTasks
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    from pydantic import BaseModel, Field
except ImportError:
    raise ImportError(
        "FastAPI not installed. Run: pip install 'fastapi[standard]' uvicorn"
    )


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class OrchestratorRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=5000, description="The request to process")
    max_iterations: int = Field(3, ge=1, le=5, description="Max engineer↔critic iterations")


class RunbookRequest(BaseModel):
    incident: str = Field(..., min_length=1, max_length=5000)
    client: Optional[str] = None
    severity: str = Field("Medium", pattern="^(Critical|High|Medium|Low)$")
    additional_context: Optional[str] = None


class TerraformRequest(BaseModel):
    requirement: str = Field(..., min_length=1, max_length=5000)
    provider: str = Field("azurerm")
    validate: bool = True


class SecurityAuditRequest(BaseModel):
    scope: str = Field(..., min_length=1, max_length=5000)
    client: Optional[str] = None
    focus_areas: Optional[list[str]] = None
    additional_context: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    version: str
    uptime_seconds: float
    services: dict


class UsageResponse(BaseModel):
    total_requests: int
    total_tokens: int
    requests_today: int


# ---------------------------------------------------------------------------
# In-memory state (replace with Redis/DB in production)
# ---------------------------------------------------------------------------
_start_time = time.time()
_request_count = 0
_token_count = 0
_daily_requests: dict[str, int] = {}

# API keys store — in production, use a database
# For now, generate a default key on first run
_API_KEYS_FILE = Path(__file__).resolve().parent.parent.parent / ".secrets" / "api_keys.json"


def _load_api_keys() -> set[str]:
    """Load API keys from file or generate a default."""
    import json
    keys_file = _API_KEYS_FILE

    if keys_file.exists():
        try:
            data = json.loads(keys_file.read_text())
            return set(data.get("keys", []))
        except Exception:
            pass

    # Generate a default key
    default_key = f"pa-{secrets.token_hex(24)}"
    keys_file.parent.mkdir(parents=True, exist_ok=True)
    keys_file.write_text(json.dumps({"keys": [default_key]}, indent=2))
    keys_file.chmod(0o600)
    logger.info("Generated default API key: %s", default_key)
    logger.info("Stored in: %s", keys_file)
    return {default_key}


_valid_api_keys = _load_api_keys()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
async def verify_api_key(x_api_key: str = Header(..., alias="X-API-Key")):
    """Validate the API key from request header."""
    if x_api_key not in _valid_api_keys:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key


# ---------------------------------------------------------------------------
# Rate limiting (simple in-memory)
# ---------------------------------------------------------------------------
_rate_limits: dict[str, list[float]] = {}
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX = 10     # requests per window


async def check_rate_limit(api_key: str = Depends(verify_api_key)):
    """Simple sliding window rate limiter."""
    now = time.time()
    if api_key not in _rate_limits:
        _rate_limits[api_key] = []

    # Clean old entries
    _rate_limits[api_key] = [t for t in _rate_limits[api_key] if now - t < RATE_LIMIT_WINDOW]

    if len(_rate_limits[api_key]) >= RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Max {RATE_LIMIT_MAX} requests per {RATE_LIMIT_WINDOW}s.",
        )

    _rate_limits[api_key].append(now)
    return api_key


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 PA Agent API starting...")
    logger.info("API keys loaded: %d", len(_valid_api_keys))
    yield
    logger.info("PA Agent API shutting down...")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(
    title="PA Self-Improving Agent API",
    description="AI-powered IT infrastructure services: runbooks, Terraform modules, security audits",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve the web portal as static files
_web_dir = Path(__file__).resolve().parent.parent.parent / "web"
if _web_dir.exists():
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse

    @app.get("/", include_in_schema=False)
    async def serve_portal():
        return FileResponse(str(_web_dir / "index.html"))

    app.mount("/static", StaticFiles(directory=str(_web_dir)), name="static")


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------
def _track_request():
    global _request_count
    _request_count += 1
    today = datetime.now().strftime("%Y-%m-%d")
    _daily_requests[today] = _daily_requests.get(today, 0) + 1


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint."""
    services = {}

    # Check API keys
    for key_name in ["ANTHROPIC_API_KEY", "PERPLEXITY_API_KEY", "PINECONE_API_KEY", "E2B_API_KEY"]:
        services[key_name] = "configured" if os.getenv(key_name, "").strip() else "not_set"

    return HealthResponse(
        status="healthy",
        version="1.0.0",
        uptime_seconds=round(time.time() - _start_time, 1),
        services=services,
    )


@app.get("/usage", response_model=UsageResponse, dependencies=[Depends(verify_api_key)])
async def usage():
    """Usage statistics."""
    today = datetime.now().strftime("%Y-%m-%d")
    return UsageResponse(
        total_requests=_request_count,
        total_tokens=_token_count,
        requests_today=_daily_requests.get(today, 0),
    )


@app.post("/v1/query", dependencies=[Depends(check_rate_limit)])
async def query(req: OrchestratorRequest, background_tasks: BackgroundTasks):
    """
    General-purpose query — routes through the full orchestrator
    (Triage → Context → Engineer → Critic → Distill).
    """
    _track_request()
    try:
        from src.orchestrator import run_orchestrator
        result = run_orchestrator(req.query, max_iterations=req.max_iterations)
        return {
            "status": "success",
            "data": result,
        }
    except Exception as e:
        logger.error("Orchestrator error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/runbook", dependencies=[Depends(check_rate_limit)])
async def create_runbook(req: RunbookRequest):
    """Generate an incident runbook."""
    _track_request()
    try:
        from src.services.runbook_generator import generate_runbook
        result = generate_runbook(
            req.incident,
            client=req.client,
            severity=req.severity,
            additional_context=req.additional_context,
        )
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error("Runbook error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/terraform", dependencies=[Depends(check_rate_limit)])
async def create_terraform(req: TerraformRequest):
    """Generate a validated Terraform module."""
    _track_request()
    try:
        from src.services.terraform_builder import build_terraform_module
        result = build_terraform_module(
            req.requirement,
            provider=req.provider,
            validate=req.validate,
        )
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error("Terraform error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/v1/security-audit", dependencies=[Depends(check_rate_limit)])
async def create_security_audit(req: SecurityAuditRequest):
    """Generate a security audit report."""
    _track_request()
    try:
        from src.services.security_audit import generate_security_audit
        result = generate_security_audit(
            req.scope,
            client=req.client,
            focus_areas=req.focus_areas,
            additional_context=req.additional_context,
        )
        return {"status": "success", "data": result}
    except Exception as e:
        logger.error("Audit error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Stripe webhook (billing)
# ---------------------------------------------------------------------------

@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    """
    Handle Stripe webhook events for billing.
    Supports: checkout.session.completed, invoice.paid, invoice.payment_failed
    """
    stripe_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
    if not stripe_secret:
        raise HTTPException(status_code=501, detail="Stripe not configured")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        import stripe
        stripe.api_key = os.getenv("STRIPE_API_KEY", "")
        event = stripe.Webhook.construct_event(payload, sig_header, stripe_secret)
    except ImportError:
        raise HTTPException(status_code=501, detail="stripe package not installed")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Webhook error: {e}")

    event_type = event.get("type", "")
    logger.info("[Stripe] Event: %s", event_type)

    if event_type == "checkout.session.completed":
        session = event["data"]["object"]
        logger.info("[Stripe] Checkout completed: %s", session.get("id"))
        # TODO: Provision access for the customer

    elif event_type == "invoice.paid":
        invoice = event["data"]["object"]
        logger.info("[Stripe] Invoice paid: %s ($%s)", invoice.get("id"), invoice.get("amount_paid", 0) / 100)

    elif event_type == "invoice.payment_failed":
        invoice = event["data"]["object"]
        logger.warning("[Stripe] Payment failed: %s", invoice.get("id"))
        # TODO: Suspend access

    return {"status": "ok"}
