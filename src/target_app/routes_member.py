"""Content-frame screens: member inquiry, member detail, open share (form, review, submit)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from hands.core.log import get_logger, log_failure
from target_app.forms import (
    FIELD_DEPOSIT,
    FIELD_MEMBER_NUMBER,
    FIELD_NICKNAME,
    FIELD_SECURITY_ANSWER,
    FIELD_SHARE_TYPE,
    MEMBER_NUMBER_NOT_NUMERIC,
    parse_form_body,
    parse_member_number,
)
from target_app.members import (
    NEW_SHARE_ID,
    LookupStatus,
    MemberLookup,
    find_member,
    format_amount,
    openable_product_options,
    product_display_name,
    share_table_rows,
)
from target_app.open_share import DraftRejected, ShareDraft, validate_share_draft
from target_app.rendering import render_content_page, render_page
from target_app.services import AppServices, ServicesDep, SessionDep, TenantDep, tenant_base_path
from target_app.sessions import TellerSession, answer_matches
from target_app.tenants import TenantConfig

logger = get_logger(__name__)

router = APIRouter()

IDENTITY_REJECTED_MESSAGE = "Answer not recognized. Supervisor override required."
IDENTITY_VERIFIED_MESSAGE = "Identity verified."


class _Screen:
    """Bundles the per-request collaborators so helpers take one argument instead of four."""

    def __init__(
        self, request: Request, services: AppServices, tenant: TenantConfig, session: TellerSession
    ) -> None:
        self.request = request
        self.services = services
        self.tenant = tenant
        self.session = session

    async def content(self, template_name: str, **context: Any) -> Response:
        return await render_content_page(
            self.request, self.services, self.tenant, self.session, template_name, **context
        )


async def _inquiry_error(screen: _Screen, raw_member_number: str | None) -> Response:
    logger.info(
        "member number rejected as non-numeric | tenant=%s value=%r",
        screen.tenant.slug,
        raw_member_number,
    )
    return await screen.content(
        "inquiry.html", error=MEMBER_NUMBER_NOT_NUMERIC, member_number=raw_member_number or ""
    )


def _member_context(lookup: MemberLookup, tenant: TenantConfig) -> dict[str, Any]:
    share_rows = share_table_rows(lookup.member, tenant) if lookup.member else []
    return {"lookup": lookup, "share_rows": share_rows}


def _open_share_context(
    lookup: MemberLookup, tenant: TenantConfig, fields: Mapping[str, str], error: str | None
) -> dict[str, Any]:
    return {
        "lookup": lookup,
        "product_options": openable_product_options(tenant),
        "selected_product": fields.get(FIELD_SHARE_TYPE, ""),
        "deposit_value": fields.get(FIELD_DEPOSIT, ""),
        "nickname_value": fields.get(FIELD_NICKNAME, ""),
        "error": error,
    }


def _draft_context(draft: ShareDraft, tenant: TenantConfig) -> dict[str, Any]:
    return {
        "draft": draft,
        "product_label": product_display_name(draft.product, tenant),
        "deposit_display": format_amount(draft.deposit),
        "deposit_raw": str(draft.deposit),
        "new_share_id": NEW_SHARE_ID,
    }


async def _validated_draft(screen: _Screen, fields: Mapping[str, str]) -> ShareDraft | Response:
    """Turn a posted open-share form into a draft, or the page to show instead."""
    member_number = parse_member_number(fields.get(FIELD_MEMBER_NUMBER))
    if member_number is None:
        return await _inquiry_error(screen, fields.get(FIELD_MEMBER_NUMBER))
    lookup = find_member(member_number)
    if lookup.member is None:
        return await screen.content("member.html", **_member_context(lookup, screen.tenant))
    draft = validate_share_draft(lookup.member, fields)
    if isinstance(draft, DraftRejected):
        logger.info(
            "open share draft rejected | tenant=%s member=%s error=%s",
            screen.tenant.slug,
            member_number,
            draft.error,
        )
        context = _open_share_context(lookup, screen.tenant, fields, draft.error)
        return await screen.content("open_share.html", **context)
    return draft


@router.get("/t/{tenant}/inquiry")
async def inquiry_page(
    request: Request,
    tenant: TenantDep,
    services: ServicesDep,
    session: SessionDep,
    intent: str | None = None,
) -> Response:
    screen = _Screen(request, services, tenant, session)
    return await screen.content("inquiry.html", intent=intent, member_number="")


@router.post("/t/{tenant}/inquiry")
async def inquiry_submit(
    request: Request, tenant: TenantDep, services: ServicesDep, session: SessionDep
) -> Response:
    fields = parse_form_body(await request.body())
    member_number = parse_member_number(fields.get(FIELD_MEMBER_NUMBER))
    if member_number is None:
        screen = _Screen(request, services, tenant, session)
        return await _inquiry_error(screen, fields.get(FIELD_MEMBER_NUMBER))
    return RedirectResponse(
        url=f"{tenant_base_path(tenant.slug)}/member/{member_number}", status_code=303
    )


@router.get("/t/{tenant}/member/{member_number}")
async def member_detail(
    request: Request,
    tenant: TenantDep,
    services: ServicesDep,
    session: SessionDep,
    member_number: str,
) -> Response:
    screen = _Screen(request, services, tenant, session)
    parsed_number = parse_member_number(member_number)
    if parsed_number is None:
        return await _inquiry_error(screen, member_number)
    lookup = find_member(parsed_number)
    return await screen.content("member.html", **_member_context(lookup, tenant))


@router.get("/t/{tenant}/member/{member_number}/open-share")
async def open_share_form(
    request: Request,
    tenant: TenantDep,
    services: ServicesDep,
    session: SessionDep,
    member_number: str,
) -> Response:
    screen = _Screen(request, services, tenant, session)
    parsed_number = parse_member_number(member_number)
    if parsed_number is None:
        return await _inquiry_error(screen, member_number)
    lookup = find_member(parsed_number)
    if lookup.status is not LookupStatus.FOUND:
        return await screen.content("member.html", **_member_context(lookup, tenant))
    return await screen.content("open_share.html", **_open_share_context(lookup, tenant, {}, None))


@router.post("/t/{tenant}/review")
async def review_new_share(
    request: Request, tenant: TenantDep, services: ServicesDep, session: SessionDep
) -> Response:
    screen = _Screen(request, services, tenant, session)
    draft = await _validated_draft(screen, parse_form_body(await request.body()))
    if not isinstance(draft, ShareDraft):
        return draft
    return await screen.content("review.html", **_draft_context(draft, tenant))


@router.post("/t/{tenant}/submit")
async def submit_new_share(
    request: Request, tenant: TenantDep, services: ServicesDep, session: SessionDep
) -> Response:
    screen = _Screen(request, services, tenant, session)
    draft = await _validated_draft(screen, parse_form_body(await request.body()))
    if not isinstance(draft, ShareDraft):
        return draft
    logger.info(
        "share opened | tenant=%s member=%s share=%s",
        tenant.slug,
        draft.member.member_number,
        NEW_SHARE_ID,
    )
    return render_page(
        request, services, tenant, "confirmation.html", **_draft_context(draft, tenant)
    )


@router.get("/t/{tenant}/reports")
async def reports_page(
    request: Request, tenant: TenantDep, services: ServicesDep, session: SessionDep
) -> Response:
    return render_page(request, services, tenant, "reports.html", session=session)


@router.post("/t/{tenant}/identity/verify")
async def verify_identity(
    request: Request, tenant: TenantDep, services: ServicesDep, session: SessionDep
) -> JSONResponse:
    fields = parse_form_body(await request.body())
    submitted_answer = fields.get(FIELD_SECURITY_ANSWER, "").strip()
    if not answer_matches(submitted_answer, services.config.identity_override_answer):
        log_failure(
            logger,
            "verify_identity",
            "security answer not recognized",
            tenant=tenant.slug,
            user_id=session.user_id,
        )
        return JSONResponse({"verified": False, "message": IDENTITY_REJECTED_MESSAGE})
    logger.info(
        "identity check overridden by supervisor | tenant=%s user=%s", tenant.slug, session.user_id
    )
    return JSONResponse({"verified": True, "message": IDENTITY_VERIFIED_MESSAGE})
