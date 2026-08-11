import { useEffect, useState } from "react";
import { Button } from "../ui/Button";
import { Field, Input, Select, Textarea } from "../ui/Form";
import { Modal } from "../ui/Modal";
import { DateOfBirthInput, PhoneInput } from "../ui/SmartInputs";
import { SearchableSelect } from "../ui/SearchableSelect";
import { normalizePhone } from "../../utils/format";

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
  const [initial, setInitial] = useState({});
  const [validation, setValidation] = useState("");
  useEffect(() => {
    if (member) {
      const next = {
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
      };
      setForm(next);
      setInitial(next);
      setValidation("");
    }
  }, [member, open]);
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Chỉnh sửa hội viên"
      description={member?.code}
      dirty={JSON.stringify(form) !== JSON.stringify(initial)}
    >
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!form.name.trim()) {
            setValidation("Họ tên không được để trống.");
            return;
          }
          if (form.phone && normalizePhone(form.phone).length !== 10) {
            setValidation("Số điện thoại cần đủ 10 chữ số.");
            return;
          }
          onSubmit({
            ...form,
            name: form.name.trim(),
            email: form.email.trim(),
          });
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
              <PhoneInput
                value={form.phone || ""}
                onChange={(phone) => setForm({ ...form, phone })}
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
              <DateOfBirthInput
                value={form.dateOfBirth || ""}
                onChange={(dateOfBirth) => setForm({ ...form, dateOfBirth })}
              />
            </Field>
            <Field label="Mã MBS">
              <Input
                value={form.mbsCode || ""}
                onChange={(e) => setForm({ ...form, mbsCode: e.target.value })}
              />
            </Field>
            <Field label="Nhân viên phụ trách">
              <SearchableSelect
                value={form.salesEmployeeId || ""}
                onChange={(salesEmployeeId) =>
                  setForm({ ...form, salesEmployeeId })
                }
                clearable
                placeholder="Chưa phân công"
                searchPlaceholder="Tên hoặc mã nhân viên…"
                options={
                  options?.employees?.map((row) => ({
                    value: row.id,
                    label: row.name,
                    meta: `${row.code} · ${row.title || "Nhân viên"}`,
                  })) || []
                }
              />
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
          {(validation || error) && (
            <div className="inline-error mt-4">{validation || error}</div>
          )}
        </div>
        <div className="form-actions">
          <Button data-modal-close variant="secondary" onClick={onClose}>
            Hủy
          </Button>
          <Button type="submit" loading={pending} loadingText="Đang lưu…">
            Lưu thay đổi
          </Button>
        </div>
      </form>
    </Modal>
  );
}
