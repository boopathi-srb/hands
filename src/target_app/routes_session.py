"""Sign on, sign off, and the frameset shell (main, top, nav)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response

from hands.core.log import get_logger, log_failure
from target_app.forms import parse_form_body
from target_app.rendering import clear_session_cookie, render_page
from target_app.services import ServicesDep, SessionDep, TenantDep, tenant_base_path
from target_app.sessions import SESSION_COOKIE_NAME, credentials_match
from target_app.tenants import LAKESIDE

logger = get_logger(__name__)

router = APIRouter()

LOGIN_FAILED_MESSAGE = "Invalid User ID or Password."


def _redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url=url, status_code=303)


@router.get("/")
async def root_redirect() -> RedirectResponse:
    return _redirect(f"{tenant_base_path(LAKESIDE.slug)}/login")


@router.get("/t/{tenant}")
@router.get("/t/{tenant}/")
async def tenant_root_redirect(tenant: TenantDep) -> RedirectResponse:
    return _redirect(f"{tenant_base_path(tenant.slug)}/login")


@router.get("/t/{tenant}/login")
async def login_form(request: Request, tenant: TenantDep, services: ServicesDep) -> Response:
    return render_page(request, services, tenant, "login.html")


@router.post("/t/{tenant}/login")
async def login_submit(request: Request, tenant: TenantDep, services: ServicesDep) -> Response:
    fields = parse_form_body(await request.body())
    submitted_user_id = fields.get("USERID", "").strip()
    submitted_password = fields.get("PASSWD", "")
    config = services.config
    if not credentials_match(
        submitted_user_id, submitted_password, config.teller_user_id, config.teller_password
    ):
        log_failure(
            logger,
            "login_submit",
            "credentials rejected",
            tenant=tenant.slug,
            user_id=submitted_user_id,
        )
        return render_page(
            request,
            services,
            tenant,
            "login.html",
            status_code=401,
            error=LOGIN_FAILED_MESSAGE,
            user_id=submitted_user_id,
        )
    session = services.sessions.create(submitted_user_id, tenant.slug)
    response = _redirect(f"{tenant_base_path(tenant.slug)}/main")
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session.token,
        path=tenant_base_path(tenant.slug),
        httponly=True,
        samesite="lax",
    )
    return response


@router.get("/t/{tenant}/logout")
async def sign_off(request: Request, tenant: TenantDep, services: ServicesDep) -> Response:
    services.sessions.revoke(request.cookies.get(SESSION_COOKIE_NAME))
    response = _redirect(f"{tenant_base_path(tenant.slug)}/login")
    clear_session_cookie(response, tenant)
    return response


@router.get("/t/{tenant}/main")
async def main_frameset(
    request: Request, tenant: TenantDep, services: ServicesDep, session: SessionDep
) -> Response:
    return render_page(request, services, tenant, "main.html", session=session)


@router.get("/t/{tenant}/top")
async def top_frame(
    request: Request, tenant: TenantDep, services: ServicesDep, session: SessionDep
) -> Response:
    return render_page(request, services, tenant, "top.html", session=session)


@router.get("/t/{tenant}/nav")
async def nav_frame(
    request: Request, tenant: TenantDep, services: ServicesDep, session: SessionDep
) -> Response:
    return render_page(request, services, tenant, "nav.html", session=session)
