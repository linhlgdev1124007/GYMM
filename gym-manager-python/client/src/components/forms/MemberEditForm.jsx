import { useEffect, useState } from "react";
import { Button } from "../ui/Button";
import { Field, Input, Select, Textarea } from "../ui/Form";
import { Modal } from "../ui/Modal";

export function MemberEditForm({
  member,
  options,
  open,
  onClose,
  onSubmit,
  pending,
  error,
}) {
  const [form, setForm] = useState({});
  useEffect(() => {
    if (member)
      setForm({
        name: member.name || "",
        phone: member.phone || "",
        email: member.email || "",
        gender: member.gender || "",
        dateOfBirth: member.dateOfBirth || "",
        mbsCode: member.mbsCode || "",
        source: member.source || "",
        salesEmployeeId: member.salesEmployeeId || "",
        status: member.status || "active",
        notes: member.notes || "",
      });
  }, [member, open]);
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Chỉnh sửa hội viên"
      description={member?.code}
      size="lg"
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit(form);
        }}
      >
        <div className="modal-body">
          <div className="form-grid">
            <Field label="Họ tên" required>
              <Input
                value={form.name || ""}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </Field>
            <Field label="Điện thoại">
              <Input
                value={form.phone || ""}
                onChange={(e) => setForm({ ...form, phone: e.target.value })}
              />
            </Field>
            <Field label="Email">
              <Input
                type="email"
                value={form.email || ""}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
              />
            </Field>
            <Field label="Giới tính">
              <Select
                value={form.gender || ""}
                onChange={(e) => setForm({ ...form, gender: e.target.value })}
              >
                <option value="">Chưa chọn</option>
                <option>Nam</option>
                <option>Nữ</option>
                <option>Khác</option>
              </Select>
            </Field>
            <Field label="Ngày sinh">
              <Input
                type="date"
                value={form.dateOfBirth || ""}
                onChange={(e) =>
                  setForm({ ...form, dateOfBirth: e.target.value })
                }
              />
            </Field>
            <Field label="Mã MBS">
              <Input
                value={form.mbsCode || ""}
                onChange={(e) => setForm({ ...form, mbsCode: e.target.value })}
              />
            </Field>
            <Field label="Nhân viên phụ trách">
              <Select
                value={form.salesEmployeeId || ""}
                onChange={(e) =>
                  setForm({ ...form, salesEmployeeId: e.target.value })
                }
              >
                <option value="">Chưa gán</option>
                {options?.employees?.map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Trạng thái">
              <Select
                value={form.status || "active"}
                onChange={(e) => setForm({ ...form, status: e.target.value })}
              >
                <option value="active">Đang hoạt động</option>
                <option value="lead">Tiềm năng</option>
                <option value="frozen">Bảo lưu</option>
                <option value="blocked">Đã khóa</option>
                <option value="inactive">Tạm ngừng</option>
              </Select>
            </Field>
            <Field className="form-span" label="Ghi chú">
              <Textarea
                value={form.notes || ""}
                onChange={(e) => setForm({ ...form, notes: e.target.value })}
              />
            </Field>
          </div>
          {error && <div className="inline-error mt-4">{error}</div>}
        </div>
        <div className="form-actions">
          <Button variant="secondary" onClick={onClose}>
            Hủy
          </Button>
          <Button type="submit" disabled={pending}>
            {pending ? "Đang lưu…" : "Lưu thay đổi"}
          </Button>
        </div>
      </form>
    </Modal>
  );
}
