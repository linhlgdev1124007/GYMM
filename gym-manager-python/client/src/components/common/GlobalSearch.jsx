import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BarChart3,
  CheckCircle2,
  ClipboardCheck,
  CreditCard,
  LayoutDashboard,
  Package,
  Plus,
  Search,
  Settings,
  ShieldCheck,
  UserRound,
  UserRoundCog,
  Users,
  X,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../app/AuthContext";
import { api, queryString } from "../../services/api";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";
import { StatusBadge } from "../ui/StatusBadge";

const commands = [
  { id: "dashboard", label: "Mở Dashboard", description: "Tổng quan vận hành", path: "/dashboard", icon: LayoutDashboard, keywords: "tong quan home" },
  { id: "members", label: "Mở Hội viên", description: "Tìm kiếm và vận hành hồ sơ", path: "/members", icon: Users, keywords: "khach hang customer" },
  { id: "new-member", label: "Thêm hội viên", description: "Mở nhanh biểu mẫu tạo hồ sơ", path: "/members?create=1", icon: Plus, roles: ["admin", "manager", "receptionist"], keywords: "tao khach hang new" },
  { id: "memberships", label: "Mở Đăng ký gói", description: "Theo dõi gói và công nợ", path: "/memberships", icon: CreditCard, roles: ["admin", "manager", "receptionist"], keywords: "membership cong no" },
  { id: "new-membership", label: "Đăng ký gói cho hội viên", description: "Tìm hội viên và tạo đăng ký mới", path: "/memberships?create=1", icon: Plus, roles: ["admin", "manager", "receptionist"], keywords: "gia han tao goi" },
  { id: "plans", label: "Mở Gói tập", description: "Danh mục sản phẩm và giá", path: "/plans", icon: Package, roles: ["admin", "manager"], keywords: "dich vu package" },
  { id: "staff", label: "Mở Nhân viên", description: "Nhân sự và tải PT", path: "/trainers", icon: UserRoundCog, roles: ["admin", "manager"], keywords: "coach pt staff" },
  { id: "training", label: "Mở Khách PT", description: "Lịch tập và phân công Coach", path: "/training", icon: UserRound, keywords: "coach lich tap" },
  { id: "checkin", label: "Giám sát điểm danh", description: "Dữ liệu check-in tự động từ DAH", path: "/check-in", icon: CheckCircle2, roles: ["admin", "manager", "receptionist"], keywords: "attendance dah vao phong" },
  { id: "member-processing", label: "Mở Xử lý hội viên", description: "Phân loại check-in PT hoặc tập thường", path: "/member-processing", icon: ClipboardCheck, roles: ["admin", "manager", "receptionist", "coach"], keywords: "xu ly hoi vien pt checkin" },
  { id: "payments", label: "Mở Thanh toán", description: "Đối soát phiếu thu và chứng từ", path: "/payments", icon: CreditCard, roles: ["admin", "manager", "receptionist"], keywords: "payment doanh thu bill" },
  { id: "reports", label: "Mở Báo cáo", description: "Doanh thu, attendance và công nợ", path: "/reports", icon: BarChart3, roles: ["admin", "manager"], keywords: "report phan tich" },
  { id: "accounts", label: "Mở Tài khoản & quyền", description: "Người dùng và phân quyền", path: "/accounts", icon: ShieldCheck, roles: ["admin"], keywords: "user role permission" },
  { id: "settings", label: "Mở Cài đặt & thiết bị", description: "Ngân hàng và thiết bị", path: "/settings", icon: Settings, roles: ["admin"], keywords: "bank device" },
];

const normalize = (value = "") =>
  value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/đ/g, "d");

function recentMembers() {
  try {
    return JSON.parse(localStorage.getItem("pulsefit-recent-members") || "[]");
  } catch {
    return [];
  }
}

