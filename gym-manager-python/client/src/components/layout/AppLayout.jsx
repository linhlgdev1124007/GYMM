import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  NavLink,
  Outlet,
  useLocation,
  useNavigate,
  useSearchParams,
} from "react-router-dom";
import {
  BarChart3,
  CheckCircle2,
  ChevronRight,
  CreditCard,
  Dumbbell,
  LayoutDashboard,
  Menu,
  Package,
  ClipboardCheck,
  RefreshCw,
  Warehouse,
  ScrollText,
  Settings,
  ShieldCheck,
  TicketCheck,
  UserRoundCog,
  Users,
  X,
} from "lucide-react";
import { useAuth } from "../../app/AuthContext";
import { api } from "../../services/api";
import { notify } from "../../services/notify";
import { initials } from "../../utils/format";
import { GlobalSearch } from "../common/GlobalSearch";
import { NetworkStatusBanner } from "../common/NetworkStatusBanner";
import { AlertCenter } from "../common/AlertCenter";
import { CheckinSpeechPlayer } from "../common/CheckinSpeechPlayer";
import { DahAgentWatcher } from "../common/DahAgentWatcher";
import { MemberQuickDrawer } from "../../features/members/MemberQuickDrawer";

const groups = [
  {
    label: "Tổng quan",
    items: [{ to: "/dashboard", label: "Dashboard", icon: LayoutDashboard }],
  },
  {
    label: "Quản lý",
    items: [
      { to: "/members", label: "Hội viên", icon: Users },
      { to: "/memberships", label: "Đăng ký gói", icon: CreditCard, roles: ["admin", "manager", "receptionist"] },
      {
        to: "/plans",
        label: "Gói tập",
        icon: Package,
        roles: ["admin", "manager"],
      },
      {
        to: "/trainers",
        label: "Nhân viên",
        icon: UserRoundCog,
        roles: ["admin", "manager"],
      },
      { to: "/training", label: "Khách PT", icon: Dumbbell },
    ],
  },
  {
    label: "Vận hành",
    items: [
      { to: "/check-in", label: "Điểm danh", icon: CheckCircle2, roles: ["admin", "manager", "receptionist"] },
      { to: "/member-processing", label: "Xử lý hội viên", icon: ClipboardCheck, roles: ["admin", "manager", "receptionist", "coach"] },
      { to: "/day-passes", label: "Khách tập ngày", icon: TicketCheck, roles: ["admin", "manager", "receptionist"] },
      { to: "/payments", label: "Thanh toán", icon: CreditCard, roles: ["admin", "manager", "receptionist"] },
      { to: "/inventory", label: "Kho nội bộ", icon: Warehouse, roles: ["admin"] },
    ],
  },
  {
    label: "Phân tích",
    items: [
      {
        to: "/reports",
        label: "Báo cáo",
        icon: BarChart3,
        roles: ["admin", "manager"],
      },
    ],
  },
  {
    label: "Hệ thống",
    items: [
      {
        to: "/accounts",
        label: "Tài khoản & quyền",
        icon: ShieldCheck,
        roles: ["admin"],
      },
      {
        to: "/audit-logs",
        label: "Nhật ký thao tác",
        icon: ScrollText,
        roles: ["admin"],
      },
      {
        to: "/settings",
        label: "Cài đặt & thiết bị",
        icon: Settings,
        roles: ["admin"],
      },
    ],
  },
];

const AUTO_SYNC_ROLES = new Set(["admin", "manager", "receptionist"]);

function AutoSyncControl({ role }) {
  const client = useQueryClient();
  const enabled = AUTO_SYNC_ROLES.has(role);
  const status = useQuery({
    queryKey: ["dah-local-agent-status"],
    queryFn: () => api("/api/dah/local-agent/status"),
    enabled,
    refetchInterval: 60_000,
    retry: false,
    staleTime: 30_000,
  });
  const requestSync = useMutation({
    mutationFn: () => api("/api/dah/local-agent/sync-request", { method: "POST", body: { lookbackHours: 24 } }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["dah-local-agent-status"] });
      notify.success("Đã gửi yêu cầu auto sync tới DAH Agent.");
    },
    onError: (error) => notify.errorFrom(error, "Không thể gửi yêu cầu auto sync."),
  });
  const summary = status.data?.agent?.lastSyncSummary || {};
  const remaining = summary.remaining || summary;
  const issueCount = Number(remaining.failCount ?? (Number(remaining.matched || 0) + Number(remaining.unknown || 0) + Number(remaining.rejected || 0)));
  const online = status.data?.agent?.status === "online";
  return (
    <button
      type="button"
      className={`auto-sync-button ${issueCount > 0 ? "danger" : ""}`}
      onClick={() => requestSync.mutate()}
      disabled={!enabled || requestSync.isPending}
      title={enabled ? "Yêu cầu Agent sync 24 giờ gần nhất" : "Tài khoản hiện tại không có quyền sync DAH"}
    >
      <RefreshCw size={15} className={requestSync.isPending ? "animate-spin" : ""} />
      <span>
        <strong>Auto sync</strong>
        <small>{online ? "Agent online" : "Agent offline"}</small>
      </span>
      <b>{issueCount}</b>
    </button>
  );
}

