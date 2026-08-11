import { useQuery } from "@tanstack/react-query";
import { Activity, Radio, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../../services/api";
import { PageHeader } from "../../components/common/PageHeader";
import { Button } from "../../components/ui/Button";
import { DataTable } from "../../components/ui/DataTable";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { dateTime } from "../../utils/format";

export function CheckinPage() {
  const recent = useQuery({
    queryKey: ["checkins"],
    queryFn: () => api("/api/checkins?limit=40"),
    refetchInterval: 30000,
  });
  const activeSessions = recent.data?.filter((row) => row.status === "open") || [];
  const lastEvent = recent.data?.[0];
  const columns = [
    {
      key: "member",
      label: "Hội viên",
      render: (row) => (
        <Link className="hover:underline" to={`/members/${row.memberId}`}>
          <span className="cell-primary">{row.memberName}</span>
          <span className="cell-secondary block">{row.memberCode}</span>
        </Link>
      ),
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
            {activeSessions.map((row) => (
              <Link
                key={row.id}
                to={`/members/${row.memberId}`}
                className="rounded-lg border border-slate-200 bg-white p-4 transition hover:border-blue-300 hover:shadow-sm"
              >
                <div className="flex items-center gap-2">
                  <Activity size={16} className="text-emerald-600" />
                  <strong className="text-sm text-slate-950">{row.memberName}</strong>
                </div>
                <p className="mt-1 text-xs text-slate-400">
                  {row.memberCode} · Vào lúc {dateTime(row.checkedInAt)}
                </p>
              </Link>
            ))}
          </div>
        </section>
      )}

      <section>
        <div className="section-header">
          <div>
            <h2>Lịch sử điểm danh DAH</h2>
            <p>40 sự kiện vào/ra gần nhất được đồng bộ về hệ thống.</p>
          </div>
        </div>
        <DataTable
          rows={recent.data}
          columns={columns}
          loading={recent.isLoading}
          error={recent.error}
          onRetry={recent.refetch}
          emptyTitle="Chưa nhận được dữ liệu điểm danh"
          emptyDescription="Sự kiện sẽ xuất hiện khi DAH gửi webhook thành công."
        />
      </section>
    </>
  );
}
