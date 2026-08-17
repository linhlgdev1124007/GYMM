import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { format, parseISO } from "date-fns";
import {
  AlertTriangle,
  CheckCircle2,
  Dumbbell,
  RefreshCw,
  UserRound,
} from "lucide-react";
import { Link } from "react-router-dom";
import { PageHeader } from "../../components/common/PageHeader";
import { Button } from "../../components/ui/Button";
import { Pagination } from "../../components/ui/Pagination";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { api, queryString } from "../../services/api";
import { notify } from "../../services/notify";
import { dateTime, formatPhone, shortDate } from "../../utils/format";

function avatarText(name = "") {
  return name
    .trim()
    .split(/\s+/)
    .slice(-2)
    .map((part) => part[0])
    .join("")
    .toUpperCase() || "HV";
}

function slotText(slots = []) {
  return slots.map((slot) => `${slot.day} ${slot.time}`).join(", ") || "Hôm nay";
}

function HoverDetail({ item }) {
  const pt = item.ptToday?.[0];
  return (
    <div className="pointer-events-none absolute left-0 top-[calc(100%+8px)] z-20 hidden w-[360px] rounded-lg border border-slate-200 bg-white p-4 text-sm shadow-popover group-hover:block">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <strong className="text-slate-950">{item.member.name}</strong>
          <p className="mt-0.5 text-xs text-slate-500">
            {item.member.code} · {formatPhone(item.member.phone) || "Chưa có SĐT"}
          </p>
        </div>
        <StatusBadge status={item.member.status} />
      </div>
      <div className="space-y-2 text-xs text-slate-600">
        <p>
          <span className="font-medium text-slate-800">Check-in:</span>{" "}
          {dateTime(item.checkedInAt)}
        </p>
        <p>
          <span className="font-medium text-slate-800">Gói gym:</span>{" "}
          {item.gymMembership?.package?.name || "Chưa có gói"}
        </p>
        <p>
          <span className="font-medium text-slate-800">Hạn gói:</span>{" "}
          {shortDate(item.gymMembership?.expiresAt)}
        </p>
        <p>
          <span className="font-medium text-slate-800">PT hôm nay:</span>{" "}
          {pt ? `${pt.type} · ${slotText(pt.todaySlots)} · còn ${pt.remainingSessions}/${pt.totalSessions} buổi` : "Không có"}
        </p>
        {pt?.coaches?.length ? (
          <p>
            <span className="font-medium text-slate-800">Coach:</span>{" "}
            {pt.coaches.map((coach) => coach.name).join(", ")}
          </p>
        ) : null}
      </div>
    </div>
  );
}

function ProcessingCard({ item, onDecision, pendingKey }) {
  const pt = item.ptToday?.[0];
  const pendingPt = pendingKey === `${item.sessionId}:pt`;
  const pendingRegular = pendingKey === `${item.sessionId}:regular`;
  return (
    <article className="grid grid-cols-[minmax(0,1.15fr)_minmax(190px,0.85fr)_minmax(200px,1fr)_auto] items-center gap-4 border-b border-slate-200 bg-white px-4 py-3 last:border-b-0 max-[1080px]:grid-cols-1">
      <div className="group relative min-w-0">
        <Link to={`/members/${item.member.id}`} className="flex min-w-0 items-center gap-3 hover:underline">
          <div className="avatar avatar-md">
            {item.member.avatarImageData ? <img src={item.member.avatarImageData} alt="" /> : avatarText(item.member.name)}
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <UserRound size={15} className="shrink-0 text-slate-400" />
              <strong className="truncate text-slate-950">{item.member.name}</strong>
            </div>
            <p className="mt-0.5 truncate text-xs text-slate-500">
              {item.member.code} · vào {format(parseISO(item.checkedInAt), "HH:mm")}
            </p>
          </div>
        </Link>
        <HoverDetail item={item} />
      </div>

      <div className={`rounded-md border px-3 py-2 ${item.gymDanger ? "border-red-200 bg-red-50" : "border-slate-200 bg-slate-50"}`}>
        <div className="flex items-center justify-between gap-2">
          <span className="truncate text-xs font-medium text-slate-500">Gói tập</span>
          <StatusBadge status={item.gymMembership?.status || "blocked"} />
        </div>
        <p className={`mt-1 truncate text-sm font-semibold ${item.gymDanger ? "text-red-700" : "text-slate-950"}`}>
          {item.gymMembership?.package?.name || "Chưa có gói"}
        </p>
        <p className={`mt-0.5 text-xs ${item.gymDanger ? "text-red-600" : "text-slate-500"}`}>
          Hạn {shortDate(item.gymMembership?.expiresAt)}
          {item.gymDangerReason ? ` · ${item.gymDangerReason}` : ""}
        </p>
      </div>

      <div className="rounded-md border border-blue-200 bg-blue-50 px-3 py-2">
        <div className="flex items-center gap-2 text-xs font-medium text-blue-700">
          <Dumbbell size={14} />
          <span>Buổi PT hôm nay</span>
        </div>
        <p className="mt-1 truncate text-sm font-semibold text-slate-950">
          {pt ? `${pt.type} · ${slotText(pt.todaySlots)}` : "Không có lịch"}
        </p>
        <p className="mt-0.5 truncate text-xs text-slate-500">
          {pt ? `Còn ${pt.remainingSessions}/${pt.totalSessions} buổi · ${pt.coaches?.map((coach) => coach.name).join(", ") || "Chưa phân Coach"}` : "Không cần xử lý"}
        </p>
      </div>

      <div className="flex justify-end gap-2">
        <Button
          size="sm"
          variant="primary"
          loading={pendingPt}
          loadingText="Đang trừ..."
          disabled={!pt || pendingRegular}
          onClick={() => onDecision(item, "pt", pt?.id)}
        >
          <CheckCircle2 size={14} /> Tập PT
        </Button>
        <Button
          size="sm"
          variant="secondary"
          loading={pendingRegular}
          loadingText="Đang lưu..."
          disabled={pendingPt}
          onClick={() => onDecision(item, "regular")}
        >
          Tập Thường
        </Button>
      </div>
    </article>
  );
}

