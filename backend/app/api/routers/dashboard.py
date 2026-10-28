"""Dashboard aggregates (all figures come from the database)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database.session import get_db
from app.models.user import User
from app.services import dashboard_service

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("")
def dashboard(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    recent_limit: int = Query(default=5, ge=1, le=25),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> dict:
    """Summary cards, quantities by supplier / roll type, and recent activity.

    ``total_received`` is a *historical* count of rolls received - this system
    does not track rolls leaving the warehouse, so it is deliberately **not**
    labelled as current stock.  ``currently_unpaid`` is always all-time.
    """
    return dashboard_service.dashboard_summary(
        db, start_date=start_date, end_date=end_date, recent_limit=recent_limit
    )
