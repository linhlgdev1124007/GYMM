import { useEffect, useMemo, useState } from "react";
import { addDays, format, parseISO } from "date-fns";
import { Button } from "../ui/Button";
import { Field, Select } from "../ui/Form";
import { Modal } from "../ui/Modal";
import { SearchableSelect } from "../ui/SearchableSelect";
import {
  formatPhone,
  money,
  shortDate,
  statusLabel,
} from "../../utils/format";
import { DateInput, MoneyInput } from "../ui/SmartInputs";
import { ReceiptPicker } from "../ui/ReceiptPicker";

const planCollator = new Intl.Collator("vi", {
  numeric: true,
  sensitivity: "base",
});

function groupedPlanOptions(plans = []) {
  return [...plans]
    .sort((left, right) => {
      const categoryDiff = planCollator.compare(left.category || "", right.category || "");
      const priceDiff = Number(left.price || 0) - Number(right.price || 0);
      return categoryDiff || priceDiff || planCollator.compare(left.name || "", right.name || "");
    })
    .map((row) => ({
      value: row.id,
      label: row.name,
      group: row.category || "Chưa phân loại",
      meta: `${money(row.price)} · ${row.durationDays} ngày`,
    }));
}

export function MembershipForm({
  memberId,
  member,
  membership,
  currentMembership,
  options,
  open,
  onClose,
  onSubmit,
  pending,
  error,
}) {
  const today = format(new Date(), "yyyy-MM-dd");
  const [form, setForm] = useState({});
  const [initial, setInitial] = useState({});
  const [localError, setLocalError] = useState("");
  const isRenewal = !membership && Boolean(currentMembership);
  const effectiveStart = (draft = form) =>
    draft.activateNow === false
      ? draft.activationDate || draft.startsAt || today
      : draft.startsAt || today;
  const expiryFor = (draft, plan) =>
    plan?.durationDays
      ? format(addDays(new Date(`${effectiveStart(draft)}T00:00:00`), plan.durationDays), "yyyy-MM-dd")
      : "";
  useEffect(() => {
    const renewalPlan = currentMembership
      ? options?.plans?.find(
          (row) => String(row.id) === String(currentMembership.package?.id),
        )
      : null;
    const renewalStart =
      currentMembership?.expiresAt && currentMembership.expiresAt >= today
        ? format(addDays(parseISO(currentMembership.expiresAt), 1), "yyyy-MM-dd")
        : today;
    const next = membership
      ? {
          startsAt: membership.startsAt || today,
          expiresAt: membership.expiresAt || "",
          finalPrice: membership.finalPrice || 0,
          paidAmount: membership.paidAmount || 0,
          debtDueDate: membership.debtDueDate || "",
          paymentMethod: membership.payments?.[0]?.method || "cash",
          bankAccountId: "",
          status: membership.status || "active",
          activationDate: membership.activatedAt || "",
          receipts: [],
        }
      : {
          memberId,
          planId: renewalPlan?.id || "",
          startsAt: renewalStart,
          activateNow: true,
          activationDate: "",
          expiresAt: expiryFor({ startsAt: renewalStart, activateNow: true }, renewalPlan),
          finalPrice: renewalPlan?.price || 0,
          paidAmount: 0,
          debtDueDate: "",
          paymentMethod: "cash",
          bankAccountId: "",
          saleOnlineEmployeeId: "",
          directSaleEmployeeId: "",
          receipts: [],
        };
    setForm(next);
    setInitial(next);
    setLocalError("");
  }, [membership, currentMembership, memberId, options, open, today]);
  const planChange = (id) => {
    const plan = options?.plans?.find((row) => String(row.id) === String(id));
    const next = { ...form, planId: id, finalPrice: plan?.price || 0 };
    setForm({
      ...next,
      expiresAt: expiryFor(next, plan),
    });
  };
  const startChange = (startsAt) => {
    const plan = options?.plans?.find(
      (row) => String(row.id) === String(form.planId),
    );
    const next = { ...form, startsAt };
    setForm({ ...next, expiresAt: !membership && plan?.durationDays && startsAt ? expiryFor(next, plan) : form.expiresAt });
  };
  const activationModeChange = (activateNow) => {
    const plan = options?.plans?.find((row) => String(row.id) === String(form.planId));
    const next = { ...form, activateNow, activationDate: activateNow ? "" : form.activationDate };
    setForm({ ...next, expiresAt: !membership ? expiryFor(next, plan) : form.expiresAt });
  };
  const activationDateChange = (activationDate) => {
    const plan = options?.plans?.find((row) => String(row.id) === String(form.planId));
    const next = { ...form, activationDate };
    setForm({ ...next, expiresAt: !membership ? expiryFor(next, plan) : form.expiresAt });
  };
  const submit = (event) => {
    event.preventDefault();
    if (Number(form.paidAmount) > Number(form.finalPrice)) {
      setLocalError(
        "Số tiền đã thanh toán không thể lớn hơn tổng tiền của gói.",
      );
      return;
    }
    if (form.startsAt && form.expiresAt && form.expiresAt < form.startsAt) {
      setLocalError("Ngày hết hạn phải sau hoặc bằng ngày bắt đầu.");
      return;
    }
    if (
      Number(form.finalPrice) - Number(form.paidAmount) > 0 &&
      !form.debtDueDate
    ) {
      setLocalError("Vui lòng chọn hạn thanh toán cho phần công nợ mới.");
      return;
    }
    if (
      Number(form.paidAmount || 0) > 0 &&
      form.paymentMethod === "bank_transfer" &&
      !form.bankAccountId
    ) {
      setLocalError("Vui lòng chọn tài khoản nhận tiền khi thanh toán chuyển khoản.");
      return;
    }
    const data = new FormData();
    Object.entries(form).forEach(([key, value]) => {
      if (key !== "receipts" && value != null) data.append(key, value);
    });
    form.receipts.forEach((file) => data.append("receipts", file));
    const plan = options?.plans?.find(
      (row) => String(row.id) === String(form.planId),
    );
    onSubmit(data, {
      planName: membership?.package?.name || plan?.name || "Gói tập",
      expiresAt: form.expiresAt,
      paidAmount: Number(form.paidAmount || 0),
    });
  };
  const selectedPlan = options?.plans?.find(
    (row) => String(row.id) === String(form.planId),
  );
  const planOptions = useMemo(
    () => groupedPlanOptions(options?.plans || []),
    [options?.plans],
  );
  const newDebt = Math.max(
    Number(form.finalPrice) - Number(form.paidAmount),
    0,
  );
  const memberName = member?.name || membership?.memberName;
  const memberCode = member?.code;
  return (
    <Modal
      open={open}
      onClose={onClose}
      size="lg"
      title={
        membership
          ? "Cập nhật gói đăng ký"
          : `${isRenewal ? "Gia hạn gói" : "Đăng ký gói"}${memberName ? ` cho ${memberName}` : ""}`
      }
      description={
        membership?.package.name ||
        [memberCode, formatPhone(member?.phone)].filter(Boolean).join(" · ") ||
        "Kiểm tra thông tin trước khi xác nhận"
      }
      dirty={JSON.stringify(form) !== JSON.stringify(initial)}
    >
      <form onSubmit={submit}>
        <div className="modal-body space-y-5">
          {memberName && !membership && (
            <section className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3">
              <span className="text-[11px] font-semibold uppercase tracking-wide text-blue-600">
                Hội viên
              </span>
              <div className="mt-1 flex flex-wrap items-baseline justify-between gap-2">
                <strong className="text-sm text-slate-950">{memberName}</strong>
                <span className="text-xs text-slate-600">
                  {[memberCode, formatPhone(member?.phone)].filter(Boolean).join(" · ")}
                </span>
              </div>
            </section>
          )}
          {isRenewal && (
            <section className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <span className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                    Gói hiện tại
                  </span>
                  <strong className="mt-1 block text-sm text-slate-950">
                    {currentMembership.package?.name}
                  </strong>
                  <p className="mt-1 text-xs text-slate-500">
                    {shortDate(currentMembership.startsAt)} → {shortDate(currentMembership.expiresAt)}
                  </p>
                </div>
                <span className="rounded-full bg-white px-2.5 py-1 text-xs font-medium text-slate-700 ring-1 ring-slate-200">
                  {statusLabel[currentMembership.status] || currentMembership.status}
                </span>
              </div>
              {Number(currentMembership.debtAmount) > 0 && (
                <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800">
                  Gói hiện tại còn nợ <strong>{money(currentMembership.debtAmount)}</strong>. Khoản này được theo dõi riêng và không cộng vào giao dịch gia hạn mới.
                </div>
              )}
            </section>
          )}
          {!membership && (
            <section className="form-section">
              <h3 className="form-section-title">Gói và thời hạn</h3>
              <div className="form-grid">
                <Field className="form-span" label="Gói tập" required>
                  <SearchableSelect
                    value={form.planId || ""}
                    onChange={planChange}
                    placeholder="Chọn gói tập"
                    searchPlaceholder="Tìm theo tên hoặc danh mục…"
                    options={planOptions}
                  />
                </Field>
                <Field label="Ngày bắt đầu">
                  <DateInput
                    value={form.startsAt || ""}
                    onChange={startChange}
                  />
                </Field>
                <Field
                  label="Ngày hết hạn"
                  hint="Tự động theo ngày kích hoạt; có thể thay đổi."
                >
                  <DateInput
                    value={form.expiresAt || ""}
                    onChange={(expiresAt) => setForm({ ...form, expiresAt })}
                  />
                </Field>
              </div>
              <div className="mt-4 grid gap-2 rounded-md border border-slate-200 bg-slate-50 p-3">
                <label className="flex items-start gap-2 text-xs text-slate-700">
                  <input
                    type="checkbox"
                    className="mt-0.5 h-4 w-4 accent-navy-900"
                    checked={form.activateNow !== false}
                    onChange={(event) => activationModeChange(event.target.checked)}
                  />
                  <span>
                    <strong className="block text-slate-900">Kích hoạt gói ngay</strong>
                    <small className="block text-slate-500">Bỏ chọn nếu khách đăng ký trước và chờ buổi tập đầu tiên.</small>
                  </span>
                </label>
                {form.activateNow === false && (
                  <Field label="Kích hoạt lần đầu tập" hint="Có thể để trống; hệ thống sẽ kích hoạt khi check-in lần đầu.">
                    <DateInput value={form.activationDate || ""} onChange={activationDateChange} />
                  </Field>
                )}
              </div>
            </section>
          )}
          {membership && (
            <div className="form-grid">
              <Field label="Ngày bắt đầu">
                <DateInput value={form.startsAt || ""} onChange={startChange} />
              </Field>
              <Field label="Ngày hết hạn">
                <DateInput
                  value={form.expiresAt || ""}
                  onChange={(expiresAt) => setForm({ ...form, expiresAt })}
                />
              </Field>
            </div>
          )}
          <section className="form-section">
            <h3 className="form-section-title">Thanh toán</h3>
            <div className="form-grid">
              <Field label="Tổng tiền">
                <MoneyInput
                  min="0"
                  value={form.finalPrice || 0}
                  onChange={(finalPrice) => setForm({ ...form, finalPrice })}
                />
              </Field>
              <Field label={membership ? "Đã thanh toán" : "Thanh toán lần này"}>
                <MoneyInput
                  min="0"
                  max={Number(form.finalPrice) || 0}
                  value={form.paidAmount || 0}
                  onChange={(paidAmount) => setForm({ ...form, paidAmount })}
                />
              </Field>
              <div className="flex flex-col justify-center rounded-md bg-slate-50 px-3 py-2">
                <span className="text-[11px] text-slate-500">Còn lại</span>
                <strong
                  className={
                    Number(form.finalPrice) - Number(form.paidAmount) > 0
                      ? "mt-0.5 text-sm text-red-700"
                      : "mt-0.5 text-sm text-emerald-700"
                  }
                >
                  {money(
                    Math.max(
                      Number(form.finalPrice) - Number(form.paidAmount),
                      0,
                    ),
                  )}
                </strong>
              </div>
              {Number(form.finalPrice) - Number(form.paidAmount) > 0 && (
                <Field label="Hạn công nợ">
                  <DateInput
                    value={form.debtDueDate || ""}
                    onChange={(debtDueDate) =>
                      setForm({ ...form, debtDueDate })
                    }
                  />
                </Field>
              )}
              <Field label="Phương thức">
                <Select
                  value={form.paymentMethod || "cash"}
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
                <Field label="Tài khoản nhận" required={form.paymentMethod === "bank_transfer"}>
                  <Select
                    value={form.bankAccountId || ""}
                    onChange={(e) =>
                      setForm({ ...form, bankAccountId: e.target.value })
                    }
                  >
                    <option value="">Chọn tài khoản</option>
                    {options?.bankAccounts?.map((row) => (
                      <option key={row.id} value={row.id}>
                        {row.label}
                      </option>
                    ))}
                  </Select>
                </Field>
              )}
              {!membership && Number(form.paidAmount) > 0 && (
                <Field label="Ảnh phiếu thu">
                  <ReceiptPicker
                    files={form.receipts}
                    onChange={(receipts) => setForm({ ...form, receipts })}
                    disabled={pending}
                  />
                </Field>
              )}
              {membership && (
                <Field label="Trạng thái">
                  <Select
                    value={form.status || "active"}
                    onChange={(e) =>
                      setForm({ ...form, status: e.target.value })
                    }
                  >
                    <option value="active">Hoạt động</option>
                    <option value="pending">Chờ kích hoạt</option>
                    <option value="suspended">Tạm dừng</option>
                    <option value="frozen">Bảo lưu</option>
                    <option value="cancelled">Đã hủy</option>
                  </Select>
                </Field>
              )}
            </div>
          </section>
          {!membership && form.planId && (
            <section className="rounded-lg border border-slate-300 bg-white p-4 shadow-sm">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Xác nhận giao dịch
              </h3>
              <dl className="mt-3 grid grid-cols-2 gap-x-5 gap-y-3 text-xs max-[540px]:grid-cols-1">
                <div>
                  <dt className="text-slate-500">Hội viên</dt>
                  <dd className="mt-0.5 font-medium text-slate-950">{memberName || "—"}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Gói {isRenewal ? "gia hạn" : "đăng ký"}</dt>
                  <dd className="mt-0.5 font-medium text-slate-950">
                    {selectedPlan?.name || "—"}
                    {selectedPlan?.durationDays ? ` · ${selectedPlan.durationDays} ngày` : ""}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">Thời gian áp dụng</dt>
                  <dd className="mt-0.5 font-medium text-slate-950">
                    {shortDate(form.startsAt)} → {shortDate(form.expiresAt)}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">Kích hoạt</dt>
                  <dd className="mt-0.5 font-medium text-slate-950">
                    {form.activateNow !== false
                      ? "Ngay khi đăng ký"
                      : form.activationDate
                        ? shortDate(form.activationDate)
                        : "Khi check-in lần đầu"}
                  </dd>
                </div>
                <div>
                  <dt className="text-slate-500">Tổng giá trị</dt>
                  <dd className="mt-0.5 font-medium text-slate-950">{money(form.finalPrice)}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Thanh toán lần này</dt>
                  <dd className="mt-0.5 font-medium text-emerald-700">{money(form.paidAmount)}</dd>
                </div>
                <div>
                  <dt className="text-slate-500">Công nợ mới</dt>
                  <dd className={`mt-0.5 font-medium ${newDebt ? "text-red-700" : "text-emerald-700"}`}>
                    {money(newDebt)}{newDebt && form.debtDueDate ? ` · hạn ${shortDate(form.debtDueDate)}` : ""}
                  </dd>
                </div>
              </dl>
            </section>
          )}
          {(localError || error) && (
            <div className="inline-error">{localError || error}</div>
          )}
        </div>
        <div className="form-actions">
          <Button data-modal-close variant="secondary" onClick={onClose}>
            Hủy
          </Button>
          <Button
            type="submit"
            loading={pending}
            loadingText="Đang lưu…"
            disabled={!membership && !form.planId}
          >
            {membership
              ? "Lưu thay đổi"
              : isRenewal
                ? "Xác nhận gia hạn"
                : "Xác nhận đăng ký"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
