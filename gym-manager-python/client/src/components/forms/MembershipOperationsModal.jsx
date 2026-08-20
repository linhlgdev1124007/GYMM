import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { addDays, differenceInCalendarDays, format } from "date-fns";
import { ArrowRightLeft, CalendarClock, CirclePause, PackageOpen, PlayCircle, ShieldAlert } from "lucide-react";
import { api } from "../../services/api";
import { Modal } from "../ui/Modal";
import { Button } from "../ui/Button";
import { Field, Select, Textarea } from "../ui/Form";
import { DateInput, MoneyInput } from "../ui/SmartInputs";
import { SearchableSelect } from "../ui/SearchableSelect";
import { money, shortDate } from "../../utils/format";

const today = () => format(new Date(), "yyyy-MM-dd");
const nextDay = (value) => format(addDays(new Date(`${value || today()}T00:00:00`), 1), "yyyy-MM-dd");
const ADJUSTABLE_STATUSES = ["active", "pending", "frozen", "suspended", "expired"];

function freezeCompensationDays(membership, startsAt, endsAt) {
  if (!membership?.startsAt || !membership?.expiresAt || !startsAt || !endsAt) return 0;
  if (endsAt <= membership.startsAt) return 0;
  if (startsAt >= membership.expiresAt) return 0;
  const effectiveStart = startsAt > membership.startsAt ? startsAt : membership.startsAt;
  return Math.max(differenceInCalendarDays(new Date(`${endsAt}T00:00:00`), new Date(`${effectiveStart}T00:00:00`)), 0);
}

