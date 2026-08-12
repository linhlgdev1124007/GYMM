import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Link2, Pencil, Plus } from "lucide-react";
import { Link } from "react-router-dom";
import { api, queryString } from "../../services/api";
import { notify } from "../../services/notify";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";
import { PageHeader } from "../../components/common/PageHeader";
import { SearchInput } from "../../components/common/SearchInput";
import { Button } from "../../components/ui/Button";
import { DataTable } from "../../components/ui/DataTable";
import { Field, Input, Select } from "../../components/ui/Form";
import { Modal } from "../../components/ui/Modal";
import { DateInput, PhoneInput } from "../../components/ui/SmartInputs";
import { Pagination } from "../../components/ui/Pagination";
import { RowMenu } from "../../components/ui/RowMenu";
import { formatPhone, initials, normalizePhone } from "../../utils/format";
import { DahIdentityLinkModal } from "../members/DahIdentityLinkModal";

const defaultJobTitles = ["Sale", "Coach", "Marketing"];
const blank = { name: "", phone: "", email: "", title: "Coach" };

const isoDay = (offset = 0) => {
  const day = new Date();
  day.setDate(day.getDate() + offset);
  const year = day.getFullYear();
  const month = String(day.getMonth() + 1).padStart(2, "0");
  const date = String(day.getDate()).padStart(2, "0");
  return `${year}-${month}-${date}`;
};

const csvValue = (value) => `"${String(value ?? "").replaceAll('"', '""')}"`;

function minutesLabel(value) {
  if (value == null) return "";
  const hours = Math.floor(value / 60);
  const minutes = value % 60;
  return hours ? `${hours}h ${minutes}m` : `${minutes}m`;
}

function normalizeJobTitle(value) {
  return String(value || "").trim().slice(0, 80);
}