function Sidebar({ open, close, role }) {
  return (
    <>
      <div
        className={`sidebar-overlay ${open ? "open" : ""}`}
        onClick={close}
      />
      <aside className={`sidebar ${open ? "open" : ""}`}>
        <div className="brand">
          <div className="brand-mark">
            <Dumbbell size={19} />
          </div>
          <div>
            <strong>PulseFit</strong>
            <span>Gym Management</span>
          </div>
          <button
            className="sidebar-close"
            onClick={close}
            aria-label="Đóng menu"
          >
            <X size={20} />
          </button>
        </div>
        <nav>
          {groups.map((group) => {
            const items = group.items.filter(
              (item) => !item.roles || item.roles.includes(role),
            );
            return items.length ? (
              <div className="nav-group" key={group.label}>
                <span className="nav-label">{group.label}</span>
                {items.map(({ to, label, icon: Icon }) => (
                  <NavLink
                    key={to}
                    to={to}
                    onClick={close}
                    className={({ isActive }) =>
                      `nav-link ${isActive ? "active" : ""}`
                    }
                  >
                    <Icon size={17} />
                    <span>{label}</span>
                  </NavLink>
                ))}
              </div>
            ) : null;
          })}
        </nav>
        <div className="sidebar-status">
          <span />
          <div>
            <strong>Hệ thống hoạt động</strong>
            <small>MySQL · Local server</small>
          </div>
          <AutoSyncControl role={role} />
        </div>
      </aside>
    </>
  );
}

export function AppLayout() {
  const [open, setOpen] = useState(false);
  const { user, logout, logoutPending } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const current = groups
    .flatMap((group) => group.items)
    .sort((a, b) => b.to.length - a.to.length)
    .find((item) => location.pathname.startsWith(item.to));
  const quickMember = !location.pathname.startsWith("/members")
    ? params.get("member")
    : null;
  const interceptMemberLink = (event) => {
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey
    )
      return;
    const anchor = event.target.closest("a");
    if (anchor?.dataset.memberFullProfile === "true") return;
    const match = anchor?.getAttribute("href")?.match(/^\/members\/(\d+)$/);
    if (!match) return;
    event.preventDefault();
    const next = new URLSearchParams(params);
    next.set("member", match[1]);
    navigate(`${location.pathname}?${next}`);
  };
  const closeQuickMember = () =>
    setParams((currentParams) => {
      const next = new URLSearchParams(currentParams);
      next.delete("member");
      return next;
    });
  return (
    <div className="app-layout" onClickCapture={interceptMemberLink}>
      <Sidebar open={open} close={() => setOpen(false)} role={user?.role} />
      <div className="app-main">
        <NetworkStatusBanner />
        <header className="topbar">
          <div className="topbar-context">
            <button
              className="menu-button"
              onClick={() => setOpen(true)}
              aria-label="Mở menu"
            >
              <Menu size={20} />
            </button>
            <span>PulseFit</span>
            <ChevronRight size={14} />
            <strong>{current?.label || "Dashboard"}</strong>
          </div>
          <GlobalSearch />
          <CheckinSpeechPlayer enabled={["admin", "manager", "receptionist"].includes(user?.role)} />
          <AlertCenter />
          <div className="user-menu">
            <div className="avatar avatar-sm">
              {initials(user?.displayName)}
            </div>
            <div>
              <strong>{user?.displayName}</strong>
              <span>{user?.role}</span>
            </div>
            <button
              className="text-button"
              onClick={logout}
              disabled={logoutPending}
              aria-busy={logoutPending || undefined}
            >
              {logoutPending ? "Đang thoát…" : "Đăng xuất"}
            </button>
          </div>
        </header>
        <main className="main-content">
          <Outlet />
        </main>
      </div>
      <DahAgentWatcher role={user?.role} />
      <MemberQuickDrawer memberId={quickMember} onClose={closeQuickMember} />
    </div>
  );
}
