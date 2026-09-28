"""Page rendering, including applying armed faults to eligible content-frame pages."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from fastapi import Request
from fastapi.responses import Response

from hands.core.log import get_logger
from target_app.faults import FaultName, FiredFaults
from target_app.services import AppServices, tenant_base_path
from target_app.sessions import SESSION_COOKIE_NAME, TellerSession
from target_app.tenants import PRODUCT_NAME, PRODUCT_VERSION, VENDOR_NAME, TenantConfig

logger = get_logger(__name__)

SESSION_EXPIRED_TEMPLATE = "session_expired.html"
APP_ERROR_TEMPLATE = "app_error.html"


@dataclass(frozen=True)
class Overlays:
    """In-page fault decorations rendered on top of a normal page."""

    maintenance_notice: bool = False
    native_alert: bool = False
    identity_check: bool = False

    @classmethod
    def from_fired(cls, fired: FiredFaults) -> Overlays:
        return cls(
            maintenance_notice=fired.has(FaultName.MAINTENANCE_NOTICE),
            native_alert=fired.has(FaultName.NATIVE_ALERT),
            identity_check=fired.has(FaultName.IDENTITY_CHECK),
        )


def base_context(tenant: TenantConfig) -> dict[str, Any]:
    return {
        "tenant": tenant,
        "base": tenant_base_path(tenant.slug),
        "vendor_name": VENDOR_NAME,
        "product_name": PRODUCT_NAME,
        "product_version": PRODUCT_VERSION,
        "overlays": Overlays(),
    }


def render_page(
    request: Request,
    services: AppServices,
    tenant: TenantConfig,
    template_name: str,
    status_code: int = 200,
    **context: Any,
) -> Response:
    """Render a template with the tenant's base context merged under the page context."""
    full_context = base_context(tenant) | context
    return services.templates.TemplateResponse(
        request, template_name, full_context, status_code=status_code
    )


async def pause_for_fault(delay_ms: int) -> None:
    """The slow fault's delay. A module-level seam so tests can observe it without waiting."""
    await asyncio.sleep(delay_ms / 1000)


def clear_session_cookie(response: Response, tenant: TenantConfig) -> None:
    response.delete_cookie(SESSION_COOKIE_NAME, path=tenant_base_path(tenant.slug))


def _render_session_expired(
    request: Request, services: AppServices, tenant: TenantConfig, session: TellerSession
) -> Response:
    services.sessions.revoke(session.token)
    response = render_page(request, services, tenant, SESSION_EXPIRED_TEMPLATE)
    clear_session_cookie(response, tenant)
    return response


async def render_content_page(
    request: Request,
    services: AppServices,
    tenant: TenantConfig,
    session: TellerSession,
    template_name: str,
    **context: Any,
) -> Response:
    """Render a fault-eligible content page: consume armed faults, then apply them."""
    fired = services.fault_book.consume(tenant.slug)
    if fired.names:
        logger.info(
            "faults fired | tenant=%s page=%s faults=%s delay_ms=%s",
            tenant.slug,
            template_name,
            sorted(fired.names),
            fired.delay_ms,
        )
    if fired.delay_ms:
        await pause_for_fault(fired.delay_ms)
    if fired.has(FaultName.SESSION_EXPIRED):
        return _render_session_expired(request, services, tenant, session)
    if fired.has(FaultName.APP_ERROR):
        return render_page(request, services, tenant, APP_ERROR_TEMPLATE, status_code=500)
    return render_page(
        request, services, tenant, template_name, overlays=Overlays.from_fired(fired), **context
    )
