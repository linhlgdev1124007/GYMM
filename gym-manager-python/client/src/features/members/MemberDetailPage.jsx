import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  CalendarClock,
  CalendarPlus,
  CircleCheck,
  CircleX,
  ChevronRight,
  Clock3,
  Copy,
  CreditCard,
  Dumbbell,
  History,
  Mail,
  Pencil,
  Phone,
  Plus,
  ReceiptText,
  ScanFace,
} from "lucide-react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "../../services/api";
import { notify } from "../../services/notify";
import { Button } from "../../components/ui/Button";
import { DataTable } from "../../components/ui/DataTable";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { ScheduleSummary } from "../../components/ui/ScheduleSummary";
import { InlineEditField } from "../../components/ui/InlineEditField";
import { MembershipTimeline } from "../../components/ui/MembershipTimeline";
import { RowMenu } from "../../components/ui/RowMenu";
import { MemberEditForm } from "../../components/forms/MemberEditForm";
import { MembershipForm } from "../../components/forms/MembershipForm";
import { TrainingForm } from "../../components/forms/TrainingForm";
import { QuickPaymentForm } from "../../components/forms/QuickPaymentForm";
import { DebtDeadlineForm } from "../../components/forms/DebtDeadlineForm";
import { PaymentReceiptModal } from "../../components/forms/PaymentReceiptModal";
import { MembershipOperationsModal } from "../../components/forms/MembershipOperationsModal";
import { MembershipFreezeForm } from "../../components/forms/MembershipFreezeForm";
import { DahIdentityDeleteModal } from "./DahIdentityDeleteModal";
import { DahIdentityLinkModal } from "./DahIdentityLinkModal";
import { useAuth } from "../../app/AuthContext";
import {
  dateTime,
  ageFromDate,
  formatPhone,
  initials,
  money,
  shortDate,
} from "../../utils/format";

const tabGroups = [
  { key: "overview", label: "Tổng quan", tabs: [["overview", "Tổng quan"]] },
  { key: "membership", label: "Gói & tài chính", tabs: [["memberships", "Lịch sử gói"], ["payments", "Thanh toán"]] },
  { key: "operations", label: "Check-in & PT", tabs: [["checkins", "Lịch sử check-in"], ["training", "PT & lịch tập"], ["pt-sessions", "Buổi PT đã tập"]] },
  { key: "profile", label: "Hồ sơ & nhật ký", tabs: [["notes", "Ghi chú"], ["activity", "Nhật ký thao tác"]] },
];
const allTabs = tabGroups.flatMap((group) => group.tabs);

const membershipEventLabels = {
  activate: "Kích hoạt",
  suspend: "Tạm dừng",
  freeze: "Bảo lưu",
  unfreeze: "Kết thúc bảo lưu",
  transfer: "Chuyển nhượng",
  upgrade: "Nâng cấp",
  change: "Đổi gói",
  adjust_days: "Cộng / trừ ngày",
  cancel: "Hủy dịch vụ",
};

const auditFieldLabels = {
  name: "Họ tên",
  phone: "SĐT",
  email: "Email",
  gender: "Giới tính",
  dateOfBirth: "Ngày sinh",
  mbsCode: "Mã MBS",
  personUuid: "Định danh DAH",
  source: "Nguồn khách",
  notes: "Ghi chú",
  salesEmployeeId: "Nhân viên phụ trách",
  startsAt: "Ngày bắt đầu",
  expiresAt: "Ngày hết hạn",
  finalPrice: "Giá gói",
  paidAmount: "Đã thanh toán",
  debtAmount: "Công nợ",
  debtDueDate: "Hạn thanh toán",
  status: "Trạng thái",
  activationDate: "Ngày kích hoạt",
  coachIds: "Coach phụ trách",
  type: "Nhóm PT",
  totalSessions: "Tổng buổi",
  remainingSessions: "Buổi còn lại",
  schedule: "Lịch tập",
  scheduleDays: "Ngày tập",
  scheduleTime: "Giờ tập",
  oldPersonUuid: "FaceID cũ",
  newPersonUuid: "FaceID mới",
};

function auditChangeLines(item) {
  const changes = Array.isArray(item.details?.changes) ? item.details.changes : [];
  if (changes.length) {
    return changes.map((change) => ({
      key: change.field,
      label: change.label || auditFieldLabels[change.field] || change.field,
      text: `${String(change.old ?? "—")} → ${String(change.new ?? "—")}`,
    }));
  }
  const labels = Array.isArray(item.details?.fieldLabels) ? item.details.fieldLabels : [];
  if (labels.length) {
    return [{ key: "fields", label: "Đã cập nhật", text: labels.join(", ") }];
  }
  const fields = Array.isArray(item.details?.fields) ? item.details.fields : [];
  if (fields.length) {
    return [{ key: "fields", label: "Đã cập nhật", text: fields.map((field) => auditFieldLabels[field] || field).join(", ") }];
  }
  return [];
}

function eventPrimaryText(event) {
  const details = event.details || {};
  if (event.action === "freeze") {
    const days = details.plannedDays ?? details.compensatedDays ?? "";
    return `Bảo lưu ${days ? `${days} ngày` : "gói"}`;
  }
  if (event.action === "unfreeze") {
    return `Cộng bù ${details.compensatedDays || 0} ngày`;
  }
  if (event.action === "adjust_days") {
    const days = Number(details.days || 0);
    return `${days >= 0 ? "Cộng" : "Trừ"} ${Math.abs(days)} ngày`;
  }
  if (event.fromPackage && event.toPackage && event.fromPackage !== event.toPackage) {
    return `${event.fromPackage} → ${event.toPackage}`;
  }
  if (event.fromMember && event.toMember && event.fromMember !== event.toMember) {
    return `${event.fromMember} → ${event.toMember}`;
  }
  return event.reason || membershipEventLabels[event.action] || event.action;
}

