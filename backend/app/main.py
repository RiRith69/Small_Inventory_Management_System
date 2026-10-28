"""FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.routers import (
    auth,
    bot,
    catalog,
    dashboard,
    deliveries,
    payments,
    settings as settings_router,
    telegram,
    users,
)
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.database.session import get_db

logger = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    config = get_settings()
    warnings = config.validate_for_startup()
    for warning in warnings:
        logger.warning("Unsafe configuration: %s", warning)
    if config.is_production and warnings:
        raise RuntimeError("Production configuration is unsafe; set the required environment values")
    yield


def create_app() -> FastAPI:
    config = get_settings()
    application = FastAPI(
        title=config.project_name,
        version="1.0.0",
        description="Warehouse roll inventory API",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-CSRF-Token", "X-Bot-Token"],
    )
    register_exception_handlers(application)

    for router in (
        auth.router,
        users.router,
        catalog.router,
        deliveries.router,
        payments.router,
        dashboard.router,
        telegram.router,
        settings_router.router,
        bot.router,
    ):
        application.include_router(router)

    @application.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {"name": config.project_name, "status": "running", "docs": "/docs"}

    @application.get("/healthz", tags=["health"])
    def health(db: Session = Depends(get_db)) -> dict[str, str]:
        db.execute(text("SELECT 1"))
        return {"status": "ok"}

    return application


app = create_app()
