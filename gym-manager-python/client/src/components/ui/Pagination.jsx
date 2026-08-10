import { Button } from "./Button";
export function Pagination({ data, onPage }) {
  if (!data || data.pages <= 1) return null;
  return (
    <div className="pagination">
      <span>
        Trang {data.page}/{data.pages} · {data.total} kết quả
      </span>
      <div>
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
          disabled={data.page >= data.pages}
          onClick={() => onPage(data.page + 1)}
        >
          Sau
        </Button>
      </div>
    </div>
  );
}
