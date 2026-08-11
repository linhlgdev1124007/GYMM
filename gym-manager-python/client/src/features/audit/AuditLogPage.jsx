import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { ScrollText } from "lucide-react";
import { api, queryString } from "../../services/api";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";
import { PageHeader } from "../../components/common/PageHeader";
import { SearchInput } from "../../components/common/SearchInput";
import { Select } from "../../components/ui/Form";
import { DataTable } from "../../components/ui/DataTable";
import { Pagination } from "../../components/ui/Pagination";
import { Modal } from "../../components/ui/Modal";
import { Button } from "../../components/ui/Button";
import { dateTime } from "../../utils/format";

const actionLabels = {
  create: "Tạo mới",
  update: "Cập nhật",
  delete: "Xóa",
  archive: "Lưu trữ",
  payment: "Thanh toán",
  upload_receipt: "Thêm chứng từ",
  checkin: "Check-in",
  checkout: "Check-out",
  freeze: "Bảo lưu",
  transfer: "Chuyển nhượng",
  upgrade: "Nâng cấp gói",
  change: "Đổi gói",
  cancel: "Hủy gói",
};
const entityLabels = {
  member: "Hội viên",
  membership: "Gói đăng ký",
  payment: "Thanh toán",
  pt_enrollment: "Đăng ký PT",
  employee: "Nhân viên",
  plan: "Gói tập",
  attendance: "Check-in",
  user: "Tài khoản",
  membership_freeze: "Lịch bảo lưu",
};

export function AuditLogPage() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const q = useDebouncedValue(search);
  const [action, setAction] = useState("all");
  const [entityType, setEntityType] = useState("all");
  const [actorId, setActorId] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(30);
  const [selected, setSelected] = useState(null);
  const query = useQuery({
    queryKey: ["audit-logs", q, action, entityType, actorId, page, pageSize],
    queryFn: () =>
      api(
        `/api/audit-logs?${queryString({ q, action, entityType, actorId, page, pageSize })}`,
      ),
  });
  const resetPage = (setter) => (value) => {
    setter(value);
    setPage(1);
  };
  const columns = [
    {
      key: "createdAt",
      label: "Thời gian",
      sortValue: (row) => row.createdAt,
      render: (row) => (
        <span className="whitespace-nowrap">{dateTime(row.createdAt)}</span>
      ),
    },
    {
      key: "actor",
      label: "Người thao tác",
      sortValue: (row) => row.actor.name,
      render: (row) => (
        <div>
          <span className="cell-primary">{row.actor.name}</span>
          <div className="cell-secondary">
            {row.actor.username} · {row.actor.role}
          </div>
        </div>
      ),
    },
    {
      key: "action",
      label: "Hành động",
      sortValue: (row) => actionLabels[row.action] || row.action,
      render: (row) => (
        <span className={`audit-action audit-${row.action}`}>
          {actionLabels[row.action] || row.action}
        </span>
      ),
    },
    {
      key: "summary",
      label: "Nội dung",
      sortValue: (row) => row.summary,
      render: (row) => (
        <div>
          <span className="cell-primary">{row.summary}</span>
          <div className="cell-secondary">
            {entityLabels[row.entityType] || row.entityType} #
            {row.entityId || "—"}
          </div>
        </div>
      ),
    },
    {
      key: "member",
      label: "Hồ sơ liên quan",
      sortValue: (row) => row.customerId || 0,
      render: (row) =>
        row.customerId ? (
          <Link
            onClick={(event) => event.stopPropagation()}
            className="text-xs font-medium text-blue-700 hover:underline"
            to={`/members/${row.customerId}?tab=activity`}
          >
            Xem hội viên
          </Link>
        ) : (
          <span className="text-slate-300">—</span>
        ),
    },
  ];
  return (
    <>
      <PageHeader
        eyebrow="Kiểm soát nội bộ"
        title="Nhật ký thao tác"
        description="Dấu vết bất biến của các thay đổi dữ liệu quan trọng trong hệ thống."
        action={
          <div className="audit-retention">
            <ScrollText size={15} />
            <span>Audit trail đang hoạt động</span>
          </div>
        }
      />
      <div className="toolbar">
        <SearchInput
          value={search}
          onChange={resetPage(setSearch)}
          placeholder="Nội dung, người thao tác…"
        />
        <Select
          className="input w-44"
          value={action}
          onChange={(event) => resetPage(setAction)(event.target.value)}
        >
          <option value="all">Mọi hành động</option>
          {Object.entries(actionLabels).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
        <Select
          className="input w-44"
          value={entityType}
          onChange={(event) => resetPage(setEntityType)(event.target.value)}
        >
          <option value="all">Mọi đối tượng</option>
          {Object.entries(entityLabels).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
        <Select
          className="input w-48"
          value={actorId}
          onChange={(event) => resetPage(setActorId)(event.target.value)}
        >
          <option value="">Mọi người thao tác</option>
          {query.data?.actors?.map((actor) => (
            <option key={actor.id} value={actor.id}>
              {actor.name}
            </option>
          ))}
        </Select>
      </div>
      <DataTable
        rows={query.data?.items}
        columns={columns}
        loading={query.isLoading}
        error={query.error}
        onRetry={query.refetch}
        onRowClick={setSelected}
        selectedRowId={selected?.id}
        emptyTitle="Chưa có nhật ký phù hợp"
        emptyDescription="Thử thay đổi bộ lọc hoặc từ khóa tìm kiếm."
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
        open={!!selected}
        onClose={() => setSelected(null)}
        title="Chi tiết nhật ký"
        description={
          selected
            ? `${selected.actor.name} · ${dateTime(selected.createdAt)}`
            : ""
        }
      >
        {selected && (
          <div className="modal-body space-y-4">
            <div className="audit-detail-summary">
              <span className={`audit-action audit-${selected.action}`}>
                {actionLabels[selected.action] || selected.action}
              </span>
              <strong>{selected.summary}</strong>
              <small>
                {entityLabels[selected.entityType] || selected.entityType} #
                {selected.entityId || "—"}
              </small>
            </div>
            <dl className="audit-detail-list">
              <div>
                <dt>Người thao tác</dt>
                <dd>
                  {selected.actor.name} ({selected.actor.username})
                </dd>
              </div>
              <div>
                <dt>Vai trò</dt>
                <dd>{selected.actor.role}</dd>
              </div>
              <div>
                <dt>Thời gian</dt>
                <dd>{dateTime(selected.createdAt)}</dd>
              </div>
              {Object.entries(selected.details || {}).map(([key, value]) => (
                <div key={key}>
                  <dt>{key}</dt>
                  <dd>
                    {typeof value === "object"
                      ? JSON.stringify(value, null, 2)
                      : String(value ?? "—")}
                  </dd>
                </div>
              ))}
            </dl>
          </div>
        )}
        <div className="form-actions">
          <Button
            data-modal-close
            variant="secondary"
            onClick={() => setSelected(null)}
          >
            Đóng
          </Button>
          {selected?.customerId && (
            <Button
              onClick={() =>
                navigate(`/members/${selected.customerId}?tab=activity`)
              }
            >
              Xem hồ sơ
            </Button>
          )}
        </div>
      </Modal>
    </>
  );
}
