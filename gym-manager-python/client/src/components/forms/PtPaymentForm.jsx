import { useEffect, useState } from "react";
import { Button } from "../ui/Button";
import { Field, Input, Select } from "../ui/Form";
import { Modal } from "../ui/Modal";
import { MoneyInput } from "../ui/SmartInputs";
import { ReceiptPicker } from "../ui/ReceiptPicker";
import { money, shortDate } from "../../utils/format";

function currentDatetimeLocal() {
  const now = new Date();
  const pad = (value) => String(value).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
}

function initialForm(enrollment, installment) {
  return {
    mode: "full",
    amount: installment?.remainingAmount || enrollment?.debtAmount || 0,
    paymentMethod: "cash",
    bankAccountId: "",
    paidAt: currentDatetimeLocal(),
    receipts: [],
  };
}

export function PtPaymentForm({
  enrollment,
  installment,
  options,
  canWaive = false,
  open,
  onClose,
  onSubmit,
  pending,
  error,
}) {
  const [initial, setInitial] = useState(() => initialForm(enrollment, installment));
  const [form, setForm] = useState(() => initialForm(enrollment, installment));
  useEffect(() => {
    const next = initialForm(enrollment, installment);
    setInitial(next);
    setForm(next);
  }, [enrollment, installment, open]);
  if (!enrollment) return null;

  const currentDebt = Number(enrollment.debtAmount || 0);
  const remaining = form.mode === "waive"
    ? 0
    : Math.max(currentDebt - Number(form.amount || 0), 0);
  const fullAmount = installment?.remainingAmount || currentDebt;
  const setMode = (mode) => setForm({
    ...form,
    mode,
    amount: mode === "full" ? fullAmount : mode === "waive" ? 0 : 0,
    paymentMethod: mode === "waive" ? "cash" : form.paymentMethod,
    bankAccountId: mode === "waive" ? "" : form.bankAccountId,
    receipts: mode === "waive" ? [] : form.receipts,
  });
  const submit = (event) => {
    event.preventDefault();
    const payload = new FormData();
    payload.append("mode", form.mode);
    if (form.mode !== "waive") {
      payload.append("amount", Number(form.amount || 0));
      payload.append("paidAt", form.paidAt);
      payload.append("paymentMethod", form.paymentMethod);
      payload.append("bankAccountId", form.bankAccountId);
      if (installment?.id) payload.append("installmentId", installment.id);
      form.receipts.forEach((file) => payload.append("receipts", file));
    }
    onSubmit(payload);
  };
  const transferMissing = form.mode !== "waive"
    && form.paymentMethod === "bank_transfer"
    && !form.bankAccountId;

  return (
    <Modal
      open={open}
      onClose={onClose}
      dirty={JSON.stringify(form) !== JSON.stringify(initial)}
      title="Thu tiền PT"
      description={`${enrollment.member?.name || "Hội viên"} · ${enrollment.packageName || `PT ${enrollment.type}`}`}
    >
      <form onSubmit={submit}>
        <div className="modal-body">
          {installment && (
            <div className="mb-3 rounded-md border border-blue-100 bg-blue-50 px-3 py-2 text-xs text-blue-800">
              Thu cho kỳ hạn {shortDate(installment.dueDate)} · còn {money(installment.remainingAmount)}
            </div>
          )}
          <div className="mb-4 grid grid-cols-2 gap-3 rounded-md bg-slate-50 p-3 text-xs">
            <div><span className="text-slate-500">Công nợ PT hiện tại</span><strong className="mt-1 block text-sm text-red-700">{money(currentDebt)}</strong></div>
            <div><span className="text-slate-500">Sau giao dịch</span><strong className={`mt-1 block text-sm ${remaining ? "text-red-700" : "text-emerald-700"}`}>{money(remaining)}</strong></div>
          </div>
          <div className="form-grid">
            <div className="form-span segmented-control">
              <button type="button" className={form.mode === "full" ? "active" : ""} onClick={() => setMode("full")}>{installment ? "Thu đủ kỳ này" : "Thu đủ"}</button>
              <button type="button" className={form.mode === "partial" ? "active" : ""} onClick={() => setMode("partial")}>Thu một phần</button>
              {canWaive && <button type="button" className={form.mode === "waive" ? "active" : ""} onClick={() => setMode("waive")}>Miễn/điều chỉnh</button>}
            </div>
            {form.mode === "waive" ? (
              <div className="form-span rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800">
                Công nợ PT sẽ được đưa về 0 bằng cách điều chỉnh giá trị gói còn bằng số tiền đã thu. Thao tác được lưu trong Audit Log.
              </div>
            ) : (
              <>
                <Field className="form-span" label="Số tiền thu lần này" required>
                  <MoneyInput autoFocus min={1} max={currentDebt} value={form.amount} onChange={(amount) => setForm({ ...form, amount })} />
                </Field>
                <Field label="Phương thức">
                  <Select value={form.paymentMethod} onChange={(event) => setForm({ ...form, paymentMethod: event.target.value, bankAccountId: event.target.value === "cash" ? "" : form.bankAccountId })}>
                    <option value="cash">Tiền mặt</option>
                    <option value="bank_transfer">Chuyển khoản</option>
                    <option value="card">Thẻ</option>
                  </Select>
                </Field>
                <Field label="Ngày thu thực tế" required hint="Dùng khi nhập bù giao dịch đã thu trước đó.">
                  <Input type="datetime-local" value={form.paidAt} onChange={(event) => setForm({ ...form, paidAt: event.target.value })} />
                </Field>
                {form.paymentMethod !== "cash" && (
                  <Field label="Tài khoản nhận" required={form.paymentMethod === "bank_transfer"}>
                    <Select value={form.bankAccountId} onChange={(event) => setForm({ ...form, bankAccountId: event.target.value })}>
                      <option value="">Không áp dụng</option>
                      {options?.bankAccounts?.map((row) => <option key={row.id} value={row.id}>{row.label}</option>)}
                    </Select>
                  </Field>
                )}
                <Field className="form-span" label="Ảnh phiếu thu">
                  <ReceiptPicker files={form.receipts} onChange={(receipts) => setForm({ ...form, receipts })} disabled={pending} />
                </Field>
              </>
            )}
          </div>
          {transferMissing && <div className="inline-error mt-4">Vui lòng chọn tài khoản nhận tiền khi thanh toán PT chuyển khoản.</div>}
          {error && <div className="inline-error mt-4">{error}</div>}
        </div>
        <div className="form-actions">
          <Button data-modal-close type="button" variant="secondary" onClick={onClose}>Hủy</Button>
          <Button type="submit" loading={pending} loadingText="Đang ghi nhận…" disabled={form.mode !== "waive" && (Number(form.amount) <= 0 || Number(form.amount) > currentDebt || transferMissing)}>
            {form.mode === "waive" ? "Ghi nhận điều chỉnh" : "Ghi nhận thanh toán"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
