import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Pencil, Plus, ShieldCheck } from "lucide-react";
import { api } from "../../services/api";
import { notify } from "../../services/notify";
import { PageHeader } from "../../components/common/PageHeader";
import { Button } from "../../components/ui/Button";
import { DataTable } from "../../components/ui/DataTable";
import { Modal } from "../../components/ui/Modal";
import { Field, Input, Select } from "../../components/ui/Form";
import { StatusBadge } from "../../components/ui/StatusBadge";

const blank = { username: "", displayName: "", employeeId: "", role: "receptionist", active: true, password: "" };

export function AccountsPage() {
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState(blank);
  const [error, setError] = useState("");
  const query = useQuery({ queryKey: ["users"], queryFn: () => api("/api/users") });
  useEffect(() => {
    setForm(
      selected
        ? {
            username: selected.username,
            displayName: selected.displayName,
            employeeId: selected.employee?.id || "",
            role: selected.role,
            active: selected.active,
            password: "",
          }
        : blank,
    );
  }, [selected, open]);
  const save = useMutation({
    mutationFn: (payload) =>
      api(selected ? `/api/users/${selected.id}` : "/api/users", {
        method: selected ? "PATCH" : "POST",
        body: payload,
      }),
    onSuccess: (user) => {
      client.invalidateQueries({ queryKey: ["users"] });
      client.invalidateQueries({ queryKey: ["audit-logs"] });
      setOpen(false);
      setSelected(null);
      notify.success(
        selected
          ? `Đã cập nhật tài khoản ${user.username}.`
          : `Đã tạo tài khoản ${user.username}.`,
      );
    },
    onError: (reason) => setError(reason.message),
  });
  const edit = (row) => {
    setSelected(row);
    setError("");
    setOpen(true);
  };
  const employeeOptions = [
    ...(selected?.employee ? [selected.employee] : []),
    ...(query.data?.employees || []),
  ].filter((row, index, rows) => rows.findIndex((item) => item.id === row.id) === index);
  const submit = (event) => {
    event.preventDefault();
    setError("");
    save.mutate({
      username: form.username,
      displayName: form.displayName,
      employeeId: form.employeeId || null,
      role: form.role,
      active: form.active,
      ...(form.password ? { password: form.password } : {}),
    });
  };
  return (
    <>
      <PageHeader
        eyebrow="Bảo mật & phân quyền"
        title="Tài khoản người dùng"
        description="Cấp quyền đăng nhập cho nhân viên và kiểm soát phạm vi nghiệp vụ."
        action={
          <Button onClick={() => { setSelected(null); setError(""); setOpen(true); }}>
            <Plus size={15} /> Tạo tài khoản
          </Button>
        }
      />
      <div className="permission-summary">
        <ShieldCheck size={18} />
        <div><strong>Nguyên tắc quyền tối thiểu</strong><p>Mỗi nhân viên chỉ nên được cấp vai trò đúng với công việc thực tế. Mọi thay đổi đều được ghi Audit Log.</p></div>
      </div>
      <DataTable
        rows={query.data?.items}
        loading={query.isLoading}
        error={query.error}
        onRetry={query.refetch}
        onRowClick={edit}
        columns={[
          {
            key: "account",
            label: "Tài khoản",
            render: (row) => <div><span className="cell-primary">{row.displayName}</span><div className="cell-secondary">@{row.username}</div></div>,
          },
          { key: "employee", label: "Nhân viên liên kết", render: (row) => row.employee?.name || "Tài khoản độc lập" },
          { key: "role", label: "Vai trò", render: (row) => <span className="role-badge">{row.role}</span> },
          { key: "status", label: "Trạng thái", render: (row) => <StatusBadge status={row.active ? "active" : "inactive"} /> },
          { key: "action", label: "", render: (row) => <Button size="sm" variant="ghost" onClick={(event) => { event.stopPropagation(); edit(row); }}><Pencil size={13} /> Chỉnh sửa</Button> },
        ]}
      />
      <Modal
        open={open}
        onClose={() => { setOpen(false); setSelected(null); }}
        title={selected ? "Cập nhật tài khoản" : "Tạo tài khoản nhân viên"}
        description={selected ? `@${selected.username}` : "Thông tin đăng nhập và phạm vi quyền"}
        dirty={JSON.stringify(form) !== JSON.stringify(selected ? { username: selected.username, displayName: selected.displayName, employeeId: selected.employee?.id || "", role: selected.role, active: selected.active, password: "" } : blank)}
      >
        <form onSubmit={submit}>
          <div className="modal-body space-y-4">
            <div className="form-grid">
              <Field label="Nhân viên liên kết" hint="Không bắt buộc">
                <Select value={form.employeeId} onChange={(event) => {
                  const employee = employeeOptions.find((row) => String(row.id) === event.target.value);
                  setForm({ ...form, employeeId: event.target.value, displayName: form.displayName || employee?.name || "" });
                }}>
                  <option value="">Không liên kết</option>
                  {employeeOptions.map((row) => <option key={row.id} value={row.id}>{row.name} · {row.code}</option>)}
                </Select>
              </Field>
              <Field label="Tên hiển thị" required>
                <Input value={form.displayName} onChange={(event) => setForm({ ...form, displayName: event.target.value })} />
              </Field>
              <Field label="Tên đăng nhập" required hint="Chữ thường, số, dấu . _ -">
                <Input disabled={!!selected} autoComplete="off" value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value.toLowerCase() })} />
              </Field>
              <Field label={selected ? "Đặt mật khẩu mới" : "Mật khẩu"} required={!selected} hint={selected ? "Để trống nếu không đổi" : "Tối thiểu 8 ký tự"}>
                <Input type="password" autoComplete="new-password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} />
              </Field>
              <Field className="form-span" label="Vai trò" required>
                <Select value={form.role} onChange={(event) => setForm({ ...form, role: event.target.value })}>
                  {query.data?.roles?.map((role) => <option key={role.value} value={role.value}>{role.label} — {role.description}</option>)}
                </Select>
              </Field>
              {selected && (
                <Field className="form-span" label="Trạng thái">
                  <Select value={form.active ? "active" : "inactive"} onChange={(event) => setForm({ ...form, active: event.target.value === "active" })}>
                    <option value="active">Đang hoạt động</option>
                    <option value="inactive">Khóa đăng nhập</option>
                  </Select>
                </Field>
              )}
            </div>
            {error && <div className="inline-error">{error}</div>}
          </div>
          <div className="form-actions">
            <Button data-modal-close variant="secondary" onClick={() => setOpen(false)}>Hủy</Button>
            <Button type="submit" loading={save.isPending} loadingText="Đang lưu…"><KeyRound size={14} />{selected ? "Lưu tài khoản" : "Tạo tài khoản"}</Button>
          </div>
        </form>
      </Modal>
    </>
  );
}
