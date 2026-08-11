import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { UserRoundCheck, UserRoundPlus } from "lucide-react";
import { api, queryString } from "../../services/api";
import { notify } from "../../services/notify";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";
import { PageHeader } from "../../components/common/PageHeader";
import { SearchInput } from "../../components/common/SearchInput";
import { Button } from "../../components/ui/Button";
import { DataTable } from "../../components/ui/DataTable";
import { Select } from "../../components/ui/Form";
import { Pagination } from "../../components/ui/Pagination";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { ScheduleSummary } from "../../components/ui/ScheduleSummary";
import { TrainingForm } from "../../components/forms/TrainingForm";
import { formatPhone, shortDate } from "../../utils/format";

export function TrainingPage() {
  const client = useQueryClient();
  const [type, setType] = useState("1:1");
  const [search, setSearch] = useState("");
  const [assignment, setAssignment] = useState("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [selected, setSelected] = useState(null);
  const [formError, setFormError] = useState("");
  const q = useDebouncedValue(search);
  const query = useQuery({
    queryKey: ["training", type, q, assignment, page, pageSize],
    queryFn: () =>
      api(
        `/api/training?${queryString({ type, q, assignment, page, pageSize })}`,
      ),
  });
  const options = useQuery({
    queryKey: ["member-options"],
    queryFn: () => api("/api/members/options"),
    staleTime: 300000,
  });
  const save = useMutation({
    mutationFn: (payload) =>
      api(`/api/training/${selected.id}`, { method: "PATCH", body: payload }),
    onSuccess: (_data, payload) => {
      client.invalidateQueries({ queryKey: ["training"] });
      client.invalidateQueries({ queryKey: ["members"] });
      client.invalidateQueries({ queryKey: ["member", selected.memberId] });
      setSelected(null);
      const coachCount = payload.coachIds?.length || 0;
      notify.success(
        coachCount
          ? `Đã cập nhật ${coachCount} Coach cho ${selected.member.name}.`
          : `Đã để ${selected.member.name} ở trạng thái chưa phân Coach.`,
      );
    },
    onError: (error) => setFormError(error.message),
  });
  const edit = (row) => {
    setFormError("");
    setSelected(row);
  };
  const columns = [
    {
      key: "member",
      label: "Hội viên",
      sortValue: (row) => row.member.name,
      render: (row) => (
        <Link
          to={`/members/${row.memberId}`}
          className="cell-primary hover:underline"
        >
          {row.member.name}
          <div className="cell-secondary">
            {row.member.code} · {formatPhone(row.member.phone)}
          </div>
        </Link>
      ),
    },
    {
      key: "coach",
      label: "Coach phụ trách",
      sortValue: (row) => row.coaches?.map((coach) => coach.name).join(", ") || "",
      render: (row) =>
        row.coaches?.length ? (
          <div className="flex max-w-64 flex-wrap gap-1.5">
            {row.coaches.map((coach) => (
              <span
                key={coach.id}
                className="rounded bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700"
              >
                {coach.name}
              </span>
            ))}
          </div>
        ) : (
          <button
            className="inline-flex items-center gap-1.5 rounded bg-amber-50 px-2 py-1 text-xs font-medium text-amber-800 hover:bg-amber-100"
            onClick={() => edit(row)}
          >
            <UserRoundPlus size={13} /> Chưa phân công
          </button>
        ),
    },
    {
      key: "schedule",
      label: "Lịch tập",
      sortValue: (row) => row.scheduleDays?.join(",") || row.schedule || "",
      render: (row) => (
        <ScheduleSummary
          schedule={row.schedule}
          scheduleDays={row.scheduleDays}
          scheduleTime={row.scheduleTime}
          emptyText="Chưa chọn thứ"
          compact
        />
      ),
    },
    {
      key: "period",
      label: "Thời hạn",
      sortValue: (row) => row.expiresAt,
      render: (row) =>
        `${shortDate(row.startsAt)} → ${shortDate(row.expiresAt)}`,
    },
    {
      key: "sessions",
      label: "Số buổi",
      sortValue: (row) => row.remainingSessions,
      render: (row) => `${row.remainingSessions}/${row.totalSessions}`,
    },
    {
      key: "status",
      label: "Trạng thái",
      sortValue: (row) => row.status,
      render: (row) => <StatusBadge status={row.status} />,
    },
    {
      key: "action",
      label: "",
      sortable: false,
      render: (row) => (
        <Button size="sm" variant="ghost" onClick={() => edit(row)}>
          {row.coaches?.length ? (
            <UserRoundCheck size={14} />
          ) : (
            <UserRoundPlus size={14} />
          )}
          {row.coaches?.length ? "Sửa phân công" : "Phân công"}
        </Button>
      ),
    },
  ];
  return (
    <>
      <PageHeader
        eyebrow="Quản lý"
        title="Khách PT"
        description="Theo dõi đăng ký PT và phân công một hoặc nhiều Coach cho từng khách."
      />
      <div className="tabs mb-4">
        {["1:1", "1:2", "1:3"].map((value) => (
          <button
            key={value}
            className={`tab ${type === value ? "active" : ""}`}
            onClick={() => {
              setType(value);
              setPage(1);
            }}
          >
            {value}
            <span className="ml-1 text-[11px] text-slate-400">
              {query.data?.counts?.[value] || 0}
            </span>
          </button>
        ))}
      </div>
      <div className="toolbar">
        <SearchInput
          value={search}
          onChange={(value) => {
            setSearch(value);
            setPage(1);
          }}
          placeholder="Tên, điện thoại hoặc mã hội viên…"
        />
        <Select
          className="input w-48"
          value={assignment}
          onChange={(event) => {
            setAssignment(event.target.value);
            setPage(1);
          }}
        >
          <option value="all">Tất cả phân công</option>
          <option value="unassigned">Chưa có Coach</option>
          <option value="assigned">Đã có Coach</option>
        </Select>
        <div className="toolbar-spacer" />
        <span className="text-xs text-slate-400">
          {query.data?.pagination.total || 0} đăng ký
        </span>
      </div>
      <DataTable
        rows={query.data?.items}
        columns={columns}
        loading={query.isLoading}
        error={query.error}
        onRetry={query.refetch}
        emptyTitle={
          assignment === "unassigned"
            ? "Không có đăng ký chờ phân công"
            : `Chưa có khách PT ${type}`
        }
        emptyDescription={
          assignment === "unassigned"
            ? "Tất cả khách trong tab này đã có Coach phụ trách."
            : "Đăng ký PT từ hồ sơ hội viên để khách xuất hiện tại đây."
        }
        emptyAction={
          search || assignment !== "all" ? (
            <Button size="sm" variant="secondary" onClick={() => { setSearch(""); setAssignment("all"); setPage(1); }}>
              Xóa tìm kiếm và bộ lọc
            </Button>
          ) : (
            <Link className="btn btn-primary btn-sm" to="/members?view=no_pt">
              Tìm hội viên để đăng ký PT
            </Link>
          )
        }
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
      <TrainingForm
        enrollment={selected}
        options={options.data}
        open={!!selected}
        onClose={() => setSelected(null)}
        onSubmit={(payload) => save.mutate(payload)}
        pending={save.isPending}
        error={formError}
      />
    </>
  );
}
