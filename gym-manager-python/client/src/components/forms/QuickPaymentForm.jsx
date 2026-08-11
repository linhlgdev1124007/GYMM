import { useEffect, useState } from "react";
import { Button } from "../ui/Button";
import { Field, Select } from "../ui/Form";
import { Modal } from "../ui/Modal";
import { money } from "../../utils/format";
import { MoneyInput } from "../ui/SmartInputs";
import { ReceiptPicker } from "../ui/ReceiptPicker";

export function QuickPaymentForm({
  membership,
  options,
  open,
  onClose,
  onSubmit,
  pending,
  error,
}) {
  const [form, setForm] = useState({
    amount: 0,
    paymentMethod: "cash",
    bankAccountId: "",
    receipts: [],
  });
  const initial = {
    amount: membership?.debtAmount || 0,
    paymentMethod: "cash",
    bankAccountId: "",
    receipts: [],
  };
  useEffect(() => setForm(initial), [membership, open]);
  if (!membership) return null;
  const remaining = Math.max(
    Number(membership.debtAmount || 0) - Number(form.amount || 0),
    0,
  );
  const submit = (event) => {
    event.preventDefault();
    const payload = new FormData();
    payload.append("startsAt", membership.startsAt || "");
    payload.append("expiresAt", membership.expiresAt || "");
    payload.append("finalPrice", membership.finalPrice || 0);
    payload.append(
      "paidAmount",
      Number(membership.paidAmount || 0) + Number(form.amount || 0),
    );
    payload.append(
      "debtDueDate",
      remaining ? membership.debtDueDate || "" : "",
    );
    payload.append("paymentMethod", form.paymentMethod);
    payload.append("bankAccountId", form.bankAccountId);
    payload.append(
      "status",
      membership.status === "expiring" ? "active" : membership.status,
    );
    form.receipts.forEach((file) => payload.append("receipts", file));
    onSubmit(payload, { amount: Number(form.amount || 0) });
  };
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
            {form.paymentMethod !== "cash" && (
              <Field label="Tài khoản nhận">
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
          </div>
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
            disabled={Number(form.amount) <= 0}
          >
            Ghi nhận thanh toán
          </Button>
        </div>
      </form>
    </Modal>
  );
}
