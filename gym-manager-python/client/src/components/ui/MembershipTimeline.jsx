import { Pencil, Trash2 } from "lucide-react";
import { shortDate } from "../../utils/format";

const statusLabel = {
  active: "Đang bảo lưu",
  scheduled: "Sắp bảo lưu",
  completed: "Đã qua bảo lưu",
};

const dateMs = (value) => new Date(`${value}T00:00:00`).getTime();

function todayPosition(timeline) {
  if (!timeline?.startsAt || !timeline?.expiresAt || !timeline.totalDays) {
    return null;
  }
  const elapsed = Math.round((Date.now() - dateMs(timeline.startsAt)) / 86400000);
  if (elapsed < 0 || elapsed > timeline.totalDays) return null;
  return `${Math.min(Math.max((elapsed / timeline.totalDays) * 100, 0), 100)}%`;
}

function remainingText(days) {
  if (days == null) return "—";
  if (days < 0) return `Quá hạn ${Math.abs(days)} ngày`;
  return `${days} ngày`;
}

export function MembershipTimeline({ membership, compact = false, onEditFreeze, onDeleteFreeze }) {
  const timeline = membership?.timeline;
  if (!timeline?.segments?.length) return null;
  const freezes = timeline.freezes || timeline.segments.filter((segment) => segment.type === "freeze");
  const marker = todayPosition(timeline);
  return (
    <div className={`membership-timeline ${compact ? "compact" : ""}`}>
      <div className="membership-timeline-head">
        <div>
          <span>Còn lại</span>
          <strong>{remainingText(timeline.remainingDays)}</strong>
        </div>
        <div>
          <span>Hạn hiện tại</span>
          <strong>{shortDate(timeline.expiresAt)}</strong>
        </div>
        <div>
          <span>Cộng bù</span>
          <strong>{timeline.totalCompensatedDays || 0} ngày</strong>
        </div>
      </div>
      <div className="membership-timeline-bar" aria-label="Timeline thời hạn gói">
        {timeline.segments.map((segment, index) => {
          const basis = timeline.totalDays
            ? `${Math.max((segment.days / timeline.totalDays) * 100, 1.5)}%`
            : "100%";
          return (
            <span
              key={`${segment.type}-${segment.startsAt}-${segment.endsAt}-${index}`}
              className={`membership-timeline-segment ${segment.type === "freeze" ? `freeze ${segment.status}` : "active"}`}
              style={{ flexBasis: basis }}
              title={`${segment.label}: ${shortDate(segment.startsAt)} → ${shortDate(segment.endsAt)} · ${segment.days} ngày${segment.reason ? ` · ${segment.reason}` : ""}`}
            />
          );
        })}
        {marker && <i className="membership-timeline-today" style={{ left: marker }} />}
      </div>
      <div className="membership-timeline-scale">
        <span>{shortDate(timeline.startsAt)}</span>
        <span>{shortDate(timeline.expiresAt)}</span>
      </div>
      {!!freezes.length && (
        <div className="membership-freeze-list">
          {freezes.map((freeze) => (
            <div key={freeze.id}>
              <span className={`freeze-dot ${freeze.status}`} />
              <div>
                <strong>
                  {statusLabel[freeze.status] || "Bảo lưu"} · {shortDate(freeze.startsAt)} → {shortDate(freeze.endsAt)}
                </strong>
                <p>
                  {freeze.days} ngày bảo lưu · đã cộng {freeze.compensatedDays || 0} ngày
                  {freeze.completedAt ? ` · kết thúc ${shortDate(freeze.completedAt)}` : ""}
                  {freeze.reason ? ` · ${freeze.reason}` : ""}
                </p>
              </div>
              {(onEditFreeze || onDeleteFreeze) && (
                <div className="freeze-actions">
                  {onEditFreeze && (
                    <button type="button" onClick={() => onEditFreeze(freeze)} title="Sửa bảo lưu" aria-label="Sửa bảo lưu">
                      <Pencil size={14} />
                    </button>
                  )}
                  {onDeleteFreeze && (
                    <button type="button" onClick={() => onDeleteFreeze(freeze)} title="Hủy bảo lưu" aria-label="Hủy bảo lưu">
                      <Trash2 size={14} />
                    </button>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
