import { Button } from "./Button";
import { Select } from "./Form";

const defaultOptions = [10, 20, 30, 50, 100];

export function Pagination({
  data,
  onPage,
  pageSize,
  onPageSize,
  pageSizeOptions = defaultOptions,
}) {
  if (!data || data.total === 0) return null;
  const totalPages = Number(data.totalPages || data.pages || 1);
  const currentPageSize = Number(pageSize || data.pageSize || 20);
  const first = (data.page - 1) * currentPageSize + 1;
  const last = Math.min(data.page * currentPageSize, data.total);
  return (
    <div className="pagination">
      <div className="pagination-summary">
        <span>
          {first}-{last}/{data.total} kết quả · Trang {data.page}/{totalPages}
        </span>
        {onPageSize && (
          <label>
            <span>Số dòng</span>
            <Select
              value={currentPageSize}
              onChange={(event) => onPageSize(Number(event.target.value))}
            >
              {pageSizeOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </Select>
          </label>
        )}
      </div>
      <div className="pagination-actions">
        <Button
          variant="secondary"
          size="sm"
          disabled={data.page <= 1}
          onClick={() => onPage(data.page - 1)}
        >
          Trước
        </Button>
        <Button
          variant="secondary"
          size="sm"
          disabled={data.page >= totalPages}
          onClick={() => onPage(data.page + 1)}
        >
          Sau
        </Button>
      </div>
    </div>
  );
}
