import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { differenceInMinutes, format, parseISO, subDays } from "date-fns";
import {
  Activity,
  AlertTriangle,
  Clock3,
  Link2,
  Radio,
  RefreshCw,
  UserCheck,
  Users,
} from "lucide-react";
import { Link } from "react-router-dom";
import { api, queryString } from "../../services/api";
import { notify } from "../../services/notify";
import { PageHeader } from "../../components/common/PageHeader";
import { Button } from "../../components/ui/Button";
import { DataTable } from "../../components/ui/DataTable";
import { DateInput } from "../../components/ui/SmartInputs";
import { Pagination } from "../../components/ui/Pagination";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { dateTime, initials } from "../../utils/format";

function CheckinAvatar({ image, name, compact = false }) {
  return (
    <div className={`avatar ${compact ? "avatar-sm" : "avatar-md"}`}>
      {image ? <img src={image} alt="" /> : initials(name)}
    </div>
  );
}

function durationText(start, end) {
  if (!start) return "—";
  const startAt = parseISO(start);
  const endAt = end ? parseISO(end) : new Date();
  const minutes = Math.max(differenceInMinutes(endAt, startAt), 0);
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (!hours) return `${rest} phút`;
  return `${hours} giờ ${rest ? `${rest} phút` : ""}`.trim();
}

function eventActionLabel(action) {
  const labels = {
    checkin: "Check-in",
    checkout: "Check-out",
    mixed: "Vào/ra đồng thời",
    duplicate_scan: "Quét lặp",
    unknown_identity: "Chưa liên kết",
    missing_dah_identity: "Thiếu định danh",
    identity_linked: "Đã liên kết hội viên",
    employee_identity_linked: "Đã liên kết nhân viên",
    verify_failed: "Xác thực lỗi",
    denied: "Từ chối",
    snapshot: "Snapshot",
  };
  return labels[action] || action || "—";
}

function PersonCell({ row }) {
  const name = row.employeeName || row.memberName || row.faceName || "Face chưa gán";
  const image = row.memberAvatarImageData || row.imageData;
  const details = row.employeeId
    ? `${row.employeeCode} · Nhân viên`
    : row.memberId
      ? `${row.memberCode}${row.memberStatus === "lead" ? " · Tiềm năng" : ""}`
      : row.personUuid
        ? `UUID ${row.personUuid}`
        : row.personId
          ? `PersonID ${row.personId}`
          : "Không có định danh";
  const content = (
    <div className="member-cell">
      <CheckinAvatar image={image} name={name} />
      <div className="min-w-0">
        <span className="cell-primary block truncate">{name}</span>
        <span className="cell-secondary block truncate">{details}</span>
      </div>
    </div>
  );
  return row.memberId ? (
    <Link className="hover:underline" to={`/members/${row.memberId}`}>
      {content}
    </Link>
  ) : content;
}

function MetricCard({ icon: Icon, label, value, detail, tone = "slate" }) {
  const tones = {
    slate: "border-slate-200 bg-white text-slate-600",
    emerald: "border-emerald-200 bg-emerald-50 text-emerald-700",
    amber: "border-amber-200 bg-amber-50 text-amber-700",
    blue: "border-blue-200 bg-blue-50 text-blue-700",
  };
  return (
    <div className={`rounded-lg border px-4 py-3 ${tones[tone] || tones.slate}`}>
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-medium">{label}</span>
        <Icon size={16} />
      </div>
      <strong className="mt-1 block text-2xl font-semibold tracking-tight text-slate-950">
        {value}
      </strong>
      <span className="text-xs text-slate-500">{detail}</span>
    </div>
  );
}

