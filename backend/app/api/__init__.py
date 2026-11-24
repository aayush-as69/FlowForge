from app.api.admin import (audit_router, dashboard_router, functions_info_router, integrations_router, policies_router,
                           vendors_router)
from app.api.action_center import router as action_center_router
from app.api.analytics import router as analytics_router
from app.api.approvals import router as approvals_router
from app.api.builder import router as builder_router
from app.api.auth import router as auth_router
from app.api.exceptions import router as exceptions_router
from app.api.requests import functions_router, router as requests_router
from app.api.workflows import router as workflows_router
from app.api.workflows import steps_router

routers = [auth_router, functions_router, functions_info_router, requests_router, workflows_router, steps_router,
           approvals_router, exceptions_router, policies_router, vendors_router, integrations_router, audit_router,
           dashboard_router, action_center_router, analytics_router, builder_router]