export function TrainersPage() {
  const client = useQueryClient();
  const [search, setSearch] = useState("");
  const q = useDebouncedValue(search);
  const [titleFilter, setTitleFilter] = useState("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState(null);
  const [identityTarget, setIdentityTarget] = useState(null);
  const [attendanceOpen, setAttendanceOpen] = useState(false);
  const [attendancePreset, setAttendancePreset] = useState("today");
  const [attendanceDate, setAttendanceDate] = useState(isoDay());
  const [confirm, setConfirm] = useState(null);
  const [form, setForm] = useState(blank);
  const [error, setError] = useState("");
  useEffect(
    () =>
      setForm(
        selected
          ? {
              name: selected.name,
              phone: selected.phone || "",
              email: selected.email || "",
              title: selected.title || "",
            }
          : blank,
      ),
    [selected, open],
  );
  const query = useQuery({
    queryKey: ["trainers", q, titleFilter, page, pageSize],
    queryFn: () =>
      api(`/api/trainers?${queryString({ q, title: titleFilter, page, pageSize })}`),
  });
  const jobTitles = useMemo(
    () =>
      Array.from(
        new Set([
          ...defaultJobTitles,
          ...(query.data?.jobTitles || []).map((row) => row.name),
          normalizeJobTitle(form.title),
        ].filter(Boolean)),
      ).sort((a, b) => a.localeCompare(b, "vi")),
    [form.title, query.data?.jobTitles],
  );
  const edit = (row) => {
    setSelected(row);
    setError("");
    setOpen(true);
  };
  const save = useMutation({
    mutationFn: (payload) =>
      api(selected ? `/api/trainers/${selected.id}` : "/api/trainers", {
        method: selected ? "PATCH" : "POST",
        body: {
          ...payload,
          name: payload.name.trim(),
          phone: normalizePhone(payload.phone),
          email: payload.email.trim(),
          title: normalizeJobTitle(payload.title) || "Coach",
        },
      }),
    onSuccess: (data) => {
      client.invalidateQueries({ queryKey: ["trainers"] });
      client.invalidateQueries({ queryKey: ["member-options"] });
      setOpen(false);
      setSelected(null);
      notify.success(
        selected
          ? `Đã lưu hồ sơ ${data.name || selected.name}.`
          : `Đã thêm nhân viên ${data.name}.`,
      );
    },
    onError: (e) => setError(e.message),
  });
  const remove = useMutation({
    mutationFn: (row) => api(`/api/trainers/${row.id}`, { method: "DELETE" }),
    onSuccess: (data) => {
      client.invalidateQueries({ queryKey: ["trainers"] });
      client.invalidateQueries({ queryKey: ["member-options"] });
      setConfirm(null);
      notify.success(
        data.archived
          ? `Đã ẩn ${confirm.name} vì nhân viên có lịch sử liên quan.`
          : `Đã xóa nhân viên ${confirm.name}.`,
      );
    },
    onError: (e) =>
      notify.errorFrom(e, "Không thể xóa nhân viên. Vui lòng thử lại."),
  });
  const attendanceDay =
    attendancePreset === "yesterday"
      ? isoDay(-1)
      : attendancePreset === "custom"
        ? attendanceDate || isoDay()
        : isoDay();
  const exportAttendance = useMutation({
    mutationFn: () =>
      api(`/api/trainers/attendance?${queryString({ day: attendanceDay })}`),
    onSuccess: (data) => {
      const rows = data.items || [];
      const csv = [
        "Ngày,Ca,Mã nhân viên,Họ tên,Điện thoại,Chức vụ,Check-in,Check-out,Tổng thời gian,Nguồn,Trạng thái",
        ...rows.map((row) =>
          [
            data.date,
            row.shiftNo,
            row.employeeCode,
            row.employeeName,
            row.phone,
            row.title,
            row.checkedInAt ? new Date(row.checkedInAt).toLocaleString("vi-VN") : "",
            row.checkedOutAt ? new Date(row.checkedOutAt).toLocaleString("vi-VN") : "",
            minutesLabel(row.durationMinutes),
            row.source,
            row.status,
          ].map(csvValue).join(","),
        ),
      ].join("\n");
      const url = URL.createObjectURL(
        new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" }),
      );
      const link = document.createElement("a");
      link.href = url;
      link.download = `pulsefit-employee-attendance-${data.date}.csv`;
      link.click();
      URL.revokeObjectURL(url);
      notify.success(`Đã tải ${rows.length} dòng chấm công nhân viên.`);
      setAttendanceOpen(false);
    },
    onError: (e) =>
      notify.errorFrom(e, "Không thể tải chấm công nhân viên."),
  });
  const columns = [
    {
      key: "trainer",
      label: "Nhân viên",
      sortValue: (r) => r.name,
      render: (r) => (
        <button
          className="member-cell text-left"
          onClick={(e) => {
            e.stopPropagation();
            edit(r);
          }}
        >
          <div className="avatar avatar-md">{initials(r.name)}</div>
          <div>
            <span className="cell-primary hover:text-blue-700">{r.name}</span>
            <div className="cell-secondary">{r.code}</div>
          </div>
        </button>
      ),
    },
    {
      key: "phone",
      label: "Điện thoại",
      sortValue: (r) => r.phone,
      render: (r) => formatPhone(r.phone) || "—",
    },
    {
      key: "title",
      label: "Chức vụ",
      sortValue: (r) => r.title || "",
      render: (r) => r.title || "—",
    },
    {
      key: "registeredPtClients",
      label: "Khách đăng ký",
      className: "text-right",
      sortValue: (r) => r.registeredPtClients ?? -1,
      render: (r) =>
        r.isPtRole ? (
          <Link
            to={`/members?trainerId=${r.id}`}
            className="font-medium text-blue-700 hover:underline"
            onClick={(e) => e.stopPropagation()}
          >
            {r.registeredPtClients}
          </Link>
        ) : "—",
    },
    {
      key: "activePtClients",
      label: "Đang hoạt động",
      className: "text-right",
      sortValue: (r) => r.activePtClients ?? -1,
      render: (r) => (r.isPtRole ? r.activePtClients : "—"),
    },
    {
      key: "expiredPtClients",
      label: "Hết hạn",
      className: "text-right",
      sortValue: (r) => r.expiredPtClients ?? -1,
      render: (r) => (r.isPtRole ? r.expiredPtClients : "—"),
    },
    {
      key: "actions",
      label: "",
      sortable: false,
      render: (r) => (
        <div className="flex justify-end gap-1">
          <Button
            size="sm"
            variant="ghost"
            onClick={(e) => {
              e.stopPropagation();
              edit(r);
            }}
          >
            <Pencil size={13} />
            Sửa
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={(e) => {
              e.stopPropagation();
              setIdentityTarget(r);
            }}
          >
            <Link2 size={13} />
            {r.dahIdentity ? "Đổi DAH" : "Liên kết DAH"}
          </Button>
          <RowMenu>
            <button className="danger" onClick={() => setConfirm(r)}>
              Xóa nhân viên
            </button>
          </RowMenu>
        </div>
      ),
    },
  ];
  return (
    <>
      <PageHeader
        eyebrow="Quản lý"
        title="Nhân viên"
        description="Click nhân viên để chỉnh sửa; chỉ chức vụ PT hiển thị thống kê khách đăng ký."
        action={
          <div className="flex flex-wrap justify-end gap-2">
            <Button
              variant="secondary"
              onClick={() => setAttendanceOpen(true)}
              loading={exportAttendance.isPending}
              loadingText="Đang tải..."
            >
              <Download size={16} />
              Tải chấm công
            </Button>
            <Button onClick={() => edit(null)}>
              <Plus size={16} />
              Thêm nhân viên
            </Button>
          </div>
        }
      />
      <div className="toolbar">
        <SearchInput
          value={search}
          onChange={(value) => {
            setSearch(value);
            setPage(1);
          }}
          placeholder="Tên, điện thoại, mã nhân viên, chức vụ…"
        />
        <Select
          className="input w-48"
          value={titleFilter}
          onChange={(event) => {
            setTitleFilter(event.target.value);
            setPage(1);
          }}
        >
          <option value="all">Mọi chức vụ</option>
          {jobTitles.map((title) => (
            <option key={title} value={title}>
              {title}
            </option>
          ))}
        </Select>
      </div>
      <DataTable
        columns={columns}
        rows={query.data?.items}
        loading={query.isLoading}
        error={query.error}
        onRetry={query.refetch}
        onRowClick={edit}
      />
      <Pagination
        data={query.data?.pagination}
        onPage={setPage}
        pageSize={pageSize}
        onPageSize={(value) => {
          setPageSize(value);
          setPage(1);
        }}
      />
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        dirty={
          JSON.stringify(form) !==
          JSON.stringify(
            selected
              ? {
                  name: selected.name,
                  phone: selected.phone || "",
                  email: selected.email || "",
                  title: selected.title || "",
                }
              : blank,
          )
        }
        title={selected ? "Chỉnh sửa nhân viên" : "Thêm nhân viên"}
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (form.phone && normalizePhone(form.phone).length !== 10) {
              setError("Số điện thoại cần đủ 10 chữ số.");
              return;
            }
            save.mutate(form);
          }}
        >
          <div className="modal-body">
            <div className="form-grid">
              <Field className="form-span" label="Họ tên" required>
                <Input
                  autoFocus
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                />
              </Field>
              <Field label="Điện thoại">
                <PhoneInput
                  value={form.phone}
                  onChange={(phone) => setForm({ ...form, phone })}
                />
              </Field>
              <Field label="Email">
                <Input
                  type="email"
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                />
              </Field>
              <div className="field form-span">
                <span className="field-label">Chức vụ</span>
                <Select
                  value={form.title || "Coach"}
                  onChange={(event) =>
                    setForm({ ...form, title: event.target.value })
                  }
                >
                  {jobTitles.map((title) => (
                    <option key={title} value={title}>
                      {title}
                    </option>
                  ))}
                </Select>
                <span className="field-hint">
                  Thêm chức vụ mới và đánh dấu chức vụ PT tại Cài đặt.
                </span>
              </div>
            </div>
            {error && <div className="inline-error mt-4">{error}</div>}
          </div>
          <div className="form-actions">
            <Button
              data-modal-close
              variant="secondary"
              onClick={() => setOpen(false)}
            >
              Hủy
            </Button>
            <Button
              type="submit"
              loading={save.isPending}
              loadingText="Đang lưu…"
            >
              Lưu nhân viên
            </Button>
          </div>
        </form>
      </Modal>
      <Modal
        open={attendanceOpen}
        onClose={() => setAttendanceOpen(false)}
        title="Tải chấm công nhân viên"
        description="Chọn ngày cần xuất dữ liệu check-in/check-out theo từng ca."
      >
        <div className="modal-body">
          <div className="form-grid">
            <Field className="form-span" label="Khoảng ngày">
              <Select
                value={attendancePreset}
                onChange={(event) => {
                  const value = event.target.value;
                  setAttendancePreset(value);
                  if (value === "today") setAttendanceDate(isoDay());
                  if (value === "yesterday") setAttendanceDate(isoDay(-1));
                }}
              >
                <option value="today">Hôm nay</option>
                <option value="yesterday">Hôm qua</option>
                <option value="custom">Ngày cụ thể</option>
              </Select>
            </Field>
            {attendancePreset === "custom" && (
              <Field className="form-span" label="Ngày cụ thể">
                <DateInput
                  value={attendanceDate}
                  onChange={setAttendanceDate}
                />
              </Field>
            )}
          </div>
        </div>
        <div className="form-actions">
          <Button
            data-modal-close
            variant="secondary"
            onClick={() => setAttendanceOpen(false)}
          >
            Hủy
          </Button>
          <Button
            onClick={() => exportAttendance.mutate()}
            loading={exportAttendance.isPending}
            loadingText="Đang tải..."
            disabled={attendancePreset === "custom" && !attendanceDate}
          >
            <Download size={16} />
            Tải file
          </Button>
        </div>
      </Modal>
      <Modal
        open={!!confirm}
        onClose={() => setConfirm(null)}
        title="Xóa nhân viên?"
        description="Nhân viên đã có lịch sử sẽ được ẩn thay vì xóa dữ liệu."
      >
        <div className="modal-body">
          <p className="text-[13px] text-slate-600">
            Bạn đang xóa <strong>{confirm?.name}</strong>. Dữ liệu liên quan sẽ
            được bảo toàn.
          </p>
        </div>
        <div className="form-actions">
          <Button
            data-modal-close
            variant="secondary"
            onClick={() => setConfirm(null)}
          >
            Hủy
          </Button>
          <Button
            variant="danger"
            onClick={() => remove.mutate(confirm)}
            loading={remove.isPending}
            loadingText="Đang xóa…"
          >
            Xóa nhân viên
          </Button>
        </div>
      </Modal>
      <DahIdentityLinkModal
        open={!!identityTarget}
        onClose={() => setIdentityTarget(null)}
        memberId={identityTarget?.id}
        memberName={identityTarget?.name}
        targetType="employee"
        onLinked={() => {
          client.invalidateQueries({ queryKey: ["trainers"] });
          client.invalidateQueries({ queryKey: ["dah-events"] });
          client.invalidateQueries({ queryKey: ["checkins"] });
          setIdentityTarget(null);
          notify.success(`Đã liên kết DAH cho ${identityTarget?.name}.`);
        }}
      />
    </>
  );
}
