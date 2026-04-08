from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from src.config import settings
from src.routes.wan import router as wan_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print(f"Starting {settings.app_name}")
    print(f"Workflows dir: {settings.workflows_dir}")
    yield
    # Shutdown
    print("Shutting down...")


app = FastAPI(title=settings.app_name, lifespan=lifespan)


# Global exception handler - prevents server crashes
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch all unhandled exceptions to prevent server crashes."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": type(exc).__name__,
            "detail": str(exc) if settings.debug else "Internal server error",
            "path": str(request.url.path),
        }
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(wan_router)


@app.get("/health")
async def health_check():
    return {"status": "ok"}

