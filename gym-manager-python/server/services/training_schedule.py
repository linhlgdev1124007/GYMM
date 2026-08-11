import json
import re

from fastapi import HTTPException


WEEKDAYS = ("Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật")
TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def normalize_schedule(payload: dict) -> list[dict[str, str]]:
    """Validate the new per-day schedule, with support for legacy clients."""
    if "schedule" in payload:
        raw_schedule = payload.get("schedule") or []
    else:
        legacy_time = str(payload.get("scheduleTime") or "").strip()
        raw_schedule = [
            {"day": day, "time": legacy_time}
            for day in (payload.get("scheduleDays") or [])
        ]

    if not isinstance(raw_schedule, list):
        raise HTTPException(422, "Lịch tập PT không hợp lệ.")

    by_day = {}
    for slot in raw_schedule:
        if not isinstance(slot, dict):
            raise HTTPException(422, "Lịch tập PT không hợp lệ.")
        day = str(slot.get("day") or "").strip()
        time = str(slot.get("time") or "").strip()
        if day not in WEEKDAYS:
            raise HTTPException(422, f"Ngày tập '{day}' không hợp lệ.")
        if not TIME_PATTERN.fullmatch(time):
            raise HTTPException(422, f"Giờ tập của {day} phải có dạng HH:mm.")
        by_day[day] = time
    return [{"day": day, "time": by_day[day]} for day in WEEKDAYS if day in by_day]


def schedule_storage(schedule: list[dict[str, str]]) -> tuple[str | None, str | None, str | None]:
    if not schedule:
        return None, None, None
    times = {slot["time"] for slot in schedule}
    legacy_time = next(iter(times)) if len(times) == 1 else None
    return (
        json.dumps(schedule, ensure_ascii=False),
        ", ".join(slot["day"] for slot in schedule),
        legacy_time,
    )


def schedule_data(enrollment) -> list[dict[str, str]]:
    if getattr(enrollment, "schedule_json", None):
        try:
            stored = json.loads(enrollment.schedule_json)
            if isinstance(stored, list):
                return stored
        except (TypeError, ValueError):
            pass
    time = enrollment.schedule_time or ""
    if not time:
        return []
    return [
        {"day": value.strip(), "time": time}
        for value in (enrollment.schedule_days or "").split(",")
        if value.strip()
    ]
