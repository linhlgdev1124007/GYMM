import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { addDays, differenceInCalendarDays, format } from "date-fns";
import { ArrowRightLeft, CalendarClock, PackageOpen, ShieldAlert } from "lucide-react";
import { api } from "../../services/api";
import { Modal } from "../ui/Modal";
import { Button } from "../ui/Button";
import { Field, Select, Textarea } from "../ui/Form";
import { DateInput, MoneyInput } from "../ui/SmartInputs";
import { SearchableSelect } from "../ui/SearchableSelect";
import { money, shortDate } from "../../utils/format";

const today = () => format(new Date(), "yyyy-MM-dd");

export function MembershipOperationsModal({ membership, memberId, options, open, onClose, onSubmit, pending, error }) {
  const [action, setAction] = useState("freeze");
  const [form, setForm] = useState({});
  const members = useQuery({
    queryKey: ["transfer-candidates"],
    queryFn: () => api("/api/members?pageSize=100&sort=name"),
    enabled: open && action === "transfer",
    staleTime: 60_000,
  });
  useEffect(() => {
    setForm({
      startsAt: today(),
      endsAt: today(),
      targetMemberId: "",
      planId: "",
      finalPrice: membership?.finalPrice || 0,
      expiresAt: membership?.expiresAt || "",
      effectiveAt: today(),
      reason: "",
    });
    setAction("freeze");
  }, [membership?.id, open]);
  const plan = options?.plans?.find((row) => String(row.id) === String(form.planId));
  const freezeDays = form.startsAt && form.endsAt
    ? Math.max(differenceInCalendarDays(new Date(`${form.endsAt}T00:00:00`), new Date(`${form.startsAt}T00:00:00`)) + 1, 0)
    : 0;
  const compensatedExpiry = membership?.expiresAt && freezeDays
    ? format(addDays(new Date(`${membership.expiresAt}T00:00:00`), freezeDays), "yyyy-MM-dd")
    : membership?.expiresAt;
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
      payload: {
        action,
        reason: form.reason,
        effectiveAt: form.effectiveAt,
        ...(action === "transfer" ? { targetMemberId: form.targetMemberId } : {}),
        ...(action === "change" || action === "upgrade"
          ? { planId: form.planId, finalPrice: form.finalPrice, expiresAt: form.expiresAt }
          : {}),
      },
    });
  };
  const valid = String(form.reason || "").trim() && (
    (action === "freeze" && freezeDays > 0) ||
    (action === "transfer" && form.targetMemberId) ||
    ((action === "change" || action === "upgrade") && form.planId) ||
    action === "cancel"
  );
  return (
    <Modal open={open} onClose={onClose} title="Quản lý vòng đời gói" description={`${membership.package.name} · ${membership.code}`} size="lg" dirty={!!form.reason || !!form.targetMemberId || !!form.planId}>
      <form onSubmit={submit}>
        <div className="modal-body space-y-5">
          <div className="membership-command-summary">
            <div><span>Thời hạn hiện tại</span><strong>{shortDate(membership.startsAt)} → {shortDate(membership.expiresAt)}</strong></div>
            <div><span>Tài chính</span><strong>{money(membership.paidAmount)} đã thu · {money(membership.debtAmount)} nợ</strong></div>
          </div>
          <Field label="Nghiệp vụ cần thực hiện" required>
            <Select value={action} onChange={(event) => setAction(event.target.value)}>
              <option value="freeze">Bảo lưu và cộng bù thời hạn</option>
              <option value="transfer">Chuyển nhượng sang hội viên khác</option>
              <option value="upgrade">Nâng cấp gói</option>
              <option value="change">Đổi gói</option>
              <option value="cancel">Hủy gói</option>
            </Select>
          </Field>
          {action === "freeze" && (
            <section className="operation-panel">
              <div className="operation-heading"><CalendarClock size={17} /><div><strong>Bảo lưu gói</strong><span>Thời hạn được cộng bù tự động theo số ngày bảo lưu.</span></div></div>
              <div className="form-grid">
                <Field label="Bắt đầu" required><DateInput min={today()} value={form.startsAt} onChange={(startsAt) => setForm({ ...form, startsAt, endsAt: form.endsAt < startsAt ? startsAt : form.endsAt })} /></Field>
                <Field label="Kết thúc" required><DateInput min={form.startsAt || today()} value={form.endsAt} onChange={(endsAt) => setForm({ ...form, endsAt })} /></Field>
              </div>
              <div className="compensation-preview"><span>Cộng bù <strong>{freezeDays} ngày</strong></span><ArrowRightLeft size={14} /><span>Hạn mới <strong>{shortDate(compensatedExpiry)}</strong></span></div>
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
              <div className="operation-heading"><PackageOpen size={17} /><div><strong>{action === "upgrade" ? "Nâng cấp" : "Đổi"} gói tập</strong><span>Tiền đã thu được giữ nguyên và công nợ sẽ tính lại.</span></div></div>
              <div className="form-grid">
                <Field className="form-span" label="Gói mới" required>
                  <SearchableSelect value={form.planId} onChange={(planId) => {
                    const next = options?.plans?.find((row) => String(row.id) === String(planId));
                    setForm({ ...form, planId, finalPrice: next?.price || 0 });
                  }} options={(options?.plans || []).filter((row) => row.id !== membership.package.id).map((row) => ({ value: row.id, label: row.name, meta: `${row.category} · ${money(row.price)} · ${row.durationDays} ngày` }))} placeholder="Chọn gói thay thế" />
                </Field>
                <Field label="Giá gói mới"><MoneyInput min={membership.paidAmount} value={form.finalPrice} onChange={(finalPrice) => setForm({ ...form, finalPrice })} /></Field>
                <Field label="Ngày hết hạn"><DateInput value={form.expiresAt} onChange={(expiresAt) => setForm({ ...form, expiresAt })} /></Field>
              </div>
              {plan && <div className="compensation-preview"><span>Gói mới <strong>{plan.name}</strong></span><span>Công nợ dự kiến <strong>{money(Math.max(Number(form.finalPrice) - Number(membership.paidAmount), 0))}</strong></span></div>}
            </section>
          )}
          {action === "cancel" && (
            <div className="destructive-notice"><ShieldAlert size={18} /><div><strong>Hủy quyền sử dụng gói</strong><p>Thao tác không tự tạo hoàn tiền và hội viên sẽ không thể dùng gói này để check-in.</p></div></div>
          )}
          {action !== "freeze" && (
            <Field label="Ngày hiệu lực"><DateInput value={form.effectiveAt} onChange={(effectiveAt) => setForm({ ...form, effectiveAt })} /></Field>
          )}
          <Field label="Lý do / căn cứ" required hint="Được lưu trong lịch sử gói và Audit Log">
            <Textarea rows={3} value={form.reason} onChange={(event) => setForm({ ...form, reason: event.target.value })} placeholder="Ví dụ: Yêu cầu của hội viên ngày…" />
          </Field>
          {error && <div className="inline-error">{error}</div>}
        </div>
        <div className="form-actions">
          <Button data-modal-close variant="secondary" onClick={onClose}>Đóng</Button>
          <Button type="submit" variant={action === "cancel" ? "danger" : "primary"} loading={pending} loadingText="Đang xử lý…" disabled={!valid}>
            {action === "freeze" ? "Xác nhận bảo lưu" : action === "transfer" ? "Xác nhận chuyển nhượng" : action === "cancel" ? "Hủy gói" : action === "upgrade" ? "Nâng cấp gói" : "Đổi gói"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
