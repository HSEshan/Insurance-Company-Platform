"""Dashboard KPI and reporting response schemas."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ClaimStatus, PolicyType


class NamedCount(BaseModel):
    key: str
    label: str
    count: int


class NamedMoney(BaseModel):
    key: str
    label: str
    amount: Decimal


class AgentProductionRow(BaseModel):
    agent_id: uuid.UUID
    agent_name: str
    policies_written: int
    annual_premium: Decimal


class MonthCount(BaseModel):
    month: str  # YYYY-MM
    count: int


class ManagerDashboard(BaseModel):
    active_policies_total: int
    active_policies_by_type: list[NamedCount]
    new_policies_this_month: int
    new_policies_last_month: int
    new_policies_sparkline: list[MonthCount]
    open_claims: int
    avg_days_to_close: float | None
    loss_ratio_12m: Decimal | None
    premium_collected_mtd: Decimal
    premium_target_mtd: Decimal
    top_agents: list[AgentProductionRow]
    claims_by_status: list[NamedCount]
    payments_overdue: int


class AgentActivityItem(BaseModel):
    id: uuid.UUID
    action: str
    entity_type: str
    entity_id: uuid.UUID
    created_at: datetime
    summary: str | None = None


class AgentDashboard(BaseModel):
    customers_total: int
    customers_new_this_month: int
    policies_active: int
    policies_expiring_30d: int
    pending_quote_approvals: int
    recent_activity: list[AgentActivityItem]


class AdjusterQueueItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    claim_number: str
    status: ClaimStatus
    fraud_flag: bool
    estimated_damage: Decimal | None = None
    created_at: datetime
    age_days: int
    days_info_remaining: int | None = None


class AdjusterDashboard(BaseModel):
    assigned_queue: list[AdjusterQueueItem]
    awaiting_info: list[AdjusterQueueItem]
    avg_days_to_resolution_personal: float | None
    avg_days_to_resolution_team: float | None
    claims_closed_this_month: int


class CustomerPolicyCard(BaseModel):
    id: uuid.UUID
    policy_number: str
    policy_type: PolicyType
    status: str
    next_payment_date: date | None = None
    next_payment_amount: Decimal | None = None


class CustomerClaimCard(BaseModel):
    id: uuid.UUID
    claim_number: str
    status: ClaimStatus
    incident_date: date
    estimated_damage: Decimal | None = None


class CustomerPaymentCard(BaseModel):
    id: uuid.UUID
    amount: Decimal
    status: str
    payment_type: str
    processed_at: datetime | None = None
    reference_number: str | None = None


class CustomerDashboard(BaseModel):
    active_policies: list[CustomerPolicyCard]
    open_claims: list[CustomerClaimCard]
    recent_payments: list[CustomerPaymentCard]
    unread_notifications: int = Field(ge=0)


class LossRatioRow(BaseModel):
    policy_type: PolicyType
    premium_collected: Decimal
    claims_paid: Decimal
    loss_ratio: Decimal | None
