import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  CalendarPlus,
  CreditCard,
  Dumbbell,
  Pencil,
  Plus,
  ReceiptText,
  ScanFace,
  TriangleAlert,
} from "lucide-react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../../services/api";
import { notify } from "../../services/notify";
import { Button } from "../../components/ui/Button";
import { DataTable } from "../../components/ui/DataTable";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { ScheduleSummary } from "../../components/ui/ScheduleSummary";
import { InlineEditField } from "../../components/ui/InlineEditField";
import { RowMenu } from "../../components/ui/RowMenu";
import { MemberEditForm } from "../../components/forms/MemberEditForm";
import { MembershipForm } from "../../components/forms/MembershipForm";
import { TrainingForm } from "../../components/forms/TrainingForm";
import { QuickPaymentForm } from "../../components/forms/QuickPaymentForm";
import { DebtDeadlineForm } from "../../components/forms/DebtDeadlineForm";
import { PaymentReceiptModal } from "../../components/forms/PaymentReceiptModal";
import { MembershipOperationsModal } from "../../components/forms/MembershipOperationsModal";
import { DahIdentityLinkModal } from "./DahIdentityLinkModal";
import { useAuth } from "../../app/AuthContext";
import {
  dateTime,
  formatPhone,
  initials,
  money,
  shortDate,
} from "../../utils/format";

const tabs = [
  ["overview", "Tổng quan"],
  ["memberships", "Lịch sử gói"],
  ["payments", "Thanh toán"],
  ["checkins", "Lịch sử check-in"],
  ["training", "PT & lịch tập"],
  ["notes", "Ghi chú"],
  ["activity", "Nhật ký"],
];

