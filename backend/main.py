"""
Wine Shelf Scanner API

FastAPI backend for processing wine shelf images and returning ratings.

Usage:
    uvicorn main:app --reload
"""

import logging

from fastapi import FastAPI

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
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
