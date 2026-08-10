import { statusLabel } from "../../utils/format";
export function StatusBadge({ status }) {
  return (
    <span className={`status status-${status || "neutral"}`}>
      <span aria-hidden="true" />
      {statusLabel[status] || status || "Không xác định"}
    </span>
  );
}
