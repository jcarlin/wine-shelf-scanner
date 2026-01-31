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
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import Config

# Configure logging from environment
logging.basicConfig(
    level=getattr(logging, Config.log_level(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)
logger.info(f"Starting with LOG_LEVEL={Config.log_level()}, DEV_MODE={Config.is_dev()}")
from fastapi.middleware.cors import CORSMiddleware

from app.routes import scan_router

app = FastAPI(
    title="Wine Shelf Scanner API",
    description="Scan wine shelves and get instant ratings",
    version="0.1.0",
)

# CORS middleware for iOS app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to your app's bundle ID
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files for web UI (e2e testing)
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Include routers
app.include_router(scan_router, tags=["scan"])


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
