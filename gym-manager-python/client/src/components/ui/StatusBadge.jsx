import { statusLabel } from "../../utils/format";

const palettes = {
  active: ["text-emerald-700", "bg-emerald-500"],
  open: ["text-emerald-700", "bg-emerald-500"],
  paid: ["text-emerald-700", "bg-emerald-500"],
  online: ["text-emerald-700", "bg-emerald-500"],
  completed: ["text-emerald-700", "bg-emerald-500"],
  expiring: ["text-amber-700", "bg-amber-500"],
  pending: ["text-amber-700", "bg-amber-500"],
  maintenance: ["text-amber-700", "bg-amber-500"],
  suspended: ["text-amber-700", "bg-amber-500"],
  lead: ["text-sky-700", "bg-sky-500"],
  frozen: ["text-cyan-700", "bg-cyan-500"],
  inactive: ["text-slate-600", "bg-slate-400"],
  closed: ["text-slate-600", "bg-slate-400"],
  offline: ["text-slate-600", "bg-slate-400"],
  cancelled: ["text-slate-600", "bg-slate-400"],
  expired: ["text-red-700", "bg-red-500"],
  blocked: ["text-red-700", "bg-red-500"],
  overdue: ["text-red-700", "bg-red-500"],
};

export function StatusBadge({ status }) {
  const [textClass, dotClass] = palettes[status] || [
    "text-slate-600",
    "bg-slate-400",
  ];
  return (
    <span className={`status status-${status || "neutral"} ${textClass}`}>
      <span aria-hidden="true" className={dotClass} />
      {statusLabel[status] || status || "Không xác định"}
    </span>
  );
}