export function MembershipOperationsModal({ membership, memberships = [], memberId, options, open, initialAction, onClose, onSubmit, pending, error }) {
  const [action, setAction] = useState("freeze");
  const [form, setForm] = useState({});
  const adjustableMemberships = useMemo(
    () =>
      (memberships.length ? memberships : membership ? [membership] : [])
        .filter((row) => ADJUSTABLE_STATUSES.includes(row.status) && row.expiresAt),
    [memberships, membership],
  );
  const members = useQuery({
    queryKey: ["transfer-candidates"],
    queryFn: () => api("/api/members?pageSize=100&sort=name"),
    enabled: open && action === "transfer",
    staleTime: 60_000,
  });
  useEffect(() => {
    const eligible = (memberships.length ? memberships : membership ? [membership] : [])
      .filter((row) => ADJUSTABLE_STATUSES.includes(row.status) && row.expiresAt);
    setForm({
      startsAt: today(),
      endsAt: nextDay(today()),
      targetMemberId: "",
      membershipId: initialAction === "adjust_days" ? eligible[0]?.id || membership?.id || "" : membership?.id || "",
      planId: "",
      finalPrice: membership?.finalPrice || 0,
      expiresAt: membership?.expiresAt || "",
      debtDueDate: membership?.debtDueDate || "",
      overpaymentPolicy: "keep_credit",
      refundAt: today(),
      refundMethod: "cash",
      refundBankAccountId: "",
      days: "",
      effectiveAt: today(),
      reason: "",
    });
    setAction(initialAction || (["pending", "suspended", "frozen"].includes(membership?.status) ? "activate" : "freeze"));
  }, [membership?.id, memberships, open, initialAction]);
  useEffect(() => {
    if (action === "adjust_days" && adjustableMemberships.length && !adjustableMemberships.some((row) => String(row.id) === String(form.membershipId))) {
      setForm((current) => ({ ...current, membershipId: adjustableMemberships[0].id }));
    }
  }, [action, adjustableMemberships, form.membershipId]);
  const targetMembership = action === "adjust_days"
    ? adjustableMemberships.find((row) => String(row.id) === String(form.membershipId)) || membership
    : membership;
  const plan = options?.plans?.find((row) => String(row.id) === String(form.planId));
  const enteredFreezeDays = form.startsAt && form.endsAt
    ? Math.max(differenceInCalendarDays(new Date(`${form.endsAt}T00:00:00`), new Date(`${form.startsAt}T00:00:00`)), 0)
    : 0;
  const freezeDays = freezeCompensationDays(targetMembership, form.startsAt, form.endsAt);
  const compensatedExpiry = targetMembership?.expiresAt && freezeDays
    ? format(addDays(new Date(`${targetMembership.expiresAt}T00:00:00`), freezeDays), "yyyy-MM-dd")
    : targetMembership?.expiresAt;
  const candidates = useMemo(
    () =>
      (members.data?.items || [])
        .filter((row) => String(row.id) !== String(memberId))
        .map((row) => ({ value: row.id, label: row.name, meta: `${row.code} · ${row.phone || "Chưa có SĐT"}${row.membership ? " · Đang có gói" : ""}` })),
    [members.data, memberId],
  );
  if (!membership) return null;
  const submit = (event) => {
    event.preventDefault();
    if (action === "freeze") {
      onSubmit({ action, payload: { startsAt: form.startsAt, endsAt: form.endsAt, reason: form.reason } });
      return;
    }
    onSubmit({
      action,
      membershipId: action === "adjust_days" ? form.membershipId : undefined,
      payload: {
        action,
        reason: form.reason,
        effectiveAt: form.effectiveAt,
        ...(action === "activate" ? { activatedAt: form.effectiveAt } : {}),
        ...(action === "suspend" ? { suspendedAt: form.effectiveAt } : {}),
        ...(action === "transfer" ? { targetMemberId: form.targetMemberId } : {}),
        ...(action === "adjust_days" ? { days: form.days } : {}),
        ...(action === "change" || action === "upgrade"
          ? {
              planId: form.planId,
              finalPrice: form.finalPrice,
              expiresAt: form.expiresAt,
              debtDueDate: form.debtDueDate,
              overpaymentPolicy: form.overpaymentPolicy,
              refundAt: form.refundAt,
              refundMethod: form.refundMethod,
              refundBankAccountId: form.refundBankAccountId,
            }
          : {}),
      },
    });
  };
  const paidAmount = Number(membership?.paidAmount || 0);
  const newPrice = Number(form.finalPrice || 0);
  const projectedDebt = Math.max(newPrice - paidAmount, 0);
  const projectedOverpaid = Math.max(paidAmount - newPrice, 0);
  const valid = String(form.reason || "").trim() && (
    (action === "freeze" && enteredFreezeDays > 0) ||
    action === "activate" ||
    action === "suspend" ||
    (action === "adjust_days" && adjustableMemberships.some((row) => String(row.id) === String(form.membershipId)) && Number(form.days || 0) !== 0) ||
    (action === "transfer" && form.targetMemberId) ||
    ((action === "change" || action === "upgrade") && form.planId && (!projectedDebt || form.debtDueDate) && (!projectedOverpaid || form.overpaymentPolicy) && (form.overpaymentPolicy !== "external_refund" || (form.refundAt && (form.refundMethod !== "bank_transfer" || form.refundBankAccountId)))) ||
    action === "cancel"
  );
  return (
    <Modal open={open} onClose={onClose} title="Quản lý vòng đời gói" description={`${targetMembership?.package.name || membership.package.name} · ${targetMembership?.code || membership.code}`} size="lg" dirty={!!form.reason || !!form.targetMemberId || !!form.planId || !!form.days}>
      <form onSubmit={submit}>
        <div className="modal-body space-y-5">
          <div className="membership-command-summary">
            <div><span>Thời hạn hiện tại</span><strong>{shortDate(targetMembership?.startsAt)} → {shortDate(targetMembership?.expiresAt)}</strong></div>
            <div><span>Tài chính</span><strong>{money(targetMembership?.paidAmount)} đã thu · {money(targetMembership?.debtAmount)} nợ</strong></div>
          </div>
          <Field label="Nghiệp vụ cần thực hiện" required>
            <Select value={action} onChange={(event) => setAction(event.target.value)}>
              <option value="activate">Kích hoạt lần đầu tập</option>
              <option value="suspend">Tạm dừng gói</option>
              <option value="freeze">Bảo lưu và cộng bù thời hạn</option>
              <option value="adjust_days">Cộng / trừ ngày</option>
              <option value="transfer">Chuyển nhượng sang hội viên khác</option>
              <option value="upgrade">Nâng cấp gói</option>
              <option value="change">Đổi gói</option>
              <option value="cancel">Hủy dịch vụ và inactive hội viên</option>
            </Select>
          </Field>
          {action === "activate" && (
            <section className="operation-panel">
              <div className="operation-heading"><PlayCircle size={17} /><div><strong>Kích hoạt lần đầu tập</strong><span>Chuyển gói chờ kích hoạt/tạm dừng sang đang hoạt động và ghi nhận ngày kích hoạt.</span></div></div>
            </section>
          )}
          {action === "suspend" && (
            <section className="operation-panel">
              <div className="operation-heading"><CirclePause size={17} /><div><strong>Tạm dừng gói</strong><span>Dùng khi kích hoạt nhầm. Khi kích hoạt lại, hệ thống cộng bù số ngày tạm dừng vào hạn gói.</span></div></div>
            </section>
          )}
          {action === "freeze" && (
            <section className="operation-panel">
              <div className="operation-heading"><CalendarClock size={17} /><div><strong>Bảo lưu gói</strong><span>Thời hạn được cộng bù tự động theo số ngày bảo lưu.</span></div></div>
              <div className="form-grid">
                <Field label="Bắt đầu" required><DateInput value={form.startsAt} onChange={(startsAt) => setForm({ ...form, startsAt, endsAt: form.endsAt <= startsAt ? nextDay(startsAt) : form.endsAt })} /></Field>
                <Field label="Kết thúc" required><DateInput min={nextDay(form.startsAt)} value={form.endsAt} onChange={(endsAt) => setForm({ ...form, endsAt })} /></Field>
              </div>
              <div className="compensation-preview"><span>Cộng bù <strong>{freezeDays} ngày</strong></span><ArrowRightLeft size={14} /><span>Hạn mới <strong>{shortDate(compensatedExpiry)}</strong></span></div>
            </section>
          )}
          {action === "adjust_days" && (
            <section className="operation-panel">
              <div className="operation-heading"><CalendarClock size={17} /><div><strong>Cộng / trừ ngày</strong><span>Điều chỉnh trực tiếp ngày hết hạn gói và lưu lịch sử đối soát. Gói hết hạn sẽ tự hoạt động lại nếu hạn mới từ hôm nay trở đi.</span></div></div>
              <Field label="Gói áp dụng" required>
                <Select value={form.membershipId || ""} onChange={(event) => setForm({ ...form, membershipId: event.target.value })}>
                  {adjustableMemberships.map((row) => (
                    <option key={row.id} value={row.id}>
                      {row.package.name} · {shortDate(row.startsAt)} → {shortDate(row.expiresAt)}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Số ngày" required hint="Nhập số dương để cộng, số âm để trừ.">
                <input className="input tabular-nums" type="number" step="1" value={form.days} onChange={(event) => setForm({ ...form, days: event.target.value })} />
              </Field>
              {targetMembership?.expiresAt && Number(form.days || 0) !== 0 && (
                <div className="compensation-preview">
                  <span>Hạn hiện tại <strong>{shortDate(targetMembership.expiresAt)}</strong></span>
                  <ArrowRightLeft size={14} />
                  <span>Hạn mới <strong>{shortDate(format(addDays(new Date(`${targetMembership.expiresAt}T00:00:00`), Number(form.days || 0)), "yyyy-MM-dd"))}</strong></span>
                </div>
              )}
            </section>
          )}
          {action === "transfer" && (
            <section className="operation-panel">
              <div className="operation-heading"><ArrowRightLeft size={17} /><div><strong>Chuyển nhượng quyền sử dụng</strong><span>Lịch sử thanh toán vẫn thuộc người thanh toán ban đầu.</span></div></div>
              <Field label="Hội viên nhận" required>
                <SearchableSelect value={form.targetMemberId} onChange={(targetMemberId) => setForm({ ...form, targetMemberId })} options={candidates} placeholder="Chọn hội viên nhận chuyển nhượng" searchPlaceholder="Tìm tên, mã hoặc số điện thoại…" />
              </Field>
            </section>
          )}
          {(action === "change" || action === "upgrade") && (
            <section className="operation-panel">
              <div className="operation-heading"><PackageOpen size={17} /><div><strong>{action === "upgrade" ? "Nâng cấp" : "Đổi"} gói tập</strong><span>Giá gói, công nợ và phần tiền dư sẽ được tính lại theo lựa chọn xử lý bên dưới.</span></div></div>
              <div className="form-grid">
                <Field className="form-span" label="Gói mới" required>
                  <SearchableSelect value={form.planId} onChange={(planId) => {
                    const next = options?.plans?.find((row) => String(row.id) === String(planId));
                    setForm({ ...form, planId, finalPrice: next?.price || 0 });
                  }} options={(options?.plans || []).filter((row) => row.id !== membership.package.id).map((row) => ({ value: row.id, label: row.name, meta: `${row.category} · ${money(row.price)} · ${row.durationDays} ngày` }))} placeholder="Chọn gói thay thế" />
                </Field>
                <Field label="Giá gói mới"><MoneyInput min={0} value={form.finalPrice} onChange={(finalPrice) => setForm({ ...form, finalPrice })} /></Field>
                <Field label="Ngày hết hạn"><DateInput value={form.expiresAt} onChange={(expiresAt) => setForm({ ...form, expiresAt })} /></Field>
                {projectedDebt > 0 && (
                  <Field label="Hạn công nợ mới" required>
                    <DateInput value={form.debtDueDate || ""} onChange={(debtDueDate) => setForm({ ...form, debtDueDate })} />
                  </Field>
                )}
                {projectedOverpaid > 0 && (
                  <Field className="form-span" label="Xử lý tiền dư" required>
                    <Select value={form.overpaymentPolicy || "keep_credit"} onChange={(event) => setForm({ ...form, overpaymentPolicy: event.target.value })}>
                      <option value="keep_credit">Giữ dư trên hồ sơ để đối soát sau</option>
                      <option value="external_refund">Đã/ sẽ hoàn tiền ngoài hệ thống</option>
                      <option value="reduce_paid">Điều chỉnh số đã thu về bằng giá gói mới</option>
                    </Select>
                  </Field>
                )}
                {projectedOverpaid > 0 && form.overpaymentPolicy === "external_refund" && (
                  <>
                    <Field label="Ngày hoàn tiền" required>
                      <DateInput value={form.refundAt || ""} onChange={(refundAt) => setForm({ ...form, refundAt })} />
                    </Field>
                    <Field label="Phương thức hoàn">
                      <Select value={form.refundMethod || "cash"} onChange={(event) => setForm({ ...form, refundMethod: event.target.value, refundBankAccountId: event.target.value === "cash" ? "" : form.refundBankAccountId })}>
                        <option value="cash">Tiền mặt</option>
                        <option value="bank_transfer">Chuyển khoản</option>
                        <option value="card">Thẻ</option>
                      </Select>
                    </Field>
                    {form.refundMethod !== "cash" && (
                      <Field className="form-span" label="Tài khoản hoàn" required={form.refundMethod === "bank_transfer"}>
                        <Select value={form.refundBankAccountId || ""} onChange={(event) => setForm({ ...form, refundBankAccountId: event.target.value })}>
                          <option value="">Chọn tài khoản</option>
                          {options?.bankAccounts?.map((row) => (
                            <option key={row.id} value={row.id}>{row.label}</option>
                          ))}
                        </Select>
                      </Field>
                    )}
                  </>
                )}
              </div>
              {plan && (
                <div className="compensation-preview">
                  <span>Gói mới <strong>{plan.name}</strong></span>
                  <span>Đã thu <strong>{money(paidAmount)}</strong></span>
                  <span>Công nợ dự kiến <strong>{money(projectedDebt)}</strong></span>
                  {projectedOverpaid > 0 && <span>Tiền dư <strong>{money(projectedOverpaid)}</strong></span>}
                </div>
              )}
            </section>
          )}
          {action === "cancel" && (
            <div className="destructive-notice"><ShieldAlert size={18} /><div><strong>Hủy dịch vụ và inactive hội viên</strong><p>Thao tác không tự tạo hoàn tiền. Gói này sẽ bị hủy và hội viên được chuyển sang trạng thái inactive ngay cả khi còn gói khác.</p></div></div>
          )}
          {action !== "freeze" && action !== "adjust_days" && (
            <Field label={action === "activate" ? "Ngày kích hoạt" : action === "suspend" ? "Ngày tạm dừng" : "Ngày hiệu lực"}>
              <DateInput min={action === "suspend" ? today() : undefined} value={form.effectiveAt} onChange={(effectiveAt) => setForm({ ...form, effectiveAt })} />
            </Field>
          )}
          <Field label="Lý do / căn cứ" required hint="Được lưu trong lịch sử gói và Audit Log">
            <Textarea rows={3} value={form.reason} onChange={(event) => setForm({ ...form, reason: event.target.value })} placeholder="Ví dụ: Yêu cầu của hội viên ngày…" />
          </Field>
          {error && <div className="inline-error">{error}</div>}
        </div>
        <div className="form-actions">
          <Button data-modal-close variant="secondary" onClick={onClose}>Đóng</Button>
          <Button type="submit" variant={action === "cancel" ? "danger" : "primary"} loading={pending} loadingText="Đang xử lý…" disabled={!valid}>
            {action === "activate" ? "Kích hoạt gói" : action === "suspend" ? "Tạm dừng gói" : action === "freeze" ? "Xác nhận bảo lưu" : action === "adjust_days" ? "Điều chỉnh ngày" : action === "transfer" ? "Xác nhận chuyển nhượng" : action === "cancel" ? "Hủy dịch vụ" : action === "upgrade" ? "Nâng cấp gói" : "Đổi gói"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
