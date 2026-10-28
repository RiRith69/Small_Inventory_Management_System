"""Dashboard aggregates.

Important distinction the UI must preserve:
``total_received`` is a *historical* count of rolls that arrived; it is NOT
current physical stock (this system does not track rolls leaving the warehouse).
``total_unpaid`` is what the supplier has not been paid for yet.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.core.timezone import local_today
from app.services import delivery_service, payment_service
from app.services.queries import (
    fetch_delivery_rows,
    group_rows_by,
    totals_for_rows,
    validate_date_range,
)


def dashboard_summary(
    db: Session,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    recent_limit: int = 5,
) -> dict:
    validate_date_range(start_date, end_date)

    rows = fetch_delivery_rows(db, start_date=start_date, end_date=end_date)
    totals = totals_for_rows(rows)

    by_supplier = [
        {"supplier_id": k[0], "supplier_name": k[1], **v}
        for k, v in group_rows_by(
            rows, lambda r: (r.delivery.supplier_id, r.delivery.supplier.name if r.delivery.supplier else "")
        ).items()
    ]
    by_supplier.sort(key=lambda x: x["supplier_name"])

    by_roll_type = [
        {
            "roll_type_id": k[0],
            "roll_type_code": k[1],
            "roll_type_name": k[2],
            "roll_type_name_en": k[3],
            **v,
        }
        for k, v in group_rows_by(
            rows,
            lambda r: (
                r.delivery.roll_type_id,
                r.delivery.roll_type.code if r.delivery.roll_type else "",
                r.delivery.roll_type.name_km if r.delivery.roll_type else "",
                r.delivery.roll_type.name_en if r.delivery.roll_type else "",
            ),
        ).items()
    ]
    by_roll_type.sort(key=lambda x: x["roll_type_name"])
    by_supplier_and_roll_type = []
    grouped_supplier_types = group_rows_by(
        rows,
        lambda r: (
            r.delivery.supplier_id,
            r.delivery.roll_type_id,
            r.delivery.supplier.name if r.delivery.supplier else "",
            r.delivery.roll_type.name_km if r.delivery.roll_type else "",
            r.delivery.roll_type.name_en if r.delivery.roll_type else "",
            r.delivery.roll_type.code if r.delivery.roll_type else "",
        ),
    )
    for key, values in grouped_supplier_types.items():
        by_supplier_and_roll_type.append(
            {
                "supplier_id": key[0],
                "roll_type_id": key[1],
                "supplier_name": key[2],
                "roll_type_name": key[3],
                "roll_type_name_en": key[4],
                "roll_type_code": key[5],
                **values,
            }
        )
    by_supplier_and_roll_type.sort(key=lambda row: (row["supplier_name"], row["roll_type_name"]))

    # "Currently unpaid" is always all-time: the warehouse still owes for these.
    all_rows = fetch_delivery_rows(db)
    currently_unpaid = sum(r.unpaid_quantity for r in all_rows)
    currently_partially_paid = sum(1 for r in all_rows if 0 < r.paid_quantity < r.quantity_received)

    today = local_today()
    received_today = sum(
        r.quantity_received for r in fetch_delivery_rows(db, start_date=today, end_date=today)
    )

    recent_deliveries = [
        {
            "id": r.id,
            "delivery_date": r.delivery.delivery_date,
            "supplier_name": r.delivery.supplier.name if r.delivery.supplier else None,
            "roll_type_name": r.delivery.roll_type.name_km if r.delivery.roll_type else None,
            "roll_type_name_km": r.delivery.roll_type.name_km if r.delivery.roll_type else None,
            "roll_type_name_en": r.delivery.roll_type.name_en if r.delivery.roll_type else None,
            "roll_type_code": r.delivery.roll_type.code if r.delivery.roll_type else None,
            "quantity_received": r.quantity_received,
            "quantity_paid": r.paid_quantity,
            "quantity_unpaid": r.unpaid_quantity,
            "status": r.status.value,
        }
        for r in delivery_service.recent_deliveries(db, limit=recent_limit)
    ]

    recent_payments = payment_service.recent_payments(db, limit=recent_limit)

    return {
        "range": {"start_date": start_date, "end_date": end_date},
        "summary": {
            "total_received": totals["received"],
            "total_paid": totals["paid"],
            "total_unpaid": totals["unpaid"],
            "delivery_count": len(rows),
            "received_today": received_today,
            "currently_unpaid": currently_unpaid,
            "partially_paid_deliveries": currently_partially_paid,
        },
        "by_supplier": by_supplier,
        "by_roll_type": by_roll_type,
        "by_supplier_and_roll_type": by_supplier_and_roll_type,
        "recent_deliveries": recent_deliveries,
        "recent_payments": recent_payments,
    }
