import { AlertCircle, Inbox } from "lucide-react";
import { useMemo, useState } from "react";

const collator = new Intl.Collator("vi", {
  numeric: true,
  sensitivity: "base",
});

function normalizeSortValue(value) {
  if (value instanceof Date) return value.getTime();
  if (typeof value === "number") return Number.isFinite(value) ? value : 0;
  if (typeof value === "boolean") return value ? 1 : 0;
  return String(value ?? "").trim();
}

function fallbackSortValue(row, key) {
  if (row?.[key] != null) return row[key];
  if (key === "member") return row.memberName || row.member?.name || row.name;
  if (key === "trainer") return row.trainerName || row.trainer?.name;
  if (key === "coach") return row.coachName || row.coaches?.map((coach) => coach.name).join(", ");
  if (key === "package") return row.packageName || row.package?.name || row.package;
  if (key === "period") return row.expiresAt || row.startsAt;
  if (key === "time") return row.eventTime || row.receivedAt || row.createdAt;
  return "";
}

export function DataTable({
  columns,
  rows,
  loading,
  error,
  onRetry,
  emptyTitle = "Không có dữ liệu",
  emptyDescription = "Thử thay đổi bộ lọc hoặc tạo dữ liệu mới.",
  emptyAction,
  rowKey = "id",
  onRowClick,
  selectedRowId,
  selection,
  onSelectionChange,
  density = "standard",
}) {
  const [sort, setSort] = useState({ key: "", direction: "asc" });
  if (error)
    return (
      <div className="empty-state border-y border-red-100 bg-red-50/40">
        <AlertCircle size={22} className="text-red-500" />
        <div>
          <strong>Không thể tải dữ liệu</strong>
          <p>{error.message || "Vui lòng thử lại sau."}</p>
          {onRetry && (
            <button
              className="mt-2 text-xs font-semibold text-red-700 underline"
              onClick={onRetry}
            >
              Thử lại
            </button>
          )}
        </div>
      </div>
    );
  const dataRows = Array.isArray(rows) ? rows : [];
  const visibleColumns = useMemo(
    () =>
      selection
        ? [
            {
              key: "__select",
              label: (
                <input
                  type="checkbox"
                  aria-label="Chọn tất cả"
                  checked={
                    !!dataRows.length &&
                    dataRows.every((row) => selection.includes(row[rowKey]))
                  }
                  onChange={(event) =>
                    onSelectionChange?.(
                      event.target.checked
                        ? [
                            ...new Set([
                              ...selection,
                              ...dataRows.map((row) => row[rowKey]),
                            ]),
                          ]
                        : selection.filter(
                            (id) =>
                              !dataRows.some((row) => row[rowKey] === id),
                          ),
                    )
                  }
                />
              ),
              className: "selection-cell",
              sortable: false,
              render: (row) => (
                <input
                  type="checkbox"
                  aria-label={`Chọn ${row.name || row[rowKey]}`}
                  checked={selection.includes(row[rowKey])}
                  onClick={(event) => event.stopPropagation()}
                  onChange={(event) =>
                    onSelectionChange?.(
                      event.target.checked
                        ? [...selection, row[rowKey]]
                        : selection.filter((id) => id !== row[rowKey]),
                    )
                  }
                />
              ),
            },
            ...columns,
          ]
        : columns,
    [columns, dataRows, onSelectionChange, rowKey, selection],
  );
  const sortedRows = useMemo(() => {
    if (!sort.key || !dataRows.length) return dataRows;
    const column = visibleColumns.find((item) => item.key === sort.key);
    if (!column || column.sortable === false || column.key === "__select") {
      return dataRows;
    }
    const valueFor = (row) => {
      const raw = column.sortValue
        ? column.sortValue(row)
        : fallbackSortValue(row, column.key);
      return normalizeSortValue(raw);
    };
    return [...dataRows].sort((a, b) => {
      const left = valueFor(a);
      const right = valueFor(b);
      const result =
        typeof left === "number" && typeof right === "number"
          ? left - right
          : collator.compare(String(left), String(right));
      return sort.direction === "asc" ? result : -result;
    });
  }, [dataRows, sort, visibleColumns]);
  const actionColumn = (column) => ["action", "actions", "receipt"].includes(column.key);
  const canSortColumn = (column) =>
    column.sortable !== false && column.key !== "__select" && !actionColumn(column);
  const sortNext = (column) =>
    setSort((current) => ({
      key: column.key,
      direction:
        current.key === column.key && current.direction === "asc"
          ? "desc"
          : "asc",
    }));
  return (
    <div
      className={`table-shell ${density === "compact" ? "table-compact" : ""}`}
    >
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              {visibleColumns.map((column) => (
                <th
                  key={column.key}
                  className={`${column.className || ""} ${actionColumn(column) ? "sticky-action-col" : ""}`}
                >
                  {!canSortColumn(column) ? column.label : (
                    <button
                      type="button"
                      className="table-sort-button"
                      aria-sort={
                        sort.key === column.key
                          ? sort.direction === "asc"
                            ? "ascending"
                            : "descending"
                          : "none"
                      }
                      onClick={() => sortNext(column)}
                    >
                      {column.label}
                      {sort.key === column.key && <span>{sort.direction === "asc" ? "↑" : "↓"}</span>}
                    </button>
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading
              ? Array.from({ length: 6 }).map((_, index) => (
                  <tr key={index}>
                    {visibleColumns.map((column) => (
                      <td key={column.key}>
                        <div className="skeleton h-4 w-3/4" />
                      </td>
                    ))}
                  </tr>
                ))
              : sortedRows.map((row) => (
                  <tr
                    key={row[rowKey]}
                    className={`${onRowClick ? "clickable-row" : ""} ${selectedRowId === row[rowKey] ? "selected-row" : ""}`}
                    tabIndex={onRowClick ? 0 : undefined}
                    onClick={() => onRowClick?.(row)}
                    onKeyDown={(event) => {
                      if (
                        onRowClick &&
                        (event.key === "Enter" || event.key === " ")
                      ) {
                        event.preventDefault();
                        onRowClick(row);
                      }
                      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                        event.preventDefault();
                        const next =
                          event.key === "ArrowDown"
                            ? event.currentTarget.nextElementSibling
                            : event.currentTarget.previousElementSibling;
                        next?.focus();
                      }
                    }}
                  >
                    {visibleColumns.map((column) => (
                      <td
                        key={column.key}
                        className={`${column.className || ""} ${actionColumn(column) ? "sticky-action-col" : ""}`}
                      >
                        {column.render ? column.render(row) : row[column.key]}
                      </td>
                    ))}
                  </tr>
                ))}
          </tbody>
        </table>
      </div>
      {!loading && !dataRows.length && (
        <div className="empty-state">
          <Inbox size={22} />
          <div>
            <strong>{emptyTitle}</strong>
            <p>{emptyDescription}</p>
            {emptyAction && <div className="empty-state-action">{emptyAction}</div>}
          </div>
        </div>
      )}
    </div>
  );
}
