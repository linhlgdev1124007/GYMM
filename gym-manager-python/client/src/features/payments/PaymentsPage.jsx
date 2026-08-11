import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ReceiptText } from "lucide-react";
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
import { PaymentReceiptModal } from "../../components/forms/PaymentReceiptModal";
import { notify } from "../../services/notify";

const methods = {
  cash: "Tiền mặt",
  bank_transfer: "Chuyển khoản",
  card: "Thẻ",
  apple_pay: "Apple Pay",
};
export function PaymentsPage() {
  const client = useQueryClient();
  const [search, setSearch] = useState("");
  const q = useDebouncedValue(search);
  const [method, setMethod] = useState("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [selectedPayment, setSelectedPayment] = useState(null);
  const [formError, setFormError] = useState("");
  const query = useQuery({
    queryKey: ["payments", q, method, dateFrom, dateTo, page, pageSize],
    queryFn: () =>
      api(
        `/api/payments?${queryString({ q, method, dateFrom, dateTo, page, pageSize })}`,
      ),
  });
  const uploadReceipts = useMutation({
    mutationFn: ({ id, data }) =>
      api(`/api/payments/${id}/receipts`, { method: "POST", body: data }),
    onSuccess: (payment) => {
      client.invalidateQueries({ queryKey: ["payments"] });
      client.invalidateQueries({ queryKey: ["member", payment.memberId] });
      setSelectedPayment(payment);
      notify.success(`Đã thêm chứng từ cho ${payment.number}.`);
    },
    onError: (error) => setFormError(error.message),
  });
  const columns = [
    {
      key: "number",
      label: "Phiếu thu",
      sortValue: (r) => r.number,
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
      sortValue: (r) => r.memberName,
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
      sortValue: (r) => r.amount,
      render: (r) => (
        <span className="font-medium text-slate-900">{money(r.amount)}</span>
      ),
    },
    {
      key: "method",
      label: "Phương thức",
      sortValue: (r) => methods[r.method] || r.method,
      render: (r) => methods[r.method] || r.method,
    },
    {
      key: "paidAt",
      label: "Ngày thu",
      sortValue: (r) => r.paidAt,
      render: (r) => dateTime(r.paidAt),
    },
    {
      key: "status",
      label: "Trạng thái",
      sortValue: () => "paid",
      render: (r) => <StatusBadge status="paid" />,
    },
    {
      key: "receipt",
      label: "Chứng từ",
      sortValue: (r) => r.receiptCount || 0,
      render: (r) => (
        <button
          className="receipt-count-button"
          onClick={() => {
            setFormError("");
            setSelectedPayment(r);
          }}
        >
          <ReceiptText size={14} />
          {r.receiptCount ? `${r.receiptCount} ảnh` : "+ Thêm bill"}
        </button>
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
        error={query.error}
        onRetry={query.refetch}
      />
      <Pagination
        data={query.data?.pagination}
        onPage={setPage}
        pageSize={pageSize}
        onPageSize={(value) => {
          setPageSize(value);
          setPage(1);
        }}
      />
      <PaymentReceiptModal
        payment={selectedPayment}
        open={!!selectedPayment}
        onClose={() => {
          setSelectedPayment(null);
          setFormError("");
        }}
        onUpload={(data) =>
          uploadReceipts.mutate({ id: selectedPayment.id, data })
        }
        pending={uploadReceipts.isPending}
        error={formError}
      />
    </>
  );
}
