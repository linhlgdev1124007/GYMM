import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { HelpCircle, KeyRound, Pencil, Plus, ShieldCheck } from "lucide-react";
import { api } from "../../services/api";
import { notify } from "../../services/notify";
import { PageHeader } from "../../components/common/PageHeader";
import { Button } from "../../components/ui/Button";
import { DataTable } from "../../components/ui/DataTable";
import { Modal } from "../../components/ui/Modal";
import { Field, Input, Select } from "../../components/ui/Form";
import { StatusBadge } from "../../components/ui/StatusBadge";

const blank = { username: "", displayName: "", employeeId: "", role: "receptionist", active: true, password: "" };

const roleColumns = [
  ["admin", "Admin"],
  ["manager", "Manager"],
  ["receptionist", "Receptionist"],
  ["coach", "Coach"],
];

const rolePermissionRows = [
  ["Dashboard", { admin: true, manager: true, receptionist: true, coach: true }],
  ["Hội viên", { admin: true, manager: true, receptionist: true, coach: true }],
  ["Chi tiết hội viên", { admin: true, manager: true, receptionist: true, coach: true }],
  ["Đăng ký gói", { admin: true, manager: true, receptionist: true, coach: false }],
  ["Gói tập", { admin: true, manager: true, receptionist: false, coach: false }],
  ["Nhân viên", { admin: true, manager: true, receptionist: false, coach: false }],
  ["Khách PT / Training", { admin: true, manager: true, receptionist: true, coach: true }],
  ["Điểm danh", { admin: true, manager: true, receptionist: true, coach: false }],
  ["Xử lý hội viên", { admin: true, manager: true, receptionist: true, coach: true }],
  ["Thanh toán", { admin: true, manager: true, receptionist: true, coach: false }],
  ["Báo cáo", { admin: true, manager: true, receptionist: false, coach: false }],
  ["Settings", { admin: true, manager: false, receptionist: false, coach: false }],
  ["Audit logs", { admin: true, manager: false, receptionist: false, coach: false }],
  ["Accounts", { admin: true, manager: false, receptionist: false, coach: false }],
];

function RolePermissionHelp() {
  return (
    <span className="role-help">
      <span className="role-help-trigger" tabIndex={0} aria-label="Xem bảng quyền theo vai trò">
        <HelpCircle size={14} />
      </span>
      <span className="role-help-popover" role="tooltip">
        <span className="role-help-head">
          <span>
            <strong>Ma trận quyền theo vai trò</strong>
            <small>So sánh nhanh các trang được phép truy cập trước khi cấp tài khoản.</small>
          </span>
          <span className="role-help-legend">
            <em className="allowed">Có</em>
            <em className="denied">Không</em>
          </span>
        </span>
        <span className="role-help-matrix">
          <span className="role-help-matrix-row header">
            <span>Trang</span>
            {roleColumns.map(([key, label]) => (
              <span key={key}>{label}</span>
            ))}
          </span>
          {rolePermissionRows.map(([page, permissions]) => (
            <span className="role-help-matrix-row" key={page}>
              <span>{page}</span>
              {roleColumns.map(([key]) => (
                <span key={key}>
                  <em className={permissions[key] ? "allowed" : "denied"}>
                    {permissions[key] ? "Có" : "Không"}
                  </em>
                </span>
              ))}
            </span>
          ))}
        </span>
        <span className="role-help-note">
          Audit logs, log hệ thống và log biến động gói chỉ hiển thị cho Admin.
        </span>
        <span className="role-help-mobile">
          {roleColumns.map(([key, label]) => (
            <span className="role-help-card" key={key}>
              <strong>{label}</strong>
              <span>
                {rolePermissionRows.map(([page, permissions]) => (
                  <small key={page}>
                    <span>{page}</span>
                    <em className={permissions[key] ? "allowed" : "denied"}>
                      {permissions[key] ? "Có" : "Không"}
                    </em>
                  </small>
                ))}
              </span>
            </span>
          ))}
        </span>
      </span>
    </span>
  );
}

export function AccountsPage() {
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState(null);
  const [form, setForm] = useState(blank);
  const [error, setError] = useState("");
  const [passwordTarget, setPasswordTarget] = useState(null);
  const [passwordForm, setPasswordForm] = useState({ password: "", confirmPassword: "" });
  const [passwordError, setPasswordError] = useState("");
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
  const changePassword = useMutation({
    mutationFn: (payload) =>
      api(`/api/users/${passwordTarget.id}/password`, {
        method: "PATCH",
        body: payload,
      }),
    onSuccess: (result) => {
      client.invalidateQueries({ queryKey: ["audit-logs"] });
      setPasswordTarget(null);
      setPasswordForm({ password: "", confirmPassword: "" });
      notify.success(
        `Đã đổi mật khẩu cho @${result.username}.${result.sessionsRevoked ? " Các phiên đăng nhập cũ đã được đăng xuất." : ""}`,
      );
    },
    onError: (reason) => setPasswordError(reason.message),
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
      ...(!selected ? { password: form.password } : {}),
    });
  };
  const openPassword = (row) => {
    setPasswordTarget(row);
    setPasswordForm({ password: "", confirmPassword: "" });
    setPasswordError("");
  };
  const submitPassword = (event) => {
    event.preventDefault();
    setPasswordError("");
    if (passwordForm.password !== passwordForm.confirmPassword) {
      setPasswordError("Xác nhận mật khẩu không khớp.");
      return;
    }
    changePassword.mutate(passwordForm);
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
          { key: "action", label: "", render: (row) => <div className="flex justify-end gap-1"><Button size="sm" variant="ghost" onClick={(event) => { event.stopPropagation(); openPassword(row); }}><KeyRound size={13} /> Đổi mật khẩu</Button><Button size="sm" variant="ghost" onClick={(event) => { event.stopPropagation(); edit(row); }}><Pencil size={13} /> Chỉnh sửa</Button></div> },
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
              {!selected && (
                <Field label="Mật khẩu" required hint="Tối thiểu 8 ký tự">
                  <Input type="password" minLength={8} autoComplete="new-password" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} />
                </Field>
              )}
              <Field className="form-span" label={<>Vai trò <RolePermissionHelp /></>} required>
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
      <Modal
        open={!!passwordTarget}
        onClose={() => setPasswordTarget(null)}
        title="Đổi mật khẩu tài khoản"
        description={passwordTarget ? `${passwordTarget.displayName} · @${passwordTarget.username}` : ""}
        dirty={Boolean(passwordForm.password || passwordForm.confirmPassword)}
      >
        <form onSubmit={submitPassword}>
          <div className="modal-body space-y-4">
            <Field label="Mật khẩu mới" required hint="Tối thiểu 8 ký tự">
              <Input
                type="password"
                minLength={8}
                autoComplete="new-password"
                value={passwordForm.password}
                onChange={(event) => setPasswordForm({ ...passwordForm, password: event.target.value })}
              />
            </Field>
            <Field label="Xác nhận mật khẩu" required>
              <Input
                type="password"
                minLength={8}
                autoComplete="new-password"
                value={passwordForm.confirmPassword}
                onChange={(event) => setPasswordForm({ ...passwordForm, confirmPassword: event.target.value })}
              />
            </Field>
            {passwordError && <div className="inline-error">{passwordError}</div>}
          </div>
          <div className="form-actions">
            <Button data-modal-close variant="secondary" onClick={() => setPasswordTarget(null)}>Hủy</Button>
            <Button type="submit" loading={changePassword.isPending} loadingText="Đang đổi…"><KeyRound size={14} /> Đổi mật khẩu</Button>
          </div>
        </form>
      </Modal>
    </>
  );
}
