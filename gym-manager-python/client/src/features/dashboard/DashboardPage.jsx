import { useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  CalendarClock,
  Clock3,
  CreditCard,
  RefreshCw,
  ScanLine,
  ScrollText,
  Users,
  WalletCards,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Link } from "react-router-dom";
import { useAuth } from "../../app/AuthContext";
import { api, queryString } from "../../services/api";
import { DataTable } from "../../components/ui/DataTable";
import { Pagination } from "../../components/ui/Pagination";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { Select } from "../../components/ui/Form";
import { dateTime, money } from "../../utils/format";

const initials = (name = "") =>
  name
    .split(" ")
    .filter(Boolean)
    .slice(-2)
    .map((part) => part[0])
    .join("")
    .toUpperCase() || "PF";

const roleLabels = {
  admin: "Điều hành hệ thống",
  manager: "Điều hành kinh doanh",
  receptionist: "Vận hành quầy lễ tân",
  coach: "Vận hành huấn luyện",
};

const priorityLabels = {
  critical: "Khẩn cấp",
  high: "Ưu tiên cao",
  medium: "Cần theo dõi",
};

const priorityClasses = {
  critical: "priority-critical",
  high: "priority-high",
  medium: "priority-medium",
};

const metricToneClasses = {
  positive: "tone-positive",
  warning: "tone-warning",
  danger: "tone-danger",
  neutral: "tone-neutral",
};

const auditActionLabels = {
  create: "Tạo mới",
  update: "Cập nhật",
  delete: "Xóa",
  archive: "Lưu trữ",
  payment: "Thanh toán",
  upload_receipt: "Thêm chứng từ",
  checkin: "Check-in",
  checkout: "Check-out",
  freeze: "Bảo lưu",
  unfreeze: "Kết thúc bảo lưu",
  adjust_days: "Cộng / trừ ngày",
  activate: "Kích hoạt",
  suspend: "Tạm dừng",
  transfer: "Chuyển nhượng",
  upgrade: "Nâng cấp gói",
  change: "Đổi gói",
  cancel: "Hủy dịch vụ",
  login: "Đăng nhập",
  logout: "Đăng xuất",
  login_failed: "Đăng nhập lỗi",
  identity_link: "Gán FaceID",
  dah_checkin: "DAH check-in",
  dah_checkout: "DAH check-out",
  dah_denied: "DAH từ chối",
  dah_event: "DAH",
};

const auditEntityLabels = {
  member: "Hội viên",
  membership: "Gói đăng ký",
  payment: "Thanh toán",
  pt_enrollment: "Đăng ký PT",
  employee: "Nhân viên",
  plan: "Gói tập",
  attendance: "Check-in",
  user: "Tài khoản",
  auth: "Xác thực",
  membership_freeze: "Lịch bảo lưu",
  dah_identity: "FaceID",
};

const roleDisplay = {
  admin: "Admin",
  manager: "Manager",
  receptionist: "Lễ tân",
  coach: "Coach",
  system: "Hệ thống",
};