export function MemberProcessingPage() {
  const client = useQueryClient();
  const today = format(new Date(), "yyyy-MM-dd");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const query = useQuery({
    queryKey: ["member-processing", today, page, pageSize],
    queryFn: () => api(`/api/member-processing?${queryString({ day: today, page, pageSize })}`),
    refetchInterval: 2000,
  });
  const decision = useMutation({
    mutationFn: ({ item, decision: choice, ptEnrollmentId }) =>
      api(`/api/member-processing/${item.sessionId}`, {
        method: "POST",
        body: { decision: choice, ptEnrollmentId },
      }),
    onSuccess: (_data, variables) => {
      client.invalidateQueries({ queryKey: ["member-processing"] });
      client.invalidateQueries({ queryKey: ["training"] });
      client.invalidateQueries({ queryKey: ["checkins"] });
      notify.success(variables.decision === "pt" ? "Đã ghi nhận tập PT và trừ 1 buổi." : "Đã ghi nhận tập thường.");
    },
    onError: (error) => notify.errorFrom(error, "Không thể xử lý lượt check-in này."),
  });
  const pendingKey = decision.isPending
    ? `${decision.variables.item.sessionId}:${decision.variables.decision}`
    : null;
  const items = query.data?.items || [];
  return (
    <>
      <PageHeader
        eyebrow="Vận hành"
        title="Xử lý hội viên"
        description="Chỉ hiển thị hội viên đã check-in hôm nay và có lịch PT hôm nay."
        action={(
          <Button
            variant="secondary"
            loading={query.isFetching}
            loadingText="Đang tải..."
            onClick={() => query.refetch()}
          >
            <RefreshCw size={15} /> Làm mới
          </Button>
        )}
      />

      <section className="overflow-visible rounded-lg border border-slate-200 bg-white">
        <div className="flex items-center justify-between gap-3 border-b border-slate-200 px-4 py-3">
          <div>
            <h2 className="text-[15px] font-semibold text-slate-950">
              Queue PT hôm nay
            </h2>
            <p className="mt-1 text-xs text-slate-500">
              Chọn Tập PT để trừ buổi, hoặc Tập Thường để bỏ qua buổi PT của lượt check-in này.
            </p>
          </div>
          <span className="pill">{query.data?.pagination?.total || 0} cần xử lý</span>
        </div>
        {query.error ? (
          <div className="flex items-center gap-2 px-4 py-8 text-sm text-red-700">
            <AlertTriangle size={17} />
            <span>{query.error.message}</span>
          </div>
        ) : query.isLoading ? (
          <div className="space-y-3 p-4">
            <div className="skeleton h-16 w-full" />
            <div className="skeleton h-16 w-full" />
            <div className="skeleton h-16 w-full" />
          </div>
        ) : items.length ? (
          items.map((item) => (
            <ProcessingCard
              key={item.sessionId}
              item={item}
              pendingKey={pendingKey}
              onDecision={(row, choice, ptEnrollmentId) =>
                decision.mutate({ item: row, decision: choice, ptEnrollmentId })
              }
            />
          ))
        ) : (
          <div className="px-4 py-12 text-center">
            <Dumbbell className="mx-auto text-slate-300" size={32} />
            <h3 className="mt-3 text-sm font-semibold text-slate-950">
              Không có hội viên cần xử lý
            </h3>
            <p className="mt-1 text-sm text-slate-500">
              Queue chỉ nhận hội viên đã check-in hôm nay và có lịch PT hôm nay.
            </p>
          </div>
        )}
      </section>
      <Pagination
        data={query.data?.pagination}
        pageSize={pageSize}
        onPage={setPage}
        onPageSize={(value) => {
          setPageSize(value);
          setPage(1);
        }}
      />
    </>
  );
}
