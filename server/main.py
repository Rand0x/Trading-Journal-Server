"""
Main Application Entry Point for Trading Journal Server
"""

import base64
import os
import logging
import secrets
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

import asyncio
from server.database import init_db
from server.routers import accounts, trades, dashboard, analytics, playbooks, mistakes, sync
from server.connectors.ctrader_api import sync_all_active_ctrader_accounts

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("TradingJournal")

_UNPROTECTED_PATHS = {
    "/api/health",
    "/api/sync/mql",
    "/api/sync/ctrader-push",
    "/favicon.ico",
    "/apple-touch-icon.png",
}


def get_access_credentials():
    """Return optional HTTP Basic Auth credentials from the environment."""
    username = os.getenv("JOURNAL_USERNAME", "")
    password = os.getenv("JOURNAL_PASSWORD", "")
    if bool(username) != bool(password):
        raise RuntimeError(
            "Set both JOURNAL_USERNAME and JOURNAL_PASSWORD, or set neither."
        )
    return (username, password) if username else None


def is_authorized(authorization_header: str | None, credentials: tuple[str, str]) -> bool:
    """Validate a Basic Auth header without logging credentials."""
    if not authorization_header or not authorization_header.startswith("Basic "):
        return False
    try:
        supplied = base64.b64decode(
            authorization_header.removeprefix("Basic "), validate=True
        ).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return False
    expected = f"{credentials[0]}:{credentials[1]}"
    return secrets.compare_digest(supplied, expected)

async def background_auto_sync_loop():
    """Periodically syncs configured cTrader accounts in background."""
    while True:
        try:
            await asyncio.sleep(300) # Check every 5 minutes
            logger.info("Executing periodic background cTrader auto-sync...")
            # Broker connectors use blocking network clients. Keep them off
            # the asyncio event loop so health checks and the UI stay responsive.
            await asyncio.to_thread(sync_all_active_ctrader_accounts)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Background auto-sync task encountered error: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    get_access_credentials()  # Fail fast on an incomplete authentication setup.
    logger.info("Starting Trading Journal Server...")
    init_db()
    logger.info("Database initialized.")
    # Launch background auto-sync loop
    sync_task = asyncio.create_task(background_auto_sync_loop())
    yield
    logger.info("Shutting down Trading Journal Server...")
    sync_task.cancel()
    try:
        await sync_task
    except asyncio.CancelledError:
        pass

app = FastAPI(
    title="Trading Journal Server",
    description="TradeZella-style trading journal with TradingView Lightweight Charts, MT4/MT5/cTrader connectors.",
    version="1.0.0",
    lifespan=lifespan
)

# The bundled web interface is served from the same origin. Cross-origin
# requests remain disabled unless explicitly configured for a trusted origin.
allowed_origins = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]
if allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )


@app.middleware("http")
async def require_optional_basic_auth(request, call_next):
    """Protect the UI and management API when access credentials are set.

    EA and cBot push endpoints retain their separate per-account Journal API
    Key authentication, so desktop trading terminals do not need Basic Auth.
    """
    credentials = get_access_credentials()
    if credentials and request.url.path not in _UNPROTECTED_PATHS:
        if not is_authorized(request.headers.get("authorization"), credentials):
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required"},
                headers={"WWW-Authenticate": 'Basic realm="Trading Journal"'},
            )
    return await call_next(request)

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
        "ai_enabled": False
    }

@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    """Serves the browser favicon."""
    return FileResponse(os.path.join(STATIC_DIR, "favicon.ico"))

@app.get("/apple-touch-icon.png", include_in_schema=False)
def apple_touch_icon():
    """Serves the Apple touch icon."""
    return FileResponse(os.path.join(STATIC_DIR, "apple-touch-icon.png"))

@app.get("/")
def serve_spa():
    """Serves the Single Page Web Application."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    return FileResponse(index_path)

if __name__ == "__main__":
    import uvicorn
    # One worker is suitable for the bundled SQLite deployment.
    uvicorn.run("server.main:app", host="0.0.0.0", port=8000, reload=False, workers=1)
