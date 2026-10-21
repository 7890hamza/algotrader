from __future__ import annotations

from contextlib import asynccontextmanager

from algotrader_logger import RequestLoggingMiddleware
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routers import (
    accounts,
    deals,
    market_data,
    meta,
    orders,
    positions,
)
from app.infrastructure.config import ServiceContainer
from app.infrastructure.logging import configure_logging
from app.infrastructure.mt5_client import TradingDisabledError
from app.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    configure_logging(settings.log_level, settings.log_format)

    container = ServiceContainer(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await container.startup()
        yield
        await container.shutdown()

    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.state.container = container
    app.add_middleware(RequestLoggingMiddleware)

    app.include_router(meta.router)
    app.include_router(accounts.router)
    app.include_router(orders.router)
    app.include_router(positions.router)
    app.include_router(deals.router)
    app.include_router(market_data.router)

    @app.exception_handler(TradingDisabledError)
    async def trading_disabled(_request: Request, exc: TradingDisabledError) -> JSONResponse:
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    return app


app = create_app()


def run() -> None:
    """CLI entry point defined in pyproject scripts."""

    import uvicorn

    container: ServiceContainer = app.state.container
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=container.settings.service_port,
        log_level=container.settings.log_level.lower(),
    )
