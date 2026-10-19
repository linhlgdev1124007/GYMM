import { useState } from "react";

export const auditNoteLabels = {
  reason: "Lý do",
  pricingNote: "Ghi chú giá",
  note: "Ghi chú",
  notes: "Ghi chú",
};

export function auditNotes(item) {
  const changes = Array.isArray(item.details?.changes) ? item.details.changes : [];
  const seen = new Set();
  const result = [];
  for (const [key, label] of Object.entries(auditNoteLabels)) {
    const change = changes.find((entry) => entry.field === key);
    const value = change
      ? `${String(change.old ?? "—")} → ${String(change.new ?? "—")}`
      : item.details?.[key];
    const text = typeof value === "string" ? value.trim() : "";
    if (text && !seen.has(text)) {
      seen.add(text);
      result.push({ key, label, text });
    }
  }
  if (typeof item.currentPricingNote === "string" && item.currentPricingNote.trim()) {
    result.push({ key: "currentPricingNote", label: "Ghi chú giá hiện tại của gói", text: item.currentPricingNote.trim() });
  }
  return result;
}

export function auditChanges(item) {
  return (Array.isArray(item.details?.changes) ? item.details.changes : [])
    .filter((change) => !Object.hasOwn(auditNoteLabels, change.field));
}

export function AuditNotes({ item }) {
  const [expanded, setExpanded] = useState(false);
  const notes = auditNotes(item);
  if (!notes.length) return null;
  return (
    <div className="mt-1 max-w-xl text-xs text-slate-600">
      {notes.map(({ key, label, text }) => (
        <div key={key} className={`whitespace-pre-wrap [overflow-wrap:anywhere] ${expanded ? "" : "line-clamp-2"}`}>
          <b>{label}:</b> {text}
        </div>
      ))}
      <button
        type="button"
        className="mt-1 text-xs font-medium text-blue-700 hover:underline"
        aria-expanded={expanded}
        onClick={(event) => { event.stopPropagation(); setExpanded(!expanded); }}
      >
        {expanded ? "Thu gọn ghi chú" : "Xem đầy đủ ghi chú"}
      </button>
    </div>
  );
}
