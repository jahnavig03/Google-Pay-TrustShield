"""FastAPI application factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .adapters import build_services
from .routes import cases, health, merchant, payment
from .settings import cors_allow_origins

log = logging.getLogger(__name__)

DESCRIPTION = (
    "Prototype simulator - synthetic data. Multi-agent safety layer for UPI payments. "
    "The gateway owns Governance and the append-only Firestore audit_log."
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    services = build_services()
    app.state.services = services
    log.info(
        "gateway ready: mode=%s store=%s publisher=%s",
        services.mode,
        services.store_backend,
        services.publisher_backend,
    )
    try:
        yield
    finally:
        await services.store.close()
        await services.publisher.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Google Pay TrustShield gateway",
        description=DESCRIPTION,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_allow_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(payment.router)
    app.include_router(merchant.router)
    app.include_router(cases.router)
    return app
