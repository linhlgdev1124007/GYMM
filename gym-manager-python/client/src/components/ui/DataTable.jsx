import { AlertCircle, Inbox } from "lucide-react";

export function DataTable({
  columns,
  rows,
  loading,
  error,
  onRetry,
  emptyTitle = "Không có dữ liệu",
  emptyDescription = "Thử thay đổi bộ lọc hoặc tạo dữ liệu mới.",
  rowKey = "id",
  onRowClick,
  selectedRowId,
  selection,
  onSelectionChange,
  density = "standard",
}) {
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
  const visibleColumns = selection
    ? [
        {
          key: "__select",
          label: (
            <input
              type="checkbox"
              aria-label="Chọn tất cả"
              checked={
                !!rows?.length &&
                rows.every((row) => selection.includes(row[rowKey]))
              }
              onChange={(event) =>
                onSelectionChange?.(
                  event.target.checked
                    ? [
                        ...new Set([
                          ...selection,
                          ...rows.map((row) => row[rowKey]),
                        ]),
                      ]
                    : selection.filter(
                        (id) => !rows.some((row) => row[rowKey] === id),
                      ),
                )
              }
            />
          ),
          className: "selection-cell",
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
    : columns;
  return (
    <div
      className={`table-shell ${density === "compact" ? "table-compact" : ""}`}
    >
      <div className="table-scroll">
        <table className="data-table">
          <thead>
            <tr>
              {visibleColumns.map((column) => (
                <th key={column.key} className={column.className}>
                  {column.label}
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
              : rows?.map((row) => (
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
                    }}
                  >
                    {visibleColumns.map((column) => (
                      <td key={column.key} className={column.className}>
                        {column.render ? column.render(row) : row[column.key]}
                      </td>
                    ))}
                  </tr>
                ))}
          </tbody>
        </table>
      </div>
      {!loading && !rows?.length && (
        <div className="empty-state">
          <Inbox size={22} />
          <div>
            <strong>{emptyTitle}</strong>
            <p>{emptyDescription}</p>
          </div>
        </div>
      )}
    </div>
  );
}
