import { useEffect, useMemo, useState } from "react";
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
import { initials } from "../../utils/format";
import { GlobalSearch } from "../common/GlobalSearch";
import { NetworkStatusBanner } from "../common/NetworkStatusBanner";
import { AlertCenter } from "../common/AlertCenter";
import { CheckinSpeechPlayer } from "../common/CheckinSpeechPlayer";
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
      { to: "/member-processing", label: "Xử lý hội viên", icon: ClipboardCheck, roles: ["admin", "manager", "receptionist"] },
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

const clockFormatter = new Intl.DateTimeFormat("vi-VN", {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
  timeZone: "Asia/Ho_Chi_Minh",
});

const dateFormatter = new Intl.DateTimeFormat("vi-VN", {
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  timeZone: "Asia/Ho_Chi_Minh",
});

function SystemClock() {
  const [tick, setTick] = useState(() => Date.now());
  const [sync, setSync] = useState(null);

  useEffect(() => {
    let active = true;
    let refreshTimer;

    const loadHealth = async () => {
      try {
        const response = await fetch("/api/health", { credentials: "include" });
        const data = await response.json();
        if (!active || !data?.serverTime) return;
        setSync({
          baseClientMs: Date.now(),
          baseServerMs: Date.parse(data.serverTime),
          autoCheckoutTime: data.autoCheckout?.time || "23:58",
          nextRunAt: data.autoCheckout?.nextRunAt || null,
          status: data.status,
        });
      } catch {
        if (active) {
          setSync((current) => current && { ...current, status: "offline" });
        }
      } finally {
        if (active) refreshTimer = window.setTimeout(loadHealth, 30000);
      }
    };

    loadHealth();
    return () => {
      active = false;
      window.clearTimeout(refreshTimer);
    };
  }, []);

  useEffect(() => {
    const interval = window.setInterval(() => setTick(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, []);

  const serverNow = useMemo(() => {
    if (!sync?.baseServerMs) return new Date(tick);
    return new Date(sync.baseServerMs + (tick - sync.baseClientMs));
  }, [sync, tick]);

  return (
    <div className="system-clock">
      <strong>{clockFormatter.format(serverNow)}</strong>
      <span>{dateFormatter.format(serverNow)}</span>
      <small>Auto checkout {sync?.autoCheckoutTime || "23:58"}</small>
    </div>
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
          <SystemClock />
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
      <MemberQuickDrawer memberId={quickMember} onClose={closeQuickMember} />
    </div>
  );
}
