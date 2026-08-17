import { useEffect, useState } from "react";
import { Button } from "../ui/Button";
import { Field, Input, Select } from "../ui/Form";
import { Modal } from "../ui/Modal";
import { money } from "../../utils/format";
import { MoneyInput } from "../ui/SmartInputs";
import { ReceiptPicker } from "../ui/ReceiptPicker";

function currentDatetimeLocal() {
  const now = new Date();
  const pad = (value) => String(value).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
}

function buildInitialForm(membership) {
  return {
    mode: "full",
    amount: membership?.debtAmount || 0,
    paymentMethod: "cash",
    bankAccountId: "",
    paidAt: currentDatetimeLocal(),
    receipts: [],
  };
}

export function QuickPaymentForm({
  membership,
  options,
  open,
  onClose,
  onSubmit,
  pending,
  error,
}) {
  const [initial, setInitial] = useState(() => buildInitialForm(membership));
  const [form, setForm] = useState(() => buildInitialForm(membership));
  useEffect(() => {
    const next = buildInitialForm(membership);
    setInitial(next);
    setForm(next);
  }, [membership, open]);
  if (!membership) return null;
  const remaining = Math.max(
    Number(membership.debtAmount || 0) - Number(form.amount || 0),
    0,
  );
  const submit = (event) => {
    event.preventDefault();
    if (
      Number(form.amount || 0) > 0 &&
      form.paymentMethod === "bank_transfer" &&
      !form.bankAccountId
    )
      return;
    const payload = new FormData();
    payload.append("startsAt", membership.startsAt || "");
    payload.append("expiresAt", membership.expiresAt || "");
    payload.append(
      "finalPrice",
      form.mode === "waive" ? membership.paidAmount || 0 : membership.finalPrice || 0,
    );
    payload.append(
      "paidAmount",
      form.mode === "waive"
        ? Number(membership.paidAmount || 0)
        : Number(membership.paidAmount || 0) + Number(form.amount || 0),
    );
    payload.append(
      "debtDueDate",
      remaining ? membership.debtDueDate || "" : "",
    );
    payload.append("paymentMethod", form.paymentMethod);
    payload.append("bankAccountId", form.bankAccountId);
    payload.append("paidAt", form.paidAt);
    payload.append(
      "status",
      membership.status === "expiring" ? "active" : membership.status,
    );
    form.receipts.forEach((file) => payload.append("receipts", file));
    onSubmit(payload, {
      amount: Number(form.amount || 0),
      waived: form.mode === "waive" ? Number(membership.debtAmount || 0) : 0,
    });
  };
  const setMode = (mode) =>
    setForm({
      ...form,
      mode,
      amount:
        mode === "full"
          ? membership.debtAmount || 0
          : mode === "waive"
            ? 0
            : form.amount && Number(form.amount) < Number(membership.debtAmount || 0)
              ? form.amount
              : 0,
      paymentMethod: mode === "waive" ? "cash" : form.paymentMethod,
      bankAccountId: mode === "waive" ? "" : form.bankAccountId,
      paidAt: mode === "waive" ? currentDatetimeLocal() : form.paidAt,
      receipts: mode === "waive" ? [] : form.receipts,
    });
  return (
    <Modal
      open={open}
      onClose={onClose}
      dirty={JSON.stringify(form) !== JSON.stringify(initial)}
      title="Thu tiền"
      description={`${membership.memberName || "Hội viên"} · ${membership.package.name}`}
    >
      <form onSubmit={submit}>
        <div className="modal-body">
          <div className="mb-4 grid grid-cols-2 gap-3 rounded-md bg-slate-50 p-3 text-xs">
            <div>
              <span className="text-slate-500">Công nợ hiện tại</span>
              <strong className="mt-1 block text-sm text-red-700">
                {money(membership.debtAmount)}
              </strong>
            </div>
            <div>
              <span className="text-slate-500">Sau giao dịch</span>
              <strong
                className={`mt-1 block text-sm ${remaining ? "text-red-700" : "text-emerald-700"}`}
              >
                {money(remaining)}
              </strong>
            </div>
          </div>
          <div className="form-grid">
            <div className="form-span segmented-control">
              <button
                type="button"
                className={form.mode === "full" ? "active" : ""}
                onClick={() => setMode("full")}
              >
                Thu đủ
              </button>
              <button
                type="button"
                className={form.mode === "partial" ? "active" : ""}
                onClick={() => setMode("partial")}
              >
                Thu một phần
              </button>
              <button
                type="button"
                className={form.mode === "waive" ? "active" : ""}
                onClick={() => setMode("waive")}
              >
                Miễn/điều chỉnh
              </button>
            </div>
            {form.mode === "waive" && (
              <div className="form-span rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800">
                Công nợ sẽ được đưa về 0 bằng cách điều chỉnh giá trị gói còn bằng số tiền đã thu. Thao tác này được lưu trong Audit Log.
              </div>
            )}
            {form.mode !== "waive" && (
              <>
            <Field className="form-span" label="Số tiền thu" required>
              <MoneyInput
                autoFocus
                min={1}
                max={membership.debtAmount}
                value={form.amount}
                onChange={(amount) => setForm({ ...form, amount })}
              />
            </Field>
            <Field label="Phương thức">
              <Select
                value={form.paymentMethod}
                onChange={(e) =>
                  setForm({
                    ...form,
                    paymentMethod: e.target.value,
                    bankAccountId:
                      e.target.value === "cash" ? "" : form.bankAccountId,
                  })
                }
              >
                <option value="cash">Tiền mặt</option>
                <option value="bank_transfer">Chuyển khoản</option>
                <option value="card">Thẻ</option>
              </Select>
            </Field>
            <Field label="Ngày thu thực tế" required hint="Dùng khi nhập bù giao dịch đã thu trước đó.">
              <Input
                type="datetime-local"
                value={form.paidAt}
                onChange={(e) => setForm({ ...form, paidAt: e.target.value })}
              />
            </Field>
            {form.paymentMethod !== "cash" && (
              <Field label="Tài khoản nhận" required={form.paymentMethod === "bank_transfer"}>
                <Select
                  value={form.bankAccountId}
                  onChange={(e) =>
                    setForm({ ...form, bankAccountId: e.target.value })
                  }
                >
                  <option value="">Không áp dụng</option>
                  {options?.bankAccounts?.map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.label}
                    </option>
                  ))}
                </Select>
              </Field>
            )}
            <Field className="form-span" label="Ảnh phiếu thu">
              <ReceiptPicker
                files={form.receipts}
                onChange={(receipts) => setForm({ ...form, receipts })}
                disabled={pending}
              />
            </Field>
              </>
            )}
          </div>
          {Number(form.amount || 0) > 0 &&
            form.paymentMethod === "bank_transfer" &&
            !form.bankAccountId && (
              <div className="inline-error mt-4">
                Vui lòng chọn tài khoản nhận tiền khi thanh toán chuyển khoản.
              </div>
            )}
          {error && <div className="inline-error mt-4">{error}</div>}
        </div>
        <div className="form-actions">
          <Button data-modal-close variant="secondary" onClick={onClose}>
            Hủy
          </Button>
          <Button
            type="submit"
            loading={pending}
            loadingText="Đang ghi nhận…"
            disabled={
              form.mode !== "waive" &&
              (Number(form.amount) <= 0 ||
                (form.paymentMethod === "bank_transfer" && !form.bankAccountId))
            }
          >
            {form.mode === "waive" ? "Ghi nhận điều chỉnh" : "Ghi nhận thanh toán"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
