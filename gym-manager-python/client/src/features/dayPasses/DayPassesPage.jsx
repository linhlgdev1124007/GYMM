import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import { CalendarPlus, Plus, RefreshCw, UserPlus } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api, queryString } from "../../services/api";
import { notify } from "../../services/notify";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";
import { PageHeader } from "../../components/common/PageHeader";
import { SearchInput } from "../../components/common/SearchInput";
import { Button } from "../../components/ui/Button";
import { DataTable } from "../../components/ui/DataTable";
import { Field, Input, Select, Textarea } from "../../components/ui/Form";
import { Modal } from "../../components/ui/Modal";
import { SearchableSelect } from "../../components/ui/SearchableSelect";
import { DateInput, MoneyInput, PhoneInput } from "../../components/ui/SmartInputs";
import { Pagination } from "../../components/ui/Pagination";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { dateTime, formatPhone, money, normalizePhone, shortDate } from "../../utils/format";

const DEFAULT_PRICE = 79000;
const methodLabels = {
  cash: "Tiền mặt",
  bank_transfer: "Chuyển khoản",
  card: "Thẻ",
  apple_pay: "Apple Pay",
};
const conversionPolicyLabels = {
  refunded: "Hoàn tiền",
  deducted: "Khấu trừ vào gói",
};

const initialForm = () => ({
  guestName: "",
  guestPhone: "",
  guestGender: "",
  guestNote: "",
  visitDate: format(new Date(), "yyyy-MM-dd"),
  chargedAmount: DEFAULT_PRICE,
  paidAt: "",
  paymentMethod: "cash",
  bankAccountId: "",
  salesEmployeeId: "",
  ownerEmployeeId: "",
});

