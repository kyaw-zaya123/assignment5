from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.auth import router as auth_router
from app.api.routes.gates import router as gates_router
from app.api.routes.logistics import router as logistics_router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.database.postgres import Base, engine, ensure_postgis


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    with engine.begin() as conn:
        ensure_postgis(conn)
        Base.metadata.create_all(bind=conn)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="1.1.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(auth_router, prefix=settings.api_prefix)
    app.include_router(gates_router, prefix=settings.api_prefix)
    app.include_router(logistics_router, prefix=settings.api_prefix)
    return app


app = create_app()
