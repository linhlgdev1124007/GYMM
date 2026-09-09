from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import text

from server.database import SessionLocal
from server.timeutils import vietnam_today


@dataclass
class RepairItem:
    event_id: int
    action: str
    membership_id: int
    member_name: str
    from_package: str
    to_package: str
    from_duration: int
    to_duration: int
    delta: int
    current_expiry: date
    customer_id: int | None
    membership_status: str


def _details(details_json: str | None) -> dict:
    try:
        return json.loads(details_json or "{}")
    except (TypeError, ValueError):
        return {}


def _is_old_duration_event(details_json: str | None) -> bool:
    details = _details(details_json)
    return "durationDeltaDays" not in details


def _as_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value:
        return date.fromisoformat(str(value)[:10])
    return None


def _repair_items(db, membership_id: int | None = None) -> list[RepairItem]:
    params = {}
    where_membership = ""
    if membership_id:
        where_membership = "AND me.membership_id = :membership_id"
        params["membership_id"] = membership_id

    items = []
    rows = db.execute(text(f"""
        SELECT
            me.id AS event_id,
            me.action AS action,
            me.membership_id AS membership_id,
            me.details_json AS details_json,
            m.expires_at AS current_expiry,
            m.status AS membership_status,
            m.customer_id AS customer_id,
            p.display_name AS member_name,
            fp.name AS from_package,
            tp.name AS to_package,
            fp.duration_days AS from_duration,
            tp.duration_days AS to_duration
        FROM membership_events me
        JOIN memberships m ON m.id = me.membership_id
        JOIN service_packages fp ON fp.id = me.from_package_id
        JOIN service_packages tp ON tp.id = me.to_package_id
        LEFT JOIN customers c ON c.id = m.customer_id
        LEFT JOIN people p ON p.id = c.person_id
        WHERE me.action IN ('change', 'upgrade')
          AND me.from_package_id IS NOT NULL
          AND me.to_package_id IS NOT NULL
          {where_membership}
        ORDER BY me.membership_id ASC, me.id ASC
    """), params).mappings()
    for row in rows:
        if not _is_old_duration_event(row["details_json"]):
            continue
        current_expiry = _as_date(row["current_expiry"])
        if not current_expiry:
            continue
        if row["from_duration"] is None or row["to_duration"] is None:
            continue
        delta = int(row["to_duration"]) - int(row["from_duration"])
        if delta == 0:
            continue
        items.append(
            RepairItem(
                event_id=row["event_id"],
                action=row["action"],
                membership_id=row["membership_id"],
                member_name=row["member_name"] or "",
                from_package=row["from_package"],
                to_package=row["to_package"],
                from_duration=int(row["from_duration"]),
                to_duration=int(row["to_duration"]),
                delta=delta,
                current_expiry=current_expiry,
                customer_id=row["customer_id"],
                membership_status=row["membership_status"],
            )
        )
    return items


def _status_after_repair(current_status: str, repaired_expiry: date) -> str:
    today = vietnam_today()
    if current_status == "expired" and repaired_expiry >= today:
        return "active"
    if current_status == "active" and repaired_expiry < today:
        return "expired"
    return current_status


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Repair memberships changed/upgraded before duration-delta expiry logic existed.",
    )
    parser.add_argument("--membership-id", type=int, help="Only inspect or repair one membership id.")
    parser.add_argument("--apply", action="store_true", help="Write the computed expiry changes.")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        items = _repair_items(db, args.membership_id)
        grouped: dict[int, list[RepairItem]] = defaultdict(list)
        for item in items:
            grouped[item.membership_id].append(item)

        if not grouped:
            print("No old change/upgrade events need duration repair.")
            return 0

        print("membership_id | member | current_expiry | delta_days | repaired_expiry | events")
        print("-" * 96)
        repaired_count = 0
        for target_membership_id, rows in grouped.items():
            total_delta = sum(row.delta for row in rows)
            current_expiry = rows[-1].current_expiry
            repaired_expiry = current_expiry + timedelta(days=total_delta)
            repaired_status = _status_after_repair(rows[-1].membership_status, repaired_expiry)
            event_labels = ", ".join(
                f"#{row.event_id} {row.action} {row.from_duration}->{row.to_duration} ({row.delta:+d})"
                for row in rows
            )
            print(
                f"{target_membership_id} | {rows[-1].member_name} | {current_expiry.isoformat()} | "
                f"{total_delta:+d} | {repaired_expiry.isoformat()} | {event_labels}"
            )
            if args.apply:
                db.execute(text("""
                    UPDATE memberships
                    SET expires_at = :expires_at, status = :status
                    WHERE id = :membership_id
                """), {
                    "expires_at": repaired_expiry,
                    "status": repaired_status,
                    "membership_id": target_membership_id,
                })
                if repaired_status == "active" and rows[-1].customer_id:
                    db.execute(text("""
                        UPDATE customers
                        SET status = 'active'
                        WHERE id = :customer_id AND status <> 'cancelled'
                    """), {"customer_id": rows[-1].customer_id})
                for row in rows:
                    details = _details(db.execute(text("""
                        SELECT details_json
                        FROM membership_events
                        WHERE id = :event_id
                    """), {"event_id": row.event_id}).scalar())
                    details.update({
                        "previousDurationDays": row.from_duration,
                        "newDurationDays": row.to_duration,
                        "durationDeltaDays": row.delta,
                        "repairPreviousExpiry": current_expiry.isoformat(),
                        "repairNewExpiry": repaired_expiry.isoformat(),
                        "repairAppliedAt": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                    })
                    db.execute(text("""
                        UPDATE membership_events
                        SET details_json = :details_json
                        WHERE id = :event_id
                    """), {
                        "details_json": json.dumps(details, ensure_ascii=False, default=str),
                        "event_id": row.event_id,
                    })
                repaired_count += 1

        if args.apply:
            db.commit()
            print(f"Applied repair for {repaired_count} membership(s).")
        else:
            print("Dry run only. Re-run with --apply to write these expiry changes.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
