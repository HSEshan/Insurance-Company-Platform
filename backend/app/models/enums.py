"""Domain enumerations shared across models and schemas."""

from __future__ import annotations

import enum


class UserRole(enum.StrEnum):
    customer = "customer"
    agent = "agent"
    adjuster = "adjuster"
    manager = "manager"
    super_admin = "super_admin"


class RiskTier(enum.StrEnum):
    preferred = "preferred"
    standard = "standard"
    substandard = "substandard"
    declined = "declined"


class PolicyType(enum.StrEnum):
    auto = "auto"
    home = "home"
    life = "life"


class QuoteStatus(enum.StrEnum):
    draft = "draft"
    pending_review = "pending_review"
    approved = "approved"
    rejected = "rejected"
    bound = "bound"
    expired = "expired"


class PolicyStatus(enum.StrEnum):
    draft = "draft"
    under_review = "under_review"
    active = "active"
    lapsed = "lapsed"
    cancelled = "cancelled"
    expired = "expired"


class PaymentFrequency(enum.StrEnum):
    monthly = "monthly"
    quarterly = "quarterly"
    semi_annual = "semi_annual"
    annual = "annual"


class VehicleType(enum.StrEnum):
    sedan = "sedan"
    suv = "suv"
    truck = "truck"
    motorcycle = "motorcycle"
    commercial = "commercial"


class VehicleUse(enum.StrEnum):
    personal = "personal"
    commute = "commute"
    business = "business"


class AutoCoverageType(enum.StrEnum):
    liability_only = "liability_only"
    comprehensive = "comprehensive"
    collision = "collision"
    full_coverage = "full_coverage"


class ConstructionType(enum.StrEnum):
    frame = "frame"
    masonry = "masonry"
    manufactured = "manufactured"


class RoofType(enum.StrEnum):
    shingle = "shingle"
    metal = "metal"
    tile = "tile"
    flat = "flat"


class LifeType(enum.StrEnum):
    term = "term"
    whole = "whole"
    universal = "universal"


class HealthClass(enum.StrEnum):
    preferred_plus = "preferred_plus"
    preferred = "preferred"
    standard_plus = "standard_plus"
    standard = "standard"
    substandard = "substandard"


class PremiumMode(enum.StrEnum):
    level = "level"
    increasing = "increasing"
    decreasing = "decreasing"


class BeneficiaryRelationship(enum.StrEnum):
    spouse = "spouse"
    child = "child"
    parent = "parent"
    sibling = "sibling"
    estate = "estate"
    trust = "trust"
    other = "other"


class EndorsementType(enum.StrEnum):
    add_vehicle = "add_vehicle"
    remove_vehicle = "remove_vehicle"
    coverage_change = "coverage_change"
    address_change = "address_change"
    beneficiary_change = "beneficiary_change"
    deductible_change = "deductible_change"
    limits_change = "limits_change"
    other = "other"


class EndorsementStatus(enum.StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class PremiumScheduleStatus(enum.StrEnum):
    upcoming = "upcoming"
    due = "due"
    paid = "paid"
    overdue = "overdue"
    waived = "waived"


class PaymentType(enum.StrEnum):
    premium = "premium"
    claim_payout = "claim_payout"
    refund = "refund"
    fee = "fee"


class PaymentMethod(enum.StrEnum):
    ach = "ach"
    credit_card = "credit_card"
    check = "check"
    wire = "wire"
    cash = "cash"


class PaymentStatus(enum.StrEnum):
    pending = "pending"
    completed = "completed"
    failed = "failed"
    voided = "voided"
    refunded = "refunded"


class ClaimType(enum.StrEnum):
    auto_collision = "auto_collision"
    auto_comprehensive = "auto_comprehensive"
    auto_liability = "auto_liability"
    home_dwelling = "home_dwelling"
    home_personal_property = "home_personal_property"
    home_liability = "home_liability"
    life_death_benefit = "life_death_benefit"


class ClaimStatus(enum.StrEnum):
    submitted = "submitted"
    assigned = "assigned"
    investigating = "investigating"
    info_requested = "info_requested"
    approved = "approved"
    rejected = "rejected"
    disputed = "disputed"
    paid = "paid"
    closed = "closed"


class ClaimNoteType(enum.StrEnum):
    internal = "internal"
    customer_facing = "customer_facing"
    investigation = "investigation"
    system = "system"


class DocumentOwnerType(enum.StrEnum):
    policy = "policy"
    claim = "claim"
    customer = "customer"
    quote = "quote"


class DocumentType(enum.StrEnum):
    policy_pdf = "policy_pdf"
    claim_decision_letter = "claim_decision_letter"
    id_document = "id_document"
    vehicle_photo = "vehicle_photo"
    property_photo = "property_photo"
    police_report = "police_report"
    medical_report = "medical_report"
    repair_estimate = "repair_estimate"
    proof_of_ownership = "proof_of_ownership"
    receipt = "receipt"
    other = "other"


class NotificationType(enum.StrEnum):
    claim_submitted = "claim_submitted"
    claim_status_changed = "claim_status_changed"
    claim_approved = "claim_approved"
    claim_rejected = "claim_rejected"
    policy_expiring = "policy_expiring"
    policy_lapsed = "policy_lapsed"
    payment_due = "payment_due"
    payment_overdue = "payment_overdue"
    payment_received = "payment_received"
    quote_ready = "quote_ready"
    endorsement_approved = "endorsement_approved"
    general = "general"


class ChatSessionMode(enum.StrEnum):
    ai = "ai"
    human = "human"


class ChatMessageRole(enum.StrEnum):
    user = "user"
    assistant = "assistant"
    system = "system"