function eventDetailLines(event) {
  const details = event.details || {};
  const lines = [];
  if (event.action === "freeze") {
    if (details.startsAt || details.endsAt) {
      lines.push(`Thời gian bảo lưu: ${shortDate(details.startsAt)} → ${shortDate(details.endsAt)}`);
    }
    if (details.previousExpiry || details.newExpiry) {
      lines.push(`Hạn gói: ${shortDate(details.previousExpiry)} → ${shortDate(details.newExpiry)}`);
    }
  } else if (event.action === "unfreeze") {
    if (details.startsAt || details.actualEndsAt || details.plannedEndsAt) {
      lines.push(`Thực tế: ${shortDate(details.startsAt)} → ${shortDate(details.actualEndsAt || details.plannedEndsAt)}`);
    }
    if (details.previousExpiry || details.newExpiry) {
      lines.push(`Hạn sau cộng bù: ${shortDate(details.previousExpiry)} → ${shortDate(details.newExpiry)}`);
    }
  } else if (event.action === "adjust_days") {
    if (details.previousExpiry || details.newExpiry) {
      lines.push(`Hạn gói: ${shortDate(details.previousExpiry)} → ${shortDate(details.newExpiry)}`);
    }
  } else if (event.action === "suspend" && details.suspendedAt) {
    lines.push(`Ngày tạm dừng: ${shortDate(details.suspendedAt)}`);
  } else if (event.action === "activate" && details.activatedAt) {
    lines.push(`Ngày kích hoạt: ${shortDate(details.activatedAt)}`);
  } else if ((event.action === "change" || event.action === "upgrade") && details.previousPrice != null) {
    lines.push(`Giá gói: ${money(details.previousPrice)} → ${money(details.newPrice)}`);
  }
  if (event.reason) lines.push(`Lý do: ${event.reason}`);
  return lines;
}

function isoFromDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function addIsoDays(value, days) {
  if (!value || !days) return value;
  const date = new Date(`${value}T00:00:00`);
  date.setDate(date.getDate() + days);
  return isoFromDate(date);
}

function dayDiff(startsAt, endsAt) {
  if (!startsAt || !endsAt) return 0;
  return Math.max(
    Math.round(
      (new Date(`${endsAt}T00:00:00`) - new Date(`${startsAt}T00:00:00`)) /
        86400000,
    ),
    0,
  );
}

function freezeDays(freeze) {
  return freeze.plannedDays ?? dayDiff(freeze.startsAt, freeze.endsAt);
}

function membershipPeriodInfo(membership) {
  const freezes = membership.freezes || [];
  const pendingFreezeDays = freezes
    .filter((freeze) => !freeze.completedAt)
    .reduce(
      (sum, freeze) =>
        sum + Math.max(freezeDays(freeze) - Number(freeze.compensatedDays || 0), 0),
      0,
    );
  const displayExpiresAt = addIsoDays(membership.expiresAt, pendingFreezeDays);
  const suspendedEvent = (membership.events || []).find(
    (event) => event.action === "suspend" && event.details?.suspendedAt,
  );
  const isSuspendedWithoutRestart = membership.status === "suspended";
  const adjustmentNotes = [];
  const registeredLine = membership.registeredAt
    ? `Đăng ký: ${shortDate(membership.registeredAt)}`
    : "Đăng ký: —";
  const actualLine = isSuspendedWithoutRestart
    ? `Thực tế: ${shortDate(membership.startsAt)} → đang tạm dừng`
    : `Thực tế: ${shortDate(membership.startsAt)} → ${shortDate(displayExpiresAt)}`;

  if (isSuspendedWithoutRestart && suspendedEvent) {
    adjustmentNotes.push(`Tạm dừng từ ${shortDate(suspendedEvent.details.suspendedAt)} · chưa kích hoạt lại`);
  }

  if (!isSuspendedWithoutRestart && pendingFreezeDays > 0 && displayExpiresAt !== membership.expiresAt) {
    adjustmentNotes.push(`Hạn trước bảo lưu: ${shortDate(membership.expiresAt)}`);
  }

  freezes.forEach((freeze) => {
    const days = freezeDays(freeze);
    adjustmentNotes.push(
      `${
        freeze.completedAt
          ? `Đã cộng +${freeze.compensatedDays || 0} ngày bảo lưu`
          : `Dự kiến cộng +${days} ngày bảo lưu`
      } (${shortDate(freeze.startsAt)} → ${shortDate(freeze.endsAt)})${
        freeze.reason ? ` · Lý do: ${freeze.reason}` : ""
      }`,
    );
  });

  if (!isSuspendedWithoutRestart) (membership.events || [])
    .filter((event) => event.action === "adjust_days")
    .forEach((event) => {
      const days = Number(event.details?.days || 0);
      if (!days) return;
      adjustmentNotes.push(
        `Đã ${days > 0 ? "cộng" : "trừ"} ${Math.abs(days)} ngày thủ công: ${shortDate(
          event.details?.previousExpiry,
        )} → ${shortDate(event.details?.newExpiry)}${
          event.reason ? ` · Lý do: ${event.reason}` : ""
        }`,
      );
    });

  return { registeredLine, actualLine, adjustmentNotes };
}

