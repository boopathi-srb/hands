"""Operational endpoints: fault administration and per-tenant health."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from hands.core.log import get_logger, log_failure
from target_app.faults import ANY_TENANT, ArmedFault, FaultArmRequest
from target_app.services import ServicesDep, TenantDep
from target_app.tenants import PRODUCT_NAME, PRODUCT_VERSION, VENDOR_NAME, get_tenant

logger = get_logger(__name__)

router = APIRouter()


def _armed_payload(armed_faults: list[ArmedFault]) -> dict[str, Any]:
    return {"armed": [armed.model_dump(mode="json") for armed in armed_faults]}


def _is_known_tenant_key(tenant_key: str) -> bool:
    return tenant_key == ANY_TENANT or get_tenant(tenant_key) is not None


@router.post("/_admin/faults")
async def arm_fault(arm_request: FaultArmRequest, services: ServicesDep) -> JSONResponse:
    if not _is_known_tenant_key(arm_request.tenant):
        log_failure(
            logger,
            "arm_fault",
            "unknown tenant",
            tenant=arm_request.tenant,
            fault=arm_request.fault.value,
        )
        return JSONResponse({"detail": f"Unknown tenant {arm_request.tenant!r}"}, status_code=400)
    armed = services.fault_book.arm(arm_request)
    logger.info(
        "fault armed | fault=%s tenant=%s count=%s delay_ms=%s",
        armed.fault.value,
        armed.tenant,
        armed.remaining,
        armed.delay_ms,
    )
    return JSONResponse(_armed_payload(services.fault_book.list_armed()), status_code=201)


@router.get("/_admin/faults")
async def list_faults(services: ServicesDep) -> JSONResponse:
    return JSONResponse(_armed_payload(services.fault_book.list_armed()))


@router.delete("/_admin/faults")
async def clear_faults(services: ServicesDep, tenant: str | None = None) -> JSONResponse:
    removed = services.fault_book.clear(tenant)
    logger.info("faults cleared | tenant=%s removed=%s", tenant or "all", removed)
    return JSONResponse({"removed": removed, **_armed_payload(services.fault_book.list_armed())})


@router.get("/t/{tenant}/_health")
async def tenant_health(tenant: TenantDep) -> dict[str, str]:
    return {
        "status": "ok",
        "tenant": tenant.slug,
        "brand": tenant.brand,
        "vendor": VENDOR_NAME,
        "product": PRODUCT_NAME,
        "version": PRODUCT_VERSION,
    }
