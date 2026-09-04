"""
Main Application Entry Point for Trading Journal Server
Optimized for Raspberry Pi 3 Model B (1 GB RAM).
"""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

import asyncio
from server.database import init_db
from server.routers import accounts, trades, dashboard, analytics, playbooks, mistakes, sync
from server.connectors.mt_direct_connector import sync_all_active_accounts

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("TradingJournal")

async def background_auto_sync_loop():
    """Periodically syncs all active MT4, MT5, and cTrader accounts in background."""
    while True:
        try:
            await asyncio.sleep(300) # Check every 5 minutes
            logger.info("Executing periodic background auto-sync for trading accounts...")
            sync_all_active_accounts()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Background auto-sync task encountered error: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Trading Journal Server for Raspberry Pi...")
    init_db()
    logger.info("Database initialized.")
    # Launch background auto-sync loop
    sync_task = asyncio.create_task(background_auto_sync_loop())
    yield
    logger.info("Shutting down Trading Journal Server...")
    sync_task.cancel()

app = FastAPI(
    title="Trading Journal Server (Raspi)",
    description="TradeZella-style trading journal with TradingView Lightweight Charts, MT4/MT5/cTrader connectors.",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for local network access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(accounts.router)
app.include_router(trades.router)
app.include_router(dashboard.router)
app.include_router(analytics.router)
app.include_router(playbooks.router)
app.include_router(mistakes.router)
app.include_router(sync.router)

# Static files directory
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/api/health")
def health_check():
    """Health check endpoint for Docker container and monitoring."""
    return {
        "status": "healthy",
        "service": "trading-journal-server",
        "platform": "Raspberry Pi 3 Model B (1 GB RAM Optimized)",
        "ai_enabled": False
    }

@app.get("/")
def serve_spa():
    """Serves the Single Page Web Application."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    return FileResponse(index_path)

if __name__ == "__main__":
    import uvicorn
    # Single worker process with low concurrency limit to keep RAM strictly below 60MB on Pi
    uvicorn.run("server.main:app", host="0.0.0.0", port=8000, reload=False, workers=1)