const personStatusLabels = {
  active: "Đang hoạt động",
  lead: "Tiềm năng",
  inactive: "Không hoạt động",
  cancelled: "Đã hủy",
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

function compactValue(value) {
  const text = String(value ?? "—");
  return text.length > 38 ? `${text.slice(0, 35)}…` : text;
}

function auditDetailText(row) {
  const changes = Array.isArray(row.details?.changes) ? row.details.changes : [];
  if (changes.length) {
    return changes
      .slice(0, 3)
      .map((change) => `${change.label || auditFieldLabels[change.field] || change.field}: ${compactValue(change.old)} → ${compactValue(change.new)}`)
      .join(" · ");
  }
  const labels = Array.isArray(row.details?.fieldLabels) ? row.details.fieldLabels : [];
  if (labels.length) return `Đã cập nhật: ${labels.join(", ")}`;
  const fields = Array.isArray(row.details?.fields) ? row.details.fields : [];
  if (fields.length) return `Đã cập nhật: ${fields.map((field) => auditFieldLabels[field] || field).join(", ")}`;
  return row.summary;
}

function numericDelta(current, previous, comparison = "so với hôm qua") {
  const difference = Number(current || 0) - Number(previous || 0);
  if (!difference) return { direction: "neutral", text: `Không đổi ${comparison}` };
  return {
    direction: difference > 0 ? "up" : "down",
    text: `${difference > 0 ? "+" : ""}${difference.toLocaleString("vi-VN")} ${comparison}`,
  };
}

function percentageDelta(current, previous) {
  if (!previous) return { direction: "neutral", text: "Chưa có kỳ so sánh" };
  const percent = ((Number(current || 0) - previous) / previous) * 100;
  if (Math.abs(percent) < 0.05) return { direction: "neutral", text: "Không đổi so với cùng kỳ" };
  return {
    direction: percent > 0 ? "up" : "down",
    text: `${percent > 0 ? "+" : ""}${percent.toLocaleString("vi-VN", { maximumFractionDigits: 1 })}% so với cùng kỳ`,
  };
}

function Metric({ item }) {
  const TrendIcon = item.delta?.direction === "up" ? ArrowUpRight : item.delta?.direction === "down" ? ArrowDownRight : null;
  return (
    <Link className={`command-metric ${metricToneClasses[item.tone || "neutral"]}`} to={item.to}>
      <span className="command-metric-label">{item.label}</span>
      <strong>{item.value}</strong>
      <small className={`metric-delta ${item.delta?.direction || "neutral"}`}>
        {TrendIcon && <TrendIcon size={12} />}
        {item.delta?.text || item.context}
      </small>
    </Link>
  );
}

function DashboardSkeleton() {
  return (
    <div className="dashboard-loading" aria-label="Đang tải dashboard">
      <div className="skeleton h-20" />
      <div className="grid grid-cols-3 gap-4"><div className="skeleton h-36" /><div className="skeleton h-36" /><div className="skeleton h-36" /></div>
      <div className="skeleton h-72" />
    </div>
  );
}

function HoverPerson({ person, fallback = "Không xác định", type = "member" }) {
  const name = person?.name || fallback;
  return (
    <span className="audit-person-hover">
      <span className="audit-person-name">{name}</span>
      <span className={`audit-person-card ${type === "actor" ? "actor-card" : "member-card"}`} role="tooltip">
        {type !== "actor" && (
          <span className="audit-person-avatar">
            {person?.avatarImageData ? <img src={person.avatarImageData} alt="" /> : initials(name)}
          </span>
        )}
        <span>
          <strong>{name}</strong>
          <small>{type === "actor" ? `${person?.username || "system"} · ${roleDisplay[person?.role] || person?.role || "—"}` : `${person?.code || "Chưa có mã"} · ${person?.phone || "Chưa có SĐT"}`}</small>
          {type !== "actor" && <em>{personStatusLabels[person?.status] || person?.status || "Không rõ trạng thái"}</em>}
        </span>
      </span>
    </span>
  );
}

function auditTarget(row) {
  if (row.customer) return row.customer;
  if (row.customerId) {
    return {
      id: row.customerId,
      name: `Hội viên #${row.customerId}`,
      code: `#${row.customerId}`,
      phone: "",
      status: "",
    };
  }
  return null;
}

function RecentAuditPanel({ query, scope, pageSize, onScope, onPage, onPageSize }) {
  return (
    <section className={`dashboard-workspace-section dashboard-audit-panel ${query.isFetching ? "is-refreshing" : ""}`} aria-busy={query.isFetching}>
      <div className="dashboard-section-header">
        <div>
          <h2>Thao tác gần đây</h2>
          <p>Các thay đổi mới nhất trong hệ thống để admin kiểm soát nhanh.</p>
        </div>
        <div className="dashboard-audit-tools">
          <div className="dashboard-audit-tabs" role="tablist" aria-label="Phạm vi thao tác">
            <button type="button" className={scope === "today" ? "active" : ""} onClick={() => onScope("today")}>Hôm nay</button>
            <button type="button" className={scope === "all" ? "active" : ""} onClick={() => onScope("all")}>Toàn bộ</button>
          </div>
          <label>
            <span>Số bản ghi</span>
            <Select value={pageSize} onChange={(event) => onPageSize(Number(event.target.value))}>
              {[5, 10, 20].map((value) => <option key={value} value={value}>{value}</option>)}
            </Select>
          </label>
          <Link to="/audit-logs">Xem toàn bộ <ArrowRight size={13} /></Link>
        </div>
      </div>
      {query.isLoading && !query.data ? (
        <div className="dashboard-audit-loading">
          <div className="skeleton h-12" />
          <div className="skeleton h-12" />
          <div className="skeleton h-12" />
        </div>
      ) : query.isError ? (
        <div className="dashboard-audit-error">
          <strong>Không thể tải thao tác gần đây</strong>
          <button type="button" onClick={() => query.refetch()}>Thử lại</button>
        </div>
      ) : query.data?.items?.length ? (
        <>
          <div className="dashboard-audit-list">
            {query.data.items.map((row) => {
              const target = auditTarget(row);
              const actionLabel = auditActionLabels[row.action] || row.action;
              return (
                <div className="dashboard-audit-row" key={row.id}>
                  <div className="dashboard-audit-rail">
                    <span className={`audit-action audit-${row.action}`}>{actionLabel}</span>
                    <time>{dateTime(row.createdAt)}</time>
                  </div>
                  <div className="dashboard-audit-copy">
                    <strong>
                      <HoverPerson person={row.actor} type="actor" />
                      <span> đã {actionLabel.toLowerCase()}</span>
                      {target ? (
                        <>
                          <span> cho </span>
                          <HoverPerson person={target} />
                        </>
                      ) : (
                        <span> trên {auditEntityLabels[row.entityType] || row.entityType}</span>
                      )}
                    </strong>
                    <small>{auditDetailText(row)}</small>
                  </div>
                  <div className="dashboard-audit-meta">
                    <span>{auditEntityLabels[row.entityType] || row.entityType} #{row.entityId || "—"}</span>
                    {row.customerId ? (
                      <Link className="queue-action" to={`/members/${row.customerId}?tab=activity`}>
                        Xem hồ sơ <ArrowRight size={12} />
                      </Link>
                    ) : (
                      <span className="dashboard-audit-empty-link">Không có hồ sơ</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
          <Pagination
            data={query.data.pagination}
            onPage={onPage}
            pageSize={pageSize}
          />
        </>
      ) : (
        <div className="dashboard-empty">
          <ScrollText size={18} />
          <span><strong>{scope === "today" ? "Chưa có hoạt động mới hôm nay." : "Chưa có thao tác nào"}</strong>{scope !== "today" && <small>Nhật ký mới sẽ xuất hiện tại đây.</small>}</span>
        </div>
      )}
    </section>
  );
}

export function DashboardPage() {
  const { user } = useAuth();
  const [auditScope, setAuditScope] = useState("today");
  const [auditPage, setAuditPage] = useState(1);
  const [auditPageSize, setAuditPageSize] = useState(5);
  const query = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api("/api/dashboard"),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
  const auditQuery = useQuery({
    queryKey: ["dashboard-audit-logs", auditScope, auditPage, auditPageSize],
    queryFn: () =>
      api(
        `/api/audit-logs?${queryString({ scope: auditScope, page: auditPage, pageSize: auditPageSize })}`,
      ),
    enabled: user.role === "admin",
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  });
  const data = query.data;
  const isFinancialRole = ["admin", "manager"].includes(user.role);

  if (query.isLoading) return <DashboardSkeleton />;
  if (query.isError) {
    return <div className="dashboard-error"><strong>Không thể tải dashboard</strong><p>{query.error.message}</p><button className="btn btn-secondary" onClick={() => query.refetch()}>Thử lại</button></div>;
  }

  const metrics = isFinancialRole
    ? [
        { label: "Đã thu tháng", value: money(data.metrics.revenueMonth), to: "/payments", tone: "positive", delta: percentageDelta(data.metrics.revenueMonth, data.metrics.revenuePreviousMtd) },
        { label: "Công nợ quá hạn", value: money(data.metrics.overdueDebt), to: "/members?view=debt", tone: data.metrics.overdueDebt ? "danger" : "positive", context: `${money(data.metrics.outstanding)} tổng còn phải thu` },
        { label: "Hội viên hoạt động", value: data.metrics.activeMembers.toLocaleString("vi-VN"), to: "/members?view=active", context: `${data.metrics.activeRate}% trên ${data.metrics.totalMembers.toLocaleString("vi-VN")} hội viên` },
        { label: "Check-in hôm nay", value: data.metrics.checkinsToday.toLocaleString("vi-VN"), to: "/check-in", delta: numericDelta(data.metrics.checkinsToday, data.metrics.checkinsYesterday) },
        { label: "Đang trong phòng", value: data.metrics.openVisits.toLocaleString("vi-VN"), to: "/check-in", context: "Lượt chưa checkout" },
        { label: "Hết hạn trong 7 ngày", value: data.metrics.expiring7.toLocaleString("vi-VN"), to: "/members?view=expiring", tone: data.metrics.expiring7 ? "warning" : "positive", context: `${data.metrics.expiringSoon} hợp đồng trong 14 ngày` },
      ]
    : [
        { label: "Check-in hôm nay", value: data.metrics.checkinsToday.toLocaleString("vi-VN"), to: "/check-in", delta: numericDelta(data.metrics.checkinsToday, data.metrics.checkinsYesterday) },
        { label: "Đang trong phòng", value: data.metrics.openVisits.toLocaleString("vi-VN"), to: "/check-in", context: "Lượt chưa checkout" },
        { label: "Hội viên hoạt động", value: data.metrics.activeMembers.toLocaleString("vi-VN"), to: "/members?view=active", context: `${data.metrics.activeRate}% trên tổng hội viên` },
        { label: "Hết hạn trong 7 ngày", value: data.metrics.expiring7.toLocaleString("vi-VN"), to: "/members?view=expiring", tone: data.metrics.expiring7 ? "warning" : "positive", context: `${data.metrics.expiringSoon} hợp đồng trong 14 ngày` },
        { label: "Vừa hết hạn", value: data.metrics.newlyExpired30.toLocaleString("vi-VN"), to: "/members?view=expired", tone: data.metrics.newlyExpired30 ? "danger" : "positive", context: "Hợp đồng trong 30 ngày qua" },
        { label: "Công nợ cần thu", value: money(data.metrics.overdueDebt), to: "/members?view=debt", tone: data.metrics.overdueDebt ? "danger" : "positive", context: "Các khoản đã quá hạn" },
      ];

  const health = data.membershipHealth;
  const healthRows = [
    { key: "activeStable", label: "Active ổn định", value: health.activeStable, colorClass: "health-active" },
    { key: "expiring7", label: "Hết hạn 0–7 ngày", value: health.expiring7, colorClass: "health-expiring" },
    { key: "expiring8To14", label: "Hết hạn 8–14 ngày", value: health.expiring8To14, colorClass: "health-pending" },
    { key: "expiredRecent", label: "Vừa hết hạn ≤30 ngày", value: health.expiredRecent, colorClass: "health-expired" },
    { key: "expiredOlder", label: "Hết hạn trên 30 ngày", value: health.expiredOlder, colorClass: "health-inactive" },
    { key: "pending", label: "Chờ kích hoạt", value: health.pending, colorClass: "health-lead" },
    { key: "suspended", label: "Đang tạm dừng", value: health.suspended, colorClass: "health-frozen" },
  ];

  const debtRows = [
    ["Chưa đến hạn", data.financialHealth.debtAging.notDue],
    ["Quá hạn 1–7 ngày", data.financialHealth.debtAging.days1To7],
    ["Quá hạn 8–30 ngày", data.financialHealth.debtAging.days8To30],
    ["Quá hạn trên 30 ngày", data.financialHealth.debtAging.over30],
    ["Chưa đặt hạn", data.financialHealth.debtAging.noDueDate],
  ];

  return (
    <div className={`operations-dashboard role-${user.role}`}>
      <header className="dashboard-command-header">
        <div>
          <span>{roleLabels[user.role] || "Tổng quan vận hành"}</span>
          <h1>Trung tâm điều hành</h1>
          <p>Ưu tiên công việc, sức khỏe hội viên và hiệu suất vận hành hôm nay.</p>
        </div>
        <div className="dashboard-header-actions">
          <span className="data-freshness"><Clock3 size={13} /> Cập nhật {dateTime(data.generatedAt)}</span>
          <button className="icon-button" onClick={() => query.refetch()} disabled={query.isFetching} title="Làm mới dữ liệu" aria-label="Làm mới dashboard"><RefreshCw size={16} className={query.isFetching ? "animate-spin" : ""} /></button>
          <Link className="btn btn-secondary" to={user.role === "coach" ? "/training" : "/check-in"}>{user.role === "coach" ? <Users size={15} /> : <ScanLine size={15} />}{user.role === "coach" ? "Khách PT" : "Điểm danh"}</Link>
          {isFinancialRole && <Link className="btn btn-primary" to="/payments"><CreditCard size={15} /> Thanh toán</Link>}
        </div>
      </header>

      <section className="command-metric-strip" aria-label="Chỉ số điều hành">
        {metrics.map((item) => <Metric item={item} key={item.label} />)}
      </section>

      <div className="dashboard-primary-grid">
        <section className="dashboard-workspace-section attendance-intelligence">
          <div className="dashboard-section-header">
            <div><h2>Nhịp độ check-in</h2><p>7 ngày hiện tại so với tuần liền trước</p></div>
            <Link to="/check-in">Giám sát điểm danh <ArrowRight size={13} /></Link>
          </div>
          <div className="dashboard-chart">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.activity} margin={{ top: 14, right: 12, left: -20, bottom: 0 }} barGap={3}>
                <CartesianGrid vertical={false} stroke="#e2e8f0" />
                <XAxis dataKey="label" axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: "#64748b" }} />
                <YAxis allowDecimals={false} axisLine={false} tickLine={false} tick={{ fontSize: 10, fill: "#94a3b8" }} />
                <Tooltip contentStyle={{ border: "1px solid #cbd5e1", borderRadius: 6, boxShadow: "0 8px 20px rgba(15,23,42,.08)", fontSize: 11 }} />
                <Legend iconType="square" wrapperStyle={{ fontSize: 10 }} />
                <Bar dataKey="previousCheckins" name="Tuần trước" fill="#cbd5e1" radius={[2, 2, 0, 0]} />
                <Bar dataKey="checkins" name="Tuần này" fill="#163a5f" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section className="dashboard-workspace-section membership-health">
          <div className="dashboard-section-header">
            <div><h2>Sức khỏe hợp đồng</h2><p>{health.totalContracts.toLocaleString("vi-VN")} hợp đồng gói, không phải số hội viên</p></div>
            <Link to="/memberships">Xem gói tập <ArrowRight size={13} /></Link>
          </div>
          <div className="health-distribution" aria-label="Phân bổ trạng thái hợp đồng">
            {healthRows.filter((row) => row.value).map((row) => <span key={row.key} className={row.colorClass} style={{ width: `${Math.max((row.value / health.totalContracts) * 100, 0.5)}%` }} title={`${row.label}: ${row.value}`} />)}
          </div>
          <div className="health-list">
            {healthRows.map((row) => <div key={row.key}><span><i className={`health-dot ${row.colorClass}`} />{row.label}</span><strong>{row.value.toLocaleString("vi-VN")}</strong></div>)}
          </div>
        </section>
      </div>

      <section className="dashboard-workspace-section action-queue">
        <div className="dashboard-section-header">
          <div><h2>Hàng đợi cần hành động</h2><p>Ưu tiên các vấn đề mới và còn giá trị xử lý, không trộn backlog hết hạn cũ</p></div>
          <Link to="/members">Mở danh sách hội viên <ArrowRight size={13} /></Link>
        </div>
        <DataTable
          loading={query.isFetching && !data}
          rows={data.attention}
          density="compact"
          columns={[
            { key: "priority", label: "Ưu tiên", render: (row) => <span className={`priority-badge ${priorityClasses[row.priority] || "priority-medium"}`}>{priorityLabels[row.priority]}</span> },
            { key: "member", label: "Hội viên", render: (row) => <Link className="cell-primary hover:underline" to={`/members/${row.memberId}`}>{row.member}<small className="cell-secondary block">{row.code}</small></Link> },
            { key: "issue", label: "Vấn đề", render: (row) => <div><strong className="cell-primary">{row.issue}</strong><small className="cell-secondary block">{row.package} · {row.timing}</small></div> },
            { key: "value", label: "Giá trị", className: "text-right", render: (row) => row.value != null ? <strong>{money(row.value)}</strong> : "—" },
            { key: "owner", label: "Phụ trách", render: (row) => row.owner },
            { key: "action", label: "", className: "text-right", render: (row) => <Link className="queue-action" to={`/members/${row.memberId}`}>{row.actionLabel} <ArrowRight size={12} /></Link> },
          ]}
          emptyTitle="Không có vấn đề ưu tiên"
          emptyDescription="Các vấn đề mới và công nợ cần xử lý hiện đã ổn định."
        />
      </section>

      <div className={`dashboard-secondary-grid ${isFinancialRole ? "has-finance" : ""}`}>
        {isFinancialRole && (
          <section className="dashboard-workspace-section financial-health">
            <div className="dashboard-section-header">
              <div><h2>Chất lượng công nợ</h2><p>Aging theo hạn thanh toán hiện tại</p></div>
              <Link to="/reports">Mở báo cáo <ArrowRight size={13} /></Link>
            </div>
            <div className="finance-summary"><span><WalletCards size={16} /><small>Đã thu hôm nay</small><strong>{money(data.metrics.revenueToday)}</strong></span><span><CreditCard size={16} /><small>Tổng còn phải thu</small><strong>{money(data.metrics.outstanding)}</strong></span></div>
            <div className="debt-aging-list">
              {debtRows.map(([label, bucket]) => <div key={label}><span>{label}<small>{bucket.count} hợp đồng</small></span><strong>{money(bucket.amount)}</strong></div>)}
            </div>
          </section>
        )}

        <section className="dashboard-workspace-section recent-operations">
          <div className="dashboard-section-header">
            <div><h2>Check-in gần đây</h2><p>Luồng hoạt động mới nhất tại phòng tập</p></div>
            <Link to="/check-in">Xem toàn bộ <ArrowRight size={13} /></Link>
          </div>
          <div className="recent-checkin-list">
            {data.recentCheckins.map((row) => <div key={row.id}><Clock3 size={14} /><span><strong>{row.member || "Không xác định"}</strong><small>{row.code || "Không có mã"}</small></span><time>{dateTime(row.time)}</time><StatusBadge status={row.status} /></div>)}
            {!data.recentCheckins.length && <div className="dashboard-empty"><CalendarClock size={18} /><span><strong>Chưa có check-in</strong><small>Hoạt động mới sẽ xuất hiện tại đây.</small></span></div>}
          </div>
        </section>
      </div>

      {user.role === "admin" && (
        <RecentAuditPanel
          query={auditQuery}
          scope={auditScope}
          pageSize={auditPageSize}
          onScope={(scope) => {
            setAuditScope(scope);
            setAuditPage(1);
          }}
          onPage={setAuditPage}
          onPageSize={(value) => {
            setAuditPageSize(value);
            setAuditPage(1);
          }}
        />
      )}
    </div>
  );
}
