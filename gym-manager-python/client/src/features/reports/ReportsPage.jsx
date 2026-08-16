import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
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

const todayIso = () => {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
};

function daysUntil(dueDate) {
  if (!dueDate) return null;
  const today = new Date(`${todayIso()}T00:00:00`);
  const due = new Date(`${dueDate}T00:00:00`);
  return Math.round((due - today) / 86400000);
}

function debtTiming(row) {
  const days = daysUntil(row.dueDate);
  if (days == null) return { rank: 3, label: "Chưa đặt hạn", className: "text-slate-500" };
  if (days < 0) return { rank: 0, label: `Quá hạn ${Math.abs(days)} ngày`, className: "text-red-700" };
  if (days === 0) return { rank: 1, label: "Đến hạn hôm nay", className: "text-amber-700" };
  return { rank: 2, label: `Còn ${days} ngày`, className: days <= 3 ? "text-amber-700" : "text-slate-500" };
}

function normalizeSearch(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

function inDebtAmountBucket(row, bucket) {
  const amount = Number(row.amount || 0);
  if (bucket === "under_500k") return amount < 500000;
  if (bucket === "500k_1m") return amount >= 500000 && amount < 1000000;
  if (bucket === "1m_3m") return amount >= 1000000 && amount < 3000000;
  if (bucket === "over_3m") return amount >= 3000000;
  return true;
}

export function ReportsPage() {
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [debtSearch, setDebtSearch] = useState("");
  const [debtFilter, setDebtFilter] = useState("all");
  const [debtSaleFilter, setDebtSaleFilter] = useState("all");
  const [debtPackageFilter, setDebtPackageFilter] = useState("all");
  const [debtAmountFilter, setDebtAmountFilter] = useState("all");
  const [debtSort, setDebtSort] = useState("nearest_due");
  const [debtPage, setDebtPage] = useState(1);
  const [debtPageSize, setDebtPageSize] = useState(20);
  const [revenueSaleFilter, setRevenueSaleFilter] = useState("all");
  const [revenueMethodFilter, setRevenueMethodFilter] = useState("all");
  const [revenueSort, setRevenueSort] = useState("newest");
  const [revenuePage, setRevenuePage] = useState(1);
  const [revenuePageSize, setRevenuePageSize] = useState(20);
  const [, setParams] = useSearchParams();
  const query = useQuery({
    queryKey: ["reports", dateFrom, dateTo],
    queryFn: () => api(`/api/reports?${queryString({ dateFrom, dateTo })}`),
  });
  const data = query.data;
  const revenueSaleOptions = useMemo(() => data?.revenueBySale || [], [data?.revenueBySale]);
  const revenueMethodOptions = useMemo(
    () => Array.from(new Set((data?.revenueItems || []).map((row) => row.method).filter(Boolean))).sort(),
    [data?.revenueItems],
  );
  const debtSaleOptions = useMemo(() => {
    const map = new Map();
    (data?.debts || []).forEach((row) => {
      const key = row.saleEmployeeId == null ? "unassigned" : String(row.saleEmployeeId);
      if (!map.has(key)) {
        map.set(key, {
          value: key,
          label: row.saleName || "Chưa phân công",
          title: row.saleTitle,
        });
      }
    });
    return Array.from(map.values()).sort((a, b) => a.label.localeCompare(b.label, "vi"));
  }, [data?.debts]);
  const debtPackageOptions = useMemo(
    () => Array.from(new Set((data?.debts || []).map((row) => row.package).filter(Boolean))).sort((a, b) => a.localeCompare(b, "vi")),
    [data?.debts],
  );
  const revenueRows = useMemo(() => {
    const rows = data?.revenueItems || [];
    return rows
      .filter((row) => {
        if (revenueSaleFilter !== "all") {
          const key = row.saleEmployeeId == null ? "unassigned" : String(row.saleEmployeeId);
          if (key !== revenueSaleFilter) return false;
        }
        if (revenueMethodFilter !== "all" && row.method !== revenueMethodFilter) return false;
        return true;
      })
      .sort((a, b) => {
        if (revenueSort === "oldest") return String(a.paidAt || "").localeCompare(String(b.paidAt || ""));
        if (revenueSort === "amount_desc") return Number(b.amount || 0) - Number(a.amount || 0);
        if (revenueSort === "amount_asc") return Number(a.amount || 0) - Number(b.amount || 0);
        return String(b.paidAt || "").localeCompare(String(a.paidAt || ""));
      });
  }, [data?.revenueItems, revenueMethodFilter, revenueSaleFilter, revenueSort]);
  const revenuePageRows = useMemo(() => {
    const start = (revenuePage - 1) * revenuePageSize;
    return revenueRows.slice(start, start + revenuePageSize);
  }, [revenuePage, revenuePageSize, revenueRows]);
  const revenuePagination = useMemo(
    () => ({
      page: revenuePage,
      pageSize: revenuePageSize,
      total: revenueRows.length,
      totalPages: Math.max(Math.ceil(revenueRows.length / revenuePageSize), 1),
    }),
    [revenuePage, revenuePageSize, revenueRows.length],
  );
  const debtRows = useMemo(() => {
    const rows = data?.debts || [];
    const search = normalizeSearch(debtSearch);
    return rows
      .filter((row) => {
        const timing = debtTiming(row);
        if (search) {
          const haystack = normalizeSearch([
            row.member,
            row.memberCode,
            row.phone,
            row.package,
            row.membershipCode,
            row.saleName,
          ].filter(Boolean).join(" "));
          if (!haystack.includes(search)) return false;
        }
        if (debtFilter === "overdue" && timing.rank !== 0) return false;
        if (debtFilter === "due_today" && timing.rank !== 1) return false;
        if (debtFilter === "due_soon" && !(timing.rank === 2 && daysUntil(row.dueDate) <= 7)) return false;
        if (debtFilter === "in_due" && timing.rank !== 2) return false;
        if (debtFilter === "no_due" && timing.rank !== 3) return false;
        if (debtSaleFilter !== "all") {
          const key = row.saleEmployeeId == null ? "unassigned" : String(row.saleEmployeeId);
          if (key !== debtSaleFilter) return false;
        }
        if (debtPackageFilter !== "all" && row.package !== debtPackageFilter) return false;
        if (!inDebtAmountBucket(row, debtAmountFilter)) return false;
        return true;
      })
      .sort((a, b) => {
        const left = debtTiming(a);
        const right = debtTiming(b);
        if (debtSort === "farthest_due") {
          if (!a.dueDate && !b.dueDate) return 0;
          if (!a.dueDate) return 1;
          if (!b.dueDate) return -1;
          return b.dueDate.localeCompare(a.dueDate);
        }
        if (debtSort === "overdue_oldest") {
          if (!a.dueDate && !b.dueDate) return 0;
          if (!a.dueDate) return 1;
          if (!b.dueDate) return -1;
          return a.dueDate.localeCompare(b.dueDate);
        }
        if (debtSort === "amount_desc") return Number(b.amount || 0) - Number(a.amount || 0);
        if (debtSort === "amount_asc") return Number(a.amount || 0) - Number(b.amount || 0);
        if (debtSort === "member_az") return String(a.member || "").localeCompare(String(b.member || ""), "vi");
        if (left.rank !== right.rank) return left.rank - right.rank;
        return (a.dueDate || "9999-12-31").localeCompare(b.dueDate || "9999-12-31");
      });
  }, [data?.debts, debtAmountFilter, debtFilter, debtPackageFilter, debtSaleFilter, debtSearch, debtSort]);
  const debtPageRows = useMemo(() => {
    const start = (debtPage - 1) * debtPageSize;
    return debtRows.slice(start, start + debtPageSize);
  }, [debtPage, debtPageSize, debtRows]);
  const debtPagination = useMemo(
    () => ({
      page: debtPage,
      pageSize: debtPageSize,
      total: debtRows.length,
      totalPages: Math.max(Math.ceil(debtRows.length / debtPageSize), 1),
    }),
    [debtPage, debtPageSize, debtRows.length],
  );
  const debtSummary = useMemo(() => {
    const rows = debtRows;
    return {
      all: rows.length,
      amount: rows.reduce((sum, row) => sum + Number(row.amount || 0), 0),
      overdue: rows.filter((row) => debtTiming(row).rank === 0).length,
      dueToday: rows.filter((row) => debtTiming(row).rank === 1).length,
      dueSoon: rows.filter((row) => {
        const timing = debtTiming(row);
        return timing.rank === 2 && daysUntil(row.dueDate) <= 7;
      }).length,
      noDue: rows.filter((row) => debtTiming(row).rank === 3).length,
    };
  }, [debtRows]);
  useEffect(() => {
    if (debtPage > debtPagination.totalPages) {
      setDebtPage(debtPagination.totalPages);
    }
  }, [debtPage, debtPagination.totalPages]);
  useEffect(() => {
    if (revenuePage > revenuePagination.totalPages) {
      setRevenuePage(revenuePagination.totalPages);
    }
  }, [revenuePage, revenuePagination.totalPages]);
  return (
    <>
      <PageHeader
        eyebrow="Phân tích"
        title="Báo cáo"
        description="Doanh thu đã thu, công nợ theo hạn thanh toán và dữ liệu đối chiếu vận hành."
      />
      <div className="toolbar">
        <span className="text-xs font-medium text-slate-600">
          Khoảng thời gian doanh thu / hạn công nợ
        </span>
        <DateInput
          className="input w-40"
          value={dateFrom}
          onChange={setDateFrom}
        />
        <span className="text-slate-300">→</span>
        <DateInput className="input w-40" value={dateTo} onChange={setDateTo} />
      </div>
      <div className="metric-strip grid-cols-5">
        {[
          ["Doanh thu đã thu", money(data?.summary.revenue)],
          ["Công nợ trong kỳ", money(data?.summary.debt)],
          ["Tổng cần đối chiếu", money(data?.summary.receivable)],
          ["Số phiếu thu", data?.summary.payments || 0],
          ["Lượt check-in", data?.summary.checkins || 0],
        ].map(([label, value]) => (
          <div className="metric" key={label}>
            <span>{label}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>
      <div className="section-grid">
        <section>
          <div className="section-header">
            <div>
              <h2>Doanh thu theo phương thức</h2>
              <p>Cơ cấu thu tiền trong kỳ</p>
            </div>
          </div>
          <div className="definition-list border-y border-slate-200 bg-white px-4">
            {data?.revenueByMethod.map((row) => (
              <div key={row.method}>
                <dt>{methodLabels[row.method] || row.method}</dt>
                <dd className="text-right font-medium">{money(row.amount)}</dd>
              </div>
            ))}
          </div>
        </section>
        <section>
          <div className="section-header">
            <div>
              <h2>Công nợ trong kỳ</h2>
              <p>Hạn thu nằm trong khoảng đã chọn, kèm khoản chưa đặt hạn</p>
            </div>
          </div>
          <div className="panel">
            <strong className="text-xl font-semibold text-slate-900">
              {money(data?.summary.debt)}
            </strong>
            <p className="mt-1 text-xs text-slate-500">
              {data?.debts.length || 0} gói còn dư nợ trong bộ lọc thời gian
            </p>
          </div>
        </section>
      </div>
      <section className="mt-7">
        <div className="section-header">
          <div>
            <h2>Doanh thu theo Sale</h2>
            <p>Ghi nhận theo sale của gói: sale trực tiếp, sale online, rồi sale phụ trách hội viên</p>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-3 max-[1000px]:grid-cols-2 max-[640px]:grid-cols-1">
          {(data?.revenueBySale || []).map((row) => (
            <div key={row.saleEmployeeId || "unassigned"} className="rounded-lg border border-slate-200 bg-white px-4 py-3">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-semibold text-slate-950">{row.saleName}</div>
                  <div className="mt-0.5 text-xs text-slate-500">{row.saleTitle || "Chưa có chức vụ"}</div>
                </div>
                <span className="rounded-full bg-slate-100 px-2 py-1 text-[11px] font-medium text-slate-600">
                  {row.payments} phiếu
                </span>
              </div>
              <div className="mt-3 text-xl font-semibold text-slate-950">{money(row.amount)}</div>
            </div>
          ))}
          {!query.isLoading && !(data?.revenueBySale || []).length && (
            <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-4 py-8 text-center text-sm text-slate-500">
              Chưa có doanh thu trong kỳ.
            </div>
          )}
        </div>
      </section>
      <section className="mt-7">
        <div className="section-header">
          <div>
            <h2>Chi tiết doanh thu</h2>
            <p>Danh sách từng phiếu thu để đối chiếu với file Google Sheet</p>
          </div>
          <div className="flex flex-wrap justify-end gap-2">
            <Select
              className="input w-48"
              value={revenueSaleFilter}
              onChange={(event) => {
                setRevenueSaleFilter(event.target.value);
                setRevenuePage(1);
              }}
            >
              <option value="all">Mọi sale</option>
              {revenueSaleOptions.map((row) => (
                <option key={row.saleEmployeeId || "unassigned"} value={row.saleEmployeeId == null ? "unassigned" : String(row.saleEmployeeId)}>
                  {row.saleName}
                </option>
              ))}
            </Select>
            <Select
              className="input w-44"
              value={revenueMethodFilter}
              onChange={(event) => {
                setRevenueMethodFilter(event.target.value);
                setRevenuePage(1);
              }}
            >
              <option value="all">Mọi phương thức</option>
              {revenueMethodOptions.map((method) => (
                <option key={method} value={method}>
                  {methodLabels[method] || method}
                </option>
              ))}
            </Select>
            <Select
              className="input w-44"
              value={revenueSort}
              onChange={(event) => {
                setRevenueSort(event.target.value);
                setRevenuePage(1);
              }}
            >
              <option value="newest">Mới nhất trước</option>
              <option value="oldest">Cũ nhất trước</option>
              <option value="amount_desc">Tiền cao trước</option>
              <option value="amount_asc">Tiền thấp trước</option>
            </Select>
          </div>
        </div>
        <DataTable
          loading={query.isLoading}
          error={query.error}
          onRetry={query.refetch}
          rows={revenuePageRows}
          rowKey="paymentId"
          columns={[
            {
              key: "paidAt",
              label: "Ngày thu",
              sortValue: (r) => r.paidAt,
              render: (r) => dateTime(r.paidAt),
            },
            {
              key: "paymentNo",
              label: "Phiếu thu",
              sortValue: (r) => r.paymentNo,
              render: (r) => <span className="font-medium text-slate-950">{r.paymentNo}</span>,
            },
            {
              key: "member",
              label: "Hội viên",
              sortValue: (r) => r.member,
              render: (r) => (
                <Link className="cell-primary hover:underline" to={`/members/${r.memberId}`}>
                  {r.member}
                  <span className="cell-secondary block">{r.memberCode}</span>
                </Link>
              ),
            },
            {
              key: "package",
              label: "Gói tập",
              sortValue: (r) => r.package,
              render: (r) => (
                <span>
                  {r.package || "—"}
                  {r.membershipCode && <span className="cell-secondary block">{r.membershipCode}</span>}
                </span>
              ),
            },
            {
              key: "sale",
              label: "Sale",
              sortValue: (r) => r.saleName,
              render: (r) => (
                <span>
                  <span className="font-medium text-slate-900">{r.saleName}</span>
                  <span className="cell-secondary block">{r.saleTitle || "—"}</span>
                </span>
              ),
            },
            {
              key: "method",
              label: "Phương thức",
              sortValue: (r) => r.method,
              render: (r) => methodLabels[r.method] || r.method,
            },
            {
              key: "amount",
              label: "Số tiền",
              className: "text-right",
              sortValue: (r) => r.amount,
              render: (r) => money(r.amount),
            },
          ]}
          emptyTitle="Không có doanh thu"
          emptyDescription="Không có phiếu thu nào trong kỳ hoặc bộ lọc hiện tại."
        />
        <Pagination
          data={revenuePagination}
          onPage={setRevenuePage}
          pageSize={revenuePageSize}
          onPageSize={(value) => {
            setRevenuePageSize(value);
            setRevenuePage(1);
          }}
        />
      </section>
      <section className="mt-7">
        <div className="section-header">
          <div>
            <h2>Chi tiết công nợ</h2>
            <p>Lọc theo hạn thanh toán trong khoảng báo cáo, ưu tiên khoản cần xử lý trước</p>
          </div>
        </div>
        <div className="mb-3 grid grid-cols-5 gap-2 max-[900px]:grid-cols-2 max-[520px]:grid-cols-1">
          {[
            ["Tổng sau lọc", money(debtSummary.amount)],
            ["Số khoản", debtSummary.all],
            ["Quá hạn", debtSummary.overdue],
            ["Đến hạn hôm nay", debtSummary.dueToday],
            ["Sắp tới hạn 7 ngày", debtSummary.dueSoon],
          ].map(([label, value]) => (
            <div key={label} className="rounded-md border border-slate-200 bg-white px-3 py-2">
              <div className="text-[10px] font-medium uppercase tracking-wide text-slate-500">{label}</div>
              <div className="mt-1 text-sm font-semibold text-slate-950">{value}</div>
            </div>
          ))}
        </div>
        <div className="mb-3 flex flex-wrap gap-2">
          <input
            className="input w-64"
            value={debtSearch}
            onChange={(event) => {
              setDebtSearch(event.target.value);
              setDebtPage(1);
            }}
            placeholder="Tìm tên, mã, SĐT, gói, sale"
          />
          <Select
            className="input w-44"
            value={debtFilter}
            onChange={(event) => {
              setDebtFilter(event.target.value);
              setDebtPage(1);
            }}
          >
            <option value="all">Mọi trạng thái</option>
            <option value="overdue">Quá hạn</option>
            <option value="due_today">Đến hạn hôm nay</option>
            <option value="due_soon">Sắp tới hạn 7 ngày</option>
            <option value="in_due">Trong hạn</option>
            <option value="no_due">Chưa đặt hạn</option>
          </Select>
          <Select
            className="input w-48"
            value={debtSaleFilter}
            onChange={(event) => {
              setDebtSaleFilter(event.target.value);
              setDebtPage(1);
            }}
          >
            <option value="all">Mọi sale</option>
            {debtSaleOptions.map((row) => (
              <option key={row.value} value={row.value}>
                {row.label}{row.title ? ` - ${row.title}` : ""}
              </option>
            ))}
          </Select>
          <Select
            className="input w-48"
            value={debtPackageFilter}
            onChange={(event) => {
              setDebtPackageFilter(event.target.value);
              setDebtPage(1);
            }}
          >
            <option value="all">Mọi gói tập</option>
            {debtPackageOptions.map((name) => (
              <option key={name} value={name}>{name}</option>
            ))}
          </Select>
          <Select
            className="input w-44"
            value={debtAmountFilter}
            onChange={(event) => {
              setDebtAmountFilter(event.target.value);
              setDebtPage(1);
            }}
          >
            <option value="all">Mọi mức nợ</option>
            <option value="under_500k">Dưới 500K</option>
            <option value="500k_1m">500K - dưới 1M</option>
            <option value="1m_3m">1M - dưới 3M</option>
            <option value="over_3m">Từ 3M</option>
          </Select>
          <Select
            className="input w-44"
            value={debtSort}
            onChange={(event) => {
              setDebtSort(event.target.value);
              setDebtPage(1);
            }}
          >
            <option value="nearest_due">Cần xử lý trước</option>
            <option value="overdue_oldest">Quá hạn lâu trước</option>
            <option value="farthest_due">Xa hạn trước</option>
            <option value="amount_desc">Nợ cao trước</option>
            <option value="amount_asc">Nợ thấp trước</option>
            <option value="member_az">Tên A-Z</option>
          </Select>
        </div>
        <DataTable
          loading={query.isLoading}
          error={query.error}
          onRetry={query.refetch}
          rows={debtPageRows}
          rowKey="membershipId"
          columns={[
            {
              key: "member",
              label: "Hội viên",
              sortValue: (r) => r.member,
              render: (r) => (
                <Link className="cell-primary hover:underline" to={`/members/${r.memberId}`}>
                  {r.member}
                  <span className="cell-secondary block">
                    {[r.memberCode, r.phone].filter(Boolean).join(" · ")}
                  </span>
                </Link>
              ),
            },
            {
              key: "package",
              label: "Gói tập",
              sortValue: (r) => r.package,
              render: (r) => (
                <span>
                  {r.package || "—"}
                  {r.membershipCode && <span className="cell-secondary block">{r.membershipCode}</span>}
                </span>
              ),
            },
            {
              key: "sale",
              label: "Sale",
              sortValue: (r) => r.saleName,
              render: (r) => (
                <span>
                  <span className="font-medium text-slate-900">{r.saleName}</span>
                  <span className="cell-secondary block">{r.saleTitle || "—"}</span>
                </span>
              ),
            },
            {
              key: "amount",
              label: "Số tiền",
              className: "text-right",
              sortValue: (r) => r.amount,
              render: (r) => money(r.amount),
            },
            {
              key: "dueDate",
              label: "Hạn thanh toán",
              sortValue: (r) => r.dueDate || "9999-12-31",
              render: (r) => shortDate(r.dueDate),
            },
            {
              key: "status",
              label: "Tình trạng",
              sortValue: (r) => debtTiming(r).rank,
              render: (r) => {
                const timing = debtTiming(r);
                return (
                  <span className={`text-xs font-medium ${timing.className}`}>
                    {timing.label}
                  </span>
                );
              },
            },
            {
              key: "action",
              label: "Thao tác",
              className: "text-right",
              sortable: false,
              render: (r) => (
                <Button
                  size="sm"
                  variant="secondary"
                  onClick={() =>
                    setParams((current) => {
                      const next = new URLSearchParams(current);
                      next.set("member", r.memberId);
                      next.set("action", "payment");
                      return next;
                    })
                  }
                >
                  Thu tiền
                </Button>
              ),
            },
          ]}
          emptyTitle="Không có công nợ"
          emptyDescription="Tất cả gói tập đã được thanh toán đầy đủ."
        />
        <Pagination
          data={debtPagination}
          onPage={setDebtPage}
          pageSize={debtPageSize}
          onPageSize={(value) => {
            setDebtPageSize(value);
            setDebtPage(1);
          }}
        />
      </section>
    </>
  );
}
