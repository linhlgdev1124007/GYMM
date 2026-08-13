import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { format, subDays } from "date-fns";
import { Activity, AlertTriangle, Link2, Radio, RefreshCw } from "lucide-react";
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

function PersonCell({ row }) {
  const name = row.employeeName || row.memberName || row.faceName || "Face chưa gán";
  const image = row.memberAvatarImageData || row.imageData;
  const details = row.employeeId
    ? `${row.employeeCode} · Nhân viên`
    : row.memberId
      ? `${row.memberCode}${row.memberStatus === "lead" ? " · Tiềm năng" : ""}`
      : row.personUuid || row.personId || "Không có UUID";
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

function ActiveSessionCard({ row, checkout }) {
  const name = row.employeeName || row.memberName;
  const content = (
    <div className="flex items-start justify-between gap-3">
      <div className="flex min-w-0 items-center gap-3">
        <CheckinAvatar image={row.memberAvatarImageData} name={name} />
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Activity size={16} className="shrink-0 text-emerald-600" />
            <strong className="truncate text-sm text-slate-950">{name}</strong>
          </div>
          <p className="mt-1 truncate text-xs text-slate-400">
            {row.employeeId
              ? `${row.employeeCode} · Nhân viên`
              : `${row.memberCode}${row.memberStatus === "lead" ? " · Tiềm năng" : ""}`} · Vào lúc {dateTime(row.checkedInAt)}
          </p>
          {row.memberAccessWarning && (
            <p className="mt-2 flex items-center gap-1.5 rounded-md bg-amber-50 px-2 py-1 text-xs font-medium text-amber-800">
              <AlertTriangle size={13} />
              <span className="truncate">{row.memberAccessWarning}</span>
            </p>
          )}
        </div>
      </div>
      <Button
        size="sm"
        variant="secondary"
        loading={checkout.isPending && checkout.variables === row.id}
        loadingText="Đang checkout…"
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          checkout.mutate(row.id);
        }}
      >
        Checkout
      </Button>
    </div>
  );
  return row.employeeId ? (
    <div className="rounded-lg border border-slate-200 bg-white p-4">{content}</div>
  ) : (
    <Link
      to={`/members/${row.memberId}`}
      className="rounded-lg border border-slate-200 bg-white p-4 transition hover:border-blue-300 hover:shadow-sm"
    >
      {content}
    </Link>
  );
}