export function DayPassesPage() {
  const client = useQueryClient();
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const q = useDebouncedValue(search);
  const [status, setStatus] = useState("all");
  const [method, setMethod] = useState("all");
  const today = format(new Date(), "yyyy-MM-dd");
  const [dateFrom, setDateFrom] = useState(today);
  const [dateTo, setDateTo] = useState(today);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(30);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(initialForm);
  const [error, setError] = useState("");
  const [conversionDraft, setConversionDraft] = useState(null);
  const [conversionPolicy, setConversionPolicy] = useState("refunded");

  const query = useQuery({
    queryKey: ["day-passes", q, status, method, dateFrom, dateTo, page, pageSize],
    queryFn: () => api(`/api/day-passes?${queryString({ q, status, method, dateFrom, dateTo, page, pageSize })}`),
  });
  const options = useQuery({
    queryKey: ["member-options"],
    queryFn: () => api("/api/members/options"),
    staleTime: 5 * 60_000,
  });
  const employees = useMemo(
    () =>
      (options.data?.employees || []).map((row) => ({
        value: row.id,
        label: row.name,
        meta: `${row.code} · ${row.title || "Nhân viên"}`,
      })),
    [options.data?.employees],
  );
  const sales = useMemo(
    () =>
      (options.data?.salesEmployees || []).map((row) => ({
        value: row.id,
        label: row.name,
        meta: `${row.code} · ${row.title || "Sale"}`,
      })),
    [options.data?.salesEmployees],
  );

  const save = useMutation({
    mutationFn: (payload) =>
      api(editing ? `/api/day-passes/${editing.id}` : "/api/day-passes", {
        method: editing ? "PATCH" : "POST",
        body: payload,
      }),
    onSuccess: (row) => {
      client.invalidateQueries({ queryKey: ["day-passes"] });
      client.invalidateQueries({ queryKey: ["dashboard"] });
      client.invalidateQueries({ queryKey: ["reports"] });
      setOpen(false);
      setEditing(null);
      setForm(initialForm());
      notify.success(`Đã lưu lượt tập ngày của ${row.guestName}.`);
    },
    onError: (reason) => setError(reason.message),
  });
  const voidVisit = useMutation({
    mutationFn: (row) => api(`/api/day-passes/${row.id}/void`, { method: "POST", body: { reason: "Hủy từ danh sách khách tập ngày" } }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["day-passes"] });
      client.invalidateQueries({ queryKey: ["dashboard"] });
      client.invalidateQueries({ queryKey: ["reports"] });
    },
    onError: (reason) => notify.errorFrom(reason, "Không thể hủy lượt tập ngày."),
  });

  const openCreate = () => {
    setEditing(null);
    setError("");
    setForm(initialForm());
    setOpen(true);
  };
  const openEdit = (row) => {
    setEditing(row);
    setError("");
    setForm({
      guestName: row.guestName || "",
      guestPhone: row.guestPhone || "",
      guestGender: row.guestGender || "",
      guestNote: row.guestNote || "",
      visitDate: row.visitDate || today,
      chargedAmount: row.chargedAmount || DEFAULT_PRICE,
      paidAt: row.paidAt ? row.paidAt.slice(0, 16) : "",
      paymentMethod: row.paymentMethod || "cash",
      bankAccountId: row.bankAccountId || "",
      salesEmployeeId: row.salesEmployee?.id || "",
      ownerEmployeeId: row.ownerEmployee?.id || "",
    });
    setOpen(true);
  };
  const registerMember = (row) => {
    setConversionDraft(row);
    setConversionPolicy("refunded");
  };
  const confirmRegisterMember = () => {
    if (!conversionDraft) return;
    const params = new URLSearchParams();
    params.set("create", "1");
    params.set("dayPassId", conversionDraft.id);
    params.set("conversionPolicy", conversionPolicy);
    navigate(`/members?${params.toString()}`);
  };
  const submit = (event) => {
    event.preventDefault();
    setError("");
    if (!form.guestName.trim()) {
      setError("Vui lòng nhập tên khách tập ngày.");
      return;
    }
    if (Number(form.chargedAmount || 0) <= 0) {
      setError("Số tiền thu phải lớn hơn 0.");
      return;
    }
    if (Number(form.chargedAmount || 0) > 0 && form.paymentMethod === "bank_transfer" && !form.bankAccountId) {
      setError("Vui lòng chọn tài khoản nhận tiền khi thanh toán chuyển khoản.");
      return;
    }
    save.mutate({
      ...form,
      guestName: form.guestName.trim(),
      guestPhone: normalizePhone(form.guestPhone),
    });
  };

  const columns = [
    {
      key: "guest",
      label: "Khách tập ngày",
      render: (row) => (
        <button type="button" className="cell-primary text-left hover:underline" onClick={() => openEdit(row)}>
          {row.guestName}
          <span className="cell-secondary block">{formatPhone(row.guestPhone) || "Chưa có SĐT"}</span>
        </button>
      ),
    },
    { key: "visitDate", label: "Ngày tập", sortValue: (row) => row.visitDate, render: (row) => shortDate(row.visitDate) },
    { key: "paidAt", label: "Ngày thu", sortValue: (row) => row.paidAt, render: (row) => dateTime(row.paidAt) },
    { key: "amount", label: "Số tiền", className: "text-right", sortValue: (row) => row.chargedAmount, render: (row) => <strong>{money(row.chargedAmount)}</strong> },
    { key: "method", label: "Phương thức", render: (row) => methodLabels[row.paymentMethod] || row.paymentMethod },
    { key: "sale", label: "Sale/phụ trách", render: (row) => row.salesEmployee?.name || row.ownerEmployee?.name || "Chưa phân công" },
    { key: "status", label: "Trạng thái", render: (row) => <StatusBadge status={row.status} /> },
    {
      key: "actions",
      label: "",
      className: "text-right",
      sortable: false,
      render: (row) =>
        row.status === "active" ? (
          <div className="member-row-actions justify-end">
            <Button size="sm" variant="secondary" onClick={() => registerMember(row)}>
              <UserPlus size={14} />
              Đăng ký hội viên
            </Button>
            <button type="button" className="text-xs font-medium text-slate-500 hover:text-red-700" onClick={() => voidVisit.mutate(row)}>
              Hủy
            </button>
          </div>
        ) : row.convertedCustomerId ? (
          <Button size="sm" variant="secondary" onClick={() => navigate(`/members/${row.convertedCustomerId}`)}>
            Mở hồ sơ
          </Button>
        ) : null,
    },
  ];

  return (
    <>
      <PageHeader
        eyebrow="Vận hành"
        title="Khách tập ngày"
        description="Ghi nhận lượt tập vãng lai, doanh thu theo ca và chuyển đổi sang hội viên khi khách mua gói."
        action={
          <Button onClick={openCreate}>
            <Plus size={15} />
            Ghi nhận lượt tập
          </Button>
        }
      />
      <section className="command-metric-strip mb-5" aria-label="Tổng quan khách tập ngày">
        <div className="command-metric tone-positive">
          <span>Doanh thu net</span>
          <strong>{money(query.data?.summary?.netRevenue)}</strong>
          <small>Không tính lượt đã hoàn tiền</small>
        </div>
        <div className="command-metric tone-neutral">
          <span>Lượt hợp lệ</span>
          <strong>{Number(query.data?.summary?.activeVisits || 0).toLocaleString("vi-VN")}</strong>
          <small>{shortDate(dateFrom)} - {shortDate(dateTo)}</small>
        </div>
        <button type="button" className="command-metric tone-neutral" onClick={() => query.refetch()}>
          <span>Dữ liệu</span>
          <strong>{query.isFetching ? "Đang tải" : "Sẵn sàng"}</strong>
          <small><RefreshCw size={12} className={query.isFetching ? "animate-spin" : ""} /> Làm mới danh sách</small>
        </button>
      </section>
      <div className="toolbar">
        <SearchInput value={search} onChange={(value) => { setSearch(value); setPage(1); }} placeholder="Tên hoặc SĐT khách..." />
        <Select className="input w-44" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}>
          <option value="all">Mọi trạng thái</option>
          <option value="active">Đang hoạt động</option>
          <option value="converted">Đã chuyển đổi</option>
          <option value="void">Đã hủy</option>
        </Select>
        <Select className="input w-44" value={method} onChange={(event) => { setMethod(event.target.value); setPage(1); }}>
          <option value="all">Mọi phương thức</option>
          {Object.entries(methodLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </Select>
        <DateInput className="input w-40" value={dateFrom} onChange={(value) => { setDateFrom(value); setPage(1); }} />
        <DateInput className="input w-40" value={dateTo} onChange={(value) => { setDateTo(value); setPage(1); }} />
      </div>
      <DataTable
        rows={query.data?.items}
        columns={columns}
        loading={query.isLoading}
        error={query.error}
        onRetry={query.refetch}
        emptyTitle="Chưa có khách tập ngày"
        emptyDescription="Ghi nhận lượt tập đầu tiên để theo dõi doanh thu vãng lai."
      />
      <Pagination data={query.data?.pagination} onPage={setPage} pageSize={pageSize} onPageSize={(value) => { setPageSize(value); setPage(1); }} />

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title={editing ? "Cập nhật lượt tập ngày" : "Ghi nhận khách tập ngày"}
        description="Số điện thoại khách tập ngày có thể để trống."
        dirty={JSON.stringify(form) !== JSON.stringify(initialForm())}
      >
        <form onSubmit={submit}>
          <div className="modal-body space-y-5">
            <section className="form-section">
              <h3 className="form-section-title">Thông tin khách</h3>
              <div className="form-grid">
                <Field label="Họ tên" required>
                  <Input autoFocus value={form.guestName} onChange={(event) => setForm({ ...form, guestName: event.target.value })} />
                </Field>
                <Field label="Điện thoại">
                  <PhoneInput value={form.guestPhone} onChange={(guestPhone) => setForm({ ...form, guestPhone })} />
                </Field>
                <Field label="Giới tính">
                  <Select value={form.guestGender} onChange={(event) => setForm({ ...form, guestGender: event.target.value })}>
                    <option value="">Chưa chọn</option>
                    <option>Nam</option>
                    <option>Nữ</option>
                    <option>Khác</option>
                  </Select>
                </Field>
                <Field className="form-span" label="Ghi chú">
                  <Textarea value={form.guestNote} onChange={(event) => setForm({ ...form, guestNote: event.target.value })} />
                </Field>
              </div>
            </section>
            <section className="form-section">
              <h3 className="form-section-title">Ca tập và thanh toán</h3>
              <div className="form-grid">
                <Field label="Ngày tập">
                  <DateInput value={form.visitDate} onChange={(visitDate) => setForm({ ...form, visitDate })} />
                </Field>
                <Field label="Số tiền thu">
                  <MoneyInput min="0" value={form.chargedAmount} onChange={(chargedAmount) => setForm({ ...form, chargedAmount })} />
                </Field>
                <Field label="Ngày thu thực tế" hint="Để trống nếu thu ngay lúc lưu.">
                  <Input type="datetime-local" value={form.paidAt} onChange={(event) => setForm({ ...form, paidAt: event.target.value })} />
                </Field>
                <Field label="Phương thức">
                  <Select value={form.paymentMethod} onChange={(event) => setForm({ ...form, paymentMethod: event.target.value, bankAccountId: event.target.value === "cash" ? "" : form.bankAccountId })}>
                    <option value="cash">Tiền mặt</option>
                    <option value="bank_transfer">Chuyển khoản</option>
                    <option value="card">Thẻ</option>
                  </Select>
                </Field>
                {form.paymentMethod !== "cash" && (
                  <Field label="Tài khoản nhận" required={form.paymentMethod === "bank_transfer"}>
                    <Select value={form.bankAccountId} onChange={(event) => setForm({ ...form, bankAccountId: event.target.value })}>
                      <option value="">Chọn tài khoản</option>
                      {options.data?.bankAccounts?.map((row) => <option key={row.id} value={row.id}>{row.label}</option>)}
                    </Select>
                  </Field>
                )}
                <Field label="Sale">
                  <SearchableSelect value={form.salesEmployeeId} onChange={(salesEmployeeId) => setForm({ ...form, salesEmployeeId })} clearable placeholder="Chưa phân công" searchPlaceholder="Tên hoặc mã Sale..." options={sales} />
                </Field>
                <Field label="Người phụ trách">
                  <SearchableSelect value={form.ownerEmployeeId} onChange={(ownerEmployeeId) => setForm({ ...form, ownerEmployeeId })} clearable placeholder="Chưa phân công" searchPlaceholder="Tên hoặc mã nhân viên..." options={employees} />
                </Field>
              </div>
            </section>
            <section className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800">
              <CalendarPlus size={14} className="mr-1 inline align-[-2px]" />
              Khi khách mua gói tháng, người dùng sẽ chọn hoàn tiền hoặc khấu trừ trước khi mở form hội viên.
            </section>
            {error && <div className="inline-error">{error}</div>}
          </div>
          <div className="form-actions">
            <Button data-modal-close variant="secondary" onClick={() => setOpen(false)}>Hủy</Button>
            <Button type="submit" loading={save.isPending} loadingText="Đang lưu...">Lưu lượt tập</Button>
          </div>
        </form>
      </Modal>
      <Modal
        open={!!conversionDraft}
        onClose={() => setConversionDraft(null)}
        title="Đăng ký hội viên từ khách tập ngày"
        description={conversionDraft?.guestName || "Chọn cách xử lý khoản tiền đã thu trước khi mở form hội viên."}
      >
        <div className="modal-body space-y-4">
          <section className="rounded-md border border-slate-200 bg-slate-50 px-4 py-3 text-sm">
            <span className="text-xs text-slate-500">Khoản tập ngày đã thu</span>
            <strong className="mt-1 block text-slate-950">{money(conversionDraft?.chargedAmount)}</strong>
            <small className="mt-1 block text-slate-500">{shortDate(conversionDraft?.visitDate)} · {methodLabels[conversionDraft?.paymentMethod] || conversionDraft?.paymentMethod}</small>
          </section>
          <Field label="Chính sách xử lý tiền tập ngày">
            <Select value={conversionPolicy} onChange={(event) => setConversionPolicy(event.target.value)}>
              {Object.entries(conversionPolicyLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </Select>
          </Field>
          <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800">
            {conversionPolicy === "refunded"
              ? "Lượt tập ngày sẽ được đánh dấu đã chuyển đổi và ghi nhận hoàn tiền, không còn tính vào doanh thu net."
              : "Lượt tập ngày sẽ được đánh dấu đã chuyển đổi và ghi nhận khoản đã thu là tiền khấu trừ vào gói, tránh tính trùng với doanh thu gói hội viên."}
          </div>
        </div>
        <div className="form-actions">
          <Button data-modal-close variant="secondary" onClick={() => setConversionDraft(null)}>Hủy</Button>
          <Button onClick={confirmRegisterMember}>
            <UserPlus size={15} />
            Mở form hội viên
          </Button>
        </div>
      </Modal>
    </>
  );
}