function ActiveSessionRow({ row, checkout, mode }) {
  const name = row.employeeName || row.memberName;
  return (
    <div className="grid grid-cols-[minmax(0,1.2fr)_140px_120px_auto] items-center gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2.5 text-sm max-[860px]:grid-cols-1">
      <div className="flex min-w-0 items-center gap-3">
        <CheckinAvatar image={row.memberAvatarImageData} name={name} compact />
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Activity size={14} className="shrink-0 text-emerald-600" />
            <strong className="truncate text-slate-950">{name}</strong>
          </div>
          <p className="mt-0.5 truncate text-xs text-slate-400">
            {row.employeeId
              ? `${row.employeeCode} · Nhân viên`
              : `${row.memberCode}${row.memberStatus === "lead" ? " · Tiềm năng" : ""}`}
          </p>
        </div>
      </div>
      <span className="text-xs text-slate-500">Vào {dateTime(row.checkedInAt)}</span>
      <span className="text-xs font-medium text-slate-700">
        {mode === "employee" ? durationText(row.checkedInAt, row.checkedOutAt) : "Đang trong phòng"}
      </span>
      <div className="flex justify-end gap-2">
        {row.memberId && (
          <Link className="btn btn-secondary btn-sm" to={`/members/${row.memberId}`}>
            Hồ sơ
          </Link>
        )}
        <Button
          size="sm"
          variant="secondary"
          loading={checkout.isPending && checkout.variables === row.id}
          loadingText="Đang đóng..."
          onClick={() => checkout.mutate(row.id)}
        >
          Đóng phiên
        </Button>
      </div>
      {row.memberAccessWarning && (
        <div className="col-span-full flex items-center gap-1.5 rounded-md bg-amber-50 px-2 py-1 text-xs font-medium text-amber-800">
          <AlertTriangle size={13} />
          <span className="truncate">{row.memberAccessWarning}</span>
        </div>
      )}
    </div>
  );
}

