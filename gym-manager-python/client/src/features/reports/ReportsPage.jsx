import { useEffect, useMemo, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import {
  ArrowDownRight,
  ArrowUpRight,
  CalendarDays,
  Check,
  ChevronDown,
  Clock3,
  Columns3,
  Download,
  Filter,
  RefreshCw,
  Search,
  SlidersHorizontal,
  WalletCards,
  X,
} from "lucide-react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, queryString } from "../../services/api";
import { PageHeader } from "../../components/common/PageHeader";
import { DataTable } from "../../components/ui/DataTable";
import { DateInput } from "../../components/ui/SmartInputs";
import { Button } from "../../components/ui/Button";
import { Select } from "../../components/ui/Form";
import { Pagination } from "../../components/ui/Pagination";
import { dateTime, money, shortDate } from "../../utils/format";

const methodLabels = {
  cash: "Tiền mặt",
  bank_transfer: "Chuyển khoản",
  card: "Thẻ",
  apple_pay: "Apple Pay",
};
const revenueTypeLabels = {
  membership: "Gói hội viên",
  day_pass: "Khách tập ngày",
};

const reportViews = [
  ["overview", "Tổng quan"],
  ["revenue", "Doanh thu"],
  ["debt", "Công nợ"],
  ["attendance", "Điểm danh"],
];

const pad = (value) => String(value).padStart(2, "0");
const isoDate = (value) => `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`;
const todayIso = () => isoDate(new Date());
const monthStartIso = () => {
  const now = new Date();
  return isoDate(new Date(now.getFullYear(), now.getMonth(), 1));
};
const parseLocalDate = (value) => new Date(`${value}T00:00:00`);
const addDays = (value, amount) => {
  const next = parseLocalDate(value);
  next.setDate(next.getDate() + amount);
  return isoDate(next);
};
const startOfWeek = () => {
  const now = new Date();
  const offset = now.getDay() === 0 ? -6 : 1 - now.getDay();
  now.setDate(now.getDate() + offset);
  return isoDate(now);
};

function periodForPreset(preset) {
  const today = todayIso();
  if (preset === "today") return [today, today];
  if (preset === "week") return [startOfWeek(), today];
  if (preset === "previous_month") {
    const now = new Date();
    return [isoDate(new Date(now.getFullYear(), now.getMonth() - 1, 1)), isoDate(new Date(now.getFullYear(), now.getMonth(), 0))];
  }
  return [monthStartIso(), today];
}

function daysUntil(dueDate) {
  if (!dueDate) return null;
  return Math.round((parseLocalDate(dueDate) - parseLocalDate(todayIso())) / 86400000);
}

function debtTiming(row) {
  const days = daysUntil(row.dueDate);
  if (days == null) return { rank: 3, key: "no_due", label: "Chưa đặt hạn", tone: "neutral" };
  if (days < 0) return { rank: 0, key: "overdue", label: `Quá hạn ${Math.abs(days)} ngày`, tone: "danger" };
  if (days === 0) return { rank: 1, key: "due_today", label: "Đến hạn hôm nay", tone: "warning" };
  return { rank: 2, key: days <= 7 ? "due_soon" : "in_due", label: `Còn ${days} ngày`, tone: days <= 7 ? "warning" : "positive" };
}

function normalizeSearch(value) {
  return String(value || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
}

function inDebtAmountBucket(row, bucket) {
  const amount = Number(row.amount || 0);
  if (bucket === "under_500k") return amount < 500000;
  if (bucket === "500k_1m") return amount >= 500000 && amount < 1000000;
  if (bucket === "1m_3m") return amount >= 1000000 && amount < 3000000;
  if (bucket === "over_3m") return amount >= 3000000;
  return true;
}

function compareValues(left, right) {
  if (typeof left === "number" && typeof right === "number") return left - right;
  return String(left ?? "").localeCompare(String(right ?? ""), "vi", { numeric: true, sensitivity: "base" });
}

function sortedRows(rows, sort, valueFor) {
  return [...rows].sort((left, right) => {
    const result = compareValues(valueFor(left, sort.key), valueFor(right, sort.key));
    return sort.direction === "asc" ? result : -result;
  });
}

function percentDelta(current, previous) {
  if (!previous) return current ? { direction: "up", label: "Kỳ trước chưa phát sinh" } : { direction: "neutral", label: "Không đổi so với kỳ trước" };
  const value = ((Number(current || 0) - previous) / previous) * 100;
  if (Math.abs(value) < 0.05) return { direction: "neutral", label: "Không đổi so với kỳ trước" };
  return { direction: value > 0 ? "up" : "down", label: `${value > 0 ? "+" : ""}${value.toLocaleString("vi-VN", { maximumFractionDigits: 1 })}% so với kỳ trước` };
}

function Metric({ label, value, context, delta, tone = "neutral", onClick }) {
  const DeltaIcon = delta?.direction === "up" ? ArrowUpRight : delta?.direction === "down" ? ArrowDownRight : null;
  const content = (
    <>
      <span>{label}</span>
      <strong>{value}</strong>
      <small className={delta?.direction || "neutral"}>{DeltaIcon && <DeltaIcon size={13} />}{delta?.label || context}</small>
    </>
  );
  return onClick ? <button type="button" className={`report-metric tone-${tone}`} onClick={onClick}>{content}</button> : <div className={`report-metric tone-${tone}`}>{content}</div>;
}

function StatusPill({ timing }) {
  return <span className={`report-status tone-${timing.tone}`}><i />{timing.label}</span>;
}

function downloadCsv(filename, headers, rows) {
  const escape = (value) => `"${String(value ?? "").replaceAll('"', '""')}"`;
  const content = [headers.map((item) => escape(item.label)).join(","), ...rows.map((row) => headers.map((item) => escape(item.value(row))).join(","))].join("\r\n");
  const url = URL.createObjectURL(new Blob(["\ufeff", content], { type: "text/csv;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

function ChartTooltip({ active, payload, label, valueType = "money" }) {
  if (!active || !payload?.length) return null;
  return <div className="report-chart-tooltip"><strong>{shortDate(label)}</strong>{payload.map((item) => <span key={item.dataKey}><i style={{ background: item.color }} />{item.name}: {valueType === "money" ? money(item.value) : Number(item.value || 0).toLocaleString("vi-VN")}</span>)}</div>;
}

export function ReportsPage() {
  const [params, setParams] = useSearchParams();
  const initialFrom = params.get("from") || monthStartIso();
  const initialTo = params.get("to") || todayIso();
  const [dateFrom, setDateFrom] = useState(initialFrom);
  const [dateTo, setDateTo] = useState(initialTo);
  const [draftFrom, setDraftFrom] = useState(initialFrom);
  const [draftTo, setDraftTo] = useState(initialTo);
  const [view, setView] = useState(params.get("view") || "overview");
  const [compare, setCompare] = useState(params.get("compare") !== "0");
  const [debtSearch, setDebtSearch] = useState(params.get("q") || "");
  const [debtFilter, setDebtFilter] = useState(params.get("status") || "all");
  const [debtSaleFilter, setDebtSaleFilter] = useState("all");
  const [debtPackageFilter, setDebtPackageFilter] = useState("all");
  const [debtAmountFilter, setDebtAmountFilter] = useState("all");
  const [debtSort, setDebtSort] = useState({ key: "priority", direction: "asc" });
  const [debtPage, setDebtPage] = useState(1);
  const [debtPageSize, setDebtPageSize] = useState(20);
  const [debtSelection, setDebtSelection] = useState([]);
  const [revenueSaleFilter, setRevenueSaleFilter] = useState("all");
  const [revenueMethodFilter, setRevenueMethodFilter] = useState("all");
  const [revenueTypeFilter, setRevenueTypeFilter] = useState("all");
  const [revenueSort, setRevenueSort] = useState({ key: "paidAt", direction: "desc" });
  const [revenuePage, setRevenuePage] = useState(1);
  const [revenuePageSize, setRevenuePageSize] = useState(20);
  const [revenueColumns, setRevenueColumns] = useState(["paidAt", "paymentNo", "type", "member", "package", "sale", "method", "amount"]);
  const [debtColumns, setDebtColumns] = useState(["member", "package", "sale", "amount", "dueDate", "status", "action"]);
  const [savedViews, setSavedViews] = useState(() => {
    try { return JSON.parse(localStorage.getItem("pulsefit-report-debt-views") || "[]"); } catch { return []; }
  });
  const [viewName, setViewName] = useState("");

  const query = useQuery({
    queryKey: ["reports", dateFrom, dateTo],
    queryFn: () => api(`/api/reports?${queryString({ dateFrom, dateTo })}`),
    placeholderData: keepPreviousData,
  });
  const data = query.data;

  useEffect(() => {
    setParams((current) => {
      const next = new URLSearchParams(current);
      next.set("view", view);
      next.set("from", dateFrom);
      next.set("to", dateTo);
      next.set("compare", compare ? "1" : "0");
      debtSearch ? next.set("q", debtSearch) : next.delete("q");
      debtFilter !== "all" ? next.set("status", debtFilter) : next.delete("status");
      return next;
    }, { replace: true });
  }, [compare, dateFrom, dateTo, debtFilter, debtSearch, setParams, view]);

  const revenueSaleOptions = useMemo(() => data?.revenueBySale || [], [data?.revenueBySale]);
  const revenueMethodOptions = useMemo(() => Array.from(new Set((data?.revenueItems || []).map((row) => row.method).filter(Boolean))).sort(), [data?.revenueItems]);
  const debtSaleOptions = useMemo(() => {
    const map = new Map();
    (data?.debts || []).forEach((row) => {
      const key = row.saleEmployeeId == null ? "unassigned" : String(row.saleEmployeeId);
      if (!map.has(key)) map.set(key, { value: key, label: row.saleName || "Chưa phân công", title: row.saleTitle });
    });
    return Array.from(map.values()).sort((a, b) => a.label.localeCompare(b.label, "vi"));
  }, [data?.debts]);
  const debtPackageOptions = useMemo(() => Array.from(new Set((data?.debts || []).map((row) => row.package).filter(Boolean))).sort((a, b) => a.localeCompare(b, "vi")), [data?.debts]);

  const revenueRows = useMemo(() => {
    const filtered = (data?.revenueItems || []).filter((row) => {
      const saleKey = row.saleEmployeeId == null ? "unassigned" : String(row.saleEmployeeId);
      return (revenueSaleFilter === "all" || saleKey === revenueSaleFilter) && (revenueMethodFilter === "all" || row.method === revenueMethodFilter) && (revenueTypeFilter === "all" || row.type === revenueTypeFilter);
    });
    return sortedRows(filtered, revenueSort, (row, key) => key === "sale" ? row.saleName : key === "member" ? row.member : key === "package" ? row.package : key === "method" ? row.method : row[key]);
  }, [data?.revenueItems, revenueMethodFilter, revenueSaleFilter, revenueSort, revenueTypeFilter]);

  const debtRows = useMemo(() => {
    const search = normalizeSearch(debtSearch);
    const filtered = (data?.debts || []).filter((row) => {
      const timing = debtTiming(row);
      const haystack = normalizeSearch([row.member, row.memberCode, row.phone, row.package, row.membershipCode, row.saleName].filter(Boolean).join(" "));
      if (search && !haystack.includes(search)) return false;
      if (debtFilter === "overdue" && timing.key !== "overdue") return false;
      if (debtFilter === "due_today" && timing.key !== "due_today") return false;
      if (debtFilter === "due_soon" && timing.key !== "due_soon") return false;
      if (debtFilter === "in_due" && !["due_soon", "in_due"].includes(timing.key)) return false;
      if (debtFilter === "no_due" && timing.key !== "no_due") return false;
      const saleKey = row.saleEmployeeId == null ? "unassigned" : String(row.saleEmployeeId);
      if (debtSaleFilter !== "all" && saleKey !== debtSaleFilter) return false;
      if (debtPackageFilter !== "all" && row.package !== debtPackageFilter) return false;
      return inDebtAmountBucket(row, debtAmountFilter);
    });
    return sortedRows(filtered, debtSort, (row, key) => {
      if (key === "priority" || key === "status") return debtTiming(row).rank * 10000000000000 + (row.dueDate ? parseLocalDate(row.dueDate).getTime() / 1000 : 9999999999);
      if (key === "sale") return row.saleName;
      if (key === "member") return row.member;
      if (key === "package") return row.package;
      return row[key] ?? "";
    });
  }, [data?.debts, debtAmountFilter, debtFilter, debtPackageFilter, debtSaleFilter, debtSearch, debtSort]);

  const makePagination = (page, pageSize, total) => ({ page, pageSize, total, totalPages: Math.max(Math.ceil(total / pageSize), 1) });
  const revenuePagination = makePagination(revenuePage, revenuePageSize, revenueRows.length);
  const debtPagination = makePagination(debtPage, debtPageSize, debtRows.length);
  const revenuePageRows = revenueRows.slice((revenuePage - 1) * revenuePageSize, revenuePage * revenuePageSize);
  const debtPageRows = debtRows.slice((debtPage - 1) * debtPageSize, debtPage * debtPageSize);
  const debtSummary = useMemo(() => ({
    amount: debtRows.reduce((sum, row) => sum + Number(row.amount || 0), 0),
    all: debtRows.length,
    overdue: debtRows.filter((row) => debtTiming(row).key === "overdue").length,
    dueToday: debtRows.filter((row) => debtTiming(row).key === "due_today").length,
    dueSoon: debtRows.filter((row) => debtTiming(row).key === "due_soon").length,
  }), [debtRows]);

  useEffect(() => { if (debtPage > debtPagination.totalPages) setDebtPage(debtPagination.totalPages); }, [debtPage, debtPagination.totalPages]);
  useEffect(() => { if (revenuePage > revenuePagination.totalPages) setRevenuePage(revenuePagination.totalPages); }, [revenuePage, revenuePagination.totalPages]);
  useEffect(() => { setDebtSelection((current) => current.filter((id) => debtRows.some((row) => row.membershipId === id))); }, [debtRows]);

  const applyPeriod = (from = draftFrom, to = draftTo) => {
    if (!from || !to) return;
    setDateFrom(from <= to ? from : to);
    setDateTo(from <= to ? to : from);
    setDraftFrom(from <= to ? from : to);
    setDraftTo(from <= to ? to : from);
    setRevenuePage(1);
    setDebtPage(1);
  };
  const choosePreset = (preset) => {
    const [from, to] = periodForPreset(preset);
    applyPeriod(from, to);
  };
  const resetDebtFilters = () => {
    setDebtSearch(""); setDebtFilter("all"); setDebtSaleFilter("all"); setDebtPackageFilter("all"); setDebtAmountFilter("all"); setDebtSort({ key: "priority", direction: "asc" }); setDebtPage(1);
  };
  const saveDebtView = () => {
    const name = viewName.trim();
    if (!name) return;
    const next = [...savedViews.filter((item) => item.name !== name), { name, debtFilter, debtSaleFilter, debtPackageFilter, debtAmountFilter, debtSort }];
    setSavedViews(next); localStorage.setItem("pulsefit-report-debt-views", JSON.stringify(next)); setViewName("");
  };
  const applySavedView = (saved) => {
    setDebtFilter(saved.debtFilter); setDebtSaleFilter(saved.debtSaleFilter); setDebtPackageFilter(saved.debtPackageFilter); setDebtAmountFilter(saved.debtAmountFilter); setDebtSort(saved.debtSort); setDebtPage(1);
  };

  const exportRevenue = () => downloadCsv(`doanh-thu-${dateFrom}-${dateTo}.csv`, [
    { label: "Ngày thu", value: (row) => dateTime(row.paidAt) }, { label: "Phiếu thu", value: (row) => row.paymentNo }, { label: "Phân loại", value: (row) => row.revenueType }, { label: "Hội viên/Khách", value: (row) => row.member }, { label: "Mã hội viên", value: (row) => row.memberCode }, { label: "Gói tập", value: (row) => row.package }, { label: "Sale", value: (row) => row.saleName }, { label: "Phương thức", value: (row) => methodLabels[row.method] || row.method }, { label: "Số tiền", value: (row) => row.amount },
  ], revenueRows);
  const exportDebt = (selectedOnly = false) => {
    const rows = selectedOnly ? debtRows.filter((row) => debtSelection.includes(row.membershipId)) : debtRows;
    downloadCsv(`cong-no-${dateFrom}-${dateTo}.csv`, [
      { label: "Hội viên", value: (row) => row.member }, { label: "Mã hội viên", value: (row) => row.memberCode }, { label: "SĐT", value: (row) => row.phone }, { label: "Gói tập", value: (row) => row.package }, { label: "Sale", value: (row) => row.saleName }, { label: "Công nợ", value: (row) => row.amount }, { label: "Hạn thanh toán", value: (row) => row.dueDate }, { label: "Tình trạng", value: (row) => debtTiming(row).label },
    ], rows);
  };

  const revenueColumnDefinitions = [
    { key: "paidAt", label: "Ngày thu", sortValue: (row) => row.paidAt, render: (row) => dateTime(row.paidAt) },
    { key: "paymentNo", label: "Phiếu thu", render: (row) => <span className="font-medium text-slate-950">{row.paymentNo}</span> },
    { key: "type", label: "Phân loại", render: (row) => <span className={row.type === "day_pass" ? "rounded bg-sky-50 px-2 py-1 text-xs font-medium text-sky-700" : "rounded bg-slate-100 px-2 py-1 text-xs font-medium text-slate-700"}>{row.revenueType || "Gói hội viên"}</span> },
    { key: "member", label: "Hội viên/Khách", render: (row) => row.memberId ? <Link className="cell-primary hover:underline" to={`/members/${row.memberId}`}>{row.member}<span className="cell-secondary block">{row.memberCode}</span></Link> : <span className="cell-primary">{row.member}<span className="cell-secondary block">Khách tập ngày</span></span> },
    { key: "package", label: "Gói tập", render: (row) => <span>{row.package || "—"}{row.membershipCode && <span className="cell-secondary block">{row.membershipCode}</span>}</span> },
    { key: "sale", label: "Sale", render: (row) => <span><span className="font-medium text-slate-900">{row.saleName}</span><span className="cell-secondary block">{row.saleTitle || "—"}</span></span> },
    { key: "method", label: "Phương thức", render: (row) => methodLabels[row.method] || row.method },
    { key: "amount", label: "Số tiền", className: "text-right tabular-nums", render: (row) => <strong className="font-semibold text-slate-950">{money(row.amount)}</strong> },
  ];
  const debtColumnDefinitions = [
    { key: "member", label: "Hội viên", render: (row) => <Link className="cell-primary hover:underline" to={`/members/${row.memberId}`}>{row.member}<span className="cell-secondary block">{[row.memberCode, row.phone].filter(Boolean).join(" · ")}</span></Link> },
    { key: "package", label: "Gói tập", render: (row) => <span>{row.package || "—"}{row.membershipCode && <span className="cell-secondary block">{row.membershipCode}</span>}</span> },
    { key: "sale", label: "Sale", render: (row) => <span><span className="font-medium text-slate-900">{row.saleName}</span><span className="cell-secondary block">{row.saleTitle || "—"}</span></span> },
    { key: "amount", label: "Số tiền", className: "text-right tabular-nums", render: (row) => <strong className="font-semibold text-slate-950">{money(row.amount)}</strong> },
    { key: "dueDate", label: "Hạn thanh toán", render: (row) => shortDate(row.dueDate) },
    { key: "status", label: "Tình trạng", render: (row) => <StatusPill timing={debtTiming(row)} /> },
    { key: "action", label: "", sortable: false, className: "text-right", render: (row) => <Button size="sm" variant="secondary" onClick={() => setParams((current) => { const next = new URLSearchParams(current); next.set("member", row.memberId); next.set("action", "payment"); return next; })}>Thu tiền</Button> },
  ];

  const switchView = (next) => { setView(next); window.scrollTo({ top: 0, behavior: "smooth" }); };
  const activeFilterCount = [debtSaleFilter !== "all", debtPackageFilter !== "all", debtAmountFilter !== "all"].filter(Boolean).length;
  const summary = data?.summary || {};
  const revenueDelta = compare ? percentDelta(summary.revenue, summary.previousRevenue) : null;
  const checkinDelta = compare ? percentDelta(summary.checkins, summary.previousCheckins) : null;

  return (
    <div className="reports-workspace">
      <PageHeader eyebrow="Phân tích" title="Báo cáo điều hành" description="Theo dõi dòng tiền, công nợ và nhịp độ vận hành trong một không gian thống nhất." action={<div className="report-header-actions"><span className="report-freshness"><Clock3 size={13} />{data?.generatedAt ? `Cập nhật ${dateTime(data.generatedAt)}` : "Đang cập nhật"}</span><Button variant="secondary" size="sm" onClick={() => query.refetch()} loading={query.isFetching}><RefreshCw size={14} />Làm mới</Button><Button size="sm" onClick={view === "debt" ? () => exportDebt() : exportRevenue}><Download size={14} />Xuất CSV</Button></div>} />

      <section className="report-control-bar" aria-label="Phạm vi báo cáo">
        <div className="report-presets" role="group" aria-label="Khoảng thời gian nhanh">
          <button type="button" onClick={() => choosePreset("today")}>Hôm nay</button>
          <button type="button" onClick={() => choosePreset("week")}>Tuần này</button>
          <button type="button" className={dateFrom === monthStartIso() && dateTo === todayIso() ? "active" : ""} onClick={() => choosePreset("month")}>Tháng này</button>
          <button type="button" onClick={() => choosePreset("previous_month")}>Tháng trước</button>
        </div>
        <div className="report-custom-period">
          <CalendarDays size={15} />
          <label><span>Từ</span><DateInput className="input" value={draftFrom} onChange={setDraftFrom} /></label>
          <span className="period-divider">–</span>
          <label><span>Đến</span><DateInput className="input" value={draftTo} onChange={setDraftTo} /></label>
          <Button size="sm" variant="secondary" onClick={() => applyPeriod()}>Áp dụng</Button>
        </div>
        <label className="report-compare"><input type="checkbox" checked={compare} onChange={(event) => setCompare(event.target.checked)} /><span><Check size={12} /></span>So với kỳ trước</label>
      </section>

      <nav className="report-tabs" aria-label="Nhóm báo cáo">
        {reportViews.map(([key, label]) => <button type="button" key={key} className={view === key ? "active" : ""} aria-current={view === key ? "page" : undefined} onClick={() => switchView(key)}>{label}</button>)}
      </nav>

      <section className="report-metric-grid" aria-label="Chỉ số chính">
        <Metric label="Doanh thu đã thu" value={money(summary.revenue)} delta={revenueDelta} tone="positive" onClick={() => switchView("revenue")} />
        <Metric label="Doanh thu hội viên" value={money(summary.membershipRevenue)} context="Gói đăng ký, gia hạn và thu thêm" tone="neutral" onClick={() => { setRevenueTypeFilter("membership"); switchView("revenue"); }} />
        <Metric label="Khách tập ngày" value={money(summary.dayPassRevenue)} context="Lượt vãng lai chưa hoàn tiền" tone="neutral" onClick={() => { setRevenueTypeFilter("day_pass"); switchView("revenue"); }} />
        <Metric label="Còn phải thu trong kỳ" value={money(summary.debt)} context={`${summary.overdueCount || 0} khoản quá hạn`} tone={summary.overdueDebt ? "danger" : "neutral"} onClick={() => switchView("debt")} />
        <Metric label="Công nợ quá hạn" value={money(summary.overdueDebt)} context={`${money(summary.dueSoonDebt)} đến hạn trong 7 ngày`} tone={summary.overdueDebt ? "danger" : "positive"} onClick={() => { setDebtFilter("overdue"); switchView("debt"); }} />
        <Metric label="Lượt check-in" value={Number(summary.checkins || 0).toLocaleString("vi-VN")} delta={checkinDelta} tone="neutral" onClick={() => switchView("attendance")} />
      </section>

      {query.isError && <div className="report-error"><strong>Không thể tải báo cáo.</strong><span>{query.error.message}</span><button type="button" onClick={() => query.refetch()}>Thử lại</button></div>}

      {view === "overview" && (
        <div className={`report-view ${query.isFetching ? "is-refreshing" : ""}`}>
          <div className="report-overview-grid">
            <section className="report-panel report-trend-panel">
              <div className="report-panel-header"><div><h2>Xu hướng doanh thu</h2><p>Dòng tiền thực thu theo ngày trong kỳ đã chọn</p></div><button type="button" onClick={() => switchView("revenue")}>Xem chi tiết</button></div>
              <div className="report-chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={data?.daily || []} margin={{ top: 12, right: 16, left: 8, bottom: 0 }}><defs><linearGradient id="revenueArea" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#163a5f" stopOpacity={0.22} /><stop offset="100%" stopColor="#163a5f" stopOpacity={0.02} /></linearGradient></defs><CartesianGrid vertical={false} stroke="#e2e8f0" /><XAxis dataKey="date" tickFormatter={(value) => shortDate(value).slice(0, 5)} tickLine={false} axisLine={false} minTickGap={22} /><YAxis tickFormatter={(value) => `${Math.round(value / 1000000)}M`} tickLine={false} axisLine={false} width={34} /><Tooltip content={<ChartTooltip />} /><Area type="monotone" dataKey="amount" name="Đã thu" stroke="#163a5f" strokeWidth={2} fill="url(#revenueArea)" /></AreaChart></ResponsiveContainer></div>
            </section>
            <section className="report-panel report-aging-panel">
              <div className="report-panel-header"><div><h2>Ưu tiên công nợ</h2><p>Khoản đến hạn trong phạm vi báo cáo</p></div><button type="button" onClick={() => switchView("debt")}>Mở công nợ</button></div>
              <div className="aging-summary"><button type="button" className="danger" onClick={() => { setDebtFilter("overdue"); switchView("debt"); }}><span>Quá hạn</span><strong>{money(summary.overdueDebt)}</strong><small>{summary.overdueCount || 0} khoản cần xử lý</small></button><button type="button" className="warning" onClick={() => { setDebtFilter("due_soon"); switchView("debt"); }}><span>7 ngày tới</span><strong>{money(summary.dueSoonDebt)}</strong><small>Ưu tiên liên hệ trước hạn</small></button><div><span>Chưa đến hạn / chưa đặt hạn</span><strong>{money(Math.max(Number(summary.debt || 0) - Number(summary.overdueDebt || 0) - Number(summary.dueSoonDebt || 0), 0))}</strong><small>Tiếp tục theo dõi</small></div></div>
            </section>
          </div>
          <div className="report-overview-grid secondary">
            <section className="report-panel">
              <div className="report-panel-header"><div><h2>Hiệu suất Sale</h2><p>Xếp hạng theo doanh thu thực thu</p></div><button type="button" onClick={() => switchView("revenue")}>Toàn bộ Sale</button></div>
              <div className="sale-ranking">{(data?.revenueBySale || []).slice(0, 6).map((row, index) => { const max = Number(data?.revenueBySale?.[0]?.amount || 1); return <div key={row.saleEmployeeId || "unassigned"}><span className="sale-rank">{index + 1}</span><span className="sale-person"><strong>{row.saleName}</strong><small>{row.saleTitle || "Chưa có chức vụ"} · {row.payments} phiếu</small></span><span className="sale-bar"><i style={{ width: `${Math.max((row.amount / max) * 100, 2)}%` }} /></span><strong className="sale-amount">{money(row.amount)}</strong></div>; })}{!data?.revenueBySale?.length && <div className="report-empty-compact">Chưa có doanh thu trong kỳ.</div>}</div>
            </section>
            <section className="report-panel">
              <div className="report-panel-header"><div><h2>Khoản cần xử lý trước</h2><p>Sắp xếp theo mức độ khẩn cấp và hạn thanh toán</p></div><button type="button" onClick={() => switchView("debt")}>Xem tất cả</button></div>
              <div className="priority-debt-list">{debtRows.slice(0, 6).map((row) => <Link to={`/members/${row.memberId}`} key={row.membershipId}><span><strong>{row.member}</strong><small>{row.package} · {row.saleName}</small></span><span><strong>{money(row.amount)}</strong><StatusPill timing={debtTiming(row)} /></span></Link>)}{!debtRows.length && <div className="report-empty-compact">Không có khoản công nợ cần xử lý.</div>}</div>
            </section>
          </div>
        </div>
      )}

      {view === "revenue" && (
        <div className="report-view">
          <div className="report-overview-grid">
            <section className="report-panel report-trend-panel"><div className="report-panel-header"><div><h2>Doanh thu theo ngày</h2><p>{shortDate(dateFrom)} - {shortDate(dateTo)}</p></div></div><div className="report-chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={data?.daily || []} margin={{ top: 12, right: 16, left: 8, bottom: 0 }}><CartesianGrid vertical={false} stroke="#e2e8f0" /><XAxis dataKey="date" tickFormatter={(value) => shortDate(value).slice(0, 5)} tickLine={false} axisLine={false} minTickGap={22} /><YAxis tickFormatter={(value) => `${Math.round(value / 1000000)}M`} tickLine={false} axisLine={false} width={34} /><Tooltip content={<ChartTooltip />} /><Area type="monotone" dataKey="amount" name="Đã thu" stroke="#163a5f" strokeWidth={2} fill="#e8eef4" /></AreaChart></ResponsiveContainer></div></section>
            <section className="report-panel"><div className="report-panel-header"><div><h2>Phân loại doanh thu</h2><p>Tách riêng hội viên và khách tập ngày</p></div></div><div className="method-breakdown">{(data?.revenueByType || []).map((row) => <button type="button" key={row.type} onClick={() => { setRevenueTypeFilter(row.type); setRevenuePage(1); }}><span><strong>{row.label}</strong><small>{row.share}% · {row.payments} phiếu</small></span><span className="method-track"><i style={{ width: `${row.share}%` }} /></span><strong>{money(row.amount)}</strong></button>)}{!data?.revenueByType?.length && <div className="report-empty-compact">Chưa có giao dịch trong kỳ.</div>}</div></section>
          </div>
          <section className="report-panel report-section-block"><div className="report-panel-header"><div><h2>Phương thức thanh toán</h2><p>Tỷ trọng trên tổng doanh thu</p></div></div><div className="method-breakdown">{(data?.revenueByMethod || []).map((row) => <div key={row.method}><span><strong>{methodLabels[row.method] || row.method}</strong><small>{row.share}%</small></span><span className="method-track"><i style={{ width: `${row.share}%` }} /></span><strong>{money(row.amount)}</strong></div>)}{!data?.revenueByMethod?.length && <div className="report-empty-compact">Chưa có giao dịch trong kỳ.</div>}</div></section>
          <section className="report-panel report-section-block"><div className="report-panel-header"><div><h2>Hiệu suất Sale</h2><p>So sánh doanh thu và số phiếu thu của từng nhân viên</p></div></div><div className="report-sale-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={(data?.revenueBySale || []).slice(0, 12)} layout="vertical" margin={{ top: 8, right: 24, left: 20, bottom: 8 }}><CartesianGrid horizontal={false} stroke="#e2e8f0" /><XAxis type="number" tickFormatter={(value) => `${Math.round(value / 1000000)}M`} tickLine={false} axisLine={false} /><YAxis type="category" dataKey="saleName" width={130} tickLine={false} axisLine={false} /><Tooltip formatter={(value) => money(value)} /><Bar dataKey="amount" name="Doanh thu" fill="#163a5f" radius={[0, 3, 3, 0]} barSize={18} /></BarChart></ResponsiveContainer></div></section>
          <section className="report-panel report-section-block">
            <div className="report-table-header"><div><h2>Chi tiết doanh thu</h2><p>Từng phiếu thu để đối chiếu và truy vết</p></div><div className="report-table-tools"><Select aria-label="Lọc theo phân loại" value={revenueTypeFilter} onChange={(event) => { setRevenueTypeFilter(event.target.value); setRevenuePage(1); }}><option value="all">Mọi phân loại</option>{Object.entries(revenueTypeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</Select><Select aria-label="Lọc theo Sale" value={revenueSaleFilter} onChange={(event) => { setRevenueSaleFilter(event.target.value); setRevenuePage(1); }}><option value="all">Mọi Sale</option>{revenueSaleOptions.map((row) => <option key={row.saleEmployeeId || "unassigned"} value={row.saleEmployeeId == null ? "unassigned" : String(row.saleEmployeeId)}>{row.saleName}</option>)}</Select><Select aria-label="Lọc theo phương thức" value={revenueMethodFilter} onChange={(event) => { setRevenueMethodFilter(event.target.value); setRevenuePage(1); }}><option value="all">Mọi phương thức</option>{revenueMethodOptions.map((method) => <option key={method} value={method}>{methodLabels[method] || method}</option>)}</Select><details className="report-menu"><summary title="Chọn cột hiển thị"><Columns3 size={15} /><span>Cột</span><ChevronDown size={13} /></summary><div>{revenueColumnDefinitions.map((column) => <label key={column.key}><input type="checkbox" checked={revenueColumns.includes(column.key)} onChange={() => setRevenueColumns((current) => current.includes(column.key) ? current.filter((key) => key !== column.key) : [...current, column.key])} />{column.label || "Thao tác"}</label>)}</div></details><Button size="sm" variant="secondary" onClick={exportRevenue}><Download size={14} />Xuất</Button></div></div>
            <DataTable loading={query.isLoading} error={query.error} onRetry={query.refetch} rows={revenuePageRows} rowKey="paymentId" columns={revenueColumnDefinitions.filter((column) => revenueColumns.includes(column.key))} sortState={revenueSort} onSortChange={(next) => { setRevenueSort(next); setRevenuePage(1); }} emptyTitle="Không có doanh thu" emptyDescription="Không có phiếu thu nào trong kỳ hoặc bộ lọc hiện tại." />
            <Pagination data={revenuePagination} onPage={setRevenuePage} pageSize={revenuePageSize} onPageSize={(value) => { setRevenuePageSize(value); setRevenuePage(1); }} />
          </section>
        </div>
      )}

      {view === "debt" && (
        <div className="report-view">
          <section className="debt-command-bar">
            {[ ["all", "Tất cả", debtSummary.all], ["overdue", "Quá hạn", debtSummary.overdue], ["due_today", "Hôm nay", debtSummary.dueToday], ["due_soon", "7 ngày tới", debtSummary.dueSoon], ["no_due", "Chưa đặt hạn", (data?.debts || []).filter((row) => debtTiming(row).key === "no_due").length] ].map(([key, label, count]) => <button type="button" key={key} className={debtFilter === key ? "active" : ""} onClick={() => { setDebtFilter(key); setDebtPage(1); }}>{label}<strong>{count}</strong></button>)}
          </section>
          <section className="report-panel report-section-block">
            <div className="report-table-header debt-header"><div><h2>Chi tiết công nợ</h2><p>Ưu tiên theo hạn thanh toán trong khoảng {shortDate(dateFrom)} - {shortDate(dateTo)}</p></div><div className="debt-total"><span>Tổng sau lọc</span><strong>{money(debtSummary.amount)}</strong></div></div>
            <div className="report-filter-bar">
              <label className="report-search"><Search size={15} /><input value={debtSearch} onChange={(event) => { setDebtSearch(event.target.value); setDebtPage(1); }} placeholder="Tìm tên, mã, SĐT, gói hoặc Sale" />{debtSearch && <button type="button" onClick={() => setDebtSearch("")} aria-label="Xóa tìm kiếm"><X size={14} /></button>}</label>
              <Select aria-label="Sắp xếp công nợ" value={`${debtSort.key}:${debtSort.direction}`} onChange={(event) => { const [key, direction] = event.target.value.split(":"); setDebtSort({ key, direction }); setDebtPage(1); }}><option value="priority:asc">Cần xử lý trước</option><option value="dueDate:asc">Hạn gần trước</option><option value="dueDate:desc">Hạn xa trước</option><option value="amount:desc">Nợ cao trước</option><option value="amount:asc">Nợ thấp trước</option><option value="member:asc">Tên A-Z</option></Select>
              <details className="report-menu filter-menu"><summary><SlidersHorizontal size={15} /><span>Bộ lọc nâng cao</span>{activeFilterCount > 0 && <b>{activeFilterCount}</b>}<ChevronDown size={13} /></summary><div><label><span>Sale phụ trách</span><Select value={debtSaleFilter} onChange={(event) => { setDebtSaleFilter(event.target.value); setDebtPage(1); }}><option value="all">Mọi Sale</option>{debtSaleOptions.map((row) => <option key={row.value} value={row.value}>{row.label}{row.title ? ` - ${row.title}` : ""}</option>)}</Select></label><label><span>Gói tập</span><Select value={debtPackageFilter} onChange={(event) => { setDebtPackageFilter(event.target.value); setDebtPage(1); }}><option value="all">Mọi gói tập</option>{debtPackageOptions.map((name) => <option key={name}>{name}</option>)}</Select></label><label><span>Mức công nợ</span><Select value={debtAmountFilter} onChange={(event) => { setDebtAmountFilter(event.target.value); setDebtPage(1); }}><option value="all">Mọi mức nợ</option><option value="under_500k">Dưới 500K</option><option value="500k_1m">500K - dưới 1M</option><option value="1m_3m">1M - dưới 3M</option><option value="over_3m">Từ 3M</option></Select></label><button type="button" className="filter-reset" onClick={resetDebtFilters}>Xóa toàn bộ bộ lọc</button></div></details>
              <details className="report-menu"><summary><WalletCards size={15} /><span>View đã lưu</span><ChevronDown size={13} /></summary><div className="saved-view-menu">{savedViews.map((saved) => <button type="button" key={saved.name} onClick={() => applySavedView(saved)}>{saved.name}</button>)}{!savedViews.length && <small>Chưa có view nào</small>}<label><input value={viewName} onChange={(event) => setViewName(event.target.value)} placeholder="Tên view mới" /><button type="button" onClick={saveDebtView}>Lưu</button></label></div></details>
              <details className="report-menu"><summary title="Chọn cột hiển thị"><Columns3 size={15} /><span>Cột</span><ChevronDown size={13} /></summary><div>{debtColumnDefinitions.map((column) => <label key={column.key}><input type="checkbox" checked={debtColumns.includes(column.key)} onChange={() => setDebtColumns((current) => current.includes(column.key) ? current.filter((key) => key !== column.key) : [...current, column.key])} />{column.label || "Thao tác"}</label>)}</div></details>
            </div>
            {(debtSearch || debtFilter !== "all" || activeFilterCount > 0) && <div className="active-filter-row"><Filter size={13} /><span>{debtRows.length} kết quả</span>{debtFilter !== "all" && <button type="button" onClick={() => setDebtFilter("all")}>Trạng thái: {debtTiming({ dueDate: debtFilter === "no_due" ? null : debtFilter === "overdue" ? addDays(todayIso(), -1) : debtFilter === "due_today" ? todayIso() : addDays(todayIso(), 3) }).label}<X size={11} /></button>}{debtSaleFilter !== "all" && <button type="button" onClick={() => setDebtSaleFilter("all")}>Sale: {debtSaleOptions.find((item) => item.value === debtSaleFilter)?.label}<X size={11} /></button>}{debtPackageFilter !== "all" && <button type="button" onClick={() => setDebtPackageFilter("all")}>Gói: {debtPackageFilter}<X size={11} /></button>}{debtAmountFilter !== "all" && <button type="button" onClick={() => setDebtAmountFilter("all")}>Mức nợ<X size={11} /></button>}<button type="button" className="clear-filters" onClick={resetDebtFilters}>Xóa tất cả</button></div>}
            {debtSelection.length > 0 && <div className="bulk-action-bar"><strong>Đã chọn {debtSelection.length} khoản</strong><Button size="sm" variant="secondary" onClick={() => exportDebt(true)}><Download size={14} />Xuất mục đã chọn</Button><button type="button" onClick={() => setDebtSelection([])}>Bỏ chọn</button></div>}
            <DataTable loading={query.isLoading} error={query.error} onRetry={query.refetch} rows={debtPageRows} rowKey="membershipId" columns={debtColumnDefinitions.filter((column) => debtColumns.includes(column.key))} sortState={debtSort.key === "priority" ? { key: "status", direction: debtSort.direction } : debtSort} onSortChange={(next) => { setDebtSort(next); setDebtPage(1); }} selection={debtSelection} onSelectionChange={setDebtSelection} emptyTitle="Không có công nợ" emptyDescription="Không có khoản công nợ phù hợp với kỳ và bộ lọc hiện tại." />
            <Pagination data={debtPagination} onPage={setDebtPage} pageSize={debtPageSize} onPageSize={(value) => { setDebtPageSize(value); setDebtPage(1); }} />
          </section>
        </div>
      )}

      {view === "attendance" && (
        <div className="report-view"><section className="report-panel"><div className="report-panel-header"><div><h2>Nhịp độ check-in theo ngày</h2><p>{shortDate(dateFrom)} - {shortDate(dateTo)} · {summary.checkins || 0} lượt</p></div></div><div className="report-attendance-chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={data?.daily || []} margin={{ top: 16, right: 20, left: 0, bottom: 8 }}><CartesianGrid vertical={false} stroke="#e2e8f0" /><XAxis dataKey="date" tickFormatter={(value) => shortDate(value).slice(0, 5)} tickLine={false} axisLine={false} minTickGap={20} /><YAxis allowDecimals={false} tickLine={false} axisLine={false} width={34} /><Tooltip content={<ChartTooltip valueType="number" />} /><Bar dataKey="checkins" name="Check-in" fill="#163a5f" radius={[3, 3, 0, 0]} maxBarSize={34} /></BarChart></ResponsiveContainer></div></section><div className="attendance-facts"><div><span>Tổng lượt</span><strong>{Number(summary.checkins || 0).toLocaleString("vi-VN")}</strong></div><div><span>Trung bình mỗi ngày</span><strong>{Number((summary.checkins || 0) / Math.max(data?.daily?.length || 1, 1)).toLocaleString("vi-VN", { maximumFractionDigits: 1 })}</strong></div><div><span>Ngày cao nhất</span><strong>{shortDate([...(data?.daily || [])].sort((a, b) => b.checkins - a.checkins)[0]?.date)}</strong></div><div><span>So với kỳ trước</span><strong className={checkinDelta?.direction === "down" ? "text-red-700" : "text-emerald-700"}>{checkinDelta?.label || "Đang tắt so sánh"}</strong></div></div></div>
      )}
    </div>
  );
}
