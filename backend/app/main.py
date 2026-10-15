from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import blogs, health
from app.core.config import get_settings
from app.core.logging import configure_logging

settings = get_settings()
configure_logging()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    yield


app = FastAPI(
    title="Blog Generator API",
    version="1.0.0",
    docs_url="/api/docs" if settings.app_env.lower() != "production" else None,
    redoc_url="/api/redoc" if settings.app_env.lower() != "production" else None,
    openapi_url="/api/openapi.json" if settings.app_env.lower() != "production" else None,
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Content-Type"],
)
app.include_router(health.router)
app.include_router(blogs.router)
