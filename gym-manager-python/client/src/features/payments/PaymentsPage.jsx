import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, ReceiptText } from "lucide-react";
import { Link } from "react-router-dom";
import { api, queryString } from "../../services/api";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";
import { PageHeader } from "../../components/common/PageHeader";
import { SearchInput } from "../../components/common/SearchInput";
import { DataTable } from "../../components/ui/DataTable";
import { Select } from "../../components/ui/Form";
import { DateInput } from "../../components/ui/SmartInputs";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
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

const isoDateValue = (value) => {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const offset = date.getTimezoneOffset() * 60000;
  return new Date(date.getTime() - offset).toISOString().slice(0, 10);
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
  const [editingPayment, setEditingPayment] = useState(null);
  const [paidAt, setPaidAt] = useState("");
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
  const updatePayment = useMutation({
    mutationFn: ({ id, paidAt: nextPaidAt }) =>
      api(`/api/payments/${id}`, {
        method: "PATCH",
        body: { paidAt: nextPaidAt },
      }),
    onSuccess: (payment) => {
      client.invalidateQueries({ queryKey: ["payments"] });
      client.invalidateQueries({ queryKey: ["member", payment.memberId] });
      setEditingPayment(null);
      setPaidAt("");
      setFormError("");
      notify.success(`Đã sửa ngày nhận thanh toán cho ${payment.number}.`);
    },
    onError: (error) => setFormError(error.message),
  });
  useEffect(() => {
    if (!editingPayment) return;
    setPaidAt(isoDateValue(editingPayment.paidAt));
    setFormError("");
  }, [editingPayment]);
  const columns = [
    {
      key: "number",
      label: "Giao dịch",
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
        <span className={`font-medium ${Number(r.amount || 0) < 0 ? "text-red-700" : "text-slate-900"}`}>{money(r.amount)}</span>
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
      label: "Ngày giao dịch",
      sortValue: (r) => r.paidAt,
      render: (r) => (
        <div className="flex items-center gap-2">
          <span>{dateTime(r.paidAt)}</span>
          <button
            className="icon-button"
            onClick={() => setEditingPayment(r)}
            aria-label={`Sửa ngày nhận thanh toán ${r.number}`}
            title="Sửa ngày nhận thanh toán"
          >
            <Pencil size={14} />
          </button>
        </div>
      ),
    },
    {
      key: "status",
      label: "Trạng thái",
      sortValue: (r) => r.status || "paid",
      render: (r) => <StatusBadge status={r.status || "paid"} />,
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
      <Modal
        open={!!editingPayment}
        onClose={() => {
          setEditingPayment(null);
          setPaidAt("");
          setFormError("");
        }}
        title="Sửa ngày nhận thanh toán"
        dirty={paidAt !== isoDateValue(editingPayment?.paidAt)}
      >
        <form
          className="form-grid"
          onSubmit={(event) => {
            event.preventDefault();
            if (!paidAt) {
              setFormError("Vui lòng chọn ngày nhận thanh toán.");
              return;
            }
            updatePayment.mutate({ id: editingPayment.id, paidAt });
          }}
        >
          <label>
            <span>Phiếu thu</span>
            <input className="input" value={editingPayment?.number || ""} disabled />
          </label>
          <label>
            <span>Hội viên</span>
            <input className="input" value={editingPayment?.memberName || ""} disabled />
          </label>
          <label>
            <span>Số tiền</span>
            <input className="input" value={money(editingPayment?.amount)} disabled />
          </label>
          <label>
            <span>Ngày nhận thanh toán</span>
            <DateInput className="input" value={paidAt} onChange={setPaidAt} />
          </label>
          {formError && <div className="form-error md:col-span-2">{formError}</div>}
          <div className="form-actions md:col-span-2">
            <Button
              variant="secondary"
              type="button"
              onClick={() => {
                setEditingPayment(null);
                setPaidAt("");
                setFormError("");
              }}
            >
              Hủy
            </Button>
            <Button type="submit" loading={updatePayment.isPending}>
              Lưu
            </Button>
          </div>
        </form>
      </Modal>
    </>
  );
}