function activityTimestamp(value) {
  if (!value) return 0;
  const normalized = /^\d{4}-\d{2}-\d{2}$/.test(value)
    ? `${value}T00:00:00`
    : value;
  return new Date(normalized).getTime() || 0;
}

function recentMemberActivity(member) {
  const payments = (member.payments || []).map((payment) => ({
    id: `payment-${payment.id}`,
    kind: "payment",
    occurredAt: payment.paidAt,
    title: Number(payment.amount || 0) < 0 ? `Hoàn tiền ${money(Math.abs(Number(payment.amount || 0)))}` : `Đã thu ${money(payment.amount)}`,
    description: payment.description || "Thanh toán gói tập",
    meta: payment.number,
    record: payment,
  }));
  const checkins = (member.checkins || []).map((checkin) => ({
    id: `checkin-${checkin.id}`,
    kind: "checkin",
    occurredAt: checkin.checkedInAt,
    title: checkin.result === "allowed" ? "Check-in thành công" : "Ghi nhận check-in",
    description: checkin.checkedOutAt
      ? `Đã rời phòng lúc ${dateTime(checkin.checkedOutAt).split(" · ")[0]}`
      : "Đang ở phòng hoặc chưa ghi nhận check-out",
    meta: checkin.source || "Hệ thống",
    status: checkin.status,
  }));
  const membershipEvents = (member.membershipEvents || []).map((event) => ({
    id: `membership-${event.id}`,
    kind: "membership",
    occurredAt: event.effectiveAt,
    title: eventPrimaryText(event),
    description: eventDetailLines(event)[0] || membershipEventLabels[event.action] || "Thay đổi gói tập",
    meta: event.createdBy,
    action: event.action,
  }));
  return [...payments, ...checkins, ...membershipEvents]
    .sort((left, right) => activityTimestamp(right.occurredAt) - activityTimestamp(left.occurredAt));
}

function CopyValueButton({ value, label }) {
  if (!value) return null;
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(String(value));
      notify.success(`Đã sao chép ${label}.`);
    } catch {
      notify.error(`Không thể sao chép ${label}.`);
    }
  };
  return (
    <button type="button" className="copy-value-button" onClick={copy} title={`Sao chép ${label}`} aria-label={`Sao chép ${label}`}>
      <Copy size={12} />
    </button>
  );
}

