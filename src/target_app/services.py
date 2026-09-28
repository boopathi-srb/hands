"""The shared, per-app collaborators handlers need, plus FastAPI dependencies that expose them."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates

from hands.core.log import get_logger, log_failure
from target_app.config import AppConfig
from target_app.faults import FaultBook
from target_app.sessions import SESSION_COOKIE_NAME, SessionStore, TellerSession
from target_app.tenants import TenantConfig, get_tenant

TEMPLATES_DIR = Path(__file__).parent / "templates"

logger = get_logger(__name__)


@dataclass
class AppServices:
    config: AppConfig
    fault_book: FaultBook
    sessions: SessionStore
    templates: Jinja2Templates


class SignOnRequired(Exception):
    """Raised by the session dependency; the app turns it into a redirect to the tenant login."""

    def __init__(self, tenant_slug: str) -> None:
        super().__init__(tenant_slug)
        self.tenant_slug = tenant_slug


def build_services(config: AppConfig) -> AppServices:
    return AppServices(
        config=config,
        fault_book=FaultBook(default_slow_delay_ms=config.default_slow_delay_ms),
        sessions=SessionStore(),
        templates=Jinja2Templates(directory=str(TEMPLATES_DIR)),
    )


def get_services(request: Request) -> AppServices:
    services: AppServices = request.app.state.services
    return services


def resolve_tenant(tenant: str) -> TenantConfig:
    tenant_config = get_tenant(tenant)
    if tenant_config is None:
        log_failure(logger, "resolve_tenant", "unknown tenant slug", tenant=tenant)
        raise HTTPException(status_code=404, detail=f"Unknown institution {tenant!r}")
    return tenant_config


ServicesDep = Annotated[AppServices, Depends(get_services)]
TenantDep = Annotated[TenantConfig, Depends(resolve_tenant)]


def require_session(request: Request, tenant: TenantDep, services: ServicesDep) -> TellerSession:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    session = services.sessions.get(token, tenant.slug)
    if session is None:
        logger.info(
            "require_session: no valid session, redirecting to login | tenant=%s path=%s",
            tenant.slug,
            request.url.path,
        )
        raise SignOnRequired(tenant.slug)
    return session


SessionDep = Annotated[TellerSession, Depends(require_session)]


def tenant_base_path(tenant_slug: str) -> str:
    return f"/t/{tenant_slug}"
