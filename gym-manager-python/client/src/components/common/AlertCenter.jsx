import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, CalendarClock, Check, CheckCheck, CreditCard, Dumbbell, X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { api } from "../../services/api";

const icons = {
  overdue_debt: CreditCard,
  membership_expired: CalendarClock,
  membership_expiring: CalendarClock,
  pt_low_sessions: Dumbbell,
};

export function AlertCenter() {
  const [open, setOpen] = useState(false);
  const [view, setView] = useState("unread");
  const root = useRef(null);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["alerts"],
    queryFn: () => api("/api/alerts?limit=30"),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
  const markRead = useMutation({
    mutationFn: (alertKey) => api(`/api/alerts/${encodeURIComponent(alertKey)}/read`, { method: "PATCH" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alerts"] }),
  });
  const markAllRead = useMutation({
    mutationFn: () => api("/api/alerts/read-all", { method: "POST" }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["alerts"] }),
  });
  useEffect(() => {
    const close = (event) => {
      if (!root.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  const unread = query.data?.counts.unread || 0;
  const visibleItems = (query.data?.items || []).filter((item) => view === "read" ? item.isRead : !item.isRead);
  const openAlert = async (item) => {
    if (!item.isRead) await markRead.mutateAsync(item.id);
    setOpen(false);
    navigate(`/members/${item.memberId}`);
  };
  return (
    <div className="alert-center" ref={root}>
      <button
        className="alert-trigger"
        onClick={() => setOpen(!open)}
        aria-label={`${unread} thông báo chưa đọc`}
        aria-expanded={open}
      >
        <Bell size={17} />
        {!!unread && <span>{unread > 99 ? "99+" : unread}</span>}
      </button>
      {open && (
        <div className="alert-popover">
          <header>
            <div><strong>Thông báo vận hành</strong><span>{unread ? `${unread} thông báo chưa đọc` : "Bạn đã đọc tất cả thông báo"}</span></div>
            <button onClick={() => setOpen(false)} aria-label="Đóng cảnh báo"><X size={16} /></button>
          </header>
          <div className="alert-toolbar">
            <div className="alert-view-tabs" role="tablist" aria-label="Trạng thái thông báo">
              <button className={view === "unread" ? "active" : ""} onClick={() => setView("unread")}>Chưa đọc <span>{unread}</span></button>
              <button className={view === "read" ? "active" : ""} onClick={() => setView("read")}>Đã đọc</button>
            </div>
            {!!unread && <button className="mark-all-read" onClick={() => markAllRead.mutate()} disabled={markAllRead.isPending}><CheckCheck size={14} /> Đọc tất cả</button>}
          </div>
          <div className="alert-list">
            {query.isLoading ? (
              Array.from({ length: 4 }).map((_, index) => <div className="skeleton h-14" key={index} />)
            ) : query.isError ? (
              <div className="alert-empty"><strong>Không thể tải cảnh báo</strong><button onClick={() => query.refetch()}>Thử lại</button></div>
            ) : visibleItems.length ? (
              visibleItems.map((item) => {
                const Icon = icons[item.type] || Bell;
                return (
                  <div key={item.id} className={`alert-item alert-${item.severity} ${item.isRead ? "is-read" : ""}`}>
                    <button className="alert-item-main" onClick={() => openAlert(item)}>
                      <Icon size={16} />
                      <span><strong>{item.memberName} · {item.title}</strong><small>{item.description}</small></span>
                    </button>
                    {!item.isRead && <button className="alert-read-button" onClick={() => markRead.mutate(item.id)} disabled={markRead.isPending} title="Đánh dấu đã đọc" aria-label={`Đánh dấu thông báo của ${item.memberName} đã đọc`}><Check size={14} /></button>}
                    {item.isRead && <span className="alert-read-state"><Check size={12} /> Đã đọc</span>}
                  </div>
                );
              })
            ) : (
              <div className="alert-empty"><CheckCheck size={20} /><strong>{view === "unread" ? "Không có thông báo chưa đọc" : "Chưa có thông báo đã đọc"}</strong><span>{view === "unread" ? "Các cảnh báo mới sẽ xuất hiện tại đây." : "Thông báo đã đọc vẫn được lưu khi cảnh báo còn hiệu lực."}</span></div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