export function MemberDetailPage() {
  const { memberId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const client = useQueryClient();
  const [tab, setTab] = useState(() =>
    allTabs.some(([key]) => key === searchParams.get("tab"))
      ? searchParams.get("tab")
      : "overview",
  );
  const [dialog, setDialog] = useState(null);
  const [selectedMembership, setSelectedMembership] = useState(null);
  const [selectedFreeze, setSelectedFreeze] = useState(null);
  const [membershipOperationAction, setMembershipOperationAction] = useState("");
  const [selectedTraining, setSelectedTraining] = useState(null);
  const [selectedPayment, setSelectedPayment] = useState(null);
  const [formError, setFormError] = useState("");
  const [identityLinkOpen, setIdentityLinkOpen] = useState(false);
  const [identityDeleteOpen, setIdentityDeleteOpen] = useState(false);
  const [activityFilter, setActivityFilter] = useState("all");
  const workspaceHeaderRef = useRef(null);
  const [showStickyHeader, setShowStickyHeader] = useState(false);
  const isAdmin = user.role === "admin";
  const visibleTabGroups = useMemo(
    () =>
      tabGroups
        .map((group) =>
          group.key === "profile" && !isAdmin
            ? {
                ...group,
                label: "Hồ sơ",
                tabs: group.tabs.filter(([key]) => key !== "activity"),
              }
            : group,
        )
        .filter((group) => group.tabs.length),
    [isAdmin],
  );
  const visibleTabs = useMemo(
    () => visibleTabGroups.flatMap((group) => group.tabs),
    [visibleTabGroups],
  );
  useEffect(() => {
    if (!visibleTabs.some(([key]) => key === tab)) {
      setTab("overview");
      setSearchParams({}, { replace: true });
    }
  }, [tab, visibleTabs, setSearchParams]);
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
  useEffect(() => {
    const header = workspaceHeaderRef.current;
    if (!header || !member) return undefined;
    const observer = new IntersectionObserver(
      ([entry]) => setShowStickyHeader(!entry.isIntersecting),
      { rootMargin: "-72px 0px 0px 0px", threshold: 0 },
    );
    observer.observe(header);
    return () => observer.disconnect();
  }, [member]);
  const refresh = () => {
    client.invalidateQueries({ queryKey: ["member", memberId] });
    client.invalidateQueries({ queryKey: ["members"] });
    client.invalidateQueries({ queryKey: ["memberships"] });
    client.invalidateQueries({ queryKey: ["training"] });
    client.invalidateQueries({ queryKey: ["payments"] });
    client.invalidateQueries({ queryKey: ["reports"] });
    client.invalidateQueries({ queryKey: ["dashboard"] });
  };
  const updateMember = useMutation({
    mutationFn: ({ payload }) =>
      api(`/api/members/${memberId}`, { method: "PATCH", body: payload }),
    onSuccess: (data, variables) => {
      client.setQueryData(["member", memberId], data);
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
  const freezeMutation = useMutation({
    mutationFn: ({ membershipId, freezeId, payload, method }) =>
      api(`/api/memberships/${membershipId}/freezes/${freezeId}`, {
        method,
        body: method === "DELETE" ? undefined : payload,
      }),
    onSuccess: (_result, variables) => {
      refresh();
      client.invalidateQueries({ queryKey: ["alerts"] });
      client.invalidateQueries({ queryKey: ["audit-logs"] });
      setDialog(null);
      setSelectedMembership(null);
      setSelectedFreeze(null);
      notify.success(variables.method === "DELETE" ? "Đã hủy lịch bảo lưu." : "Đã cập nhật lịch bảo lưu.");
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
  const joinedAt = member.memberships.at(-1)?.registeredAt;
  const currentPeriod = current ? membershipPeriodInfo(current) : null;
  const genderLabel =
    ({ male: "Nam", female: "Nữ", other: "Khác" })[member.gender] ||
    member.gender ||
    "Chưa cập nhật";
  const age = ageFromDate(member.dateOfBirth);
  const recentActivity = recentMemberActivity(member);
  const filteredRecentActivity = recentActivity
    .filter((item) => activityFilter === "all" || item.kind === activityFilter)
    .slice(0, 8);
  const activeTabGroup = visibleTabGroups.find((group) =>
    group.tabs.some(([key]) => key === tab),
  ) || visibleTabGroups[0];
  const lifecycleLedger = (current?.events || []).filter((event) =>
    ["activate", "suspend", "freeze", "unfreeze", "adjust_days"].includes(event.action),
  );
  const accessEligible =
    member.status === "lead" ||
    (!!current &&
      ["active", "pending", "suspended"].includes(current.status) &&
      (!current.expiresAt || new Date(`${current.expiresAt}T23:59:59`) >= new Date()));
  const accessSummary = member.status === "lead"
    ? { title: "Có thể check-in", detail: "Khách tiềm năng" }
    : accessEligible
      ? { title: "Có thể check-in", detail: current?.status === "pending" ? "Sẽ kích hoạt theo quy trình hiện tại" : "Gói còn hiệu lực" }
      : { title: "Không thể check-in", detail: "Gói không hoạt động hoặc đã hết hạn" };
  const membershipUsagePercent = current?.timeline?.totalDays
    ? Math.min(
        Math.max(
          ((current.timeline.totalDays - Math.max(current.timeline.remainingDays, 0)) /
            current.timeline.totalDays) *
            100,
          0,
        ),
        100,
      )
    : 0;
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
  }
  if (current?.status === "expired") {
    lifecycleActions.push(["freeze", "Bảo lưu"]);
  }
  if (["active", "expired"].includes(current?.status)) {
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
  const openFreezeEdit = (membership, freeze) => {
    setFormError("");
    setSelectedMembership(membership);
    setSelectedFreeze(freeze);
    setDialog("freeze-edit");
  };
  const deleteFreeze = (membership, freeze) => {
    if (!window.confirm(`Hủy lịch bảo lưu ${shortDate(freeze.startsAt)} → ${shortDate(freeze.endsAt)}?`)) return;
    setFormError("");
    freezeMutation.mutate({
      membershipId: membership.id,
      freezeId: freeze.id,
      method: "DELETE",
    });
  };
  const selectTab = (key) => {
    setTab(key);
    setSearchParams(key === "overview" ? {} : { tab: key }, { replace: true });
  };
  const renderMemberActions = ({ compact = false } = {}) => (
    <>
      {canFinancial && (
        <Button
          size={compact ? "sm" : undefined}
          variant={current?.debtAmount > 0 ? undefined : "secondary"}
          onClick={() => current?.debtAmount ? open("payment", current) : notify.info("Hội viên không có công nợ.")}
        >
          <CreditCard size={15} /> Thu tiền
        </Button>
      )}
      {canFinancial && (
        <Button
          size={compact ? "sm" : undefined}
          variant={current?.debtAmount > 0 ? "secondary" : undefined}
          onClick={() => open("renew")}
        >
          <CalendarPlus size={15} /> Gia hạn
        </Button>
      )}
      {!compact && canFinancial && (
        <Button variant="secondary" onClick={() => open("edit")}>
          <Pencil size={15} /> Sửa hồ sơ
        </Button>
      )}
      {canManageLifecycle && current && lifecycleActions.length > 0 && (
        <RowMenu label={compact ? "Quản lý" : "Quản lý gói"}>
          {lifecycleActions.map(([action, label]) => (
            <button key={action} onClick={() => open("operations", current, action)}>
              {label}
            </button>
          ))}
        </RowMenu>
      )}
    </>
  );
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
      render: (r) => {
        const period = membershipPeriodInfo(r);
        return (
          <div className="membership-period-cell">
            <span>{period.registeredLine}</span>
            <strong>{period.actualLine}</strong>
            {!!period.adjustmentNotes.length && (
              <ul>
                {period.adjustmentNotes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            )}
          </div>
        );
      },
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
        <strong className={Number(row.amount || 0) < 0 ? "text-red-700" : "text-slate-900"}>{money(row.amount)}</strong>
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
    {
      key: "packageName",
      label: "Gói PT/BT",
      render: (r) => (
        <span>
          {r.packageName || "Chưa đặt tên gói"}
          <small className="cell-secondary block">{r.type}</small>
        </span>
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
      key: "finance",
      label: "Tài chính PT",
      render: (r) => (
        <span>
          {money(r.paidAmount)} / {money(r.finalPrice)}
          <small className={`cell-secondary block ${r.debtAmount > 0 ? "text-red-700" : "text-emerald-700"}`}>
            {r.debtAmount > 0 ? `${money(r.debtAmount)} nợ${r.nextDebtDueDate ? ` · hạn ${shortDate(r.nextDebtDueDate)}` : ""}` : "Đã tất toán"}
          </small>
        </span>
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
        <Button size="sm" variant="ghost" onClick={() => open("training", r)}>
          Chỉnh sửa
        </Button>
      ),
    },
  ];
  const ptSessionColumns = [
    {
      key: "createdAt",
      label: "Thời điểm ghi nhận",
      render: (r) => dateTime(r.checkedInAt || r.createdAt),
    },
    {
      key: "trainingDate",
      label: "Ngày tập",
      render: (r) => shortDate(r.trainingDate),
    },
    {
      key: "timeRange",
      label: "Ca PT",
      render: (r) =>
        r.startedAt && r.endedAt
          ? `${dateTime(r.startedAt).split(" · ")[0]} - ${dateTime(r.endedAt).split(" · ")[0]}`
          : "—",
    },
    {
      key: "action",
      label: "Nghiệp vụ",
      render: (r) =>
        r.action === "pt_checkin"
          ? "Tập PT"
          : r.action === "pt_sessions_add"
            ? "Cộng buổi"
            : r.action === "pt_sessions_subtract"
              ? "Trừ buổi"
              : r.action,
    },
    { key: "ptType", label: "Nhóm PT" },
    {
      key: "coaches",
      label: "Coach",
      render: (r) => r.coaches?.map((coach) => coach.name).join(", ") || "—",
    },
    {
      key: "deltaSessions",
      label: "Buổi",
      className: "text-right",
      render: (r) => (
        <strong className={r.deltaSessions < 0 ? "text-red-700" : "text-emerald-700"}>
          {r.deltaSessions > 0 ? "+" : ""}
          {r.deltaSessions}
        </strong>
      ),
    },
    {
      key: "remaining",
      label: "Còn lại",
      render: (r) => `${r.remainingBefore} → ${r.remainingAfter}`,
    },
    { key: "createdBy", label: "Người ghi nhận" },
    {
      key: "note",
      label: "Ghi chú",
      render: (r) => r.note || "—",
    },
  ];
  return (
    <>
      <div className="member-breadcrumb">
        <Link
          to="/members"
          className="inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-900"
        >
          <ArrowLeft size={14} />
          Danh sách hội viên
        </Link>
      </div>
      <header ref={workspaceHeaderRef} className="member-workspace-header member-command-center">
        <div className="member-identity-row">
          <div className="member-identity">
            <div className="avatar member-avatar">
              {member.avatarImageData ? (
                <img src={member.avatarImageData} alt={`Ảnh ${member.name}`} />
              ) : initials(member.name)}
            </div>
            <div className="member-identity-copy">
              <div className="member-name-row">
                <h1>{member.name}</h1>
                <StatusBadge status={displayStatus} />
              </div>
              <div className="member-identity-meta">
                <span className="member-code">{member.code}</span>
                {member.phone ? <a href={`tel:${member.phone}`}><Phone size={13} />{formatPhone(member.phone)}</a> : <span><Phone size={13} />Chưa có điện thoại</span>}
                {member.email && <a href={`mailto:${member.email}`}><Mail size={13} />{member.email}</a>}
                <span><CalendarClock size={13} />Tham gia {shortDate(joinedAt)}</span>
              </div>
            </div>
          </div>
          <div className="member-header-actions">
            {renderMemberActions()}
          </div>
        </div>
        <div className="command-center-body">
          <section className="command-contract">
            <div className="command-contract-label">
              <span>Gói hiện tại</span>
              {current && <StatusBadge status={current.status} />}
            </div>
            <div className="command-contract-title">
              <div>
                <h2>{current?.package.name || "Chưa đăng ký gói"}</h2>
                <p>{current ? `${current.code} · Đăng ký ${shortDate(current.registeredAt)}` : "Chưa có hợp đồng membership đang được ghi nhận"}</p>
              </div>
              {daysLeft != null && current?.status !== "suspended" && (
                <div className={`command-days ${daysLeft < 0 ? "danger" : daysLeft <= 14 ? "warning" : ""}`}>
                  <strong>{daysLeft < 0 ? Math.abs(daysLeft) : daysLeft}</strong>
                  <span>{daysLeft < 0 ? "ngày quá hạn" : "ngày còn lại"}</span>
                </div>
              )}
            </div>
            {current && (
              <>
                <div className="command-period">
                  <span><small>Bắt đầu</small><strong>{shortDate(current.startsAt)}</strong></span>
                  <i aria-hidden="true" />
                  <span><small>{current.status === "suspended" ? "Trạng thái" : "Hạn thực tế"}</small><strong>{current.status === "suspended" ? "Đang tạm dừng" : currentPeriod?.actualLine.split(" → ").at(-1)}</strong></span>
                </div>
                <div className="command-usage-track" aria-label={`Đã sử dụng ${Math.round(membershipUsagePercent)}% thời hạn gói`}>
                  <span style={{ width: `${membershipUsagePercent}%` }} />
                </div>
              </>
            )}
          </section>
          <dl className="command-operational-facts">
            <div className={accessEligible ? "access-allowed" : "has-issue"}>
              <dt>Trạng thái vào phòng</dt>
              <dd className="access-value">{accessEligible ? <CircleCheck size={14} /> : <CircleX size={14} />}{accessSummary.title}</dd>
              <small>{accessSummary.detail}</small>
            </div>
            <div className={current?.debtAmount ? "has-issue" : ""}>
              <dt>Tài chính</dt>
              <dd>{current?.debtAmount ? money(current.debtAmount) : "Đã thanh toán đủ"}</dd>
              <small>{current?.debtAmount ? `Công nợ · hạn ${shortDate(current.debtDueDate)}` : `${money(current?.paidAmount)} đã thu`}</small>
            </div>
            <div>
              <dt>Check-in gần nhất</dt>
              <dd>{lastCheckin ? dateTime(lastCheckin.checkedInAt) : "Chưa có lượt check-in"}</dd>
              <small>{member.checkins.length} lượt gần đây</small>
            </div>
            <div>
              <dt>Nhóm PT</dt>
              <dd>{activeTraining?.type || "Chưa đăng ký PT"}</dd>
              <small>{activeTraining ? "Gói PT hiện tại" : "Không có lịch tập"}</small>
            </div>
          </dl>
        </div>
      </header>
      <div className={`member-sticky-shell ${showStickyHeader ? "visible" : ""}`}>
        <div className="member-sticky-toolbar">
          <div><span className="sticky-avatar">{initials(member.name)}</span><span><strong>{member.name}</strong><small>{current?.package.name || "Chưa có gói"}</small></span><StatusBadge status={displayStatus} /></div>
          <div>{renderMemberActions({ compact: true })}</div>
        </div>
      </div>
      <div className="tabs member-tabs">
        {visibleTabGroups.map((group) => (
          <button
            key={group.key}
            className={`tab ${activeTabGroup.key === group.key ? "active" : ""}`}
            onClick={() => selectTab(group.tabs[0][0])}
          >
            {group.label}
          </button>
        ))}
      </div>
      {activeTabGroup.tabs.length > 1 && (
        <div className="member-secondary-tabs" aria-label={activeTabGroup.label}>
          {activeTabGroup.tabs.map(([key, label]) => (
            <button key={key} className={tab === key ? "active" : ""} onClick={() => selectTab(key)}>{label}</button>
          ))}
        </div>
      )}
      {tab === "overview" && (
        <div className="member-overview-grid">
          <main className={`member-overview-main member-role-${user.role}`}>
            {user.role === "coach" && (
              <section className="workspace-section coach-focus-section">
                <div className="workspace-section-title"><div><h2>PT & lịch tập hiện tại</h2><p>Thông tin vận hành dành cho Coach</p></div>{activeTraining && canEditPt && <button className="icon-text-action" onClick={() => open("training", activeTraining)}><Pencil size={13} /> Chỉnh sửa</button>}</div>
                {activeTraining ? (
                  <div className="coach-focus-body">
                    <div><span>Coach phụ trách</span><strong>{activeTrainingCoaches.map((coach) => coach.name).join(", ") || "Chưa phân công"}</strong></div>
                    <div><span>Số buổi còn lại</span><strong>{activeTraining.remainingSessions}/{activeTraining.totalSessions} buổi</strong></div>
                    <div><span>Thời hạn</span><strong>{shortDate(activeTraining.startsAt)} → {shortDate(activeTraining.expiresAt)}</strong></div>
                    <div className="coach-schedule"><span>Lịch tập</span><ScheduleSummary schedule={activeTraining.schedule} scheduleDays={activeTraining.scheduleDays} scheduleTime={activeTraining.scheduleTime} emptyText="Chưa chọn thứ" compact /></div>
                  </div>
                ) : <div className="compact-empty"><Dumbbell size={19} /><div><strong>Chưa có đăng ký PT</strong><p>Hội viên chưa có lịch PT đang hoạt động.</p></div></div>}
              </section>
            )}
            <section className="workspace-section membership-workspace role-contract-section">
            <div className="workspace-section-title">
              <div><h2>Hồ sơ hiệu lực gói</h2><p>Đăng ký, hiệu lực thực tế và toàn bộ nguồn điều chỉnh</p></div>
              {current && <StatusBadge status={current.status} />}
            </div>
            <div className="definition-list membership-overview-facts">
              <div>
                <dt>Gói tập</dt>
                <dd>
                  {current ? (
                    <>
                      <strong>{current.package.name}</strong>
                      <span className="cell-secondary mt-0.5 block">
                        {current.code}
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
                <dt>Ngày đăng ký</dt>
                <dd>{shortDate(current?.registeredAt)}</dd>
              </div>
              <div>
                <dt>Bắt đầu sử dụng</dt>
                <dd>{shortDate(current?.startsAt)}</dd>
              </div>
              <div>
                <dt>Hạn thực tế</dt>
                <dd>{current?.status === "suspended" ? "Chưa xác định · đang tạm dừng" : currentPeriod?.actualLine.split(" → ").at(-1) || "—"}</dd>
              </div>
              <div>
                <dt>Đối soát tài chính</dt>
                <dd>
                  {current ? (
                    <>
                      <strong>{money(current.paidAmount)}</strong> đã thu
                      <span className={`cell-secondary mt-0.5 block ${current.debtAmount ? "!text-red-700" : "!text-emerald-700"}`}>{money(current.debtAmount)} công nợ</span>
                    </>
                  ) : "—"}
                </dd>
              </div>
              <div>
                <dt>Hạn thanh toán</dt>
                <dd>{current?.debtAmount ? <button className="font-medium text-blue-700 hover:underline" onClick={() => open("deadline", current)}>{current.debtDueDate ? `${shortDate(current.debtDueDate)} · Đổi hạn` : "+ Đặt hạn"}</button> : "Không có công nợ"}</dd>
              </div>
            </div>
            {(!!lifecycleLedger.length || !!currentPeriod?.adjustmentNotes.length) && (
              <div className="lifecycle-ledger">
                <div className="lifecycle-ledger-title"><History size={14} /><span><strong>Sổ biến động hiệu lực</strong><small>Ai thay đổi, thời điểm và giá trị trước/sau</small></span></div>
                {lifecycleLedger.length ? lifecycleLedger.map((event) => (
                  <div className="lifecycle-ledger-row" key={event.id}>
                    <span className={`audit-action audit-${event.action}`}>{membershipEventLabels[event.action] || event.action}</span>
                    <div><strong>{eventPrimaryText(event)}</strong>{eventDetailLines(event).map((line) => <p key={line}>{line}</p>)}</div>
                    <div><strong>{event.createdBy || "Hệ thống"}</strong><small>{event.createdAt ? dateTime(event.createdAt) : shortDate(event.effectiveAt)}</small></div>
                  </div>
                )) : currentPeriod.adjustmentNotes.map((note) => (
                  <div className="lifecycle-ledger-row legacy" key={note}><span className="audit-action audit-adjust_days">Điều chỉnh</span><div><strong>{note}</strong></div><div><strong>Hệ thống</strong><small>Không có thời điểm ghi nhận</small></div></div>
                ))}
              </div>
            )}
            {current && <MembershipTimeline membership={current} onEditFreeze={canManageLifecycle ? (freeze) => openFreezeEdit(current, freeze) : undefined} onDeleteFreeze={canManageLifecycle ? (freeze) => deleteFreeze(current, freeze) : undefined} />}
            </section>
            <section className="workspace-section unified-activity-section role-activity-section">
              <div className="workspace-section-title">
                <div><h2>Hoạt động gần đây</h2><p>Check-in, thanh toán và biến động gói trên cùng một dòng thời gian</p></div>
                {isAdmin && <button className="section-link" onClick={() => selectTab("activity")}>Xem nhật ký <ChevronRight size={14} /></button>}
              </div>
              <div className="activity-filter-bar" aria-label="Lọc hoạt động">
                {[["all", "Tất cả"], ["membership", "Gói tập"], ["payment", "Thanh toán"], ["checkin", "Check-in"]].map(([key, label]) => (
                  <button key={key} className={activityFilter === key ? "active" : ""} onClick={() => setActivityFilter(key)}>{label}</button>
                ))}
              </div>
              <div className="unified-activity-list">
                {filteredRecentActivity.map((item) => (
                  <div
                    key={item.id}
                    className={`unified-activity-row ${item.record ? "clickable" : ""}`}
                    role={item.record ? "button" : undefined}
                    tabIndex={item.record ? 0 : undefined}
                    onClick={() => item.record && setSelectedPayment(item.record)}
                    onKeyDown={(event) => {
                      if (item.record && (event.key === "Enter" || event.key === " ")) {
                        event.preventDefault();
                        setSelectedPayment(item.record);
                      }
                    }}
                  >
                    <span className={`activity-kind-icon ${item.kind}`}>
                      {item.kind === "payment" ? <ReceiptText size={15} /> : item.kind === "checkin" ? <Clock3 size={15} /> : <History size={15} />}
                    </span>
                    <div className="activity-copy"><strong>{item.title}</strong><p>{item.description}</p></div>
                    <span className={`activity-kind-label ${item.kind}`}>{item.kind === "payment" ? "Thanh toán" : item.kind === "checkin" ? "Check-in" : membershipEventLabels[item.action] || "Gói tập"}</span>
                    <div className="activity-when"><strong>{item.occurredAt?.includes("T") ? dateTime(item.occurredAt) : shortDate(item.occurredAt)}</strong><small>{item.meta || "Hệ thống"}</small></div>
                  </div>
                ))}
                {!filteredRecentActivity.length && <div className="compact-empty"><History size={19} /><div><strong>Chưa có hoạt động phù hợp</strong><p>Không có dữ liệu trong nhóm đang chọn.</p></div></div>}
              </div>
            </section>
          </main>
          <aside className="member-profile-rail">
            <div className="workspace-section-title"><div><h2>Thông tin hội viên</h2><p>Liên hệ, hồ sơ và phụ trách</p></div>{canFinancial && <button className="icon-text-action" onClick={() => open("edit")}><Pencil size={13} /> Chỉnh sửa</button>}</div>
            <dl>
              {canFinancial ? (
                <>
                  <InlineEditField label="Điện thoại" value={member.phone} type="tel" displayValue={formatPhone(member.phone)} onSave={(phone) => updateMember.mutateAsync({ payload: { phone }, silent: true })} pending={updateMember.isPending} utilityActions={member.phone && <><a href={`tel:${member.phone}`} title="Gọi điện" aria-label="Gọi điện"><Phone size={12} /></a><CopyValueButton value={member.phone} label="số điện thoại" /></>} />
                  <InlineEditField label="Email" value={member.email} type="email" emptyAction="+ Thêm email" onSave={(email) => updateMember.mutateAsync({ payload: { email }, silent: true })} pending={updateMember.isPending} utilityActions={member.email && <><a href={`mailto:${member.email}`} title="Gửi email" aria-label="Gửi email"><Mail size={12} /></a><CopyValueButton value={member.email} label="email" /></>} />
                  <InlineEditField label="Nguồn khách" value={member.source} onSave={(source) => updateMember.mutateAsync({ payload: { source }, silent: true })} pending={updateMember.isPending} />
                </>
              ) : (
                <>
                  <div><dt>Điện thoại</dt><dd><span className="profile-value-actions">{formatPhone(member.phone) || "—"}{member.phone && <><a href={`tel:${member.phone}`} title="Gọi điện"><Phone size={12} /></a><CopyValueButton value={member.phone} label="số điện thoại" /></>}</span></dd></div>
                  <div><dt>Email</dt><dd><span className="profile-value-actions">{member.email || "—"}{member.email && <><a href={`mailto:${member.email}`} title="Gửi email"><Mail size={12} /></a><CopyValueButton value={member.email} label="email" /></>}</span></dd></div>
                  <div><dt>Nguồn khách</dt><dd>{member.source || "—"}</dd></div>
                </>
              )}
              <div>
                <dt>Ngày sinh</dt>
                <dd>{member.dateOfBirth ? `${shortDate(member.dateOfBirth)}${age != null ? ` · ${age} tuổi` : ""}` : "Chưa cập nhật"}</dd>
              </div>
              <div>
                <dt>Giới tính</dt>
                <dd>{genderLabel}</dd>
              </div>
              <div>
                <dt>Mã hội viên</dt>
                <dd><span className="profile-value-actions font-mono">{member.code}<CopyValueButton value={member.code} label="mã hội viên" /></span></dd>
              </div>
              <div>
                <dt>Mã MBS</dt>
                <dd><span className="profile-value-actions font-mono">{member.mbsCode || "—"}<CopyValueButton value={member.mbsCode} label="mã MBS" /></span></dd>
              </div>
              <div>
                <dt>Định danh DAH</dt>
                  <dd>
                    {member.personUuid ? (
                      <span className="inline-flex items-center gap-2">
                        <span className="font-mono text-[12px]">
                          {member.personUuid}
                        </span>
                        <CopyValueButton value={member.personUuid} label="mã DAH" />
                        {canFinancial && (
                          <>
                            <button
                              className="inline-flex items-center gap-1 font-medium text-blue-700 hover:underline"
                              onClick={() => setIdentityLinkOpen(true)}
                            >
                              <ScanFace size={14} /> Gán lại
                            </button>
                            <button
                              className="inline-flex items-center gap-1 font-medium text-red-700 hover:underline"
                              onClick={() => setIdentityDeleteOpen(true)}
                            >
                              Xóa
                            </button>
                          </>
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
            <section className="member-note-section">
              <div className="workspace-section-title"><div><h2>Ghi chú chăm sóc</h2><p>Thông tin nội bộ quan trọng</p></div>{canFinancial && <button className="icon-text-action" onClick={() => open("edit")}><Pencil size={13} /> Sửa</button>}</div>
              <p>{member.notes || "Chưa có ghi chú cho hội viên này."}</p>
            </section>
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
                    <div className="membership-event-card">
                      <div className="membership-event-card-head">
                        <span className={`audit-action audit-${event.action}`}>
                          {membershipEventLabels[event.action] || event.action}
                        </span>
                        <small>{event.createdBy}</small>
                      </div>
                      <strong>{eventPrimaryText(event)}</strong>
                      <ul>
                        {eventDetailLines(event).map((line) => (
                          <li key={line}>{line}</li>
                        ))}
                      </ul>
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
      {tab === "pt-sessions" && (
        <section className="mt-5">
          <div className="section-header">
            <div>
              <h2>Buổi PT đã tập</h2>
              <p>Nhật ký các lần ghi nhận tập PT, cộng buổi và trừ buổi</p>
            </div>
          </div>
          <DataTable
            rows={member.ptSessionLogs}
            columns={ptSessionColumns}
            emptyTitle="Chưa có buổi PT đã ghi nhận"
            emptyDescription="Khi xử lý hội viên bằng nút Tập PT, buổi tập sẽ xuất hiện tại đây."
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
      {isAdmin && tab === "activity" && (
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
                    {auditChangeLines(item).map((change) => (
                      <span className="audit-change-line" key={change.key}>
                        <strong>{change.label}</strong>
                        <span>{change.text}</span>
                      </span>
                    ))}
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
      <MembershipFreezeForm
        membership={selectedMembership}
        freeze={selectedFreeze}
        open={dialog === "freeze-edit"}
        onClose={() => {
          setDialog(null);
          setSelectedMembership(null);
          setSelectedFreeze(null);
        }}
        onSubmit={(payload) =>
          freezeMutation.mutate({
            membershipId: selectedMembership.id,
            freezeId: selectedFreeze.id,
            method: "PATCH",
            payload,
          })
        }
        pending={freezeMutation.isPending}
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
      <DahIdentityDeleteModal
        open={identityDeleteOpen}
        onClose={() => setIdentityDeleteOpen(false)}
        memberId={member.id}
        memberName={member.name}
        personUuid={member.personUuid}
        onDeleted={() => {
          refresh();
          notify.success(`Đã xóa FaceID của ${member.name}.`);
        }}
      />
    </>
  );
}
