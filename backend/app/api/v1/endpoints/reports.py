"""Reporting dashboards and downloadable CSV summaries."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    ADJUSTER_AND_UP,
    AGENT_AND_UP,
    MANAGER_AND_UP,
    get_current_user,
    require_roles,
)
from app.core.database import get_db
from app.core.exceptions import ForbiddenError
from app.models.enums import ClaimStatus, UserRole
from app.models.user import User
from app.schemas.common import Envelope, ok
from app.schemas.report import (
    AdjusterDashboard,
    AgentDashboard,
    CustomerDashboard,
    LossRatioRow,
    ManagerDashboard,
)
from app.services import report_service

router = APIRouter(prefix="/reports", tags=["reports"])


def _csv_response(body: str, filename: str) -> StreamingResponse:
    return StreamingResponse(
        iter([body]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/dashboard/manager", response_model=Envelope[ManagerDashboard])
async def manager_dashboard(
    _: User = Depends(require_roles(*MANAGER_AND_UP)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return ok(await report_service.manager_dashboard(db))


@router.get("/dashboard/agent", response_model=Envelope[AgentDashboard])
async def agent_dashboard(
    current_user: User = Depends(require_roles(*AGENT_AND_UP)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return ok(await report_service.agent_dashboard(db, current_user))


@router.get("/dashboard/adjuster", response_model=Envelope[AdjusterDashboard])
async def adjuster_dashboard(
    current_user: User = Depends(require_roles(*ADJUSTER_AND_UP)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return ok(await report_service.adjuster_dashboard(db, current_user))


@router.get("/dashboard/customer", response_model=Envelope[CustomerDashboard])
async def customer_dashboard(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if current_user.role != UserRole.customer:
        raise ForbiddenError("Customer dashboard is only available to customers.")
    return ok(await report_service.customer_dashboard(db, current_user))


@router.get("/claims-summary")
async def claims_summary(
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    status: ClaimStatus | None = Query(None),
    _: User = Depends(require_roles(*MANAGER_AND_UP)),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    body = await report_service.export_claims_summary_csv(
        db, date_from=date_from, date_to=date_to, status=status
    )
    return _csv_response(body, "claims-summary.csv")


@router.get("/billing-summary")
async def billing_summary(
    _: User = Depends(require_roles(*MANAGER_AND_UP)),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    body = await report_service.export_billing_summary_csv(db)
    return _csv_response(body, "billing-summary.csv")


@router.get("/loss-ratio", response_model=Envelope[list[LossRatioRow]])
async def loss_ratio(
    _: User = Depends(require_roles(*MANAGER_AND_UP)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return ok(await report_service.loss_ratio_by_line(db))


@router.get("/loss-ratio/export")
async def loss_ratio_export(
    _: User = Depends(require_roles(*MANAGER_AND_UP)),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    body = await report_service.export_loss_ratio_csv(db)
    return _csv_response(body, "loss-ratio.csv")


@router.get("/agent-production")
async def agent_production(
    _: User = Depends(require_roles(*MANAGER_AND_UP)),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    body = await report_service.export_agent_production_csv(db)
    return _csv_response(body, "agent-production.csv")


@router.get("/customer-policy-history")
async def customer_policy_history(
    customer_id: uuid.UUID = Query(...),
    _: User = Depends(require_roles(*AGENT_AND_UP)),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    body = await report_service.export_customer_policy_history_csv(db, customer_id)
    return _csv_response(body, "customer-policy-history.csv")
