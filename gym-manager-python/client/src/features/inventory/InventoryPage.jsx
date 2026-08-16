import { useMemo, useState } from "react";
import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowDownToLine,
  ArrowUpFromLine,
  Boxes,
  ChevronLeft,
  ChevronRight,
  Download,
  History,
  PackagePlus,
  Pencil,
  Plus,
  RotateCcw,
  Search,
  Warehouse,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, queryString } from "../../services/api";
import { notify } from "../../services/notify";
import { PageHeader } from "../../components/common/PageHeader";
import { DataTable } from "../../components/ui/DataTable";
import { Pagination } from "../../components/ui/Pagination";
import { Button } from "../../components/ui/Button";
import { Field, Input, Select, Textarea } from "../../components/ui/Form";
import { DateInput, MoneyInput, NumberUnitInput } from "../../components/ui/SmartInputs";
import { Modal } from "../../components/ui/Modal";
import { dateTime, money, shortDate } from "../../utils/format";

const pad = (value) => String(value).padStart(2, "0");
const isoDate = (date) => `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
const today = () => isoDate(new Date());
const localDateTime = () => {
  const value = new Date();
  value.setMinutes(value.getMinutes() - value.getTimezoneOffset());
  return value.toISOString().slice(0, 16);
};
const quantity = (value) => new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 3 }).format(Number(value || 0));
const blankProduct = { name: "", sku: "", category: "", unit: "", minimumStock: 0, initialStock: 0, initialCost: 0, note: "", isActive: true };
const blankTransaction = { type: "IN", productId: "", quantity: 1, unitCost: 0, occurredAt: localDateTime(), note: "" };

function moveAnchor(anchor, period, direction) {
  const value = new Date(`${anchor}T00:00:00`);
  if (period === "day") value.setDate(value.getDate() + direction);
  if (period === "week") value.setDate(value.getDate() + direction * 7);
  if (period === "month") value.setMonth(value.getMonth() + direction);
  if (period === "year") value.setFullYear(value.getFullYear() + direction);
  return isoDate(value);
}

function StockBadge({ row }) {
  const meta = row.stockStatus === "out"
    ? ["Hết hàng", "danger"]
    : row.stockStatus === "low"
      ? ["Sắp hết", "warning"]
      : ["Còn hàng", "positive"];
  return <span className={`inventory-badge tone-${meta[1]}`}>{meta[0]}</span>;
}

function TypeBadge({ type, reversed, reversal }) {
  return <span className={`inventory-type ${type === "IN" ? "in" : "out"} ${reversed ? "reversed" : ""}`}>{reversal ? <RotateCcw size={12} /> : type === "IN" ? <ArrowDownToLine size={12} /> : <ArrowUpFromLine size={12} />}{reversal ? "Phiếu hoàn" : type === "IN" ? "Nhập" : "Xuất"}{reversed ? " · Đã hoàn" : ""}</span>;
}

export function InventoryPage() {
  const client = useQueryClient();
  const [view, setView] = useState("products");
  const [productPage, setProductPage] = useState(1);
  const [productPageSize, setProductPageSize] = useState(30);
  const [productQ, setProductQ] = useState("");
  const [category, setCategory] = useState("all");
  const [stockStatus, setStockStatus] = useState("all");
  const [active, setActive] = useState("active");
  const [productModal, setProductModal] = useState(false);
  const [editingProduct, setEditingProduct] = useState(null);
  const [productForm, setProductForm] = useState(blankProduct);
  const [formError, setFormError] = useState("");
  const [transactionPage, setTransactionPage] = useState(1);
  const [transactionPageSize, setTransactionPageSize] = useState(30);
  const [transactionQ, setTransactionQ] = useState("");
  const [transactionType, setTransactionType] = useState("all");
  const [transactionCategory, setTransactionCategory] = useState("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [transactionModal, setTransactionModal] = useState(false);
  const [transactionForm, setTransactionForm] = useState(blankTransaction);
  const [reverseTarget, setReverseTarget] = useState(null);
  const [reverseNote, setReverseNote] = useState("");
  const [period, setPeriod] = useState("month");
  const [anchor, setAnchor] = useState(today());
  const [reportCategory, setReportCategory] = useState("all");
  const [reportProduct, setReportProduct] = useState("all");

  const products = useQuery({
    queryKey: ["inventory-products", productQ, category, stockStatus, active, productPage, productPageSize],
    queryFn: () => api(`/api/inventory/products?${queryString({ q: productQ, category, stockStatus, active, page: productPage, pageSize: productPageSize })}`),
    placeholderData: keepPreviousData,
  });
  const productOptions = useQuery({
    queryKey: ["inventory-products", "options"],
    queryFn: () => api("/api/inventory/products?active=active&page=1&pageSize=100"),
  });
  const transactions = useQuery({
    queryKey: ["inventory-transactions", transactionQ, transactionType, transactionCategory, dateFrom, dateTo, transactionPage, transactionPageSize],
    queryFn: () => api(`/api/inventory/transactions?${queryString({ q: transactionQ, type: transactionType, category: transactionCategory, dateFrom, dateTo, page: transactionPage, pageSize: transactionPageSize })}`),
    enabled: view === "transactions",
    placeholderData: keepPreviousData,
  });
  const report = useQuery({
    queryKey: ["inventory-report", period, anchor, reportCategory, reportProduct],
    queryFn: () => api(`/api/inventory/reports?${queryString({ period, anchor, category: reportCategory, productId: reportProduct === "all" ? "" : reportProduct })}`),
    enabled: view === "report",
  });
  const categories = products.data?.filters?.categories || productOptions.data?.filters?.categories || [];
  const selectedProduct = useMemo(() => (productOptions.data?.items || []).find((row) => String(row.id) === String(transactionForm.productId)), [productOptions.data?.items, transactionForm.productId]);

  const refreshInventory = () => {
    client.invalidateQueries({ queryKey: ["inventory-products"] });
    client.invalidateQueries({ queryKey: ["inventory-transactions"] });
    client.invalidateQueries({ queryKey: ["inventory-report"] });
  };
  const saveProduct = useMutation({
    mutationFn: () => api(editingProduct ? `/api/inventory/products/${editingProduct.id}` : "/api/inventory/products", { method: editingProduct ? "PATCH" : "POST", body: productForm }),
    onSuccess: () => { refreshInventory(); setProductModal(false); setEditingProduct(null); setFormError(""); notify.success(editingProduct ? "Đã cập nhật hàng hóa." : "Đã thêm hàng hóa."); },
    onError: (error) => setFormError(error.message),
  });
  const saveTransaction = useMutation({
    mutationFn: () => api("/api/inventory/transactions", { method: "POST", body: { ...transactionForm, productId: Number(transactionForm.productId), quantity: Number(transactionForm.quantity), unitCost: Number(transactionForm.unitCost) } }),
    onSuccess: () => { refreshInventory(); setTransactionModal(false); setFormError(""); notify.success(transactionForm.type === "IN" ? "Đã nhập kho." : "Đã xuất kho."); },
    onError: (error) => setFormError(error.message),
  });
  const reverseTransaction = useMutation({
    mutationFn: () => api(`/api/inventory/transactions/${reverseTarget.id}/reverse`, { method: "POST", body: { note: reverseNote } }),
    onSuccess: () => { refreshInventory(); setReverseTarget(null); setReverseNote(""); notify.success("Đã hoàn giao dịch và cập nhật lại tồn kho."); },
    onError: (error) => notify.errorFrom(error, "Không thể hoàn giao dịch."),
  });

  const openProduct = (row = null) => {
    setEditingProduct(row);
    setProductForm(row ? { name: row.name, sku: row.sku, category: row.category, unit: row.unit, minimumStock: row.minimumStock, isActive: row.isActive } : { ...blankProduct });
    setFormError("");
    setProductModal(true);
  };
  const openTransaction = (type) => {
    setTransactionForm({ ...blankTransaction, type, occurredAt: localDateTime(), productId: productOptions.data?.items?.[0]?.id || "" });
    setFormError("");
    setTransactionModal(true);
  };
  const exportUrl = `/api/inventory/export?${queryString({ type: transactionType, category: transactionCategory, dateFrom, dateTo })}`;

  return (
    <div className="inventory-page">
      <PageHeader eyebrow="Vận hành" title="Kho nội bộ" description="Vật tư tiêu hao và trang thiết bị" action={<div className="inventory-header-actions"><Button variant="secondary" onClick={() => openTransaction("OUT")}><ArrowUpFromLine size={15} />Xuất kho</Button><Button onClick={() => openTransaction("IN")}><ArrowDownToLine size={15} />Nhập hàng</Button></div>} />

      <div className="inventory-workspace-tabs" role="tablist">
        <button type="button" className={view === "products" ? "active" : ""} onClick={() => setView("products")}><Boxes size={15} />Hàng hóa</button>
        <button type="button" className={view === "transactions" ? "active" : ""} onClick={() => setView("transactions")}><History size={15} />Nhập / Xuất</button>
        <button type="button" className={view === "report" ? "active" : ""} onClick={() => setView("report")}><Warehouse size={15} />Báo cáo kho</button>
      </div>

      {view === "products" && <>
        <div className="inventory-metric-strip">
          <div><span>Tổng mặt hàng</span><strong>{products.data?.summary?.products || 0}</strong><small>Đang sử dụng</small></div>
          <div><span>Giá trị tồn</span><strong>{money(products.data?.summary?.inventoryValue)}</strong><small>Theo giá vốn bình quân</small></div>
          <button type="button" className="warning" onClick={() => { setStockStatus("low"); setProductPage(1); }}><span>Sắp hết</span><strong>{products.data?.summary?.lowStock || 0}</strong><small>Dưới mức tối thiểu</small></button>
          <button type="button" className="danger" onClick={() => { setStockStatus("out"); setProductPage(1); }}><span>Hết hàng</span><strong>{products.data?.summary?.outOfStock || 0}</strong><small>Cần bổ sung</small></button>
        </div>
        <div className="inventory-toolbar">
          <label className="inventory-search"><Search size={15} /><Input value={productQ} onChange={(event) => { setProductQ(event.target.value); setProductPage(1); }} placeholder="Tìm tên hoặc mã hàng" /></label>
          <Select value={category} onChange={(event) => { setCategory(event.target.value); setProductPage(1); }}><option value="all">Mọi danh mục</option>{categories.map((item) => <option key={item}>{item}</option>)}</Select>
          <Select value={stockStatus} onChange={(event) => { setStockStatus(event.target.value); setProductPage(1); }}><option value="all">Mọi mức tồn</option><option value="in_stock">Còn hàng</option><option value="low">Sắp hết</option><option value="out">Hết hàng</option></Select>
          <Select value={active} onChange={(event) => { setActive(event.target.value); setProductPage(1); }}><option value="active">Đang sử dụng</option><option value="inactive">Ngừng sử dụng</option><option value="all">Tất cả trạng thái</option></Select>
          <Button onClick={() => openProduct()}><Plus size={15} />Thêm hàng</Button>
        </div>
        <DataTable loading={products.isLoading} error={products.error} rows={products.data?.items || []} density="compact" columns={[
          { key: "category", label: "Danh mục" },
          { key: "name", label: "Hàng hóa", className: "inventory-product-col", render: (row) => <span className="inventory-product-name"><strong>{row.name}</strong><small>{row.sku}</small></span> },
          { key: "unit", label: "Đơn vị" },
          { key: "currentStock", label: "Tồn hiện tại", className: "text-right", render: (row) => <strong className="tabular-nums">{quantity(row.currentStock)}</strong> },
          { key: "averageCost", label: "Giá vốn", className: "text-right", render: (row) => money(row.averageCost) },
          { key: "inventoryValue", label: "Giá trị tồn", className: "text-right", render: (row) => <strong>{money(row.inventoryValue)}</strong> },
          { key: "status", label: "Trạng thái", sortable: false, render: (row) => row.isActive ? <StockBadge row={row} /> : <span className="inventory-badge">Ngừng sử dụng</span> },
          { key: "action", label: "", sortable: false, render: (row) => <button type="button" className="icon-button" title="Sửa hàng hóa" onClick={() => openProduct(row)}><Pencil size={14} /></button> },
        ]} emptyTitle="Chưa có hàng hóa" emptyDescription="Thêm mặt hàng đầu tiên để bắt đầu quản lý kho." emptyAction={<Button onClick={() => openProduct()}><PackagePlus size={15} />Thêm hàng</Button>} />
        <Pagination data={products.data?.pagination} onPage={setProductPage} pageSize={productPageSize} onPageSize={(value) => { setProductPageSize(value); setProductPage(1); }} />
      </>}

      {view === "transactions" && <>
        <div className="inventory-toolbar transactions">
          <label className="inventory-search"><Search size={15} /><Input value={transactionQ} onChange={(event) => { setTransactionQ(event.target.value); setTransactionPage(1); }} placeholder="Tìm hàng hóa hoặc ghi chú" /></label>
          <DateInput value={dateFrom} onChange={(value) => { setDateFrom(value); setTransactionPage(1); }} placeholder="Từ ngày" />
          <DateInput value={dateTo} onChange={(value) => { setDateTo(value); setTransactionPage(1); }} placeholder="Đến ngày" />
          <Select value={transactionType} onChange={(event) => { setTransactionType(event.target.value); setTransactionPage(1); }}><option value="all">Nhập và xuất</option><option value="IN">Chỉ nhập</option><option value="OUT">Chỉ xuất</option></Select>
          <Select value={transactionCategory} onChange={(event) => { setTransactionCategory(event.target.value); setTransactionPage(1); }}><option value="all">Mọi danh mục</option>{categories.map((item) => <option key={item}>{item}</option>)}</Select>
          <a className="btn btn-secondary btn-sm" href={exportUrl}><Download size={14} />Xuất CSV</a>
        </div>
        <DataTable loading={transactions.isLoading} error={transactions.error} rows={transactions.data?.items || []} density="compact" columns={[
          { key: "occurredAt", label: "Ngày tháng", render: (row) => dateTime(row.occurredAt) },
          { key: "product", label: "Hàng hóa", className: "inventory-product-col", render: (row) => <span className="inventory-product-name"><strong>{row.productName}</strong><small>{row.category} · {row.sku}</small></span> },
          { key: "type", label: "Loại", render: (row) => <TypeBadge type={row.type} reversed={row.status === "REVERSED"} reversal={!!row.reversedTransactionId} /> },
          { key: "quantity", label: "Số lượng", className: "text-right", render: (row) => <strong className={`inventory-quantity ${row.type === "IN" ? "in" : "out"}`}>{row.type === "IN" ? "+" : "−"}{quantity(row.quantity)} {row.unit}</strong> },
          { key: "unitCost", label: "Đơn giá", className: "text-right", render: (row) => money(row.unitCost) },
          { key: "totalAmount", label: "Tổng tiền", className: "text-right", render: (row) => <strong>{money(row.totalAmount)}</strong> },
          { key: "note", label: "Ghi chú", render: (row) => row.note || "—" },
          { key: "createdBy", label: "Người tạo" },
          { key: "action", label: "", sortable: false, render: (row) => row.status !== "REVERSED" && !row.reversedTransactionId ? <button type="button" className="icon-button" title="Hoàn giao dịch" onClick={() => { setReverseTarget(row); setReverseNote(""); }}><RotateCcw size={14} /></button> : null },
        ]} emptyTitle="Chưa có giao dịch kho" emptyDescription="Các phiếu nhập và xuất sẽ xuất hiện tại đây." />
        <Pagination data={transactions.data?.pagination} onPage={setTransactionPage} pageSize={transactionPageSize} onPageSize={(value) => { setTransactionPageSize(value); setTransactionPage(1); }} />
      </>}

      {view === "report" && <>
        <div className="inventory-report-toolbar">
          <div className="inventory-period-switch">{[["day", "Ngày"], ["week", "Tuần"], ["month", "Tháng"], ["year", "Năm"]].map(([key, label]) => <button type="button" key={key} className={period === key ? "active" : ""} onClick={() => setPeriod(key)}>{label}</button>)}</div>
          <button type="button" className="icon-button" onClick={() => setAnchor(moveAnchor(anchor, period, -1))} aria-label="Kỳ trước"><ChevronLeft size={16} /></button>
          <DateInput value={anchor} onChange={(value) => setAnchor(value || today())} />
          <button type="button" className="icon-button" onClick={() => setAnchor(moveAnchor(anchor, period, 1))} aria-label="Kỳ sau"><ChevronRight size={16} /></button>
          <span className="inventory-report-range">{report.data ? `${shortDate(report.data.dateFrom)} – ${shortDate(report.data.dateTo)}` : ""}</span>
          <Select value={reportCategory} onChange={(event) => setReportCategory(event.target.value)}><option value="all">Mọi danh mục</option>{categories.map((item) => <option key={item}>{item}</option>)}</Select>
          <Select value={reportProduct} onChange={(event) => setReportProduct(event.target.value)}><option value="all">Mọi hàng hóa</option>{(productOptions.data?.items || []).map((row) => <option key={row.id} value={row.id}>{row.name}</option>)}</Select>
        </div>
        <div className="inventory-report-kpis">
          <div><span>Chi phí nhập</span><strong>{money(report.data?.summary?.inboundCost)}</strong><small>Trong kỳ</small></div>
          <div><span>Giá trị đã xuất</span><strong>{money(report.data?.summary?.outboundCost)}</strong><small>Theo giá vốn</small></div>
          <div><span>Tồn đầu kỳ</span><strong>{quantity(report.data?.summary?.openingStock)}</strong><small>Tổng đơn vị quy đổi</small></div>
          <div><span>Tồn cuối kỳ</span><strong>{quantity(report.data?.summary?.closingStock)}</strong><small>Nhập trừ xuất</small></div>
          <div className={(report.data?.summary?.netMovement || 0) < 0 ? "danger" : "positive"}><span>Biến động ròng</span><strong>{(report.data?.summary?.netMovement || 0) > 0 ? "+" : ""}{quantity(report.data?.summary?.netMovement)}</strong><small>Trong kỳ</small></div>
        </div>
        <div className="inventory-report-grid">
          <section className="inventory-report-panel wide"><header><div><span>Biến động nhập / xuất</span><small>Theo số lượng giao dịch</small></div></header><div className="inventory-chart">{report.data?.series?.length ? <ResponsiveContainer width="100%" height="100%"><BarChart data={report.data.series} margin={{ top: 12, right: 12, left: -12, bottom: 0 }}><CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" /><XAxis dataKey="bucket" tick={{ fontSize: 10 }} axisLine={false} tickLine={false} /><YAxis tick={{ fontSize: 10 }} axisLine={false} tickLine={false} /><Tooltip formatter={(value) => quantity(value)} /><Bar dataKey="inQuantity" name="Nhập" fill="#0f766e" radius={[3, 3, 0, 0]} /><Bar dataKey="outQuantity" name="Xuất" fill="#d97706" radius={[3, 3, 0, 0]} /></BarChart></ResponsiveContainer> : <div className="inventory-chart-empty">Chưa có biến động trong kỳ</div>}</div></section>
          <section className="inventory-report-panel"><header><div><span>Chi phí xuất theo danh mục</span><small>Giá vốn đã sử dụng</small></div></header><div className="inventory-category-list">{(report.data?.categoryCosts || []).map((row) => <div key={row.category}><span>{row.category}</span><strong>{money(row.value)}</strong><i style={{ width: `${Math.max(4, (row.value / Math.max(...report.data.categoryCosts.map((item) => item.value))) * 100)}%` }} /></div>)}{!report.data?.categoryCosts?.length && <p>Chưa có chi phí xuất trong kỳ.</p>}</div></section>
          <section className="inventory-report-panel"><header><div><span>Tiêu hao nhiều nhất</span><small>Xếp theo giá trị xuất</small></div></header><div className="inventory-usage-list">{(report.data?.topUsage || []).map((row, index) => <div key={row.productId}><b>{index + 1}</b><span><strong>{row.productName}</strong><small>{quantity(row.quantity)} {row.unit}</small></span><em>{money(row.value)}</em></div>)}{!report.data?.topUsage?.length && <p>Chưa có dữ liệu tiêu hao.</p>}</div></section>
        </div>
      </>}

      <Modal open={productModal} onClose={() => setProductModal(false)} title={editingProduct ? "Cập nhật hàng hóa" : "Thêm hàng hóa"} description={editingProduct ? `${editingProduct.name} · ${editingProduct.sku}` : "Tạo mặt hàng trong kho nội bộ"} dirty={false}>
        <form onSubmit={(event) => { event.preventDefault(); saveProduct.mutate(); }}><div className="modal-body"><div className="form-grid"><Field label="Tên hàng hóa" required className="form-span"><Input autoFocus value={productForm.name} onChange={(event) => setProductForm({ ...productForm, name: event.target.value })} /></Field><Field label="Danh mục" required><Input list="inventory-categories" value={productForm.category} onChange={(event) => setProductForm({ ...productForm, category: event.target.value })} /><datalist id="inventory-categories">{categories.map((item) => <option key={item}>{item}</option>)}</datalist></Field><Field label="Đơn vị tính" required><Input value={productForm.unit} onChange={(event) => setProductForm({ ...productForm, unit: event.target.value })} placeholder="Chai, hộp, cái..." /></Field><Field label="Mã hàng"><Input value={productForm.sku} onChange={(event) => setProductForm({ ...productForm, sku: event.target.value.toUpperCase() })} placeholder="Tự sinh nếu để trống" /></Field><Field label="Mức tồn tối thiểu"><NumberUnitInput allowDecimal value={productForm.minimumStock} unit={productForm.unit || "đơn vị"} onChange={(value) => setProductForm({ ...productForm, minimumStock: value })} /></Field>{!editingProduct && <><Field label="Tồn đầu kỳ"><NumberUnitInput allowDecimal value={productForm.initialStock} unit={productForm.unit || "đơn vị"} onChange={(value) => setProductForm({ ...productForm, initialStock: value })} /></Field><Field label="Đơn giá đầu kỳ"><MoneyInput value={productForm.initialCost} onChange={(value) => setProductForm({ ...productForm, initialCost: value })} /></Field><Field label="Ghi chú" className="form-span"><Textarea value={productForm.note} onChange={(event) => setProductForm({ ...productForm, note: event.target.value })} /></Field></>}{editingProduct && <Field label="Trạng thái" className="form-span"><Select value={productForm.isActive ? "active" : "inactive"} onChange={(event) => setProductForm({ ...productForm, isActive: event.target.value === "active" })}><option value="active">Đang sử dụng</option><option value="inactive">Ngừng sử dụng</option></Select></Field>}</div>{formError && <div className="inline-error mt-4">{formError}</div>}</div><div className="form-actions"><Button variant="secondary" onClick={() => setProductModal(false)}>Hủy</Button><Button type="submit" loading={saveProduct.isPending} disabled={!productForm.name || !productForm.category || !productForm.unit}>Lưu hàng hóa</Button></div></form>
      </Modal>

      <Modal open={transactionModal} onClose={() => setTransactionModal(false)} title={transactionForm.type === "IN" ? "Nhập hàng" : "Xuất kho"} description="Ghi nhận biến động tồn kho">
        <form onSubmit={(event) => { event.preventDefault(); saveTransaction.mutate(); }}><div className="modal-body"><div className="inventory-transaction-switch"><button type="button" className={transactionForm.type === "IN" ? "active in" : ""} onClick={() => setTransactionForm({ ...transactionForm, type: "IN" })}><ArrowDownToLine size={14} />Nhập kho</button><button type="button" className={transactionForm.type === "OUT" ? "active out" : ""} onClick={() => setTransactionForm({ ...transactionForm, type: "OUT" })}><ArrowUpFromLine size={14} />Xuất kho</button></div><div className="form-grid mt-4"><Field label="Ngày giao dịch" required className="form-span"><Input type="datetime-local" value={transactionForm.occurredAt} onChange={(event) => setTransactionForm({ ...transactionForm, occurredAt: event.target.value })} /></Field><Field label="Hàng hóa" required className="form-span"><Select autoFocus value={transactionForm.productId} onChange={(event) => setTransactionForm({ ...transactionForm, productId: event.target.value })}><option value="">Chọn hàng hóa</option>{(productOptions.data?.items || []).map((row) => <option key={row.id} value={row.id}>{row.name} · {row.sku}</option>)}</Select></Field>{selectedProduct && <div className="inventory-stock-context form-span"><span>Tồn hiện tại</span><strong>{quantity(selectedProduct.currentStock)} {selectedProduct.unit}</strong><small>Giá vốn {money(selectedProduct.averageCost)}</small></div>}<Field label="Số lượng" required><NumberUnitInput allowDecimal value={transactionForm.quantity} unit={selectedProduct?.unit || "đơn vị"} onChange={(value) => setTransactionForm({ ...transactionForm, quantity: value })} /></Field>{transactionForm.type === "IN" ? <Field label="Đơn giá nhập" required><MoneyInput value={transactionForm.unitCost} onChange={(value) => setTransactionForm({ ...transactionForm, unitCost: value })} /></Field> : <Field label="Giá vốn xuất"><Input value={money(selectedProduct?.averageCost)} disabled /></Field>}<div className="inventory-form-total form-span"><span>Tổng tiền</span><strong>{money(Number(transactionForm.quantity || 0) * Number(transactionForm.type === "IN" ? transactionForm.unitCost : selectedProduct?.averageCost || 0))}</strong></div><Field label="Ghi chú" className="form-span"><Textarea value={transactionForm.note} onChange={(event) => setTransactionForm({ ...transactionForm, note: event.target.value })} /></Field></div>{formError && <div className="inline-error mt-4">{formError}</div>}</div><div className="form-actions"><Button variant="secondary" onClick={() => setTransactionModal(false)}>Hủy</Button><Button type="submit" loading={saveTransaction.isPending} disabled={!transactionForm.productId || Number(transactionForm.quantity) <= 0 || (transactionForm.type === "IN" && Number(transactionForm.unitCost) <= 0)}>{transactionForm.type === "IN" ? "Xác nhận nhập" : "Xác nhận xuất"}</Button></div></form>
      </Modal>

      <Modal open={!!reverseTarget} onClose={() => setReverseTarget(null)} size="sm" title="Hoàn giao dịch?" description={reverseTarget ? `${reverseTarget.productName} · ${dateTime(reverseTarget.occurredAt)}` : ""}><div className="modal-body"><div className="inventory-reverse-warning"><AlertTriangle size={17} /><span>Hệ thống sẽ tạo giao dịch đối ứng và cập nhật lại tồn kho.</span></div><Field label="Lý do hoàn" required><Textarea autoFocus value={reverseNote} onChange={(event) => setReverseNote(event.target.value)} /></Field></div><div className="form-actions"><Button variant="secondary" onClick={() => setReverseTarget(null)}>Hủy</Button><Button variant="danger" loading={reverseTransaction.isPending} disabled={!reverseNote.trim()} onClick={() => reverseTransaction.mutate()}><RotateCcw size={14} />Hoàn giao dịch</Button></div></Modal>
    </div>
  );
}