export function MemberDetailPage() {
  const { memberId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const client = useQueryClient();
  const [tab, setTab] = useState(() =>
    tabs.some(([key]) => key === searchParams.get("tab"))
      ? searchParams.get("tab")
      : "overview",
  );
  const [dialog, setDialog] = useState(null);
  const [selectedMembership, setSelectedMembership] = useState(null);
  const [membershipOperationAction, setMembershipOperationAction] = useState("");
  const [selectedTraining, setSelectedTraining] = useState(null);
  const [selectedPayment, setSelectedPayment] = useState(null);
  const [formError, setFormError] = useState("");
  const [identityLinkOpen, setIdentityLinkOpen] = useState(false);
  const memberQuery = useQuery({
    queryKey: ["member", memberId],
    queryFn: () => api(`/api/members/${memberId}`),
  });
  const options = useQuery({
    queryKey: ["member-options"],
    queryFn: () => api("/api/members/options"),
    staleTime: 300000,
  });
  const member = memberQuery.data;
  const refresh = () => {
    client.invalidateQueries({ queryKey: ["member", memberId] });
    client.invalidateQueries({ queryKey: ["members"] });
    client.invalidateQueries({ queryKey: ["memberships"] });
    client.invalidateQueries({ queryKey: ["training"] });
    client.invalidateQueries({ queryKey: ["dashboard"] });
  };
  const updateMember = useMutation({
    mutationFn: ({ payload }) =>
      api(`/api/members/${memberId}`, { method: "PATCH", body: payload }),
    onSuccess: (_data, variables) => {
      refresh();
      if (!variables.silent) {
        setDialog(null);
        notify.success(`Đã lưu hồ sơ ${member.name}.`);
      }
    },
    onError: (e, variables) => {
      if (!variables.silent) setFormError(e.message);
    },
  });
  const saveMembership = useMutation({
    mutationFn: ({ membership, data }) =>
      api(
        membership ? `/api/memberships/${membership.id}` : "/api/memberships",
        { method: membership ? "PATCH" : "POST", body: data },
      ),
    onSuccess: (_data, variables) => {
      refresh();
      setDialog(null);
      setSelectedMembership(null);
      if (variables.feedback?.amount) {
        notify.success(
          `Đã ghi nhận ${money(variables.feedback.amount)} cho ${member.name}.`,
        );
      } else if (variables.feedback?.expiresAt) {
        notify.success(
          `Đã lưu ${variables.feedback.planName} đến ${shortDate(variables.feedback.expiresAt)} cho ${member.name}.`,
        );
      } else {
        notify.success(`Đã cập nhật gói tập của ${member.name}.`);
      }
    },
    onError: (e) => setFormError(e.message),
  });
  const saveDeadline = useMutation({
    mutationFn: ({ membership, payload }) =>
      api(`/api/memberships/${membership.id}/debt-due-date`, {
        method: "PATCH",
        body: payload,
      }),
    onSuccess: () => {
      refresh();
      setDialog(null);
      setSelectedMembership(null);
      notify.success(`Đã lưu hạn thanh toán cho ${member.name}.`);
    },
    onError: (e) => setFormError(e.message),
  });
  const saveTraining = useMutation({
    mutationFn: ({ enrollment, payload }) =>
      api(
        enrollment
          ? `/api/training/${enrollment.id}`
          : `/api/members/${memberId}/training`,
        { method: enrollment ? "PATCH" : "POST", body: payload },
      ),
    onSuccess: () => {
      refresh();
      setDialog(null);
      setSelectedTraining(null);
      notify.success(`Đã cập nhật đăng ký PT của ${member.name}.`);
    },
    onError: (e) => setFormError(e.message),
  });
  const uploadReceipts = useMutation({
    mutationFn: ({ paymentId, data }) =>
      api(`/api/payments/${paymentId}/receipts`, {
        method: "POST",
        body: data,
      }),
    onSuccess: (payment) => {
      refresh();
      setSelectedPayment(payment);
      notify.success(`Đã thêm chứng từ cho ${payment.number}.`);
    },
    onError: (error) => setFormError(error.message),
  });
  const membershipOperation = useMutation({
    mutationFn: ({ action, membershipId, payload }) =>
      api(
        action === "freeze"
          ? `/api/memberships/${(selectedMembership || current).id}/freeze`
          : `/api/memberships/${membershipId || (selectedMembership || current).id}/actions`,
        { method: "POST", body: payload },
      ),
    onSuccess: (result, variables) => {
      refresh();
      client.invalidateQueries({ queryKey: ["alerts"] });
      client.invalidateQueries({ queryKey: ["audit-logs"] });
      setDialog(null);
      setSelectedMembership(null);
      if (variables.action === "freeze") {
        notify.success("Đã bảo lưu và cộng bù thời hạn gói.");
      } else {
        notify.success({
          title: result.summary,
          action:
            variables.action === "transfer"
              ? {
                  label: "Xem người nhận",
                  onClick: () => navigate(`/members/${result.customerId}`),
                }
              : undefined,
        });
      }
    },
    onError: (reason) => setFormError(reason.message),
  });
  if (memberQuery.isLoading)
    return (
      <div className="space-y-4">
        <div className="skeleton h-16 w-full" />
        <div className="skeleton h-14 w-full" />
        <div className="skeleton h-64 w-full" />
      </div>
    );
  if (memberQuery.isError)
    return <div className="inline-error">{memberQuery.error.message}</div>;
  const current = member.memberships[0];
  const displayStatus = current?.status || member.status;
  const canFinancial = ["admin", "manager", "receptionist"].includes(user.role);
  const canManageLifecycle = ["admin", "manager"].includes(user.role);
  const activeTraining = member.training.find((row) => row.status === "active");
  const canEditPt = canFinancial || (user.role === "coach" && !!activeTraining);
  const activeTrainingCoaches = activeTraining?.coaches || [];
  const lastCheckin = member.checkins[0];
  const daysLeft = current?.expiresAt
    ? Math.ceil((new Date(current.expiresAt) - new Date()) / 86400000)
    : null;
  const lifecycleActions = [];
  if (current?.status === "pending") {
    lifecycleActions.push(["activate", "Kích hoạt ngay"]);
  }
  if (current?.status === "suspended") {
    lifecycleActions.push(["activate", "Kích hoạt lại"]);
  }
  if (current?.status === "frozen") {
    lifecycleActions.push(["activate", "Kích hoạt lại"]);
  }
  if (current?.status === "active") {
    lifecycleActions.push(["suspend", "Tạm dừng"]);
    lifecycleActions.push(["freeze", "Bảo lưu"]);
    lifecycleActions.push(["adjust_days", "Cộng / trừ ngày"]);
  }
  if (["active", "pending", "frozen", "suspended"].includes(current?.status)) {
    lifecycleActions.push(["cancel", "Hủy dịch vụ"]);
  }
  const open = (name, record = null, operationAction = "") => {
    setFormError("");
    setMembershipOperationAction(name === "operations" ? operationAction : "");
    if (
      name === "membership" ||
      name === "payment" ||
      name === "deadline" ||
      name === "operations"
    )
      setSelectedMembership(record);
    if (name === "renew") setSelectedMembership(null);
    if (name === "training") setSelectedTraining(record);
    setDialog(name);
  };
  const membershipColumns = [
    {
      key: "package",
      label: "Gói tập",
      render: (r) => (
        <div>
          <span className="cell-primary">{r.package.name}</span>
          <div className="cell-secondary">{r.code}</div>
        </div>
      ),
    },
    {
      key: "period",
      label: "Thời hạn",
      render: (r) => (
        <span>
          {shortDate(r.startsAt)} → {shortDate(r.expiresAt)}
        </span>
      ),
    },
    { key: "paid", label: "Đã thanh toán", render: (r) => money(r.paidAmount) },
    {
      key: "debt",
      label: "Công nợ",
      render: (r) => (
        <button
          className={
            r.debtAmount ? "font-medium text-red-700 hover:underline" : ""
          }
          onClick={() => r.debtAmount && open("payment", r)}
        >
          {money(r.debtAmount)}
        </button>
      ),
    },
    {
      key: "status",
      label: "Trạng thái",
      render: (r) => <StatusBadge status={r.status} />,
    },
    {
      key: "action",
      label: "",
      render: (r) => (
        <div className="flex justify-end gap-1">
          {canFinancial && (
            <Button size="sm" variant="ghost" onClick={() => open("membership", r)}>
              Chi tiết
            </Button>
          )}
          {canManageLifecycle && r.status !== "cancelled" && (
            <Button size="sm" variant="secondary" onClick={() => open("operations", r)}>
              Quản lý
            </Button>
          )}
        </div>
      ),
    },
  ];
  const paymentColumns = [
    {
      key: "number",
      label: "Giao dịch",
      render: (row) => (
        <div>
          <span className="cell-primary">{row.number}</span>
          <div className="cell-secondary">{dateTime(row.paidAt)}</div>
        </div>
      ),
    },
    {
      key: "package",
      label: "Gói tập",
      render: (row) => row.description || "Thanh toán gói",
    },
    {
      key: "amount",
      label: "Số tiền",
      className: "text-right",
      render: (row) => (
        <strong className="text-slate-900">{money(row.amount)}</strong>
      ),
    },
    {
      key: "method",
      label: "Phương thức",
      render: (row) =>
        ({ cash: "Tiền mặt", bank_transfer: "Chuyển khoản", card: "Thẻ" })[
          row.method
        ] || row.method,
    },
    {
      key: "receipts",
      label: "Chứng từ",
      render: (row) => (
        <button
          className="receipt-count-button"
          onClick={() => {
            setFormError("");
            setSelectedPayment(row);
          }}
        >
          <ReceiptText size={14} />
          {row.receiptCount ? `${row.receiptCount} ảnh` : "+ Thêm bill"}
        </button>
      ),
    },
  ];
  const trainingColumns = [
    { key: "type", label: "Hình thức" },
    {
      key: "coach",
      label: "Coach",
      render: (r) =>
        r.coaches?.length ? (
          r.coaches.map((coach) => coach.name).join(", ")
        ) : (
          <span className="font-medium text-amber-700">Chưa phân công</span>
        ),
    },
    {
      key: "schedule",
      label: "Lịch tập",
      render: (r) => (
        <ScheduleSummary
          schedule={r.schedule}
          scheduleDays={r.scheduleDays}
          scheduleTime={r.scheduleTime}
          compact
        />
      ),
    },
    {
      key: "period",
      label: "Thời hạn",
      render: (r) => (
        <span>
          {shortDate(r.startsAt)} → {shortDate(r.expiresAt)}
        </span>
      ),
    },
    {
      key: "sessions",
      label: "Số buổi",
      render: (r) => `${r.remainingSessions}/${r.totalSessions}`,
    },
    {
      key: "status",
      label: "Trạng thái",
      render: (r) => <StatusBadge status={r.status} />,
    },
    {
      key: "action",
      label: "",
      render: (r) => (
        <Button size="sm" variant="ghost" onClick={() => open("training", r)}>
          Chỉnh sửa
        </Button>
      ),
    },
  ];
  return (
    <>
      <div className="mb-4">
        <Link
          to="/members"
          className="inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-900"
        >
          <ArrowLeft size={14} />
          Hội viên
        </Link>
      </div>
      <header className="profile-header">
        <div className="avatar">
          {member.avatarImageData ? (
            <img src={member.avatarImageData} alt="" />
          ) : (
            initials(member.name)
          )}
        </div>
        <div className="profile-title">
          <div className="flex items-center gap-3">
            <h1>{member.name}</h1>
            <StatusBadge status={displayStatus} />
          </div>
          <p>
            {member.code} · {member.phone || "Chưa có số điện thoại"} · Tham gia
            từ {shortDate(member.memberships.at(-1)?.registeredAt)}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {canFinancial && (
            <>
              <Button onClick={() => current?.debtAmount ? open("payment", current) : notify.info("Hội viên không có công nợ.")}>
                <CreditCard size={15} /> Thu tiền
              </Button>
              <Button variant="secondary" onClick={() => open("renew")}>
                <CalendarPlus size={15} /> Gia hạn
              </Button>
              <Button variant="secondary" onClick={() => open("edit")}>
                <Pencil size={15} /> Sửa
              </Button>
            </>
          )}
          {canManageLifecycle && current && lifecycleActions.length > 0 && (
            <RowMenu>
              {lifecycleActions.map(([action, label]) => (
                <button key={action} onClick={() => open("operations", current, action)}>
                  {label}
                </button>
              ))}
            </RowMenu>
          )}
        </div>
      </header>
      <div className="summary-strip mt-5">
        <div className="summary-item">
          <span>Gói hiện tại</span>
          <strong>{current?.package.name || "Chưa có gói"}</strong>
        </div>
        <div className="summary-item">
          <span>Hết hạn</span>
          <strong>
            {shortDate(current?.expiresAt)}{" "}
            {daysLeft != null &&
              `· ${daysLeft >= 0 ? `${daysLeft} ngày` : "Quá hạn"}`}
          </strong>
        </div>
        <div className="summary-item">
          <span>Công nợ</span>
          <strong className={current?.debtAmount ? "!text-red-700" : ""}>
            {money(current?.debtAmount)}
          </strong>
        </div>
        <div className="summary-item">
          <span>Check-in cuối</span>
          <strong>
            {lastCheckin ? shortDate(lastCheckin.checkedInAt) : "Chưa có"}
          </strong>
        </div>
        <div className="summary-item">
          <span>PT hiện tại</span>
          <strong>
            {activeTraining
              ? activeTrainingCoaches.map((coach) => coach.name).join(", ") ||
                "Chưa phân công"
              : "Chưa đăng ký"}
          </strong>
        </div>
      </div>
      <div className="tabs mt-5">
        {tabs.map(([key, label]) => (
          <button
            key={key}
            className={`tab ${tab === key ? "active" : ""}`}
            onClick={() => {
              setTab(key);
              setSearchParams(key === "overview" ? {} : { tab: key }, {
                replace: true,
              });
            }}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "overview" && (
        <div className="detail-grid">
          <section>
            <div className="section-header">
              <div>
                <h2>Tình trạng vận hành</h2>
                <p>Thông tin cần biết và hành động tiếp theo</p>
              </div>
            </div>
            {daysLeft != null && daysLeft <= 14 && (
              <div className="detail-alert">
                <span className="flex items-center gap-2">
                  <TriangleAlert size={15} />
                  Gói{" "}
                  {daysLeft < 0 ? "đã hết hạn" : `hết hạn sau ${daysLeft} ngày`}
                </span>
                {canFinancial && <button onClick={() => open("renew")}>Gia hạn</button>}
              </div>
            )}
            {current?.debtAmount > 0 && (
              <div className="detail-alert debt">
                <span className="flex items-center gap-2">
                  <TriangleAlert size={15} />
                  Còn nợ {money(current.debtAmount)}
                </span>
                {canFinancial && <button onClick={() => open("payment", current)}>Thu tiền</button>}
              </div>
            )}
            {!activeTraining && (
              <div className="detail-alert">
                <span className="flex items-center gap-2">
                  <TriangleAlert size={15} />
                  Chưa đăng ký PT
                </span>
                {canFinancial && <button onClick={() => open("training")}>Đăng ký PT</button>}
              </div>
            )}
            {activeTraining && !activeTrainingCoaches.length && (
              <div className="detail-alert">
                <span className="flex items-center gap-2">
                  <TriangleAlert size={15} />
                  Đăng ký PT đang chờ phân công Coach
                </span>
                {canEditPt && <button onClick={() => open("training", activeTraining)}>Phân công</button>}
              </div>
            )}
            <div className="definition-list mt-4">
              <div>
                <dt>Gói hiện tại</dt>
                <dd>
                  {current ? (
                    <>
                      <strong>{current.package.name}</strong>
                      <span className="cell-secondary mt-0.5 block">
                        {shortDate(current.startsAt)} →{" "}
                        {shortDate(current.expiresAt)}
                      </span>
                    </>
                  ) : canFinancial ? (
                    <button
                      className="font-medium text-blue-700"
                      onClick={() => open("renew")}
                    >
                      + Đăng ký gói
                    </button>
                  ) : "—"}
                </dd>
              </div>
              <div>
                <dt>Tài chính</dt>
                <dd>
                  {current ? (
                    <>
                      {money(current.paidAmount)} đã thu ·{" "}
                      <span
                        className={
                          current.debtAmount
                            ? "text-red-700"
                            : "text-emerald-700"
                        }
                      >
                        {money(current.debtAmount)} công nợ
                      </span>
                    </>
                  ) : (
                    "—"
                  )}
                </dd>
              </div>
              <div>
                <dt>Hạn thanh toán</dt>
                <dd>
                  {current?.debtAmount ? (
                    <button
                      className="font-medium text-blue-700 hover:underline"
                      onClick={() => open("deadline", current)}
                    >
                      {current.debtDueDate
                        ? `${shortDate(current.debtDueDate)} · Đổi hạn`
                        : "+ Đặt hạn"}
                    </button>
                  ) : (
                    "—"
                  )}
                </dd>
              </div>
              <div>
                <dt>Check-in gần nhất</dt>
                <dd>
                  {lastCheckin
                    ? dateTime(lastCheckin.checkedInAt)
                    : "Chưa có lượt check-in"}
                </dd>
              </div>
              <div>
                <dt>Tổng check-in gần đây</dt>
                <dd>{member.checkins.length} lượt</dd>
              </div>
              <div>
                <dt>PT & lịch</dt>
                <dd>
                  {activeTraining ? (
                    <>
                      {activeTrainingCoaches
                        .map((coach) => coach.name)
                        .join(", ") || "Chưa phân công Coach"}{" "}
                      · {activeTraining.type}
                      <div className="cell-secondary mt-0.5 block">
                        <ScheduleSummary
                          schedule={activeTraining.schedule}
                          scheduleDays={activeTraining.scheduleDays}
                          scheduleTime={activeTraining.scheduleTime}
                          emptyText="Chưa chọn thứ"
                          compact
                        />
                      </div>
                    </>
                  ) : canEditPt ? (
                    <button
                      className="font-medium text-blue-700"
                      onClick={() => open("training")}
                    >
                      + Gán PT
                    </button>
                  ) : "—"}
                </dd>
              </div>
              <div>
                <dt>Ghi chú quan trọng</dt>
                <dd>
                  {member.notes || (canFinancial ? (
                    <button
                      className="font-medium text-blue-700"
                      onClick={() => open("edit")}
                    >
                      + Thêm ghi chú
                    </button>
                  ) : "—")}
                </dd>
              </div>
            </div>
          </section>
          <aside className="info-rail">
            <h3>Liên hệ & phụ trách</h3>
            <dl>
              {canFinancial ? (
                <>
                  <InlineEditField label="Điện thoại" value={member.phone} type="tel" displayValue={formatPhone(member.phone)} onSave={(phone) => updateMember.mutateAsync({ payload: { phone }, silent: true })} pending={updateMember.isPending} />
                  <InlineEditField label="Email" value={member.email} type="email" emptyAction="+ Thêm email" onSave={(email) => updateMember.mutateAsync({ payload: { email }, silent: true })} pending={updateMember.isPending} />
                  <InlineEditField label="Nguồn khách" value={member.source} onSave={(source) => updateMember.mutateAsync({ payload: { source }, silent: true })} pending={updateMember.isPending} />
                </>
              ) : (
                <>
                  <div><dt>Điện thoại</dt><dd>{formatPhone(member.phone) || "—"}</dd></div>
                  <div><dt>Email</dt><dd>{member.email || "—"}</dd></div>
                  <div><dt>Nguồn khách</dt><dd>{member.source || "—"}</dd></div>
                </>
              )}
              <div>
                <dt>Mã MBS</dt>
                <dd>{member.mbsCode || "—"}</dd>
              </div>
              <div>
                <dt>Định danh DAH</dt>
                  <dd>
                    {member.personUuid ? (
                      <span className="inline-flex items-center gap-2">
                        <span className="font-mono text-[12px]">
                          {member.personUuid}
                        </span>
                        {canFinancial && (
                          <button
                            className="inline-flex items-center gap-1 font-medium text-blue-700 hover:underline"
                            onClick={() => setIdentityLinkOpen(true)}
                          >
                            <ScanFace size={14} /> Gán lại
                          </button>
                        )}
                      </span>
                    ) : canFinancial ? (
                    <button
                      className="inline-flex items-center gap-1 font-medium text-blue-700 hover:underline"
                      onClick={() => setIdentityLinkOpen(true)}
                    >
                      <ScanFace size={14} /> Liên kết định danh
                    </button>
                  ) : (
                    "Chưa liên kết"
                  )}
                </dd>
              </div>
              <div>
                <dt>Phụ trách</dt>
                <dd>{member.salesEmployee || "Chưa gán"}</dd>
              </div>
            </dl>
          </aside>
        </div>
      )}
      {tab === "memberships" && (
        <section className="mt-5">
          <div className="section-header">
            <div>
              <h2>Lịch sử gói tập</h2>
              <p>Đăng ký, gia hạn, thanh toán và phiếu thu</p>
            </div>
            {canFinancial && (
              <Button size="sm" onClick={() => open("renew")}>
                <Plus size={14} /> Đăng ký gói
              </Button>
            )}
          </div>
          <DataTable columns={membershipColumns} rows={member.memberships} />
          {!!member.membershipEvents?.length && (
            <div className="mt-6">
              <div className="section-header">
                <div><h3>Lịch sử biến động gói</h3><p>Bảo lưu, chuyển nhượng, đổi, nâng cấp và hủy gói</p></div>
              </div>
              <div className="membership-event-timeline">
                {member.membershipEvents.map((event) => (
                  <div key={event.id}>
                    <time>{shortDate(event.effectiveAt)}</time>
                    <span className={`audit-action audit-${event.action}`}>{({ freeze: "Bảo lưu", unfreeze: "Kết thúc bảo lưu", transfer: "Chuyển nhượng", upgrade: "Nâng cấp", change: "Đổi gói", cancel: "Hủy dịch vụ" })[event.action] || event.action}</span>
                    <div>
                      <strong>{event.action === "freeze" ? `${event.details?.compensatedDays || ""} ngày bảo lưu` : event.fromPackage && event.toPackage && event.fromPackage !== event.toPackage ? `${event.fromPackage} → ${event.toPackage}` : event.fromMember && event.toMember && event.fromMember !== event.toMember ? `${event.fromMember} → ${event.toMember}` : event.reason}</strong>
                      <p>{event.reason} · {event.createdBy}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </section>
      )}
      {tab === "payments" && (
        <section className="mt-5">
          <div className="section-header">
            <div>
              <h2>Lịch sử thanh toán</h2>
              <p>
                Mỗi lần thu tiền là một giao dịch độc lập, kèm đầy đủ chứng từ
              </p>
            </div>
            <div className="text-right">
              <span className="block text-[11px] text-slate-400">
                Tổng đã ghi nhận
              </span>
              <strong className="text-sm text-slate-900">
                {money(
                  member.payments.reduce(
                    (sum, row) => sum + Number(row.amount || 0),
                    0,
                  ),
                )}
              </strong>
            </div>
          </div>
          <DataTable
            columns={paymentColumns}
            rows={member.payments}
            emptyTitle="Chưa có giao dịch"
            emptyDescription="Các lần thanh toán sẽ xuất hiện tại đây."
          />
        </section>
      )}
      {tab === "checkins" && (
        <section className="mt-5">
          <div className="section-header">
            <div>
              <h2>Lịch sử check-in</h2>
              <p>100 lượt ra vào gần nhất</p>
            </div>
          </div>
          <DataTable
            rows={member.checkins}
            columns={[
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
              { key: "source", label: "Nguồn" },
              {
                key: "result",
                label: "Kết quả",
                render: (r) => (
                  <StatusBadge
                    status={r.result === "allowed" ? "active" : "pending"}
                  />
                ),
              },
              {
                key: "status",
                label: "Trạng thái",
                render: (r) => <StatusBadge status={r.status} />,
              },
            ]}
          />
        </section>
      )}
      {tab === "training" && (
        <section className="mt-5">
          <div className="section-header">
            <div>
              <h2>PT & lịch tập</h2>
              <p>Toàn bộ lịch sử PT và số buổi</p>
            </div>
            {canEditPt && (
              <Button size="sm" onClick={() => open("training", activeTraining)}>
                <Dumbbell size={14} />
                {activeTraining ? "Chỉnh sửa PT" : "Đăng ký PT"}
              </Button>
            )}
          </div>
          <DataTable
            rows={member.training}
            columns={trainingColumns}
            emptyTitle="Chưa đăng ký PT"
            emptyDescription="Đăng ký PT để thiết lập coach, số buổi và lịch tập."
          />
        </section>
      )}
      {tab === "notes" && (
        <section className="mt-5 max-w-3xl">
          <div className="section-header">
            <div>
              <h2>Ghi chú chăm sóc</h2>
              <p>Thông tin nội bộ dành cho nhân viên phụ trách</p>
            </div>
            {canFinancial && (
              <Button size="sm" variant="secondary" onClick={() => open("edit")}>
                <Pencil size={14} /> Chỉnh sửa
              </Button>
            )}
          </div>
          <div className="border-y border-slate-200 bg-white px-4 py-5 text-[13px] leading-6 text-slate-700">
            {member.notes || (
              <span className="text-slate-400">
                Chưa có ghi chú cho hội viên này.
              </span>
            )}
          </div>
        </section>
      )}
      {tab === "activity" && (
        <section className="mt-5 max-w-3xl">
          <div className="section-header">
            <div>
              <h2>Nhật ký thao tác</h2>
              <p>Ai đã thay đổi gì trên hồ sơ này và vào thời điểm nào</p>
            </div>
          </div>
          <div className="activity-timeline">
            {member.auditLogs?.length ? (
              member.auditLogs.map((item) => (
                <div key={item.id}>
                  <time>{dateTime(item.createdAt)}</time>
                  <div>
                    <strong>{item.summary}</strong>
                    <p>
                      {item.actor.name} · {item.actor.role}
                    </p>
                  </div>
                </div>
              ))
            ) : (
              <div>
                <time>—</time>
                <div>
                  <strong>Chưa có nhật ký mới</strong>
                  <p>
                    Các thao tác từ thời điểm bật Audit Log sẽ được lưu tại đây.
                  </p>
                </div>
              </div>
            )}
          </div>
        </section>
      )}
      <MemberEditForm
        member={member}
        options={options.data}
        open={dialog === "edit"}
        onClose={() => setDialog(null)}
        onSubmit={(payload) => updateMember.mutate({ payload })}
        pending={updateMember.isPending}
        error={formError}
      />
      <MembershipForm
        memberId={memberId}
        member={member}
        currentMembership={current}
        membership={selectedMembership}
        options={options.data}
        open={dialog === "membership" || dialog === "renew"}
        onClose={() => {
          setDialog(null);
          setSelectedMembership(null);
        }}
        onSubmit={(data, feedback) =>
          saveMembership.mutate({
            membership: selectedMembership,
            data,
            feedback,
          })
        }
        pending={saveMembership.isPending}
        error={formError}
      />
      <QuickPaymentForm
        membership={selectedMembership || current}
        options={options.data}
        open={dialog === "payment"}
        onClose={() => setDialog(null)}
        onSubmit={(data, feedback) =>
          saveMembership.mutate({
            membership: selectedMembership || current,
            data,
            feedback,
          })
        }
        pending={saveMembership.isPending}
        error={formError}
      />
      <DebtDeadlineForm
        membership={selectedMembership || current}
        open={dialog === "deadline"}
        onClose={() => {
          setDialog(null);
          setSelectedMembership(null);
        }}
        onSubmit={(payload) =>
          saveDeadline.mutate({
            membership: selectedMembership || current,
            payload,
          })
        }
        pending={saveDeadline.isPending}
        error={formError}
      />
      <PaymentReceiptModal
        payment={selectedPayment}
        open={!!selectedPayment}
        onClose={() => {
          setSelectedPayment(null);
          setFormError("");
        }}
        onUpload={(data) =>
          uploadReceipts.mutate({ paymentId: selectedPayment.id, data })
        }
        pending={uploadReceipts.isPending}
        error={formError}
      />
      <MembershipOperationsModal
        membership={selectedMembership || current}
        memberships={member.memberships}
        memberId={memberId}
        options={options.data}
        open={dialog === "operations"}
        initialAction={membershipOperationAction}
        onClose={() => {
          setDialog(null);
          setSelectedMembership(null);
          setMembershipOperationAction("");
        }}
        onSubmit={(variables) => membershipOperation.mutate(variables)}
        pending={membershipOperation.isPending}
        error={formError}
      />
      <TrainingForm
        enrollment={selectedTraining}
        options={options.data}
        open={dialog === "training"}
        onClose={() => {
          setDialog(null);
          setSelectedTraining(null);
        }}
        onSubmit={(payload) =>
          saveTraining.mutate({ enrollment: selectedTraining, payload })
        }
        pending={saveTraining.isPending}
        error={formError}
      />
      <DahIdentityLinkModal
        open={identityLinkOpen}
        onClose={() => setIdentityLinkOpen(false)}
        memberId={member.id}
        memberName={member.name}
        currentPersonUuid={member.personUuid}
        currentAvatarImageData={member.avatarImageData}
        onLinked={() => {
          refresh();
          notify.success(`Đã cập nhật định danh DAH cho ${member.name}.`);
        }}
      />
    </>
  );
}
