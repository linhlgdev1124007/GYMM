import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Activity, Link2, Radio, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../../services/api";
import { PageHeader } from "../../components/common/PageHeader";
import { Button } from "../../components/ui/Button";
import { DataTable } from "../../components/ui/DataTable";
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

export function CheckinPage() {
  const [eventView, setEventView] = useState("all");
  const recent = useQuery({
    queryKey: ["checkins"],
    queryFn: () => api("/api/checkins?limit=40"),
    refetchInterval: 30000,
  });
  const events = useQuery({
    queryKey: ["dah-events", eventView],
    queryFn: () => api(`/api/dah/events?view=${eventView}&limit=60`),
    refetchInterval: 5000,
  });
  const activeSessions = recent.data?.filter((row) => row.status === "open") || [];
  const lastEvent = recent.data?.[0];
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
            onClick={() => recent.refetch()}
            loading={recent.isFetching}
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
            Màn hình dành cho dữ liệu vào/ra tự động từ DAH, không thao tác thủ công tại đây.
          </p>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <span className="text-xs text-slate-500">Đang ở phòng</span>
          <strong className="mt-1 block text-2xl text-slate-950">{activeSessions.length}</strong>
          <span className="text-xs text-slate-400">phiên chưa ghi nhận giờ ra</span>
        </div>
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <span className="text-xs text-slate-500">Sự kiện mới nhất</span>
          <strong className="mt-2 block text-sm text-slate-950">
            {lastEvent ? dateTime(lastEvent.checkedInAt) : "Chưa có dữ liệu"}
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
          <div className="grid grid-cols-3 gap-3 max-[900px]:grid-cols-2 max-[600px]:grid-cols-1">
            {activeSessions.map((row) => {
              const name = row.employeeName || row.memberName;
              const content = (
                <>
                <div className="flex items-center gap-3">
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
                  </div>
                </div>
                </>
              );
              return row.employeeId ? (
                <div
                  key={row.id}
                  className="rounded-lg border border-slate-200 bg-white p-4"
                >
                  {content}
                </div>
              ) : (
                <Link
                  key={row.id}
                  to={`/members/${row.memberId}`}
                  className="rounded-lg border border-slate-200 bg-white p-4 transition hover:border-blue-300 hover:shadow-sm"
                >
                  {content}
                </Link>
              );
            })}
          </div>
        </section>
      )}

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
              onClick={() => setEventView(key)}
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
      </section>
    </>
  );
}
