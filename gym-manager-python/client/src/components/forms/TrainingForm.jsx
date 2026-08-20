import { useEffect, useState } from "react";
import { format } from "date-fns";
import { Button } from "../ui/Button";
import { Field, Input, Select } from "../ui/Form";
import { Modal } from "../ui/Modal";
import { MultiSearchableSelect } from "../ui/MultiSearchableSelect";
import { SearchableSelect } from "../ui/SearchableSelect";
import { DateInput, MoneyInput, NumberUnitInput, TimeInput } from "../ui/SmartInputs";
import { money } from "../../utils/format";

export const weekdays = [
  "Thứ 2",
  "Thứ 3",
  "Thứ 4",
  "Thứ 5",
  "Thứ 6",
  "Thứ 7",
  "Chủ nhật",
];

export const emptyTrainingForm = () => ({
  memberId: "",
  packageName: "",
  coachIds: [],
  type: "1:1",
  totalSessions: 12,
  startsAt: format(new Date(), "yyyy-MM-dd"),
  expiresAt: "",
  finalPrice: 0,
  paidAmount: 0,
  paidAt: format(new Date(), "yyyy-MM-dd"),
  paymentMethod: "cash",
  bankAccountId: "",
  debtInstallments: [],
  schedule: [],
  status: "active",
});

function enrollmentForm(enrollment) {
  if (!enrollment) return emptyTrainingForm();
  const legacySchedule = (enrollment.scheduleDays || []).map((day) => ({
    day,
    time: enrollment.scheduleTime || "07:00",
  }));
  return {
    memberId: enrollment.memberId || "",
    packageName: enrollment.packageName || "",
    coachIds: (
      enrollment.coaches || (enrollment.coach ? [enrollment.coach] : [])
    ).map((coach) => String(coach.id)),
    type: enrollment.type,
    totalSessions: enrollment.totalSessions,
    remainingSessions: enrollment.remainingSessions,
    startsAt: enrollment.startsAt || "",
    expiresAt: enrollment.expiresAt || "",
    finalPrice: enrollment.finalPrice || 0,
    paidAmount: enrollment.paidAmount || 0,
    paidAt: format(new Date(), "yyyy-MM-dd"),
    paymentMethod: "cash",
    bankAccountId: "",
    debtInstallments: enrollment.debtInstallments || [],
    schedule: enrollment.schedule || legacySchedule,
    status: enrollment.status,
  };
}

