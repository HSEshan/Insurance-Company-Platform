"""Aggregates all v1 endpoint routers."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    audit,
    auth,
    chat,
    claims,
    customers,
    documents,
    health,
    notifications,
    payments,
    policies,
    public,
    quotes,
    reports,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(public.router)
api_router.include_router(auth.router)
api_router.include_router(admin.router)
api_router.include_router(customers.router)
api_router.include_router(quotes.router)
api_router.include_router(policies.router)
api_router.include_router(claims.router)
api_router.include_router(documents.router)
api_router.include_router(payments.router)
api_router.include_router(notifications.router)
api_router.include_router(audit.router)
api_router.include_router(reports.router)
api_router.include_router(chat.router)
