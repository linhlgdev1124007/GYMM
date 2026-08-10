import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Search, UserRound, XCircle } from "lucide-react";
import { toast } from "sonner";
import { api, queryString } from "../../services/api";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";
import { PageHeader } from "../../components/common/PageHeader";
import { Button } from "../../components/ui/Button";
import { DataTable } from "../../components/ui/DataTable";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { dateTime, shortDate } from "../../utils/format";

export function CheckinPage() {
  const client = useQueryClient();
  const [search, setSearch] = useState("");
  const q = useDebouncedValue(search, 250);
  const [selected, setSelected] = useState(null);
  const candidates = useQuery({
    queryKey: ["checkin-candidates", q],
    queryFn: () => api(`/api/checkins/candidates?${queryString({ q })}`),
    enabled: q.length > 1,
  });
  const recent = useQuery({
    queryKey: ["checkins"],
    queryFn: () => api("/api/checkins?limit=40"),
    refetchInterval: 30000,
  });
  const refresh = () => {
    client.invalidateQueries({ queryKey: ["checkins"] });
    client.invalidateQueries({ queryKey: ["dashboard"] });
    client.invalidateQueries({ queryKey: ["member"] });
  };
  const checkin = useMutation({
    mutationFn: () =>
      api("/api/checkins", { method: "POST", body: { memberId: selected.id } }),
    onSuccess: () => {
      refresh();
      setSelected(null);
      setSearch("");
      toast.success("Check-in thành công.");
    },
    onError: (e) => toast.error(e.message),
  });
  const checkout = useMutation({
    mutationFn: (id) =>
      api(`/api/checkins/${id}/checkout`, { method: "PATCH" }),
    onSuccess: () => {
      refresh();
      toast.success("Đã check-out.");
    },
  });
  const columns = [
    {
      key: "member",
      label: "Hội viên",
      render: (r) => (
        <div>
          <span className="cell-primary">{r.memberName}</span>
          <div className="cell-secondary">{r.memberCode}</div>
        </div>
      ),
    },
    {
      key: "checkedInAt",
      label: "Giờ vào",
      render: (r) => dateTime(r.checkedInAt),
    },
    {
      key: "checkedOutAt",
      label: "Giờ ra",
      render: (r) => dateTime(r.checkedOutAt),
    },
    {
      key: "status",
      label: "Trạng thái",
      render: (r) => <StatusBadge status={r.status} />,
    },
    {
      key: "action",
      label: "",
      render: (r) =>
        r.status === "open" && (
          <Button
            size="sm"
            variant="secondary"
            onClick={() => checkout.mutate(r.id)}
          >
            Check-out
          </Button>
        ),
    },
  ];
  return (
    <>
      <PageHeader
        eyebrow="Vận hành"
        title="Check-in"
        description="Tìm, xác minh gói tập và check-in hội viên trong vài thao tác."
      />
      <div className="grid grid-cols-[minmax(0,1fr)_360px] gap-6 max-[900px]:grid-cols-1">
        <section>
          <div className="section-header">
            <div>
              <h2>Check-in hội viên</h2>
              <p>Tìm theo tên, điện thoại, mã hội viên hoặc MBS.</p>
            </div>
          </div>
          <div className="relative">
            <div className="search-input h-11">
              <Search size={17} />
              <input
                autoFocus
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setSelected(null);
                }}
                placeholder="Tìm hội viên…"
              />
            </div>
            {q.length > 1 && !selected && (
              <div className="absolute z-10 mt-1 w-full rounded-md border border-slate-200 bg-white p-1 shadow-popover">
                {candidates.isLoading ? (
                  <div className="p-3">
                    <div className="skeleton h-8" />
                  </div>
                ) : (
                  candidates.data?.map((row) => (
                    <button
                      key={row.id}
                      className="flex w-full items-center gap-3 rounded px-3 py-2.5 text-left hover:bg-slate-50"
                      onClick={() => setSelected(row)}
                    >
                      <div className="avatar avatar-md">
                        <UserRound size={15} />
                      </div>
                      <div className="flex-1">
                        <strong className="text-[13px] font-medium">
                          {row.name}
                        </strong>
                        <p className="text-xs text-slate-400">
                          {row.code} · {row.phone}
                        </p>
                      </div>
                      {row.eligible ? (
                        <CheckCircle2 size={17} className="text-emerald-600" />
                      ) : (
                        <XCircle size={17} className="text-red-500" />
                      )}
                    </button>
                  ))
                )}
                {!candidates.isLoading && !candidates.data?.length && (
                  <p className="px-3 py-6 text-center text-xs text-slate-400">
                    Không tìm thấy hội viên.
                  </p>
                )}
              </div>
            )}
          </div>
          {selected && (
            <div className="mt-4 border-y border-slate-200 bg-white p-5">
              <div className="flex items-start justify-between">
                <div>
                  <span className="text-xs text-slate-400">
                    {selected.code}
                  </span>
                  <h3 className="mt-1 text-base font-semibold">
                    {selected.name}
                  </h3>
                  <p className="mt-1 text-xs text-slate-500">
                    {selected.phone}
                  </p>
                </div>
                <button
                  className="icon-button"
                  onClick={() => setSelected(null)}
                  aria-label="Bỏ chọn"
                >
                  <XCircle size={18} />
                </button>
              </div>
              <div className="mt-5 grid grid-cols-2 gap-4 border-t border-slate-100 pt-4">
                <div>
                  <span className="text-[11px] uppercase tracking-wide text-slate-400">
                    Gói tập
                  </span>
                  <p className="mt-1 text-[13px] font-medium">
                    {selected.membership || "Chưa có gói"}
                  </p>
                </div>
                <div>
                  <span className="text-[11px] uppercase tracking-wide text-slate-400">
                    Hết hạn
                  </span>
                  <p className="mt-1 text-[13px] font-medium">
                    {shortDate(selected.expiresAt)}
                  </p>
                </div>
              </div>
              <div
                className={`mt-4 flex items-center gap-2 rounded-md px-3 py-2.5 text-xs ${selected.eligible ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"}`}
              >
                {selected.eligible ? (
                  <CheckCircle2 size={16} />
                ) : (
                  <XCircle size={16} />
                )}{" "}
                {selected.eligible ? "Gói tập còn hiệu lực" : selected.reason}
              </div>
              <Button
                className="mt-4 w-full"
                size="lg"
                disabled={!selected.eligible || checkin.isPending}
                onClick={() => checkin.mutate()}
              >
                {checkin.isPending ? "Đang check-in…" : "Xác nhận check-in"}
              </Button>
            </div>
          )}
        </section>
        <aside>
          <div className="section-header">
            <div>
              <h2>Đang ở phòng</h2>
              <p>Các phiên chưa check-out</p>
            </div>
          </div>
          <div className="border-y border-slate-200 bg-white divide-y divide-slate-100">
            {recent.data
              ?.filter((r) => r.status === "open")
              .map((row) => (
                <div
                  key={row.id}
                  className="flex items-center justify-between px-3 py-3"
                >
                  <div>
                    <strong className="text-[13px] font-medium">
                      {row.memberName}
                    </strong>
                    <p className="text-[11px] text-slate-400">
                      Vào lúc {dateTime(row.checkedInAt)}
                    </p>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => checkout.mutate(row.id)}
                  >
                    Check-out
                  </Button>
                </div>
              ))}
            {!recent.data?.some((r) => r.status === "open") && (
              <p className="px-3 py-8 text-center text-xs text-slate-400">
                Không có phiên đang mở.
              </p>
            )}
          </div>
        </aside>
      </div>
      <section className="mt-7">
        <div className="section-header">
          <div>
            <h2>Check-in gần đây</h2>
            <p>Lịch sử hoạt động tại quầy</p>
          </div>
        </div>
        <DataTable
          rows={recent.data}
          columns={columns}
          loading={recent.isLoading}
        />
      </section>
    </>
  );
}