export function TrainingFields({ form, setForm, options, editing = false, coachMode = false, requireMember = false, memberOptions = [] }) {
  const coaches =
    options?.employees?.filter((row) => row.isPtRole) ||
    [];
  const coachOptions = coaches.map((row) => ({
    value: row.id,
    label: row.name,
    meta: row.title,
  }));
  const sessionPreset = [12, 24, 36].includes(Number(form.totalSessions))
    ? String(form.totalSessions)
    : "other";
  const selectedDays = new Set((form.schedule || []).map((slot) => slot.day));
  const remainingDebt = Math.max(Number(form.finalPrice || 0) - Number(form.paidAmount || 0), 0);
  const debtTotal = (form.debtInstallments || []).reduce((sum, row) => sum + Number(row.amount || 0), 0);
  const setDebtInstallment = (index, patch) =>
    setForm({
      ...form,
      debtInstallments: (form.debtInstallments || []).map((row, rowIndex) =>
        rowIndex === index ? { ...row, ...patch } : row,
      ),
    });
  const addDebtInstallment = () =>
    setForm({
      ...form,
      debtInstallments: [
        ...(form.debtInstallments || []),
        { amount: Math.max(remainingDebt - debtTotal, 0), dueDate: form.expiresAt || form.startsAt || format(new Date(), "yyyy-MM-dd"), note: "" },
      ],
    });
  const toggleDay = (day) =>
    setForm({
      ...form,
      schedule: selectedDays.has(day)
        ? form.schedule.filter((slot) => slot.day !== day)
        : weekdays
            .filter((weekday) => selectedDays.has(weekday) || weekday === day)
            .map(
              (weekday) =>
                form.schedule.find((slot) => slot.day === weekday) || {
                  day: weekday,
                  time: "07:00",
                },
            ),
    });
  const setSlotTime = (day, time) =>
    setForm({
      ...form,
      schedule: form.schedule.map((slot) =>
        slot.day === day ? { ...slot, time } : slot,
      ),
    });

  return (
    <>
      <div className="form-grid">
        {!editing && requireMember && !coachMode && (
          <Field className="form-span" label="Hội viên" required>
            <SearchableSelect
              value={form.memberId || ""}
              onChange={(memberId) => setForm({ ...form, memberId })}
              options={memberOptions}
              placeholder="Chọn hội viên đã có"
              searchPlaceholder="Tìm tên, mã hoặc số điện thoại..."
            />
          </Field>
        )}
        {!coachMode && (
          <Field className="form-span" label="Gói PT/BT">
            <Input
              value={form.packageName || ""}
              onChange={(event) => setForm({ ...form, packageName: event.target.value })}
              placeholder="Ví dụ: PT Kids 12 buổi"
            />
          </Field>
        )}
        {!coachMode && <Field label="Hình thức">
          <Select
            value={form.type || "1:1"}
            onChange={(event) => setForm({ ...form, type: event.target.value })}
          >
            <option>1:1</option>
            <option>1:2</option>
            <option>1:3</option>
          </Select>
        </Field>}
        {!coachMode && <Field
          label="Coach phụ trách"
          hint="Không bắt buộc · có thể phân công sau."
        >
          <MultiSearchableSelect
            values={form.coachIds || []}
            onChange={(coachIds) => setForm({ ...form, coachIds })}
            options={coachOptions}
            ariaLabel="Chọn Coach phụ trách"
          />
        </Field>}
        {!coachMode && <Field label="Tổng số buổi">
          <Select
            value={sessionPreset}
            onChange={(event) =>
              setForm({
                ...form,
                totalSessions:
                  event.target.value === "other"
                    ? 1
                    : Number(event.target.value),
              })
            }
          >
            <option value="12">12 buổi</option>
            <option value="24">24 buổi</option>
            <option value="36">36 buổi</option>
            <option value="other">Khác</option>
          </Select>
        </Field>}
        {!coachMode && sessionPreset === "other" && (
          <Field label="Số buổi khác">
            <NumberUnitInput
              min="1"
              unit="buổi"
              value={form.totalSessions || 1}
              onChange={(totalSessions) =>
                setForm({ ...form, totalSessions: Number(totalSessions) })
              }
            />
          </Field>
        )}
        {editing && (
          <Field label="Số buổi còn lại">
            <NumberUnitInput
              min="0"
              unit="buổi"
              value={form.remainingSessions ?? 0}
              onChange={(remainingSessions) =>
                setForm({ ...form, remainingSessions: Number(remainingSessions) })
              }
            />
          </Field>
        )}
        {!coachMode && <Field label="Ngày bắt đầu">
          <DateInput
            value={form.startsAt || ""}
            onChange={(startsAt) => setForm({ ...form, startsAt })}
          />
        </Field>}
        {!coachMode && <Field label="Ngày hết hạn">
          <DateInput
            value={form.expiresAt || ""}
            onChange={(expiresAt) => setForm({ ...form, expiresAt })}
          />
        </Field>}
        {!coachMode && (
          <>
            <Field label="Giá trị gói PT">
              <MoneyInput min="0" value={form.finalPrice || 0} onChange={(finalPrice) => setForm({ ...form, finalPrice })} />
            </Field>
            <Field label={editing ? "Đã thu PT" : "Thanh toán lần này"}>
              <MoneyInput min="0" max={Number(form.finalPrice || 0)} value={form.paidAmount || 0} onChange={(paidAmount) => setForm({ ...form, paidAmount })} />
            </Field>
            {Number(form.paidAmount || 0) > 0 && (
              <>
                <Field label="Ngày thu tiền">
                  <DateInput value={form.paidAt || ""} onChange={(paidAt) => setForm({ ...form, paidAt })} />
                </Field>
                <Field label="Phương thức">
                  <Select value={form.paymentMethod || "cash"} onChange={(event) => setForm({ ...form, paymentMethod: event.target.value, bankAccountId: event.target.value === "cash" ? "" : form.bankAccountId })}>
                    <option value="cash">Tiền mặt</option>
                    <option value="bank_transfer">Chuyển khoản</option>
                    <option value="card">Thẻ</option>
                  </Select>
                </Field>
                {form.paymentMethod !== "cash" && (
                  <Field className="form-span" label="Tài khoản nhận" required={form.paymentMethod === "bank_transfer"}>
                    <Select value={form.bankAccountId || ""} onChange={(event) => setForm({ ...form, bankAccountId: event.target.value })}>
                      <option value="">Chọn tài khoản</option>
                      {options?.bankAccounts?.map((row) => <option key={row.id} value={row.id}>{row.label}</option>)}
                    </Select>
                  </Field>
                )}
              </>
            )}
          </>
        )}
        {!coachMode && remainingDebt > 0 && (
          <div className="field form-span">
            <span className="field-label">Hạn công nợ PT</span>
            <div className="grid gap-2">
              {(form.debtInstallments || []).map((row, index) => (
                <div key={index} className="grid gap-2 rounded-md border border-slate-200 bg-slate-50 p-2 sm:grid-cols-[1fr_150px_auto]">
                  <MoneyInput min="0" value={row.amount || 0} onChange={(amount) => setDebtInstallment(index, { amount })} />
                  <DateInput value={row.dueDate || ""} onChange={(dueDate) => setDebtInstallment(index, { dueDate })} />
                  <button type="button" className="btn btn-secondary" onClick={() => setForm({ ...form, debtInstallments: form.debtInstallments.filter((_, rowIndex) => rowIndex !== index) })}>Bỏ</button>
                </div>
              ))}
              <button type="button" className="btn btn-secondary w-fit" onClick={addDebtInstallment}>+ Thêm hạn công nợ</button>
            </div>
            <span className={Math.round(debtTotal) === Math.round(remainingDebt) ? "field-hint" : "field-error"}>
              Tổng hạn nợ {money(debtTotal)} / còn nợ {money(remainingDebt)}
            </span>
          </div>
        )}
        <div className="field form-span">
          <span className="field-label">Lịch tập theo thứ</span>
          <div className="flex flex-wrap gap-2">
            {weekdays.map((day) => (
              <button
                key={day}
                type="button"
                onClick={() => toggleDay(day)}
                className={`rounded-md border px-2.5 py-1.5 text-xs ${selectedDays.has(day) ? "border-navy-800 bg-navy-900 text-white" : "border-slate-200 bg-white text-slate-600"}`}
              >
                {day}
              </button>
            ))}
          </div>
          {!!form.schedule?.length && (
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              {form.schedule.map((slot) => (
                <div
                  key={slot.day}
                  className="flex items-center gap-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-2"
                >
                  <span className="min-w-16 text-xs font-medium text-slate-700">
                    {slot.day}
                  </span>
                  <TimeInput
                    value={slot.time || ""}
                    onChange={(time) => setSlotTime(slot.day, time)}
                  />
                </div>
              ))}
            </div>
          )}
          <span className="field-hint">
            Chọn thứ rồi đặt giờ riêng cho từng ngày.
          </span>
        </div>
        {editing && (
          <Field label="Trạng thái">
            <Select
              value={form.status || "active"}
              onChange={(event) => setForm({ ...form, status: event.target.value })}
            >
              <option value="active">Đang tập</option>
              <option value="completed">Hoàn thành</option>
              <option value="inactive">Ngừng</option>
            </Select>
          </Field>
        )}
      </div>
      {!coachMode && !form.coachIds?.length && (
        <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
          Đăng ký sẽ được lưu ở trạng thái chưa phân công Coach để đội ngũ xử lý sau.
        </div>
      )}
    </>
  );
}

