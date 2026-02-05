"""
Wine Shelf Scanner API

FastAPI backend for processing wine shelf images and returning ratings.

Usage:
    uvicorn main:app --reload
"""

# Load environment variables from .env file FIRST
from dotenv import load_dotenv
load_dotenv()

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from app.config import Config

# Configure logging from environment
logging.basicConfig(
    level=getattr(logging, Config.log_level(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
logger.info(f"Starting with LOG_LEVEL={Config.log_level()}, DEV_MODE={Config.is_dev()}")
from fastapi.middleware.cors import CORSMiddleware

from app.routes import scan_router, feedback_router, report_router

# Startup state - set to True once DB is ready
_is_ready = False


def is_ready() -> bool:
    """Check if the service is ready to handle requests."""
    return _is_ready


def set_ready(ready: bool = True):
    """Set the service ready state."""
    global _is_ready
    _is_ready = ready


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    # Startup: mark as ready (DB download handled by startup.py before uvicorn)
    set_ready(True)
    logger.info("Service ready to handle requests")
    yield
    # Shutdown
    set_ready(False)


app = FastAPI(
    title="Wine Shelf Scanner API",
    description="Scan wine shelves and get instant ratings",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS middleware for web and mobile apps
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://wine-shelf-scanner.vercel.app",
        "http://localhost:3000",  # Local Next.js dev
    ],
    allow_origin_regex=r"https://wine-shelf-scanner(-[a-z0-9-]+)?\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def warmup_middleware(request: Request, call_next):
    """Return 503 with retry hint if service is still warming up."""
    # Always allow health checks (for probes) and root
    if request.url.path in ("/health", "/", "/docs", "/openapi.json"):
        return await call_next(request)

    if not is_ready():
        return JSONResponse(
            status_code=503,
            content={
                "error": "Service warming up",
                "message": "The server is starting up. Please retry in a few seconds.",
                "retry_after": 10,
            },
            headers={"Retry-After": "10"},
        )

    return await call_next(request)

# Static files for web UI (e2e testing)
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Include routers
app.include_router(scan_router, tags=["scan"])
app.include_router(feedback_router, tags=["feedback"])
app.include_router(report_router, tags=["report"])


@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "name": "Wine Shelf Scanner API",
        "version": "0.1.0",
        "docs": "/docs",
    }


@app.get("/health")
async def health():
    """Health check endpoint for Cloud Run probes."""
    return {"status": "healthy"}


@app.get("/app")
async def serve_app():
    """Serve the web UI for Playwright e2e testing."""
    index_path = Path(__file__).parent / "static" / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"error": "Web UI not found. Create backend/static/index.html"}
