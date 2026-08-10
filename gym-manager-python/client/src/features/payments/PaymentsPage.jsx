import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { Link } from "react-router-dom";
import { api, queryString } from "../../services/api";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";
import { PageHeader } from "../../components/common/PageHeader";
import { SearchInput } from "../../components/common/SearchInput";
import { DataTable } from "../../components/ui/DataTable";
import { Select } from "../../components/ui/Form";
import { DateInput } from "../../components/ui/SmartInputs";
import { Pagination } from "../../components/ui/Pagination";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { dateTime, money } from "../../utils/format";

const methods = {
  cash: "Tiền mặt",
  bank_transfer: "Chuyển khoản",
  card: "Thẻ",
  apple_pay: "Apple Pay",
};
export function PaymentsPage() {
  const [search, setSearch] = useState("");
  const q = useDebouncedValue(search);
  const [method, setMethod] = useState("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(1);
  const query = useQuery({
    queryKey: ["payments", q, method, dateFrom, dateTo, page],
    queryFn: () =>
      api(
        `/api/payments?${queryString({ q, method, dateFrom, dateTo, page, pageSize: 20 })}`,
      ),
  });
  const columns = [
    {
      key: "number",
      label: "Phiếu thu",
      render: (r) => (
        <div>
          <span className="cell-primary">{r.number}</span>
          <div className="cell-secondary">
            {r.description || "Thanh toán gói"}
          </div>
        </div>
      ),
    },
    {
      key: "member",
      label: "Hội viên",
      render: (r) => (
        <Link
          to={`/members/${r.memberId}`}
          className="cell-primary hover:underline"
        >
          {r.memberName}
        </Link>
      ),
    },
    {
      key: "amount",
      label: "Số tiền",
      className: "text-right",
      render: (r) => (
        <span className="font-medium text-slate-900">{money(r.amount)}</span>
      ),
    },
    {
      key: "method",
      label: "Phương thức",
      render: (r) => methods[r.method] || r.method,
    },
    { key: "paidAt", label: "Ngày thu", render: (r) => dateTime(r.paidAt) },
    {
      key: "status",
      label: "Trạng thái",
      render: (r) => <StatusBadge status="paid" />,
    },
    {
      key: "receipt",
      label: "",
      render: (r) =>
        r.receiptUrl && (
          <a
            href={r.receiptUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-xs text-navy-700 hover:underline"
          >
            Phiếu <ExternalLink size={12} />
          </a>
        ),
    },
  ];
  return (
    <>
      <PageHeader
        eyebrow="Vận hành"
        title="Thanh toán"
        description="Đối soát phiếu thu, phương thức và doanh thu theo hội viên."
      />
      <div className="toolbar">
        <SearchInput
          value={search}
          onChange={(v) => {
            setSearch(v);
            setPage(1);
          }}
          placeholder="Phiếu thu, hội viên, mã hội viên…"
        />
        <Select
          className="input w-44"
          value={method}
          onChange={(e) => {
            setMethod(e.target.value);
            setPage(1);
          }}
        >
          <option value="all">Mọi phương thức</option>
          {Object.entries(methods).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
        <DateInput
          className="input w-40"
          value={dateFrom}
          onChange={setDateFrom}
          aria-label="Từ ngày"
        />
        <DateInput
          className="input w-40"
          value={dateTo}
          onChange={setDateTo}
          aria-label="Đến ngày"
        />
      </div>
      <DataTable
        columns={columns}
        rows={query.data?.items}
        loading={query.isLoading}
      />
      <Pagination data={query.data?.pagination} onPage={setPage} />
    </>
  );
}
