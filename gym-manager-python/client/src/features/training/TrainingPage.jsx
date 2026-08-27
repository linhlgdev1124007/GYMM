import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Minus, Plus, UserRoundCheck, UserRoundPlus } from "lucide-react";
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
import { formatPhone, money, shortDate } from "../../utils/format";
import { useAuth } from "../../app/AuthContext";

export function TrainingPage() {
  const { user } = useAuth();
  const coachMode = user.role === "coach";
  const client = useQueryClient();
  const [type, setType] = useState("1:1");
  const [search, setSearch] = useState("");
  const [assignment, setAssignment] = useState("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [selected, setSelected] = useState(null);
  const [creating, setCreating] = useState(false);
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
    queryKey: ["member-options", coachMode ? "base" : "no-pt-members"],
    queryFn: () => api(`/api/members/options?${queryString({ includeMembers: !coachMode, memberView: "no_pt" })}`),
    staleTime: 300000,
  });
  const memberOptions = (options.data?.members || []).map((row) => ({
    value: row.id,
    label: row.name,
    meta: `${row.code} · ${formatPhone(row.phone)}${row.membership ? ` · ${row.membership.packageName || row.membership.package?.name || "Có gói"}` : ""}`,
  }));
  const create = useMutation({
    mutationFn: (payload) => api(`/api/members/${payload.memberId}/training`, { method: "POST", body: payload }),
    onSuccess: (data) => {
      client.invalidateQueries({ queryKey: ["training"] });
      client.invalidateQueries({ queryKey: ["members"] });
      client.invalidateQueries({ queryKey: ["payments"] });
      client.invalidateQueries({ queryKey: ["reports"] });
      setCreating(false);
      notify.success(`Đã thêm hội viên PT ${data.member?.name || ""}.`);
    },
    onError: (error) => setFormError(error.message),
  });
  const save = useMutation({
    mutationFn: (payload) => {
      const body = coachMode
        ? (({ remainingSessions, schedule, status }) => ({ remainingSessions, schedule, status }))(payload)
        : payload;
      return api(`/api/training/${selected.id}`, { method: "PATCH", body });
    },
    onSuccess: (_data, payload) => {
      client.invalidateQueries({ queryKey: ["training"] });
      client.invalidateQueries({ queryKey: ["members"] });
      client.invalidateQueries({ queryKey: ["member", selected.memberId] });
      client.invalidateQueries({ queryKey: ["payments"] });
      client.invalidateQueries({ queryKey: ["reports"] });
      setSelected(null);
      const coachCount = payload.coachIds?.length || 0;
      notify.success(coachMode ? `Đã cập nhật tiến độ PT của ${selected.member.name}.` : (
        coachCount
          ? `Đã cập nhật ${coachCount} Coach cho ${selected.member.name}.`
          : `Đã để ${selected.member.name} ở trạng thái chưa phân Coach.`
      ));
    },
    onError: (error) => setFormError(error.message),
  });
  const adjustSessions = useMutation({
    mutationFn: ({ row, action }) =>
      api(`/api/training/${row.id}/sessions`, {
        method: "POST",
        body: { action, amount: 1, note: action === "add" ? "Cộng nhanh từ màn Khách PT" : "Trừ nhanh từ màn Khách PT" },
      }),
    onSuccess: (_data, variables) => {
      client.invalidateQueries({ queryKey: ["training"] });
      client.invalidateQueries({ queryKey: ["members"] });
      client.invalidateQueries({ queryKey: ["member", variables.row.memberId] });
      notify.success(variables.action === "add" ? "Đã cộng 1 buổi PT." : "Đã trừ 1 buổi PT.");
    },
    onError: (error) => notify.errorFrom(error, "Không thể cập nhật số buổi PT."),
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
          <div className="cell-secondary">
            {row.packageName || "Chưa đặt tên gói"} · {row.type}
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
        ) : coachMode ? (
          <span className="text-xs text-slate-400">Chưa phân công</span>
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
      key: "finance",
      label: "Tài chính PT",
      sortValue: (row) => row.debtAmount || 0,
      render: (row) => (
        <span className="flex flex-col text-xs">
          <strong className="text-slate-900">{money(row.paidAmount)} / {money(row.finalPrice)}</strong>
          <small className={row.debtAmount > 0 ? "text-red-700" : "text-emerald-700"}>
            {row.debtAmount > 0 ? `${money(row.debtAmount)} nợ${row.nextDebtDueDate ? ` · hạn ${shortDate(row.nextDebtDueDate)}` : ""}` : "Đã tất toán"}
          </small>
        </span>
      ),
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
      render: (row) => {
        const isAssignedCoach = row.coaches?.some((coach) => coach.id === user.employee?.id);
        if (coachMode && !isAssignedCoach) return null;
        const pendingKey = adjustSessions.isPending
          ? `${adjustSessions.variables.row.id}:${adjustSessions.variables.action}`
          : null;
        return (
          <div className="flex justify-end gap-1.5">
            <Button
              size="sm"
              variant="secondary"
              loading={pendingKey === `${row.id}:subtract`}
              loadingText="Trừ..."
              disabled={row.remainingSessions <= 0 || pendingKey === `${row.id}:add`}
              onClick={() => adjustSessions.mutate({ row, action: "subtract" })}
            >
              <Minus size={14} /> 1
            </Button>
            <Button
              size="sm"
              variant="secondary"
              loading={pendingKey === `${row.id}:add`}
              loadingText="Cộng..."
              disabled={pendingKey === `${row.id}:subtract`}
              onClick={() => adjustSessions.mutate({ row, action: "add" })}
            >
              <Plus size={14} /> 1
            </Button>
            <Button size="sm" variant="ghost" onClick={() => edit(row)}>
              {row.coaches?.length ? (
                <UserRoundCheck size={14} />
              ) : (
                <UserRoundPlus size={14} />
              )}
              {coachMode ? "Cập nhật" : row.coaches?.length ? "Sửa" : "Phân công"}
            </Button>
          </div>
        );
      },
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
        {!coachMode && (
          <Button onClick={() => { setFormError(""); setCreating(true); }}>
            <UserRoundPlus size={15} /> Thêm hội viên PT
          </Button>
        )}
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
            : "Thêm từ danh sách hội viên hiện có để bắt đầu quản lý lịch tập và công nợ PT."
        }
        emptyAction={
          search || assignment !== "all" ? (
            <Button size="sm" variant="secondary" onClick={() => { setSearch(""); setAssignment("all"); setPage(1); }}>
              Xóa tìm kiếm và bộ lọc
            </Button>
          ) : !coachMode && (
            <Button size="sm" onClick={() => { setFormError(""); setCreating(true); }}>
              <UserRoundPlus size={14} /> Thêm hội viên PT
            </Button>
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
        coachMode={coachMode}
      />
      <TrainingForm
        enrollment={null}
        options={options.data}
        memberOptions={memberOptions}
        requireMember
        open={creating}
        onClose={() => setCreating(false)}
        onSubmit={(payload) => create.mutate(payload)}
        pending={create.isPending}
        error={formError}
        coachMode={false}
      />
    </>
  );
}
