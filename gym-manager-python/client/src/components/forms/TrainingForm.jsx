import { useEffect, useState } from "react";
import { format } from "date-fns";
import { Button } from "../ui/Button";
import { Field, Select } from "../ui/Form";
import { Modal } from "../ui/Modal";
import { MultiSearchableSelect } from "../ui/MultiSearchableSelect";
import { DateInput, NumberUnitInput, TimeInput } from "../ui/SmartInputs";

const weekdays = [
  "Thứ 2",
  "Thứ 3",
  "Thứ 4",
  "Thứ 5",
  "Thứ 6",
  "Thứ 7",
  "Chủ nhật",
];

export function TrainingForm({
  enrollment,
  options,
  open,
  onClose,
  onSubmit,
  pending,
  error,
}) {
  const [form, setForm] = useState({});
  const [initial, setInitial] = useState({});
  useEffect(() => {
    const next = enrollment
      ? {
          coachIds: (
            enrollment.coaches || (enrollment.coach ? [enrollment.coach] : [])
          ).map((coach) => String(coach.id)),
          type: enrollment.type,
          totalSessions: enrollment.totalSessions,
          remainingSessions: enrollment.remainingSessions,
          startsAt: enrollment.startsAt || "",
          expiresAt: enrollment.expiresAt || "",
          scheduleDays: enrollment.scheduleDays || [],
          scheduleTime: enrollment.scheduleTime || "",
          status: enrollment.status,
        }
      : {
          coachIds: [],
          type: "1:1",
          totalSessions: 12,
          startsAt: format(new Date(), "yyyy-MM-dd"),
          expiresAt: "",
          scheduleDays: [],
          scheduleTime: "",
          status: "active",
        };
    setForm(next);
    setInitial(next);
  }, [enrollment, open]);
  const toggleDay = (day) =>
    setForm({
      ...form,
      scheduleDays: form.scheduleDays.includes(day)
        ? form.scheduleDays.filter((value) => value !== day)
        : [...form.scheduleDays, day],
    });
  const coaches =
    options?.employees?.filter((row) => /coach|pt/i.test(row.title || "")) ||
    [];
  const coachOptions = coaches.map((row) => ({
    value: row.id,
    label: row.name,
    meta: row.title,
  }));
  const sessionPreset = [12, 24, 36].includes(Number(form.totalSessions))
    ? String(form.totalSessions)
    : "other";
  return (
    <Modal
      open={open}
      onClose={onClose}
      dirty={JSON.stringify(form) !== JSON.stringify(initial)}
      title={enrollment ? "Chỉnh sửa đăng ký PT" : "Đăng ký PT"}
      description="Có thể đăng ký trước và phân công một hoặc nhiều Coach sau."
    >
      <form
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit(form);
        }}
      >
        <div className="modal-body">
          <div className="form-grid">
            <Field label="Hình thức">
              <Select
                value={form.type || "1:1"}
                onChange={(event) =>
                  setForm({ ...form, type: event.target.value })
                }
              >
                <option>1:1</option>
                <option>1:2</option>
                <option>1:3</option>
              </Select>
            </Field>
            <Field
              label="Coach phụ trách"
              hint="Không bắt buộc · có thể để trống và phân công sau."
            >
              <MultiSearchableSelect
                values={form.coachIds || []}
                onChange={(coachIds) => setForm({ ...form, coachIds })}
                options={coachOptions}
                ariaLabel="Chọn Coach phụ trách"
              />
            </Field>
            <Field label="Tổng số buổi">
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
            </Field>
            {sessionPreset === "other" && (
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
            {enrollment && (
              <Field label="Số buổi còn lại">
                <NumberUnitInput
                  min="0"
                  unit="buổi"
                  value={form.remainingSessions ?? 0}
                  onChange={(remainingSessions) =>
                    setForm({
                      ...form,
                      remainingSessions: Number(remainingSessions),
                    })
                  }
                />
              </Field>
            )}
            <Field label="Ngày bắt đầu">
              <DateInput
                value={form.startsAt || ""}
                onChange={(startsAt) => setForm({ ...form, startsAt })}
              />
            </Field>
            <Field label="Ngày hết hạn">
              <DateInput
                value={form.expiresAt || ""}
                onChange={(expiresAt) => setForm({ ...form, expiresAt })}
              />
            </Field>
            <Field className="form-span" label="Ngày tập">
              <div className="flex flex-wrap gap-2">
                {weekdays.map((day) => (
                  <button
                    key={day}
                    type="button"
                    onClick={() => toggleDay(day)}
                    className={`rounded-md border px-2.5 py-1.5 text-xs ${form.scheduleDays?.includes(day) ? "border-navy-800 bg-navy-900 text-white" : "border-slate-200 bg-white text-slate-600"}`}
                  >
                    {day}
                  </button>
                ))}
              </div>
            </Field>
            <Field label="Giờ tập" hint="Ưu tiên các mốc 30 phút.">
              <TimeInput
                value={form.scheduleTime || ""}
                onChange={(scheduleTime) => setForm({ ...form, scheduleTime })}
              />
            </Field>
            {enrollment && (
              <Field label="Trạng thái">
                <Select
                  value={form.status || "active"}
                  onChange={(event) =>
                    setForm({ ...form, status: event.target.value })
                  }
                >
                  <option value="active">Đang tập</option>
                  <option value="completed">Hoàn thành</option>
                  <option value="inactive">Ngừng</option>
                </Select>
              </Field>
            )}
          </div>
          {!form.coachIds?.length && (
            <div className="mt-4 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
              Đăng ký sẽ được lưu ở trạng thái chưa phân công Coach để đội ngũ
              xử lý sau.
            </div>
          )}
          {error && <div className="inline-error mt-4">{error}</div>}
        </div>
        <div className="form-actions">
          <Button
            data-modal-close
            type="button"
            variant="secondary"
            onClick={onClose}
          >
            Hủy
          </Button>
          <Button type="submit" disabled={pending}>
            {pending ? "Đang lưu…" : "Lưu đăng ký PT"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
