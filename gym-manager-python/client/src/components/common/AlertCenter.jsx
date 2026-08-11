import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bell, CalendarClock, CreditCard, Dumbbell, X } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../../services/api";

const icons = {
  overdue_debt: CreditCard,
  membership_expiring: CalendarClock,
  pt_low_sessions: Dumbbell,
};

export function AlertCenter() {
  const [open, setOpen] = useState(false);
  const root = useRef(null);
  const query = useQuery({
    queryKey: ["alerts"],
    queryFn: () => api("/api/alerts?limit=30"),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });
  useEffect(() => {
    const close = (event) => {
      if (!root.current?.contains(event.target)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  const total = query.data?.counts.total || 0;
  return (
    <div className="alert-center" ref={root}>
      <button
        className="alert-trigger"
        onClick={() => setOpen(!open)}
        aria-label={`${total} cảnh báo vận hành`}
        aria-expanded={open}
      >
        <Bell size={17} />
        {!!total && <span>{total > 99 ? "99+" : total}</span>}
      </button>
      {open && (
        <div className="alert-popover">
          <header>
            <div><strong>Cảnh báo vận hành</strong><span>Tự động làm mới mỗi phút</span></div>
            <button onClick={() => setOpen(false)} aria-label="Đóng cảnh báo"><X size={16} /></button>
          </header>
          <div className="alert-counts">
            <span><strong>{query.data?.counts.overdueDebt || 0}</strong>Nợ quá hạn</span>
            <span><strong>{query.data?.counts.expiring || 0}</strong>Sắp hết hạn</span>
            <span><strong>{query.data?.counts.ptLowSessions || 0}</strong>PT ít buổi</span>
          </div>
          <div className="alert-list">
            {query.isLoading ? (
              Array.from({ length: 4 }).map((_, index) => <div className="skeleton h-14" key={index} />)
            ) : query.isError ? (
              <div className="alert-empty"><strong>Không thể tải cảnh báo</strong><button onClick={() => query.refetch()}>Thử lại</button></div>
            ) : query.data?.items.length ? (
              query.data.items.map((item) => {
                const Icon = icons[item.type] || Bell;
                return (
                  <Link key={item.id} to={`/members/${item.memberId}`} onClick={() => setOpen(false)} className={`alert-item alert-${item.severity}`}>
                    <Icon size={16} />
                    <span><strong>{item.memberName} · {item.title}</strong><small>{item.description}</small></span>
                  </Link>
                );
              })
            ) : (
              <div className="alert-empty"><Bell size={20} /><strong>Không có cảnh báo cần xử lý</strong><span>Dữ liệu vận hành hiện đang ổn định.</span></div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