export function TrainingForm({
  enrollment,
  options,
  memberOptions = [],
  requireMember = false,
  open,
  onClose,
  onSubmit,
  pending,
  error,
  coachMode = false,
}) {
  const [form, setForm] = useState(emptyTrainingForm);
  const [initial, setInitial] = useState(emptyTrainingForm);
  const [localError, setLocalError] = useState("");
  useEffect(() => {
    const next = enrollmentForm(enrollment);
    setForm(next);
    setInitial(next);
    setLocalError("");
  }, [enrollment, open]);
  const remainingDebt = Math.max(Number(form.finalPrice || 0) - Number(form.paidAmount || 0), 0);
  const debtTotal = (form.debtInstallments || []).reduce((sum, row) => sum + Number(row.amount || 0), 0);
  return (
    <Modal
      open={open}
      onClose={onClose}
      dirty={JSON.stringify(form) !== JSON.stringify(initial)}
      title={coachMode ? "Cập nhật tiến độ PT" : enrollment ? "Chỉnh sửa đăng ký PT" : "Đăng ký PT"}
      description={coachMode ? "Cập nhật lịch tập, số buổi còn lại và trạng thái của khách được phân công." : "Lịch tập có thể đặt một mốc giờ riêng cho từng thứ."}
    >
      <form
        onSubmit={(event) => {
          event.preventDefault();
          if (!enrollment && requireMember && !form.memberId) {
            setLocalError("Vui lòng chọn hội viên đăng ký PT.");
            return;
          }
          if (Number(form.paidAmount || 0) > Number(form.finalPrice || 0)) {
            setLocalError("Số tiền PT đã thanh toán không thể lớn hơn giá trị gói.");
            return;
          }
          if (Number(form.paidAmount || 0) > 0 && form.paymentMethod === "bank_transfer" && !form.bankAccountId) {
            setLocalError("Vui lòng chọn tài khoản nhận tiền khi thanh toán PT chuyển khoản.");
            return;
          }
          if (remainingDebt > 0 && Math.round(debtTotal) !== Math.round(remainingDebt)) {
            setLocalError("Tổng các hạn công nợ PT phải bằng số tiền còn nợ.");
            return;
          }
          if (remainingDebt > 0 && !(form.debtInstallments || []).every((row) => Number(row.amount || 0) > 0 && row.dueDate)) {
            setLocalError("Vui lòng nhập đủ số tiền và ngày hạn cho từng kỳ công nợ PT.");
            return;
          }
          onSubmit(form);
        }}
      >
        <div className="modal-body">
          <TrainingFields
            form={form}
            setForm={setForm}
            options={options}
            editing={!!enrollment}
            coachMode={coachMode}
            requireMember={requireMember}
            memberOptions={memberOptions}
          />
          {(localError || error) && <div className="inline-error mt-4">{localError || error}</div>}
        </div>
        <div className="form-actions">
          <Button data-modal-close type="button" variant="secondary" onClick={onClose}>
            Hủy
          </Button>
          <Button type="submit" loading={pending} loadingText="Đang lưu…">
            {coachMode ? "Lưu cập nhật" : "Lưu đăng ký PT"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
