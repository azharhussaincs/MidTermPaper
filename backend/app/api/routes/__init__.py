"""API routers."""

from app.api.routes import assessments, clinician, system

ROUTERS = [system.router, assessments.router, clinician.router]

__all__ = ["ROUTERS"]