export function CheckinPage() {
  const client = useQueryClient();
  const [workspaceView, setWorkspaceView] = useState("member");
  const [eventView, setEventView] = useState("unknown");
  const today = format(new Date(), "yyyy-MM-dd");
  const yesterday = format(subDays(new Date(), 1), "yyyy-MM-dd");
  const [dateView, setDateView] = useState("today");
  const [customDate, setCustomDate] = useState(today);
  const [memberPage, setMemberPage] = useState(1);
  const [memberPageSize, setMemberPageSize] = useState(20);
  const [employeePage, setEmployeePage] = useState(1);
  const [employeePageSize, setEmployeePageSize] = useState(20);
  const [eventPage, setEventPage] = useState(1);
  const [eventPageSize, setEventPageSize] = useState(20);
  const selectedDate =
    dateView === "yesterday" ? yesterday : dateView === "custom" ? customDate : today;

  const changeDateView = (nextView) => {
    setDateView(nextView);
    setMemberPage(1);
    setEmployeePage(1);
  };

  const memberRecent = useQuery({
    queryKey: ["checkins", "member", selectedDate, memberPage, memberPageSize],
    queryFn: () =>
      api(`/api/checkins?${queryString({ day: selectedDate, type: "member", page: memberPage, pageSize: memberPageSize })}`),
    refetchInterval: 30000,
  });
  const employeeRecent = useQuery({
    queryKey: ["checkins", "employee", selectedDate, employeePage, employeePageSize],
    queryFn: () =>
      api(`/api/checkins?${queryString({ day: selectedDate, type: "employee", page: employeePage, pageSize: employeePageSize })}`),
    refetchInterval: 30000,
  });
  const events = useQuery({
    queryKey: ["dah-events", eventView, eventPage, eventPageSize],
    queryFn: () =>
      api(`/api/dah/events?${queryString({ view: eventView, page: eventPage, pageSize: eventPageSize })}`),
    refetchInterval: 5000,
  });
  const unknownEvents = useQuery({
    queryKey: ["dah-events", "unknown-summary"],
    queryFn: () => api(`/api/dah/events?${queryString({ view: "unknown", page: 1, pageSize: 10 })}`),
    refetchInterval: 5000,
  });

  const checkout = useMutation({
    mutationFn: (sessionId) =>
      api(`/api/checkins/${sessionId}/checkout`, { method: "PATCH" }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["checkins"] });
      client.invalidateQueries({ queryKey: ["dashboard"] });
      notify.success("Đã đóng phiên điểm danh.");
    },
    onError: (error) =>
      notify.errorFrom(error, "Không thể đóng phiên này. Vui lòng thử lại."),
  });

  const memberCheckins = memberRecent.data?.items || [];
  const employeeCheckins = employeeRecent.data?.items || [];
  const activeMemberSessions = memberCheckins.filter((row) => row.status === "open");
  const activeEmployeeSessions = employeeCheckins.filter((row) => row.status === "open");
  const warningSessions = activeMemberSessions.filter((row) => row.memberAccessWarning);
  const lastEventAt = [memberRecent.data?.lastEventAt, employeeRecent.data?.lastEventAt]
    .filter(Boolean)
    .sort()
    .at(-1);

  const currentAttendance =
    workspaceView === "employee"
      ? {
          key: "employee",
          title: "Điểm danh nhân viên",
          description: "Theo dõi ca làm, thời lượng hiện diện và phiên chưa ghi nhận giờ ra.",
          rows: employeeCheckins,
          activeRows: activeEmployeeSessions,
          query: employeeRecent,
          pageSize: employeePageSize,
          setPage: setEmployeePage,
          setPageSize: setEmployeePageSize,
          emptyTitle: "Chưa có lượt điểm danh nhân viên",
          emptyDescription: "Dữ liệu sẽ xuất hiện khi nhân viên quét DAH trong ngày này.",
          activeEmpty: "Không có nhân viên đang mở ca.",
        }
      : {
          key: "member",
          title: "Điểm danh khách",
          description: "Tập trung ghi nhận lượt vào của hội viên và khách tiềm năng.",
          rows: memberCheckins,
          activeRows: activeMemberSessions,
          query: memberRecent,
          pageSize: memberPageSize,
          setPage: setMemberPage,
          setPageSize: setMemberPageSize,
          emptyTitle: "Chưa có lượt điểm danh khách",
          emptyDescription: "Dữ liệu sẽ xuất hiện khi hội viên hoặc khách quét DAH trong ngày này.",
          activeEmpty: "Không có khách đang trong phòng.",
        };

  const workspaceTabs = [
    ["member", "Khách", activeMemberSessions.length, memberRecent.data?.pagination?.total || 0],
    ["employee", "Nhân viên", activeEmployeeSessions.length, employeeRecent.data?.pagination?.total || 0],
    ["events", "Sự kiện DAH", unknownEvents.data?.pagination?.total || 0, events.data?.pagination?.total || 0],
  ];
  const eventViews = [
    ["unknown", "Cần xử lý"],
    ["all", "Tất cả"],
    ["allowed", "Đã ghi nhận"],
    ["denied", "Từ chối"],
    ["duplicates", "Quét lặp"],
  ];
  const attendanceColumns = [
    {
      key: "person",
      label: workspaceView === "employee" ? "Nhân viên" : "Khách",
      sortValue: (row) => row.employeeName || row.memberName || "",
      render: (row) => <PersonCell row={row} />,
    },
    {
      key: "checkedInAt",
      label: "Giờ vào",
      render: (row) => dateTime(row.checkedInAt),
    },
    {
      key: "checkedOutAt",
      label: "Giờ ra",
      render: (row) => dateTime(row.checkedOutAt),
    },
    ...(workspaceView === "employee"
      ? [{
          key: "duration",
          label: "Thời lượng",
          render: (row) => durationText(row.checkedInAt, row.checkedOutAt),
        }]
      : []),
    {
      key: "status",
      label: "Trạng thái",
      render: (row) => <StatusBadge status={row.status} />,
    },
  ];
  const eventColumns = [
    {
      key: "member",
      label: "Người quét",
      sortValue: (row) => row.employeeName || row.memberName || row.faceName || row.personUuid || "",
      render: (row) => <PersonCell row={row} />,
    },
    {
      key: "time",
      label: "Thời điểm",
      sortValue: (row) => row.eventTime || row.receivedAt,
      render: (row) => dateTime(row.eventTime || row.receivedAt),
    },
    {
      key: "device",
      label: "Thiết bị",
      sortValue: (row) => row.device || "DAH",
      render: (row) => row.device || "DAH",
    },
    {
      key: "similarity",
      label: "Độ khớp",
      className: "text-right",
      sortValue: (row) => row.similarity || 0,
      render: (row) => row.similarity ? `${Number(row.similarity).toFixed(1)}%` : "—",
    },
    {
      key: "status",
      label: "Kết quả",
      sortValue: (row) => row.status,
      render: (row) => (
        <StatusBadge
          status={
            row.status === "processed"
              ? "active"
              : row.status === "duplicate"
                ? "pending"
                : row.status === "unknown"
                  ? "lead"
                  : row.status === "denied" || row.status === "rejected"
                    ? "blocked"
                    : row.status
          }
        />
      ),
    },
    {
      key: "action",
      label: "Xử lý",
      sortable: false,
      render: (row) =>
        row.status === "unknown" ? (
          <Link className="btn btn-secondary btn-sm" to="/members?create=1">
            <Link2 size={13} /> Liên kết
          </Link>
        ) : (
          <span className="cell-secondary">{eventActionLabel(row.action)}</span>
        ),
    },
  ];

  return (
    <>
      <PageHeader
        eyebrow="Vận hành"
        title="Điểm danh"
        description="Giám sát lượt vào, ca nhân viên và các event DAH cần xử lý."
        action={(
          <Button
            variant="secondary"
            onClick={() => {
              memberRecent.refetch();
              employeeRecent.refetch();
              events.refetch();
              unknownEvents.refetch();
            }}
            loading={memberRecent.isFetching || employeeRecent.isFetching || events.isFetching}
            loadingText="Đang đồng bộ..."
          >
            <RefreshCw size={15} /> Làm mới
          </Button>
        )}
      />

      <div className="mb-6 grid grid-cols-5 gap-3 max-[1100px]:grid-cols-3 max-[760px]:grid-cols-1">
        <MetricCard
          icon={Users}
          label="Khách đang trong phòng"
          value={activeMemberSessions.length}
          detail={`${memberRecent.data?.pagination?.total || 0} lượt trong ngày`}
          tone="blue"
        />
        <MetricCard
          icon={UserCheck}
          label="Nhân viên đang làm việc"
          value={activeEmployeeSessions.length}
          detail={`${employeeRecent.data?.pagination?.total || 0} lượt trong ngày`}
          tone="emerald"
        />
        <MetricCard
          icon={AlertTriangle}
          label="Face cần xử lý"
          value={unknownEvents.data?.pagination?.total || 0}
          detail="chưa liên kết định danh"
          tone={(unknownEvents.data?.pagination?.total || 0) ? "amber" : "slate"}
        />
        <MetricCard
          icon={Clock3}
          label="Sự kiện mới nhất"
          value={lastEventAt ? dateTime(lastEventAt).split(" · ")[0] : "—"}
          detail={lastEventAt ? dateTime(lastEventAt).split(" · ")[1] : "chưa có dữ liệu"}
        />
        <MetricCard
          icon={Radio}
          label="DAH tự động"
          value="23:58"
          detail="tự đóng phiên còn mở"
        />
      </div>

      <div className="mb-5 flex flex-wrap items-center justify-between gap-3 border-b border-slate-200">
        <div className="tabs border-b-0">
          {workspaceTabs.map(([key, label, open, total]) => (
            <button
              key={key}
              className={`tab ${workspaceView === key ? "active" : ""}`}
              onClick={() => setWorkspaceView(key)}
            >
              {label}
              <span className="ml-2 text-[11px] text-slate-400">
                {key === "events" ? `${open} cần xử lý` : `${open} mở · ${total} lượt`}
              </span>
            </button>
          ))}
        </div>
        {workspaceView !== "events" && (
          <div className="flex flex-wrap items-center gap-3 pb-2">
            <div className="tabs border-b-0">
              {[
                ["today", "Hôm nay"],
                ["yesterday", "Hôm qua"],
                ["custom", "Chọn ngày"],
              ].map(([key, label]) => (
                <button
                  key={key}
                  className={`tab ${dateView === key ? "active" : ""}`}
                  onClick={() => changeDateView(key)}
                >
                  {label}
                </button>
              ))}
            </div>
            {dateView === "custom" && (
              <div className="w-44">
                <DateInput
                  value={customDate}
                  onChange={(value) => {
                    setCustomDate(value || today);
                    setMemberPage(1);
                    setEmployeePage(1);
                  }}
                />
              </div>
            )}
          </div>
        )}
      </div>

      {workspaceView !== "events" ? (
        <section>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-[15px] font-semibold text-slate-950">{currentAttendance.title}</h2>
              <p className="mt-1 text-xs text-slate-500">{currentAttendance.description}</p>
            </div>
            <Button
              type="button"
              variant="secondary"
              onClick={() => currentAttendance.query.refetch()}
              loading={currentAttendance.query.isFetching}
              loadingText="Đang tải..."
            >
              <RefreshCw size={14} /> Làm mới tab
            </Button>
          </div>

          <div className="mb-5 rounded-lg border border-slate-200 bg-white">
            <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
              <div>
                <h3 className="text-sm font-semibold text-slate-950">
                  {workspaceView === "employee" ? "Ca đang mở" : "Khách đang trong phòng"}
                </h3>
                <p className="mt-0.5 text-xs text-slate-500">
                  {workspaceView === "employee"
                    ? "Các ca này sẽ được tự động đóng lúc 23:58 nếu chưa check-out."
                    : "Checkout khách là dữ liệu phụ; lượt vào là tín hiệu chính."}
                </p>
              </div>
              <span className="pill">{currentAttendance.activeRows.length} đang mở</span>
            </div>
            {workspaceView === "member" && warningSessions.length > 0 && (
              <div className="border-b border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                <div className="flex items-start gap-2">
                  <AlertTriangle size={17} className="mt-0.5 shrink-0" />
                  <div>
                    <strong>Có {warningSessions.length} khách đang ở phòng cần kiểm tra gói.</strong>
                    <p className="mt-1 text-xs leading-5">
                      Bao gồm khách chưa kích hoạt, gói bảo lưu/tạm dừng hoặc gói đã hết hạn.
                    </p>
                  </div>
                </div>
              </div>
            )}
            <div className="space-y-2 p-3">
              {currentAttendance.activeRows.length ? (
                currentAttendance.activeRows.map((row) => (
                  <ActiveSessionRow
                    key={row.id}
                    row={row}
                    checkout={checkout}
                    mode={workspaceView}
                  />
                ))
              ) : (
                <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-8 text-center text-sm text-slate-500">
                  {currentAttendance.activeEmpty}
                </div>
              )}
            </div>
          </div>

          <DataTable
            rows={currentAttendance.rows}
            columns={attendanceColumns}
            loading={currentAttendance.query.isLoading}
            error={currentAttendance.query.error}
            onRetry={currentAttendance.query.refetch}
            emptyTitle={currentAttendance.emptyTitle}
            emptyDescription={currentAttendance.emptyDescription}
            density={workspaceView === "employee" ? "compact" : "standard"}
          />
          <Pagination
            data={currentAttendance.query.data?.pagination}
            pageSize={currentAttendance.pageSize}
            onPage={currentAttendance.setPage}
            onPageSize={(value) => {
              currentAttendance.setPageSize(value);
              currentAttendance.setPage(1);
            }}
          />
        </section>
      ) : (
        <section>
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-[15px] font-semibold text-slate-950">Sự kiện DAH</h2>
              <p className="mt-1 text-xs text-slate-500">
                Inbox kỹ thuật cho face chưa liên kết, lượt bị từ chối và quét lặp.
              </p>
            </div>
            <Button
              type="button"
              variant="secondary"
              onClick={() => events.refetch()}
              loading={events.isFetching}
              loadingText="Đang tải..."
            >
              <RefreshCw size={14} /> Làm mới event
            </Button>
          </div>
          <div className="tabs mb-4">
            {eventViews.map(([key, label]) => (
              <button
                key={key}
                className={`tab ${eventView === key ? "active" : ""}`}
                onClick={() => {
                  setEventView(key);
                  setEventPage(1);
                }}
              >
                {label}
              </button>
            ))}
          </div>
          <DataTable
            rows={events.data?.items}
            columns={eventColumns}
            loading={events.isLoading}
            error={events.error}
            onRetry={events.refetch}
            emptyTitle="Chưa nhận được event DAH"
            emptyDescription="Event sẽ xuất hiện khi DAH gửi webhook Verify/Snap."
          />
          <Pagination
            data={events.data?.pagination}
            pageSize={eventPageSize}
            onPage={setEventPage}
            onPageSize={(value) => {
              setEventPageSize(value);
              setEventPage(1);
            }}
          />
        </section>
      )}
    </>
  );
}