export function GlobalSearch() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [active, setActive] = useState(0);
  const [recent, setRecent] = useState(recentMembers);
  const q = useDebouncedValue(search, 180);
  const results = useQuery({
    queryKey: ["global-search", q],
    queryFn: () =>
      api(`/api/members?${queryString({ q, page: 1, pageSize: 10 })}`),
    enabled: open && q.length >= 2,
  });
  const availableCommands = useMemo(
    () => commands.filter((item) => !item.roles || item.roles.includes(user?.role)),
    [user?.role],
  );
  const canOperateMember = ["admin", "manager", "receptionist"].includes(user?.role);
  const matchedCommands = useMemo(() => {
    const term = normalize(search.trim());
    if (!term) return availableCommands.slice(0, 6);
    return availableCommands.filter((item) =>
      normalize(`${item.label} ${item.description} ${item.keywords}`).includes(term),
    ).slice(0, 6);
  }, [availableCommands, search]);
  const memberItems = search.trim()
    ? (results.data?.items || [])
    : recent;
  const memberChoices = memberItems.flatMap((item) => {
    const base = [{ ...item, kind: "member", action: "", actionLabel: "Mở hồ sơ" }];
    if (!search.trim() || !canOperateMember) return base;
    return [
      ...base,
      { ...item, kind: "member-action", action: "payment", actionLabel: "Thu tiền" },
      { ...item, kind: "member-action", action: "renew", actionLabel: item.membership ? "Gia hạn" : "Đăng ký gói" },
      { ...item, kind: "member-action", action: "training", actionLabel: item.trainers?.length ? "Đổi nhóm PT" : "Gán nhóm PT" },
    ];
  });
  const choices = [
    ...matchedCommands.map((item) => ({ ...item, kind: "command" })),
    ...memberChoices,
  ];

  useEffect(() => {
    const shortcut = (event) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((value) => !value);
      }
    };
    document.addEventListener("keydown", shortcut);
    return () => document.removeEventListener("keydown", shortcut);
  }, []);
  useEffect(() => {
    if (!open) {
      setSearch("");
      setActive(0);
    }
  }, [open]);
  useEffect(() => setActive(0), [q]);

  const choose = (item) => {
    if (item.kind === "member" || item.kind === "member-action") {
      const nextRecent = [item, ...recent.filter((row) => row.id !== item.id)].slice(0, 5);
      setRecent(nextRecent);
      localStorage.setItem("pulsefit-recent-members", JSON.stringify(nextRecent));
      navigate(`/members?member=${item.id}${item.action ? `&action=${item.action}` : ""}`);
    } else {
      navigate(item.path);
    }
    setOpen(false);
  };

  return (
    <>
      <button className="global-search-trigger" onClick={() => setOpen(true)}>
        <Search size={15} />
        <span>Tìm kiếm hoặc mở nhanh…</span>
        <kbd>Ctrl K</kbd>
      </button>
      {open && (
        <div
          className="command-layer"
          onMouseDown={(event) =>
            event.target === event.currentTarget && setOpen(false)
          }
        >
          <section
            className="command-panel"
            role="dialog"
            aria-modal="true"
            aria-label="Tìm kiếm và thao tác nhanh"
          >
            <div className="command-input">
              <Search size={18} />
              <input
                autoFocus
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Tìm hội viên, màn hình hoặc tác vụ…"
                onKeyDown={(event) => {
                  if (event.nativeEvent?.isComposing || event.isComposing) return;
                  if (event.key === "Escape") setOpen(false);
                  if (event.key === "ArrowDown") {
                    event.preventDefault();
                    setActive((value) => Math.min(value + 1, choices.length - 1));
                  }
                  if (event.key === "ArrowUp") {
                    event.preventDefault();
                    setActive((value) => Math.max(value - 1, 0));
                  }
                  if (event.key === "Enter" && choices[active]) choose(choices[active]);
                }}
              />
              <button onClick={() => setOpen(false)} aria-label="Đóng tìm kiếm">
                <X size={17} />
              </button>
            </div>
            <div className="command-results">
              {!!matchedCommands.length && <div className="command-group-label">Điều hướng & tác vụ</div>}
              {matchedCommands.map((item, index) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.id}
                    className={index === active ? "active" : ""}
                    onMouseEnter={() => setActive(index)}
                    onClick={() => choose({ ...item, kind: "command" })}
                  >
                    <div className="command-icon"><Icon size={16} /></div>
                    <span><strong>{item.label}</strong><small>{item.description}</small></span>
                    <kbd>Enter</kbd>
                  </button>
                );
              })}
              {results.isLoading && search.trim() && (
                <div className="space-y-2 p-3">
                  <div className="skeleton h-12" />
                  <div className="skeleton h-12" />
                </div>
              )}
              {!!memberItems.length && !results.isLoading && (
                <div className="command-group-label">
                  {search.trim() ? "Hội viên" : "Hội viên gần đây"}
                </div>
              )}
              {!results.isLoading && memberChoices.map((row, index) => {
                const choiceIndex = matchedCommands.length + index;
                return (
                  <button
                    key={`member-${row.id}-${row.action || "open"}`}
                    className={choiceIndex === active ? "active" : ""}
                    onMouseEnter={() => setActive(choiceIndex)}
                    onClick={() => choose({ ...row, kind: "member" })}
                  >
                    <div className="avatar avatar-md"><UserRound size={15} /></div>
                    <span>
                      <strong>{row.name}</strong>
                      <small>
                        {row.actionLabel} · {row.code} · {row.phone || "Chưa có SĐT"} · {row.membership?.package.name || "Chưa có gói"}
                      </small>
                    </span>
                    {row.action ? <kbd>{row.actionLabel}</kbd> : <StatusBadge status={row.membership?.status || row.status} />}
                  </button>
                );
              })}
              {search.trim().length === 1 && <p>Nhập thêm một ký tự để tìm hội viên; lệnh điều hướng vẫn dùng được ngay.</p>}
              {q.length >= 2 && !results.isLoading && !memberItems.length && !matchedCommands.length && (
                <p>Không tìm thấy hội viên, màn hình hoặc tác vụ phù hợp.</p>
              )}
              {!search.trim() && !recent.length && (
                <p className="!py-4">Gõ tên hội viên hoặc tác vụ. Dùng ↑ ↓ và Enter để mở nhanh.</p>
              )}
            </div>
          </section>
        </div>
      )}
    </>
  );
}
