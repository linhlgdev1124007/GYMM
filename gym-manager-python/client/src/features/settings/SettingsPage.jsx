import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { api } from "../../services/api";
import { notify } from "../../services/notify";
import { PageHeader } from "../../components/common/PageHeader";
import { Button } from "../../components/ui/Button";
import { DataTable } from "../../components/ui/DataTable";
import { Field, Input, Select } from "../../components/ui/Form";
import { Modal } from "../../components/ui/Modal";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { dateTime } from "../../utils/format";

const blankTitle = { name: "", isPtRole: false, active: true };
const blankAccount = {
  bank: "",
  accountName: "",
  accountNumber: "",
  visibility: "public",
  status: "active",
};

function titleForm(row) {
  return row
    ? { name: row.name || "", isPtRole: !!row.isPtRole, active: row.active !== false }
    : blankTitle;
}

function accountForm(row) {
  return row
    ? {
        bank: row.bank || "",
        accountName: row.accountName || "",
        accountNumber: row.accountNumber || "",
        visibility: row.visibility || "public",
        status: row.status || "active",
      }
    : blankAccount;
}

export function SettingsPage() {
  const client = useQueryClient();
  const [titleModal, setTitleModal] = useState(null);
  const [accountModal, setAccountModal] = useState(null);
  const [titleDraft, setTitleDraft] = useState(blankTitle);
  const [accountDraft, setAccountDraft] = useState(blankAccount);
  const [error, setError] = useState("");
  const query = useQuery({
    queryKey: ["settings"],
    queryFn: () => api("/api/settings"),
  });
  const data = query.data;

  useEffect(() => {
    setTitleDraft(titleForm(titleModal));
    setError("");
  }, [titleModal]);
  useEffect(() => {
    setAccountDraft(accountForm(accountModal));
    setError("");
  }, [accountModal]);

  const saveJobTitle = useMutation({
    mutationFn: (payload) =>
      api(
        titleModal?.id
          ? `/api/settings/job-titles/${titleModal.id}`
          : "/api/settings/job-titles",
        { method: titleModal?.id ? "PATCH" : "POST", body: payload },
      ),
    onSuccess: (row) => {
      client.invalidateQueries({ queryKey: ["settings"] });
      client.invalidateQueries({ queryKey: ["trainers"] });
      client.invalidateQueries({ queryKey: ["member-options"] });
      setTitleModal(null);
      notify.success(`Đã lưu chức vụ ${row.name}.`);
    },
    onError: (reason) => setError(reason.message),
  });
  const saveAccount = useMutation({
    mutationFn: (payload) =>
      api(
        accountModal?.id
          ? `/api/settings/bank-accounts/${accountModal.id}`
          : "/api/settings/bank-accounts",
        { method: accountModal?.id ? "PATCH" : "POST", body: payload },
      ),
    onSuccess: (row) => {
      client.invalidateQueries({ queryKey: ["settings"] });
      client.invalidateQueries({ queryKey: ["member-options"] });
      setAccountModal(null);
      notify.success(`Đã lưu tài khoản ${row.bank}.`);
    },
    onError: (reason) => setError(reason.message),
  });
  const deleteJobTitle = useMutation({
    mutationFn: (row) =>
      api(`/api/settings/job-titles/${row.id}`, { method: "DELETE" }),
    onSuccess: (_, row) => {
      client.invalidateQueries({ queryKey: ["settings"] });
      client.invalidateQueries({ queryKey: ["trainers"] });
      client.invalidateQueries({ queryKey: ["member-options"] });
      notify.success(`Đã xóa chức vụ ${row.name}.`);
    },
    onError: (reason) => notify.error(reason.message),
  });
  const deleteAccount = useMutation({
    mutationFn: (row) =>
      api(`/api/settings/bank-accounts/${row.id}`, { method: "DELETE" }),
    onSuccess: (_, row) => {
      client.invalidateQueries({ queryKey: ["settings"] });
      client.invalidateQueries({ queryKey: ["member-options"] });
      notify.success(`Đã xóa tài khoản ${row.bank}.`);
    },
    onError: (reason) => notify.error(reason.message),
  });

  const handleDeleteTitle = (row) => {
    const confirmed = window.confirm(
      `Xóa chức vụ "${row.name}"?\n\nChức vụ đang có nhân viên hoạt động sẽ không thể xóa.`,
    );
    if (confirmed) deleteJobTitle.mutate(row);
  };
  const handleDeleteAccount = (row) => {
    const confirmed = window.confirm(
      `Xóa tài khoản "${row.bank} · ${row.accountNumber}"?\n\nTài khoản đã có giao dịch sẽ được ẩn để giữ lịch sử thanh toán.`,
    );
    if (confirmed) deleteAccount.mutate(row);
  };

  return (
    <>
      <PageHeader
        eyebrow="Hệ thống"
        title="Cài đặt"
        description="Quản lý tài khoản nhận tiền, chức vụ nhân sự và trạng thái thiết bị."
      />
      <section>
        <div className="section-header">
          <div>
            <h2>Chức vụ & quyền PT</h2>
            <p>Đánh dấu chức vụ nào được chọn làm Coach/PT trong lịch tập.</p>
          </div>
          <Button size="sm" onClick={() => setTitleModal({})}>
            <Plus size={14} />
            Thêm chức vụ
          </Button>
        </div>
        <DataTable
          rows={data?.jobTitles}
          loading={query.isLoading}
          error={query.error}
          onRetry={query.refetch}
          columns={[
            {
              key: "name",
              label: "Chức vụ",
              render: (row) => <span className="cell-primary">{row.name}</span>,
            },
            {
              key: "pt",
              label: "Được chọn làm PT",
              render: (row) =>
                row.isPtRole ? (
                  <StatusBadge status="active" />
                ) : (
                  <span className="text-xs text-slate-400">Không</span>
                ),
            },
            {
              key: "status",
              label: "Trạng thái",
              render: (row) => (
                <StatusBadge status={row.active ? "active" : "inactive"} />
              ),
            },
            {
              key: "actions",
              label: "",
              className: "text-right",
              render: (row) => (
                <div className="flex justify-end gap-2">
                  <Button size="sm" variant="ghost" onClick={() => setTitleModal(row)}>
                    <Pencil size={13} />
                    Sửa
                  </Button>
                  <Button
                    size="sm"
                    variant="danger"
                    disabled={deleteJobTitle.isPending}
                    onClick={() => handleDeleteTitle(row)}
                  >
                    <Trash2 size={13} />
                    Xóa
                  </Button>
                </div>
              ),
            },
          ]}
        />
      </section>
      <section className="mt-7">
        <div className="section-header">
          <div>
            <h2>Tài khoản nhận tiền</h2>
            <p>Các tài khoản hiển thị trong luồng thu tiền và đăng ký gói.</p>
          </div>
          <Button size="sm" onClick={() => setAccountModal({})}>
            <Plus size={14} />
            Thêm tài khoản
          </Button>
        </div>
        <DataTable
          rows={data?.bankAccounts}
          loading={query.isLoading}
          error={query.error}
          onRetry={query.refetch}
          columns={[
            {
              key: "bank",
              label: "Ngân hàng",
              render: (row) => (
                <div>
                  <span className="cell-primary">{row.bank}</span>
                  <div className="cell-secondary">{row.accountNumber}</div>
                </div>
              ),
            },
            { key: "accountName", label: "Chủ tài khoản" },
            { key: "visibility", label: "Phạm vi" },
            {
              key: "status",
              label: "Trạng thái",
              render: (row) => <StatusBadge status={row.status} />,
            },
            {
              key: "actions",
              label: "",
              className: "text-right",
              render: (row) => (
                <div className="flex justify-end gap-2">
                  <Button size="sm" variant="ghost" onClick={() => setAccountModal(row)}>
                    <Pencil size={13} />
                    Sửa
                  </Button>
                  <Button
                    size="sm"
                    variant="danger"
                    disabled={deleteAccount.isPending}
                    onClick={() => handleDeleteAccount(row)}
                  >
                    <Trash2 size={13} />
                    Xóa
                  </Button>
                </div>
              ),
            },
          ]}
        />
      </section>
      <section className="mt-7">
        <div className="section-header">
          <div>
            <h2>Thiết bị</h2>
            <p>DAH-1017 và cổng kiểm soát; tích hợp đồng bộ vẫn tạm hoãn.</p>
          </div>
        </div>
        <DataTable
          rows={data?.devices}
          loading={query.isLoading}
          error={query.error}
          onRetry={query.refetch}
          columns={[
            {
              key: "device",
              label: "Thiết bị",
              render: (row) => (
                <div>
                  <span className="cell-primary">{row.name}</span>
                  <div className="cell-secondary">
                    {row.code} · {row.model}
                  </div>
                </div>
              ),
            },
            { key: "ip", label: "IP" },
            {
              key: "pendingJobs",
              label: "Chờ đồng bộ",
              className: "text-right",
            },
            { key: "errors24h", label: "Lỗi 24h", className: "text-right" },
            {
              key: "lastHeartbeat",
              label: "Heartbeat",
              render: (row) => dateTime(row.lastHeartbeat),
            },
            {
              key: "status",
              label: "Trạng thái",
              render: (row) => <StatusBadge status={row.status} />,
            },
          ]}
        />
      </section>
      <Modal
        open={!!titleModal}
        onClose={() => setTitleModal(null)}
        title={titleModal?.id ? "Sửa chức vụ" : "Thêm chức vụ"}
        dirty={JSON.stringify(titleDraft) !== JSON.stringify(titleForm(titleModal))}
      >
        <form
          onSubmit={(event) => {
            event.preventDefault();
            setError("");
            saveJobTitle.mutate({
              ...titleDraft,
              name: titleDraft.name.trim(),
              renameEmployees: true,
            });
          }}
        >
          <div className="modal-body">
            <div className="form-grid">
              <Field className="form-span" label="Tên chức vụ" required>
                <Input
                  autoFocus
                  value={titleDraft.name}
                  onChange={(event) =>
                    setTitleDraft({ ...titleDraft, name: event.target.value })
                  }
                  placeholder="Sale, Coach, Marketing, CSKH…"
                />
              </Field>
              <label className="flex items-start gap-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-3 text-sm">
                <input
                  type="checkbox"
                  className="mt-0.5 h-4 w-4 accent-navy-900"
                  checked={titleDraft.isPtRole}
                  onChange={(event) =>
                    setTitleDraft({
                      ...titleDraft,
                      isPtRole: event.target.checked,
                    })
                  }
                />
                <span>
                  <strong className="block text-slate-800">
                    Cho phép chọn làm PT/Coach
                  </strong>
                  <small className="text-xs text-slate-500">
                    Nhân viên thuộc chức vụ này sẽ xuất hiện trong form đăng ký PT.
                  </small>
                </span>
              </label>
              <Field label="Trạng thái">
                <Select
                  value={titleDraft.active ? "active" : "inactive"}
                  onChange={(event) =>
                    setTitleDraft({
                      ...titleDraft,
                      active: event.target.value === "active",
                    })
                  }
                >
                  <option value="active">Đang dùng</option>
                  <option value="inactive">Ẩn</option>
                </Select>
              </Field>
            </div>
            {error && <div className="inline-error mt-4">{error}</div>}
          </div>
          <div className="form-actions">
            <Button data-modal-close variant="secondary" onClick={() => setTitleModal(null)}>
              Hủy
            </Button>
            <Button type="submit" loading={saveJobTitle.isPending} loadingText="Đang lưu…">
              Lưu chức vụ
            </Button>
          </div>
        </form>
      </Modal>
      <Modal
        open={!!accountModal}
        onClose={() => setAccountModal(null)}
        title={accountModal?.id ? "Sửa tài khoản nhận tiền" : "Thêm tài khoản nhận tiền"}
        dirty={JSON.stringify(accountDraft) !== JSON.stringify(accountForm(accountModal))}
      >
        <form
          onSubmit={(event) => {
            event.preventDefault();
            setError("");
            saveAccount.mutate({
              ...accountDraft,
              bank: accountDraft.bank.trim(),
              accountName: accountDraft.accountName.trim(),
              accountNumber: accountDraft.accountNumber.trim(),
            });
          }}
        >
          <div className="modal-body">
            <div className="form-grid">
              <Field label="Ngân hàng" required>
                <Input
                  autoFocus
                  value={accountDraft.bank}
                  onChange={(event) =>
                    setAccountDraft({ ...accountDraft, bank: event.target.value })
                  }
                  placeholder="VCB, ACB, Techcombank…"
                />
              </Field>
              <Field label="Chủ tài khoản" required>
                <Input
                  value={accountDraft.accountName}
                  onChange={(event) =>
                    setAccountDraft({
                      ...accountDraft,
                      accountName: event.target.value,
                    })
                  }
                />
              </Field>
              <Field label="Số tài khoản" required>
                <Input
                  value={accountDraft.accountNumber}
                  onChange={(event) =>
                    setAccountDraft({
                      ...accountDraft,
                      accountNumber: event.target.value,
                    })
                  }
                />
              </Field>
              <Field label="Phạm vi">
                <Select
                  value={accountDraft.visibility}
                  onChange={(event) =>
                    setAccountDraft({
                      ...accountDraft,
                      visibility: event.target.value,
                    })
                  }
                >
                  <option value="public">Public</option>
                  <option value="private">Private</option>
                </Select>
              </Field>
              <Field label="Trạng thái">
                <Select
                  value={accountDraft.status}
                  onChange={(event) =>
                    setAccountDraft({ ...accountDraft, status: event.target.value })
                  }
                >
                  <option value="active">Đang dùng</option>
                  <option value="inactive">Tạm ngừng</option>
                </Select>
              </Field>
            </div>
            {error && <div className="inline-error mt-4">{error}</div>}
          </div>
          <div className="form-actions">
            <Button data-modal-close variant="secondary" onClick={() => setAccountModal(null)}>
              Hủy
            </Button>
            <Button type="submit" loading={saveAccount.isPending} loadingText="Đang lưu…">
              Lưu tài khoản
            </Button>
          </div>
        </form>
      </Modal>
    </>
  );
}
