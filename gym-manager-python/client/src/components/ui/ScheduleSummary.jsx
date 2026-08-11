function normalizeSchedule({ schedule, scheduleDays, scheduleTime }) {
  if (Array.isArray(schedule) && schedule.length) {
    return schedule
      .filter((slot) => slot?.day)
      .map((slot) => ({
        day: slot.day,
        time: slot.time || "Chưa chọn giờ",
      }));
  }
  return (scheduleDays || []).map((day) => ({
    day,
    time: scheduleTime || "Chưa chọn giờ",
  }));
}

export function ScheduleSummary({
  schedule,
  scheduleDays,
  scheduleTime,
  emptyText = "Chưa xếp lịch",
  compact = false,
}) {
  const slots = normalizeSchedule({ schedule, scheduleDays, scheduleTime });
  if (!slots.length) return <span>{emptyText}</span>;
  return (
    <div className={compact ? "space-y-0.5" : "space-y-1"}>
      {slots.map((slot) => (
        <div key={slot.day} className="flex items-center gap-2">
          <span className="min-w-14 font-medium text-slate-700">
            {slot.day}
          </span>
          <span className="cell-secondary !mt-0">{slot.time}</span>
        </div>
      ))}
    </div>
  );
}