export function CheckinPage() {
  const client = useQueryClient();
  const [eventView, setEventView] = useState("all");
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
      api(
        `/api/dah/events?${queryString({ view: eventView, page: eventPage, pageSize: eventPageSize })}`,
      ),
    refetchInterval: 5000,
  });
  const checkout = useMutation({
    mutationFn: (sessionId) =>
      api(`/api/checkins/${sessionId}/checkout`, { method: "PATCH" }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["checkins"] });
      client.invalidateQueries({ queryKey: ["dashboard"] });
      notify.success("Đã checkout phiên đang mở.");
    },
    onError: (error) =>
      notify.errorFrom(error, "Không thể checkout phiên này. Vui lòng thử lại."),
  });
  const memberCheckins = memberRecent.data?.items || [];
  const employeeCheckins = employeeRecent.data?.items || [];
  const activeSessions = [...memberCheckins, ...employeeCheckins].filter((row) => row.status === "open");
  const activeMemberSessions = memberCheckins.filter((row) => row.status === "open");
  const activeEmployeeSessions = employeeCheckins.filter((row) => row.status === "open");
  const warningSessions = activeSessions.filter((row) => row.memberAccessWarning);
  const lastEventAt = [memberRecent.data?.lastEventAt, employeeRecent.data?.lastEventAt]
    .filter(Boolean)
    .sort()
    .at(-1);
  const activeCount = (memberRecent.data?.activeCount || 0) + (employeeRecent.data?.activeCount || 0);
  const eventViews = [
    ["all", "Tất cả"],
    ["allowed", "Được vào/ra"],
    ["denied", "Từ chối"],
    ["unknown", "Face chưa gán"],
    ["duplicates", "Quét lặp"],
  ];
  const columns = [
    {
      key: "person",
      label: "Người vào/ra",
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
    {
      key: "status",
      label: "Trạng thái",
      render: (row) => <StatusBadge status={row.status} />,
    },
  ];

  return (
    <>
      <PageHeader
        eyebrow="Vận hành"
        title="Điểm danh"
        description="Theo dõi dữ liệu vào/ra được hệ thống DAH tự động gửi về."
        action={(
          <Button
            variant="secondary"
            onClick={() => {
              memberRecent.refetch();
              employeeRecent.refetch();
            }}
            loading={memberRecent.isFetching || employeeRecent.isFetching}
            loadingText="Đang đồng bộ…"
          >
            <RefreshCw size={15} /> Làm mới dữ liệu
          </Button>
        )}
      />

      <div className="mb-7 grid grid-cols-3 gap-4 max-[760px]:grid-cols-1">
        <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4">
          <div className="flex items-center gap-2 text-sm font-semibold text-emerald-800">
            <Radio size={17} /> Chế độ tự động
          </div>
          <p className="mt-1 text-xs leading-5 text-emerald-700">
            Dữ liệu vào/ra tự động từ DAH; có thể checkout thủ công khi phiên bị quên hoặc lỗi.
          </p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <span className="text-xs text-slate-500">Đang ở phòng</span>
          <strong className="mt-1 block text-2xl text-slate-950">{activeCount}</strong>
          <span className="text-xs text-slate-400">phiên chưa ghi nhận giờ ra trong ngày đang xem</span>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <span className="text-xs text-slate-500">Sự kiện mới nhất</span>
          <strong className="mt-2 block text-sm text-slate-950">
            {lastEventAt ? dateTime(lastEventAt) : "Chưa có dữ liệu"}
          </strong>
          <span className="text-xs text-slate-400">tự làm mới mỗi 30 giây</span>
        </div>
      </div>

      {activeSessions.length > 0 && (
        <section className="mb-7">
          <div className="section-header">
            <div>
              <h2>Đang ở phòng</h2>
              <p>Các phiên DAH chưa gửi thời điểm ra.</p>
            </div>
          </div>
          {warningSessions.length > 0 && (
            <div className="mb-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
              <div className="flex items-start gap-2">
                <AlertTriangle size={17} className="mt-0.5 shrink-0" />
                <div>
                  <strong>Có {warningSessions.length} người đang ở phòng cần kiểm tra gói.</strong>
                  <p className="mt-1 text-xs leading-5">
                    Bao gồm khách chưa kích hoạt, gói bảo lưu/tạm dừng hoặc gói đã hết hạn.
                  </p>
                </div>
              </div>
            </div>
          )}
          <div className="grid grid-cols-2 gap-4 max-[900px]:grid-cols-1">
            <div>
              <div className="mb-2 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-slate-900">Khách đang ở phòng</h3>
                <span className="text-xs text-slate-500">{activeMemberSessions.length} phiên</span>
              </div>
              <div className="grid gap-3">
                {activeMemberSessions.length ? (
                  activeMemberSessions.map((row) => (
                    <ActiveSessionCard key={row.id} row={row} checkout={checkout} />
                  ))
                ) : (
                  <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">
                    Không có khách đang ở phòng.
                  </div>
                )}
              </div>
            </div>
            <div>
              <div className="mb-2 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-slate-900">Nhân viên đang ở phòng</h3>
                <span className="text-xs text-slate-500">{activeEmployeeSessions.length} phiên</span>
              </div>
              <div className="grid gap-3">
                {activeEmployeeSessions.length ? (
                  activeEmployeeSessions.map((row) => (
                    <ActiveSessionCard key={row.id} row={row} checkout={checkout} />
                  ))
                ) : (
                  <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 p-4 text-sm text-slate-500">
                    Không có nhân viên đang ở phòng.
                  </div>
                )}
              </div>
            </div>
          </div>
        </section>
      )}

      <section className="mb-7">
        <div className="section-header">
          <div>
            <h2>Lịch sử điểm danh</h2>
            <p>Xem lượt vào/ra theo ngày và phân trang danh sách.</p>
          </div>
        </div>
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div className="tabs">
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
      </section>

      <section className="mb-7">
        <div className="section-header">
          <div>
            <h2>Điểm danh khách</h2>
            <p>Lượt vào/ra của hội viên và khách tiềm năng theo ngày.</p>
          </div>
          <span className="pill">{memberRecent.data?.pagination?.total || 0} lượt</span>
        </div>
        <DataTable
          rows={memberCheckins}
          columns={columns}
          loading={memberRecent.isLoading}
          error={memberRecent.error}
          onRetry={memberRecent.refetch}
          emptyTitle="Chưa có lượt điểm danh khách"
          emptyDescription="Dữ liệu sẽ xuất hiện khi hội viên hoặc khách quét DAH trong ngày này."
        />
        <Pagination
          data={memberRecent.data?.pagination}
          pageSize={memberPageSize}
          onPage={setMemberPage}
          onPageSize={(value) => {
            setMemberPageSize(value);
            setMemberPage(1);
          }}
        />
      </section>

      <section className="mb-7">
        <div className="section-header">
          <div>
            <h2>Điểm danh nhân viên</h2>
            <p>Lượt vào/ra của nhân viên được nhận diện từ DAH.</p>
          </div>
          <span className="pill">{employeeRecent.data?.pagination?.total || 0} lượt</span>
        </div>
        <DataTable
          rows={employeeCheckins}
          columns={columns}
          loading={employeeRecent.isLoading}
          error={employeeRecent.error}
          onRetry={employeeRecent.refetch}
          emptyTitle="Chưa có lượt điểm danh nhân viên"
          emptyDescription="Dữ liệu sẽ xuất hiện khi nhân viên quét DAH trong ngày này."
        />
        <Pagination
          data={employeeRecent.data?.pagination}
          pageSize={employeePageSize}
          onPage={setEmployeePage}
          onPageSize={(value) => {
            setEmployeePageSize(value);
            setEmployeePage(1);
          }}
        />
      </section>

      <section>
        <div className="section-header">
          <div>
            <h2>Event DAH</h2>
            <p>Theo dõi quét thành công, từ chối, face chưa gán và lượt quét lặp.</p>
          </div>
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
          columns={[
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
              render: (row) => <StatusBadge status={row.status === "processed" ? "active" : row.status === "duplicate" ? "pending" : row.status === "unknown" ? "lead" : row.status === "denied" || row.status === "rejected" ? "blocked" : row.status} />,
            },
            {
              key: "action",
              label: "Thao tác",
              sortable: false,
              render: (row) =>
                row.status === "unknown" ? (
                  <Link className="btn btn-secondary btn-sm" to="/members?create=1">
                    <Link2 size={13} /> Liên kết
                  </Link>
                ) : (
                  <span className="cell-secondary">{row.action || "—"}</span>
                ),
            },
          ]}
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
    </>
  );
}
