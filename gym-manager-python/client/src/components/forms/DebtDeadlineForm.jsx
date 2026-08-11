import { useEffect, useState } from "react";
import { format } from "date-fns";
import { Button } from "../ui/Button";
import { Field } from "../ui/Form";
import { Modal } from "../ui/Modal";
import { money } from "../../utils/format";
import { DateInput } from "../ui/SmartInputs";

export function DebtDeadlineForm({
  membership,
  open,
  onClose,
  onSubmit,
  pending,
  error,
}) {
  const [dueDate, setDueDate] = useState("");
  useEffect(
    () =>
      setDueDate(membership?.debtDueDate || format(new Date(), "yyyy-MM-dd")),
    [membership, open],
  );
  if (!membership) return null;
  const initial = membership?.debtDueDate || format(new Date(), "yyyy-MM-dd");
  return (
    <Modal
      open={open}
      onClose={onClose}
      dirty={dueDate !== initial}
      size="sm"
      title={
        membership.debtDueDate ? "Đổi hạn thanh toán" : "Đặt hạn thanh toán"
      }
      description={`${membership.package.name} · Công nợ ${money(membership.debtAmount)}`}
    >
      <form
        onSubmit={(event) => {
          event.preventDefault();
          onSubmit({ debtDueDate: dueDate });
        }}
      >
        <div className="modal-body">
          <Field label="Hạn thanh toán" required>
            <DateInput autoFocus value={dueDate} onChange={setDueDate} />
          </Field>
          {error && <div className="inline-error mt-4">{error}</div>}
        </div>
        <div className="form-actions">
          <Button data-modal-close variant="secondary" onClick={onClose}>
            Hủy
          </Button>
          <Button
            type="submit"
            loading={pending}
            loadingText="Đang lưu…"
            disabled={!dueDate}
          >
            Lưu hạn thanh toán
          </Button>
        </div>
      </form>
    </Modal>
  );
}
