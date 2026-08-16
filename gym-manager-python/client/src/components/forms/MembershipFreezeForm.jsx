import { useEffect, useMemo, useState } from "react";
import { addDays, differenceInCalendarDays, format } from "date-fns";
import { ArrowRightLeft, CalendarClock } from "lucide-react";
import { Modal } from "../ui/Modal";
import { Button } from "../ui/Button";
import { Field, Textarea } from "../ui/Form";
import { DateInput } from "../ui/SmartInputs";
import { shortDate } from "../../utils/format";

const today = () => format(new Date(), "yyyy-MM-dd");
const nextDay = (value) => format(addDays(new Date(`${value || today()}T00:00:00`), 1), "yyyy-MM-dd");

function compensationDays(membership, startsAt, endsAt) {
  if (!membership?.startsAt || !membership?.expiresAt || !startsAt || !endsAt) return 0;
  if (endsAt <= membership.startsAt) return 0;
  if (startsAt >= membership.expiresAt) return 0;
  const effectiveStart = startsAt > membership.startsAt ? startsAt : membership.startsAt;
  return Math.max(
    differenceInCalendarDays(
      new Date(`${endsAt}T00:00:00`),
      new Date(`${effectiveStart}T00:00:00`),
    ),
    0,
  );
}

export function MembershipFreezeForm({ membership, freeze, open, onClose, onSubmit, pending, error }) {
  const [form, setForm] = useState({ startsAt: today(), endsAt: nextDay(today()), reason: "" });
  useEffect(() => {
    if (!open) return;
    setForm({
      startsAt: freeze?.startsAt || today(),
      endsAt: freeze?.endsAt || nextDay(freeze?.startsAt || today()),
      reason: freeze?.reason || "",
    });
  }, [freeze, open]);
  const days = useMemo(
    () => compensationDays(membership, form.startsAt, form.endsAt),
    [membership, form.startsAt, form.endsAt],
  );
  const valid = form.startsAt && form.endsAt && form.endsAt > form.startsAt && String(form.reason || "").trim();
  return (
    <Modal open={open} onClose={onClose} title="Chỉnh sửa bảo lưu" description={`${membership?.package?.name || ""} · ${membership?.code || ""}`} dirty={!!form.reason}>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit({ startsAt: form.startsAt, endsAt: form.endsAt, reason: form.reason });
        }}
      >
        <div className="modal-body space-y-5">
          <section className="operation-panel">
            <div className="operation-heading"><CalendarClock size={17} /><div><strong>Thời gian bảo lưu</strong><span>Ngày nhập được giữ nguyên; ngày cộng bù tính theo quy tắc bảo lưu hiện tại.</span></div></div>
            <div className="form-grid">
              <Field label="Bắt đầu" required>
                <DateInput value={form.startsAt} onChange={(startsAt) => setForm({ ...form, startsAt, endsAt: form.endsAt <= startsAt ? nextDay(startsAt) : form.endsAt })} />
              </Field>
              <Field label="Kết thúc" required>
                <DateInput min={nextDay(form.startsAt)} value={form.endsAt} onChange={(endsAt) => setForm({ ...form, endsAt })} />
              </Field>
            </div>
            <div className="compensation-preview">
              <span>Cộng bù dự kiến <strong>{days} ngày</strong></span>
              <ArrowRightLeft size={14} />
              <span>Hạn hiện tại <strong>{shortDate(membership?.expiresAt)}</strong></span>
            </div>
          </section>
          <Field label="Lý do / căn cứ" required>
            <Textarea rows={3} value={form.reason} onChange={(event) => setForm({ ...form, reason: event.target.value })} />
          </Field>
          {error && <div className="inline-error">{error}</div>}
        </div>
        <div className="form-actions">
          <Button data-modal-close variant="secondary" onClick={onClose}>Đóng</Button>
          <Button type="submit" loading={pending} loadingText="Đang lưu…" disabled={!valid}>Lưu bảo lưu</Button>
        </div>
      </form>
    </Modal>
  );
}
