"""Main application entry point."""
from typing import Optional

from fastapi import FastAPI, WebSocket, Cookie
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from app.routes import router
from app.auth import check_auth
from app.websocket import handle_terminal_connection


# Create FastAPI application
app = FastAPI(title="Multipass VM Manager")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Include API routes
app.include_router(router)


# ==================== Page Routes ====================

@app.get("/", response_class=HTMLResponse)
async def index(session_id: Optional[str] = Cookie(None)):
    """Main application page."""
    # Check authentication
    if not check_auth(session_id):
        return RedirectResponse(url="/login")

    # Read and return the HTML template
    with open("templates/index.html", "r") as f:
        return HTMLResponse(content=f.read())


@app.get("/login", response_class=HTMLResponse)
async def login_page():
    """Login page."""
    with open("templates/login.html", "r") as f:
        return HTMLResponse(content=f.read())


# ==================== WebSocket Route ====================

@app.websocket("/ws")
async def ws_shell(ws: WebSocket):
    """WebSocket endpoint for terminal connections."""
    await handle_terminal_connection(ws)


# ==================== Application Entry Point ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
