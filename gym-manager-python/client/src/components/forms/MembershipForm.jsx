import { useEffect, useState } from "react";
import { addDays, format } from "date-fns";
import { Button } from "../ui/Button";
import { Field, Input, Select } from "../ui/Form";
import { Modal } from "../ui/Modal";
import { SearchableSelect } from "../ui/SearchableSelect";
import { money } from "../../utils/format";

export function MembershipForm({
  memberId,
  membership,
  options,
  open,
  onClose,
  onSubmit,
  pending,
  error,
}) {
  const today = format(new Date(), "yyyy-MM-dd");
  const [form, setForm] = useState({});
  useEffect(() => {
    const plan = options?.plans?.[0];
    setForm(
      membership
        ? {
            startsAt: membership.startsAt || today,
            expiresAt: membership.expiresAt || "",
            finalPrice: membership.finalPrice || 0,
            paidAmount: membership.paidAmount || 0,
            debtDueDate: membership.debtDueDate || "",
            paymentMethod: membership.payments?.[0]?.method || "cash",
            bankAccountId: "",
            status: membership.status || "active",
            receipt: null,
          }
        : {
            memberId,
            planId: plan?.id || "",
            startsAt: today,
            expiresAt: plan?.durationDays
              ? format(addDays(new Date(), plan.durationDays), "yyyy-MM-dd")
              : "",
            finalPrice: plan?.price || 0,
            paidAmount: 0,
            debtDueDate: "",
            paymentMethod: "cash",
            bankAccountId: "",
            saleOnlineEmployeeId: "",
            directSaleEmployeeId: "",
            receipt: null,
          },
    );
  }, [membership, memberId, options, open]);
  const planChange = (id) => {
    const plan = options?.plans?.find((row) => String(row.id) === String(id));
    setForm({
      ...form,
      planId: id,
      finalPrice: plan?.price || 0,
      expiresAt: plan?.durationDays
        ? format(
            addDays(new Date(form.startsAt || today), plan.durationDays),
            "yyyy-MM-dd",
          )
        : "",
    });
  };
  const submit = (event) => {
    event.preventDefault();
    const data = new FormData();
    Object.entries(form).forEach(
      ([key, value]) => value != null && data.append(key, value),
    );
    onSubmit(data);
  };
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={membership ? "Cập nhật gói đăng ký" : "Đăng ký / gia hạn gói"}
      description={
        membership?.package.name || "Thông tin hội viên đã được điền sẵn"
      }
      size="lg"
    >
      <form onSubmit={submit}>
        <div className="modal-body space-y-5">
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
                    options={
                      options?.plans?.map((row) => ({
                        value: row.id,
                        label: row.name,
                        meta: `${row.category} · ${money(row.price)} · ${row.durationDays} ngày`,
                      })) || []
                    }
                  />
                </Field>
                <Field label="Ngày bắt đầu">
                  <Input
                    type="date"
                    value={form.startsAt || ""}
                    onChange={(e) =>
                      setForm({ ...form, startsAt: e.target.value })
                    }
                  />
                </Field>
                <Field label="Ngày hết hạn">
                  <Input
                    type="date"
                    value={form.expiresAt || ""}
                    onChange={(e) =>
                      setForm({ ...form, expiresAt: e.target.value })
                    }
                  />
                </Field>
              </div>
            </section>
          )}
          {membership && (
            <div className="form-grid">
              <Field label="Ngày bắt đầu">
                <Input
                  type="date"
                  value={form.startsAt || ""}
                  onChange={(e) =>
                    setForm({ ...form, startsAt: e.target.value })
                  }
                />
              </Field>
              <Field label="Ngày hết hạn">
                <Input
                  type="date"
                  value={form.expiresAt || ""}
                  onChange={(e) =>
                    setForm({ ...form, expiresAt: e.target.value })
                  }
                />
              </Field>
            </div>
          )}
          <section className="form-section">
            <h3 className="form-section-title">Thanh toán</h3>
            <div className="form-grid">
              <Field label="Tổng tiền">
                <Input
                  type="number"
                  min="0"
                  value={form.finalPrice || 0}
                  onChange={(e) =>
                    setForm({ ...form, finalPrice: e.target.value })
                  }
                />
              </Field>
              <Field label="Đã thanh toán">
                <Input
                  type="number"
                  min="0"
                  value={form.paidAmount || 0}
                  onChange={(e) =>
                    setForm({ ...form, paidAmount: e.target.value })
                  }
                />
              </Field>
              <Field label="Hạn công nợ">
                <Input
                  type="date"
                  value={form.debtDueDate || ""}
                  onChange={(e) =>
                    setForm({ ...form, debtDueDate: e.target.value })
                  }
                />
              </Field>
              <Field label="Phương thức">
                <Select
                  value={form.paymentMethod || "cash"}
                  onChange={(e) =>
                    setForm({ ...form, paymentMethod: e.target.value })
                  }
                >
                  <option value="cash">Tiền mặt</option>
                  <option value="bank_transfer">Chuyển khoản</option>
                  <option value="card">Thẻ</option>
                </Select>
              </Field>
              <Field label="Tài khoản nhận">
                <Select
                  value={form.bankAccountId || ""}
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
              <Field label="Ảnh phiếu thu">
                <Input
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  onChange={(e) =>
                    setForm({ ...form, receipt: e.target.files[0] })
                  }
                />
              </Field>
              {membership && (
                <Field label="Trạng thái">
                  <Select
                    value={form.status || "active"}
                    onChange={(e) =>
                      setForm({ ...form, status: e.target.value })
                    }
                  >
                    <option value="active">Hoạt động</option>
                    <option value="frozen">Bảo lưu</option>
                    <option value="cancelled">Tạm ngừng</option>
                  </Select>
                </Field>
              )}
            </div>
          </section>
          {error && <div className="inline-error">{error}</div>}
        </div>
        <div className="form-actions">
          <Button variant="secondary" onClick={onClose}>
            Hủy
          </Button>
          <Button type="submit" disabled={pending}>
            {pending
              ? "Đang lưu…"
              : membership
                ? "Lưu thay đổi"
                : "Xác nhận đăng ký"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
