"""App factory for the CoreOne Member Services mock target."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse

from hands.core.log import get_logger, log_failure
from target_app.config import AppConfig
from target_app.faults import FaultBook, parse_fault_spec
from target_app.routes_member import router as member_router
from target_app.routes_ops import router as ops_router
from target_app.routes_session import router as session_router
from target_app.services import SignOnRequired, build_services, tenant_base_path
from target_app.tenants import PRODUCT_NAME, PRODUCT_VERSION, tenant_slugs

logger = get_logger(__name__)


def seed_faults(fault_book: FaultBook, spec: str) -> int:
    """Arm faults from a COREONE_FAULTS-style spec. Bad entries are logged and skipped."""
    parsed = parse_fault_spec(spec, tenant_slugs())
    for error in parsed.errors:
        log_failure(logger, "seed_faults", error, spec=spec)
    fault_book.arm_all(parsed.requests)
    return len(parsed.requests)


async def _redirect_to_sign_on(request: Request, exc: Exception) -> RedirectResponse:
    tenant_slug = exc.tenant_slug if isinstance(exc, SignOnRequired) else ""
    return RedirectResponse(url=f"{tenant_base_path(tenant_slug)}/login", status_code=303)


def create_app(config: AppConfig) -> FastAPI:
    app = FastAPI(
        title=f"{PRODUCT_NAME} Member Services (mock)",
        version=PRODUCT_VERSION,
        docs_url=None,
        redoc_url=None,
    )
    services = build_services(config)
    app.state.services = services
    seeded_count = seed_faults(services.fault_book, config.seeded_faults)
    if seeded_count:
        logger.info("seeded %s fault(s) from config", seeded_count)
    app.add_exception_handler(SignOnRequired, _redirect_to_sign_on)
    app.include_router(session_router)
    app.include_router(member_router)
    app.include_router(ops_router)
    return app
