import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, CalendarDays, CheckCircle2, ChevronLeft, ChevronRight, ClipboardList, Clock3, Download, Eye, FileSpreadsheet, Filter, LayoutGrid, Link2, LogOut, Pencil, Plus, Rows3, Save, Search, Trash2, UserX, X } from "lucide-react";
import { Link } from "react-router-dom";
import { api, queryString } from "../../services/api";
import { notify } from "../../services/notify";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";
import { PageHeader } from "../../components/common/PageHeader";
import { SearchInput } from "../../components/common/SearchInput";
import { Button } from "../../components/ui/Button";
import { DataTable } from "../../components/ui/DataTable";
import { Field, Input, Select } from "../../components/ui/Form";
import { Modal } from "../../components/ui/Modal";
import { DateInput, PhoneInput } from "../../components/ui/SmartInputs";
import { Pagination } from "../../components/ui/Pagination";
import { RowMenu } from "../../components/ui/RowMenu";
import { formatPhone, initials, normalizePhone } from "../../utils/format";
import { useAuth } from "../../app/AuthContext";
import { DahIdentityLinkModal } from "../members/DahIdentityLinkModal";

const defaultJobTitles = ["Sale", "Coach", "Marketing"];
const blank = { name: "", phone: "", email: "", title: "Coach" };

const dateToIso = (day) => {
  const year = day.getFullYear();
  const month = String(day.getMonth() + 1).padStart(2, "0");
  const dayOfMonth = String(day.getDate()).padStart(2, "0");
  return `${year}-${month}-${dayOfMonth}`;
};

const isoDay = (offset = 0) => {
  const day = new Date();
  day.setDate(day.getDate() + offset);
  return dateToIso(day);
};
const blankShift = { workDate: isoDay(), startTime: "08:00", endTime: "12:00", note: "" };
const startOfWeek = (isoDate = isoDay()) => {
  const day = new Date(`${isoDate}T00:00:00`);
  const offset = (day.getDay() + 6) % 7;
  day.setDate(day.getDate() - offset);
  return dateToIso(day);
};
const blankBulkShift = {
  weekStart: startOfWeek(),
  weekdays: [0, 1, 2, 3, 4, 5, 6],
  startTime: "08:00",
  endTime: "12:00",
  note: "",
};
const weekDays = ["T2", "T3", "T4", "T5", "T6", "T7", "CN"];

const addDays = (isoDate, days) => {
  const date = new Date(`${isoDate}T00:00:00`);
  date.setDate(date.getDate() + days);
  return dateToIso(date);
};

const csvValue = (value) => `"${String(value ?? "").replaceAll('"', '""')}"`;

function normalizeJobTitle(value) {
  return String(value || "").trim().slice(0, 80);
}

function normalizeText(value) {
  return String(value || "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replaceAll("đ", "d")
    .replaceAll("Đ", "D")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, " ");
}

function normalizeTimePart(value) {
  const text = String(value || "").trim().toUpperCase();
  const match = text.match(/^(\d{1,2})(?:H(\d{1,2})?|:(\d{1,2}))?$/);
  if (!match) return null;
  const hour = Number(match[1]);
  const minute = Number(match[2] || match[3] || 0);
  if (hour > 23 || minute > 59) return null;
  return `${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}`;
}

function parseShiftLine(value) {
  const text = String(value || "").trim().toUpperCase().replace(/\s+/g, "");
  if (!text || ["OFF", "P", "PHEP", "PHÉP"].includes(text)) return null;
  const [start, end] = text.split("-");
  if (!start || !end) return { error: `Không đọc được ca "${value}"` };
  const startTime = normalizeTimePart(start);
  const endTime = normalizeTimePart(end);
  if (!startTime || !endTime || endTime <= startTime) return { error: `Giờ ca không hợp lệ "${value}"` };
  return { startTime, endTime };
}

function shiftsFromCell(cellValue, workDate) {
  const lines = String(cellValue || "")
    .split(/\r?\n|;/)
    .map((line) => line.trim())
    .filter(Boolean);
  const shifts = [];
  const errors = [];
  lines.forEach((line) => {
    const parsed = parseShiftLine(line);
    if (!parsed) return;
    if (parsed.error) errors.push(parsed.error);
    else shifts.push({ workDate, ...parsed });
  });
  return { shifts, errors };
}

function shiftCellText(shifts) {
  return (shifts || [])
    .map((shift) => `${shift.startTime.replace(":", "H").replace("H00", "H")}-${shift.endTime.replace(":", "H").replace("H00", "H")}`)
    .join("\n");
}

function timeOnly(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(11, 16) || "—";
  return date.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

function dateLabel(value) {
  if (!value) return "";
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString("vi-VN");
}

function sameMinute(a, b) {
  if (!a || !b) return false;
  const left = new Date(a);
  const right = new Date(b);
  if (Number.isNaN(left.getTime()) || Number.isNaN(right.getTime())) return false;
  return Math.abs(left.getTime() - right.getTime()) < 60000;
}

function shiftEventOptions(row) {
  const map = new Map();
  [...(row?.events || []), ...(row?.dayEvents || [])].forEach((event) => {
    if (event?.id && !map.has(event.id)) map.set(event.id, event);
  });
  return Array.from(map.values()).sort((a, b) => {
    const left = new Date(a.eventTime || 0).getTime();
    const right = new Date(b.eventTime || 0).getTime();
    return left - right || a.id - b.id;
  });
}

function shiftEventLabel(event) {
  return `${timeOnly(event.eventTime)} · #${event.id} · ${event.action || "DAH event"} · ${event.status || "received"}`;
}

function DahEventList({ events = [] }) {
  if (!events.length) return <span className="text-xs text-slate-400">—</span>;
  return (
    <span className="shift-dah-events" title={events.map(shiftEventLabel).join("\n")}>
      {events.map((event) => (
        <span key={event.id}>
          <strong>{timeOnly(event.eventTime)}</strong>
          <small>{event.action || "DAH"}</small>
        </span>
      ))}
    </span>
  );
}

function checkStatusClass(status) {
  if (status === "late" || status === "early_checkout") return "border-amber-200 bg-amber-50 text-amber-800";
  if (status === "on_time") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (status === "missing_checkout") return "border-slate-200 bg-slate-50 text-slate-600";
  return "border-slate-200 bg-slate-50 text-slate-600";
}

const reportStatusMeta = {
  on_time: { label: "Đúng giờ", tone: "positive", icon: CheckCircle2 },
  late: { label: "Đi trễ", tone: "warning", icon: Clock3 },
  early_checkout: { label: "Về sớm", tone: "warning", icon: LogOut },
  late_early_checkout: { label: "Trễ · Về sớm", tone: "warning-strong", icon: AlertCircle },
  absent: { label: "Vắng mặt", tone: "danger", icon: UserX },
  missing_checkout: { label: "Thiếu check-out", tone: "danger", icon: AlertCircle },
  awaiting_checkin: { label: "Chờ check-in", tone: "neutral", icon: Clock3 },
  in_progress: { label: "Đang trong ca", tone: "info", icon: Clock3 },
  upcoming: { label: "Chưa đến ca", tone: "neutral", icon: CalendarDays },
};

function ReportStatus({ row, compact = false }) {
  const meta = reportStatusMeta[row.displayStatus] || reportStatusMeta.upcoming;
  const Icon = meta.icon;
  return (
    <span className={`shift-status tone-${meta.tone} ${compact ? "compact" : ""}`}>
      <Icon size={compact ? 11 : 13} />
      <span>{row.displayStatusLabel || meta.label}</span>
      {!compact && row.displayStatus === "late" && row.lateMinutes > 0 && <strong>+{row.lateMinutes}p</strong>}
      {!compact && row.displayStatus === "early_checkout" && row.earlyCheckoutMinutes > 0 && <strong>-{row.earlyCheckoutMinutes}p</strong>}
      {!compact && row.displayStatus === "late_early_checkout" && <strong>+{row.lateMinutes}p / -{row.earlyCheckoutMinutes}p</strong>}
    </span>
  );
}

function downloadAttendanceCsv(data) {
  const rows = Array.isArray(data.rows)
    ? data.rows
    : (data.items || []).flatMap((employee) => employee.days.flatMap((day) => day.shifts.map((shift) => ({
        ...shift,
        workDate: day.workDate,
        employeeCode: employee.employeeCode,
        employeeName: employee.employeeName,
        title: employee.title,
        dahEvents: day.events,
        dayEvents: day.events,
      }))));
  const csv = [
    "Ngày,Mã nhân viên,Họ tên,Chức vụ,Ca tính công,Ca gốc,Đã duyệt đổi ca,Lý do đổi ca,Check-in,Trạng thái check-in,Check-out,Trạng thái check-out,Trạng thái tổng,Trễ phút,Checkout sớm phút,Lịch DAH,Event rà soát",
    ...rows.map((row) => {
      const dahEvents = (row.dahEvents || row.dayEvents || []).map((event) => `${timeOnly(event.eventTime)} ${event.action || "event"} ${event.status}`).join(" | ");
      const events = (row.events || []).map((event) => `${timeOnly(event.eventTime)} ${event.action || "event"} ${event.status}`).join(" | ");
      return [
        row.workDate, row.employeeCode, row.employeeName, row.title,
        `${row.startTime} - ${row.endTime}`,
        `${row.originalStartTime || row.startTime} - ${row.originalEndTime || row.endTime}`,
        row.hasOverride ? "Có" : "", row.overrideReason || "",
        row.checkedInAt ? new Date(row.checkedInAt).toLocaleString("vi-VN") : "",
        row.checkinStatusLabel, row.checkedOutAt ? new Date(row.checkedOutAt).toLocaleString("vi-VN") : "",
        row.checkoutStatusLabel, row.displayStatusLabel || row.statusLabel,
        row.lateMinutes || "", row.earlyCheckoutMinutes || "", dahEvents, events,
      ].map(csvValue).join(",");
    }),
  ].join("\n");
  const url = URL.createObjectURL(new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `pulsefit-shift-attendance-${data.dateFrom}-${data.dateTo}.csv`;
  link.click();
  URL.revokeObjectURL(url);
  return rows.length;
}


export function TrainersPage() {
  const client = useQueryClient();
  const { user } = useAuth();
  const importInputRef = useRef(null);
  const [search, setSearch] = useState("");
  const q = useDebouncedValue(search);
  const [titleFilter, setTitleFilter] = useState("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState(null);
  const [identityTarget, setIdentityTarget] = useState(null);
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [scheduleWeekStart, setScheduleWeekStart] = useState(startOfWeek());
  const [weeklyRows, setWeeklyRows] = useState([]);
  const [weeklyError, setWeeklyError] = useState("");
  const [weeklyGridVisible, setWeeklyGridVisible] = useState(false);
  const [weeklyDirty, setWeeklyDirty] = useState(false);
  const [scheduleTarget, setScheduleTarget] = useState(null);
  const [shiftForm, setShiftForm] = useState(blankShift);
  const [bulkShiftForm, setBulkShiftForm] = useState(blankBulkShift);
  const [editingShift, setEditingShift] = useState(null);
  const [shiftError, setShiftError] = useState("");
  const [importOpen, setImportOpen] = useState(false);
  const [importFileName, setImportFileName] = useState("");
  const [importDays, setImportDays] = useState([]);
  const [importRows, setImportRows] = useState([]);
  const [importError, setImportError] = useState("");
  const [reportOpen, setReportOpen] = useState(false);
  const [reportRange, setReportRange] = useState("today");
  const [reportDate, setReportDate] = useState(isoDay());
  const [reportWeekStart, setReportWeekStart] = useState(startOfWeek());
  const [reportView, setReportView] = useState("exceptions");
  const [reportStatus, setReportStatus] = useState("anomaly");
  const [reportSearch, setReportSearch] = useState("");
  const reportQ = useDebouncedValue(reportSearch);
  const [reportTitle, setReportTitle] = useState("all");
  const [reportShiftKind, setReportShiftKind] = useState("all");
  const [reportSort, setReportSort] = useState("severity");
  const [reportPage, setReportPage] = useState(1);
  const [reportPageSize, setReportPageSize] = useState(30);
  const [reportDetail, setReportDetail] = useState(null);
  const [attendanceEventForm, setAttendanceEventForm] = useState({ checkinEventId: "", checkoutEventId: "" });
  const [overrideTarget, setOverrideTarget] = useState(null);
  const [overrideForm, setOverrideForm] = useState({ workDate: isoDay(), startTime: "08:00", endTime: "12:00", reason: "" });
  const [overrideError, setOverrideError] = useState("");
  const [confirm, setConfirm] = useState(null);
  const [form, setForm] = useState(blank);
  const [error, setError] = useState("");
  const canAdjustShiftAttendance = user?.role === "admin";
  useEffect(
    () =>
      setForm(
        selected
          ? {
              name: selected.name,
              phone: selected.phone || "",
              email: selected.email || "",
              title: selected.title || "",
            }
          : blank,
      ),
    [selected, open],
  );
  const query = useQuery({
    queryKey: ["trainers", q, titleFilter, page, pageSize],
    queryFn: () =>
      api(`/api/trainers?${queryString({ q, title: titleFilter, page, pageSize })}`),
  });
  const allTrainers = useQuery({
    queryKey: ["trainers", "import-options"],
    queryFn: () => api(`/api/trainers?${queryString({ q: "", title: "all", page: 1, pageSize: 100 })}`),
  });
  const scheduleWeekEnd = addDays(scheduleWeekStart, 6);
  const scheduleDays = useMemo(
    () => weekDays.map((label, index) => ({ label, workDate: addDays(scheduleWeekStart, index) })),
    [scheduleWeekStart],
  );
  const weeklyShifts = useQuery({
    queryKey: ["trainer-shifts", "week", scheduleWeekStart, scheduleWeekEnd],
    queryFn: () =>
      api(`/api/trainer-shifts?${queryString({ dateFrom: scheduleWeekStart, dateTo: scheduleWeekEnd })}`),
    enabled: scheduleOpen,
  });
  const shiftRangeStart = bulkShiftForm.weekStart || startOfWeek(shiftForm.workDate || isoDay());
  const shiftRangeEnd = addDays(shiftRangeStart, 6);
  const shifts = useQuery({
    queryKey: ["trainer-shifts", scheduleTarget?.id, shiftRangeStart, shiftRangeEnd],
    queryFn: () =>
      api(`/api/trainers/${scheduleTarget.id}/shifts?${queryString({ dateFrom: shiftRangeStart, dateTo: shiftRangeEnd })}`),
    enabled: !!scheduleTarget?.id,
  });
  const shiftReport = useQuery({
    queryKey: ["trainer-shift-report", reportRange, reportDate, reportWeekStart, reportQ, reportTitle, reportStatus, reportShiftKind, reportSort, reportPage, reportPageSize],
    queryFn: () =>
      api(`/api/trainers/shift-report?${queryString({
        rangeType: reportRange,
        day: reportDate,
        weekStart: reportWeekStart,
        q: reportQ,
        title: reportTitle,
        status: reportView === "matrix" ? "all" : reportStatus,
        shiftKind: reportShiftKind,
        sort: reportSort,
        page: reportPage,
        pageSize: reportPageSize,
      })}`),
    enabled: reportOpen,
  });
  const jobTitles = useMemo(
    () =>
      Array.from(
        new Set([
          ...defaultJobTitles,
          ...(query.data?.jobTitles || []).map((row) => row.name),
          normalizeJobTitle(form.title),
        ].filter(Boolean)),
      ).sort((a, b) => a.localeCompare(b, "vi")),
    [form.title, query.data?.jobTitles],
  );
  const trainerNameMap = useMemo(() => {
    const map = new Map();
    (allTrainers.data?.items || []).forEach((trainer) => {
      const key = normalizeText(trainer.name);
      if (!map.has(key)) map.set(key, trainer);
      else map.set(key, null);
    });
    return map;
  }, [allTrainers.data?.items]);
  const importSummary = useMemo(() => {
    let shifts = 0;
    let errors = 0;
    let unmatched = 0;
    importRows.forEach((row) => {
      if (!row.employeeId && !trainerNameMap.get(normalizeText(row.employeeName))) unmatched += 1;
      row.cells.forEach((cell, index) => {
        const parsed = shiftsFromCell(cell, importDays[index]?.workDate);
        shifts += parsed.shifts.length;
        errors += parsed.errors.length;
      });
    });
    return { shifts, errors, unmatched, rows: importRows.length };
  }, [importDays, importRows, trainerNameMap]);
  const lockedImportEmployeeIds = useMemo(() => {
    const ids = new Set();
    importRows.forEach((row) => {
      if (row.employeeId) {
        ids.add(Number(row.employeeId));
        return;
      }
      const matched = trainerNameMap.get(normalizeText(row.employeeName));
      if (matched?.id) ids.add(matched.id);
    });
    return ids;
  }, [importRows, trainerNameMap]);
  const weekShiftCount = useMemo(
    () =>
      (weeklyRows || []).reduce(
        (total, row) =>
          total + row.cells.reduce((sum, cell, index) => sum + shiftsFromCell(cell, scheduleDays[index]?.workDate).shifts.length, 0),
        0,
      ),
    [scheduleDays, weeklyRows],
  );
  const reportSummary = shiftReport.data?.summary || { employees: 0, shifts: 0, onTime: 0, late: 0, earlyCheckout: 0, absent: 0, missingCheckout: 0, upcoming: 0, pendingReview: 0, attendanceRate: 0, onTimeRate: 0 };
  const reportMatrixDays = useMemo(() => {
    if (!shiftReport.data?.dateFrom || !shiftReport.data?.dateTo) return [];
    const days = [];
    for (let cursor = shiftReport.data.dateFrom; cursor <= shiftReport.data.dateTo && days.length < 7; cursor = addDays(cursor, 1)) days.push(cursor);
    return days;
  }, [shiftReport.data?.dateFrom, shiftReport.data?.dateTo]);
  const reportMatrixEmployees = useMemo(() => {
    const searchValue = normalizeText(reportQ);
    return (shiftReport.data?.items || []).reduce((employees, employee) => {
      if (reportTitle !== "all" && employee.title !== reportTitle) return employees;
      if (searchValue && !normalizeText(`${employee.employeeName} ${employee.employeeCode}`).includes(searchValue)) return employees;
      const days = employee.days.map((day) => ({
        ...day,
        shifts: day.shifts.filter((shift) => {
          if (reportShiftKind === "all") return true;
          const hour = Number(shift.startTime?.split(":", 1)[0]);
          const kind = hour < 12 ? "morning" : hour < 18 ? "afternoon" : "night";
          return kind === reportShiftKind;
        }),
      }));
      if (!days.some((day) => day.shifts.length)) return employees;
      employees.push({ ...employee, days });
      return employees;
    }, []);
  }, [reportQ, reportShiftKind, reportTitle, shiftReport.data?.items]);
  useEffect(() => {
    if (!reportDetail) {
      setAttendanceEventForm({ checkinEventId: "", checkoutEventId: "" });
      return;
    }
    const options = shiftEventOptions(reportDetail);
    const sessionEvents = reportDetail.events || [];
    const checkinEvent =
      options.find((event) => sameMinute(event.eventTime, reportDetail.checkedInAt)) ||
      sessionEvents[0];
    const checkoutEvent =
      options.find((event) => sameMinute(event.eventTime, reportDetail.checkedOutAt)) ||
      (sessionEvents.length > 1 ? sessionEvents[sessionEvents.length - 1] : null);
    setAttendanceEventForm({
      checkinEventId: checkinEvent?.id ? String(checkinEvent.id) : "",
      checkoutEventId: checkoutEvent?.id ? String(checkoutEvent.id) : "",
    });
  }, [reportDetail]);
  useEffect(() => {
    if (!scheduleOpen || allTrainers.isLoading || weeklyShifts.isLoading) return;
    const shiftsByEmployeeDay = new Map();
    (weeklyShifts.data?.items || []).forEach((shift) => {
      const key = `${shift.employeeId}:${shift.workDate}`;
      if (!shiftsByEmployeeDay.has(key)) shiftsByEmployeeDay.set(key, []);
      shiftsByEmployeeDay.get(key).push(shift);
    });
    const rows = (allTrainers.data?.items || []).map((trainer) => ({
      id: trainer.id,
      employeeId: trainer.id,
      employeeName: trainer.name,
      title: trainer.title || "",
      cells: scheduleDays.map((day) => shiftCellText(shiftsByEmployeeDay.get(`${trainer.id}:${day.workDate}`))),
    }));
    setWeeklyRows(rows);
    setWeeklyGridVisible((weeklyShifts.data?.items || []).length > 0);
    setWeeklyDirty(false);
    setWeeklyError("");
  }, [scheduleOpen, scheduleWeekStart, allTrainers.data?.items, allTrainers.isLoading, weeklyShifts.data?.items, weeklyShifts.isLoading, scheduleDays]);
  const edit = (row) => {
    setSelected(row);
    setError("");
    setOpen(true);
  };
  const save = useMutation({
    mutationFn: (payload) =>
      api(selected ? `/api/trainers/${selected.id}` : "/api/trainers", {
        method: selected ? "PATCH" : "POST",
        body: {
          ...payload,
          name: payload.name.trim(),
          phone: normalizePhone(payload.phone),
          email: payload.email.trim(),
          title: normalizeJobTitle(payload.title) || "Coach",
        },
      }),
    onSuccess: (data) => {
      client.invalidateQueries({ queryKey: ["trainers"] });
      client.invalidateQueries({ queryKey: ["member-options"] });
      setOpen(false);
      setSelected(null);
      notify.success(
        selected
          ? `Đã lưu hồ sơ ${data.name || selected.name}.`
          : `Đã thêm nhân viên ${data.name}.`,
      );
    },
    onError: (e) => setError(e.message),
  });
  const remove = useMutation({
    mutationFn: (row) => api(`/api/trainers/${row.id}`, { method: "DELETE" }),
    onSuccess: (data) => {
      client.invalidateQueries({ queryKey: ["trainers"] });
      client.invalidateQueries({ queryKey: ["member-options"] });
      setConfirm(null);
      notify.success(
        data.archived
          ? `Đã ẩn ${confirm.name} vì nhân viên có lịch sử liên quan.`
          : `Đã xóa nhân viên ${confirm.name}.`,
      );
    },
    onError: (e) =>
      notify.errorFrom(e, "Không thể xóa nhân viên. Vui lòng thử lại."),
  });
  const saveShift = useMutation({
    mutationFn: (payload) =>
      editingShift
        ? api(`/api/trainer-shifts/${editingShift.id}`, { method: "PATCH", body: payload })
        : api(`/api/trainers/${scheduleTarget.id}/shifts`, { method: "POST", body: payload }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["trainer-shifts"] });
      client.invalidateQueries({ queryKey: ["checkins"] });
      setShiftError("");
      setEditingShift(null);
      setShiftForm((current) => ({ ...blankShift, workDate: current.workDate }));
      notify.success("Đã lưu ca làm nhân viên.");
    },
    onError: (error) => setShiftError(error.message),
  });
  const removeShift = useMutation({
    mutationFn: (row) => api(`/api/trainer-shifts/${row.id}`, { method: "DELETE" }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["trainer-shifts"] });
      client.invalidateQueries({ queryKey: ["checkins"] });
      notify.success("Đã xóa ca làm.");
    },
    onError: (error) => notify.errorFrom(error, "Không thể xóa ca làm."),
  });
  const saveBulkShifts = useMutation({
    mutationFn: (payload) =>
      api(`/api/trainers/${scheduleTarget.id}/shifts/bulk`, {
        method: "POST",
        body: payload,
      }),
    onSuccess: (data) => {
      client.invalidateQueries({ queryKey: ["trainer-shifts"] });
      client.invalidateQueries({ queryKey: ["checkins"] });
      const skipped = data.skipped?.length || 0;
      notify.success(
        skipped
          ? `Đã tạo ${data.created} ca, bỏ qua ${skipped} ca bị trùng.`
          : `Đã tạo ${data.created} ca làm.`,
      );
    },
    onError: (error) => setShiftError(error.message),
  });
  const importShifts = useMutation({
    mutationFn: (payload) =>
      api("/api/trainer-shifts/import", { method: "POST", body: payload }),
    onSuccess: (data) => {
      client.invalidateQueries({ queryKey: ["trainer-shifts"] });
      client.invalidateQueries({ queryKey: ["checkins"] });
      client.invalidateQueries({ queryKey: ["trainers"] });
      weeklyShifts.refetch();
      setWeeklyGridVisible(true);
      setImportOpen(false);
      setImportRows([]);
      setImportDays([]);
      notify.success(`Đã nhập ${data.created} ca từ Excel.`);
    },
    onError: (error) => setImportError(error.message),
  });
  const saveWeeklySchedule = useMutation({
    mutationFn: (payload) =>
      api("/api/trainer-shifts/week", {
        method: "PUT",
        body: payload,
      }),
    onSuccess: (data) => {
      client.invalidateQueries({ queryKey: ["trainer-shifts"] });
      client.invalidateQueries({ queryKey: ["checkins"] });
      setWeeklyError("");
      setWeeklyDirty(false);
      notify.success(`Đã lưu lịch tuần: ${data.created} ca.`);
    },
    onError: (error) => setWeeklyError(error.message),
  });
  const approveShiftOverride = useMutation({
    mutationFn: ({ shiftId, payload }) =>
      api(`/api/trainer-shifts/${shiftId}/override`, {
        method: "POST",
        body: payload,
      }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["trainer-shift-report"] });
      setOverrideTarget(null);
      setOverrideError("");
      shiftReport.refetch();
      notify.success("Đã duyệt đổi ca.");
    },
    onError: (error) => setOverrideError(error.message),
  });
  const saveShiftAttendanceEvents = useMutation({
    mutationFn: ({ shiftId, payload }) =>
      api(`/api/trainer-shifts/${shiftId}/attendance-events`, {
        method: "PATCH",
        body: payload,
      }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["trainer-shift-report"] });
      client.invalidateQueries({ queryKey: ["checkins"] });
      shiftReport.refetch();
      notify.success("Đã cập nhật giờ chấm công từ webhook.");
    },
    onError: (error) => notify.errorFrom(error, "Không thể cập nhật giờ chấm công."),
  });
  const exportCurrentReport = useMutation({
    mutationFn: () => api(`/api/trainers/shift-report?${queryString({
      rangeType: reportRange,
      day: reportDate,
      weekStart: reportWeekStart,
      q: reportQ,
      title: reportTitle,
      status: reportView === "matrix" ? "all" : reportStatus,
      shiftKind: reportShiftKind,
      sort: reportSort,
      page: 1,
      pageSize: 1000,
    })}`),
    onSuccess: (data) => notify.success(`Đã tải ${downloadAttendanceCsv(data)} dòng theo bộ lọc hiện tại.`),
    onError: (error) => notify.errorFrom(error, "Không thể xuất report ca."),
  });
  const updateImportCell = (rowIndex, cellIndex, value) => {
    setImportRows((rows) =>
      rows.map((row, index) =>
        index === rowIndex
          ? { ...row, cells: row.cells.map((cell, nextIndex) => (nextIndex === cellIndex ? value : cell)) }
          : row,
      ),
    );
  };
  const updateWeeklyCell = (rowIndex, cellIndex, value) => {
    setWeeklyDirty(true);
    setWeeklyRows((rows) =>
      rows.map((row, index) =>
        index === rowIndex
          ? { ...row, cells: row.cells.map((cell, nextIndex) => (nextIndex === cellIndex ? value : cell)) }
          : row,
      ),
    );
  };
  const buildWeeklyPayload = () => {
    const rows = [];
    const errors = [];
    weeklyRows.forEach((row, rowIndex) => {
      const shifts = [];
      row.cells.forEach((cell, cellIndex) => {
        const day = scheduleDays[cellIndex];
        const parsed = shiftsFromCell(cell, day?.workDate);
        parsed.errors.forEach((error) => errors.push(`${row.employeeName || `Dòng ${rowIndex + 1}`} · ${day?.label}: ${error}`));
        shifts.push(...parsed.shifts);
      });
      rows.push({
        employeeId: row.employeeId,
        employeeName: row.employeeName,
        shifts,
      });
    });
    return { rows, errors };
  };
  const submitWeeklySchedule = () => {
    const { rows, errors } = buildWeeklyPayload();
    if (errors.length) {
      setWeeklyError(errors.slice(0, 3).join(" · "));
      return;
    }
    setWeeklyError("");
    saveWeeklySchedule.mutate({ weekStart: scheduleWeekStart, rows });
  };
  const buildImportPayload = () => {
    const rows = [];
    const errors = [];
    importRows.forEach((row, rowIndex) => {
      const shifts = [];
      row.cells.forEach((cell, cellIndex) => {
        const day = importDays[cellIndex];
        const parsed = shiftsFromCell(cell, day?.workDate);
        parsed.errors.forEach((error) => errors.push(`${row.employeeName || `Dòng ${rowIndex + 1}`} · ${day?.label}: ${error}`));
        shifts.push(...parsed.shifts);
      });
      if (shifts.length) {
        const matched = trainerNameMap.get(normalizeText(row.employeeName));
        rows.push({
          employeeId: row.employeeId || matched?.id || null,
          employeeName: row.employeeName,
          position: row.position,
          shifts,
        });
      }
    });
    return { rows, errors };
  };
  const submitImport = () => {
    const { rows, errors } = buildImportPayload();
    if (errors.length) {
      setImportError(errors.slice(0, 3).join(" · "));
      return;
    }
    const unresolved = rows.filter((row) => !row.employeeId);
    if (unresolved.length) {
      setImportError(`Còn ${unresolved.length} dòng chưa chọn nhân viên.`);
      return;
    }
    if (!rows.length) {
      setImportError("Không có ca hợp lệ để nhập.");
      return;
    }
    setImportError("");
    importShifts.mutate({ sourceName: importFileName, rows });
  };
  const readImportFile = async (file) => {
    if (!file) return;
    try {
      const formData = new FormData();
      formData.set("file", file);
      const parsed = await api("/api/trainer-shifts/import-preview", {
        method: "POST",
        body: formData,
      });
      setImportFileName(parsed.sourceName || file.name);
      setImportDays(scheduleDays);
      setImportRows(parsed.rows);
      setImportError("");
      setImportOpen(true);
    } catch (error) {
      notify.error(error.message || "Không thể đọc file Excel.");
    } finally {
      if (importInputRef.current) importInputRef.current.value = "";
    }
  };
  const setEmployeeScheduleWeek = (weekStart) => {
    const nextWeek = startOfWeek(weekStart || isoDay());
    setBulkShiftForm((current) => ({ ...current, weekStart: nextWeek }));
    setShiftForm((current) => ({ ...current, workDate: nextWeek }));
  };
  const openShiftOverride = (employee, day, shift) => {
    setOverrideTarget({ employee, day, shift });
    setOverrideError("");
    setOverrideForm({
      workDate: day.workDate,
      startTime: shift.checkedInAt ? timeOnly(shift.checkedInAt) : shift.startTime,
      endTime: shift.checkedOutAt ? timeOnly(shift.checkedOutAt) : shift.endTime,
      reason: shift.overrideReason || "Đổi ca thực tế",
    });
  };
  const columns = [
    {
      key: "trainer",
      label: "Nhân viên",
      sortValue: (r) => r.name,
      render: (r) => (
        <button
          className="member-cell text-left"
          onClick={(e) => {
            e.stopPropagation();
            edit(r);
          }}
        >
          <div className="avatar avatar-md">{initials(r.name)}</div>
          <div>
            <span className="cell-primary hover:text-blue-700">{r.name}</span>
            <div className="cell-secondary">{r.code}</div>
          </div>
        </button>
      ),
    },
    {
      key: "phone",
      label: "Điện thoại",
      sortValue: (r) => r.phone,
      render: (r) => formatPhone(r.phone) || "—",
    },
    {
      key: "title",
      label: "Chức vụ",
      sortValue: (r) => r.title || "",
      render: (r) => r.title || "—",
    },
    {
      key: "registeredPtClients",
      label: "Khách đăng ký",
      className: "text-right",
      sortValue: (r) => r.registeredPtClients ?? -1,
      render: (r) =>
        r.isPtRole ? (
          <Link
            to={`/members?trainerId=${r.id}`}
            className="font-medium text-blue-700 hover:underline"
            onClick={(e) => e.stopPropagation()}
          >
            {r.registeredPtClients}
          </Link>
        ) : "—",
    },
    {
      key: "activePtClients",
      label: "Đang hoạt động",
      className: "text-right",
      sortValue: (r) => r.activePtClients ?? -1,
      render: (r) => (r.isPtRole ? r.activePtClients : "—"),
    },
    {
      key: "expiredPtClients",
      label: "Hết hạn",
      className: "text-right",
      sortValue: (r) => r.expiredPtClients ?? -1,
      render: (r) => (r.isPtRole ? r.expiredPtClients : "—"),
    },
    {
      key: "actions",
      label: "",
      sortable: false,
      render: (r) => (
        <div className="flex justify-end gap-1">
          <Button
            size="sm"
            variant="ghost"
            onClick={(e) => {
              e.stopPropagation();
              edit(r);
            }}
          >
            <Pencil size={13} />
            Sửa
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={(e) => {
              e.stopPropagation();
              setIdentityTarget(r);
            }}
          >
            <Link2 size={13} />
            {r.dahIdentity ? "Đổi DAH" : "Liên kết DAH"}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={(e) => {
              e.stopPropagation();
              setScheduleTarget(r);
              setEditingShift(null);
              setShiftForm(blankShift);
              setBulkShiftForm(blankBulkShift);
              setShiftError("");
            }}
          >
            <CalendarDays size={13} />
            Lịch ca
          </Button>
          <RowMenu>
            <button className="danger" onClick={() => setConfirm(r)}>
              Xóa nhân viên
            </button>
          </RowMenu>
        </div>
      ),
    },
  ];
  return (
    <>
      <PageHeader
        eyebrow="Quản lý"
        title="Nhân viên"
        description="Click nhân viên để chỉnh sửa; chỉ chức vụ PT hiển thị thống kê khách đăng ký."
        action={
          <div className="flex flex-wrap justify-end gap-2">
            <input
              ref={importInputRef}
              type="file"
              accept=".xlsx"
              className="hidden"
              onChange={(event) => readImportFile(event.target.files?.[0])}
            />
            <Button
              variant="secondary"
              onClick={() => {
                setScheduleWeekStart(startOfWeek());
                setScheduleOpen(true);
              }}
            >
              <CalendarDays size={16} />
              Lịch ca
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setReportRange("today");
                setReportDate(isoDay());
                setReportWeekStart(startOfWeek());
                setReportView("exceptions");
                setReportStatus("anomaly");
                setReportSearch("");
                setReportTitle("all");
                setReportShiftKind("all");
                setReportSort("severity");
                setReportPage(1);
                setReportDetail(null);
                setReportOpen(true);
              }}
            >
              <ClipboardList size={16} />
              Report ca
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setReportRange("today");
                setReportDate(isoDay());
                setReportWeekStart(startOfWeek());
                setReportView("all");
                setReportStatus("all");
                setReportSearch("");
                setReportTitle("all");
                setReportShiftKind("all");
                setReportSort("severity");
                setReportPage(1);
                setReportDetail(null);
                setReportOpen(true);
              }}
            >
              <Download size={16} />
              Tải chấm công
            </Button>
            <Button onClick={() => edit(null)}>
              <Plus size={16} />
              Thêm nhân viên
            </Button>
          </div>
        }
      />
      <div className="toolbar">
        <SearchInput
          value={search}
          onChange={(value) => {
            setSearch(value);
            setPage(1);
          }}
          placeholder="Tên, điện thoại, mã nhân viên, chức vụ…"
        />
        <Select
          className="input w-48"
          value={titleFilter}
          onChange={(event) => {
            setTitleFilter(event.target.value);
            setPage(1);
          }}
        >
          <option value="all">Mọi chức vụ</option>
          {jobTitles.map((title) => (
            <option key={title} value={title}>
              {title}
            </option>
          ))}
        </Select>
      </div>
      <DataTable
        columns={columns}
        rows={query.data?.items}
        loading={query.isLoading}
        error={query.error}
        onRetry={query.refetch}
        onRowClick={edit}
      />
      <Pagination
        data={query.data?.pagination}
        onPage={setPage}
        pageSize={pageSize}
        onPageSize={(value) => {
          setPageSize(value);
          setPage(1);
        }}
      />
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        dirty={
          JSON.stringify(form) !==
          JSON.stringify(
            selected
              ? {
                  name: selected.name,
                  phone: selected.phone || "",
                  email: selected.email || "",
                  title: selected.title || "",
                }
              : blank,
          )
        }
        title={selected ? "Chỉnh sửa nhân viên" : "Thêm nhân viên"}
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (form.phone && normalizePhone(form.phone).length !== 10) {
              setError("Số điện thoại cần đủ 10 chữ số.");
              return;
            }
            save.mutate(form);
          }}
        >
          <div className="modal-body">
            <div className="form-grid">
              <Field className="form-span" label="Họ tên" required>
                <Input
                  autoFocus
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                />
              </Field>
              <Field label="Điện thoại">
                <PhoneInput
                  value={form.phone}
                  onChange={(phone) => setForm({ ...form, phone })}
                />
              </Field>
              <Field label="Email">
                <Input
                  type="email"
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                />
              </Field>
              <div className="field form-span">
                <span className="field-label">Chức vụ</span>
                <Select
                  value={form.title || "Coach"}
                  onChange={(event) =>
                    setForm({ ...form, title: event.target.value })
                  }
                >
                  {jobTitles.map((title) => (
                    <option key={title} value={title}>
                      {title}
                    </option>
                  ))}
                </Select>
                <span className="field-hint">
                  Thêm chức vụ mới và đánh dấu chức vụ PT tại Cài đặt.
                </span>
              </div>
            </div>
            {error && <div className="inline-error mt-4">{error}</div>}
          </div>
          <div className="form-actions">
            <Button
              data-modal-close
              variant="secondary"
              onClick={() => setOpen(false)}
            >
              Hủy
            </Button>
            <Button
              type="submit"
              loading={save.isPending}
              loadingText="Đang lưu…"
            >
              Lưu nhân viên
            </Button>
          </div>
        </form>
      </Modal>
      <Modal
        open={scheduleOpen}
        onClose={() => setScheduleOpen(false)}
        size="xl"
        dirty={weeklyDirty}
        title="Lịch ca"
        description={`Tuần ${scheduleWeekStart} đến ${scheduleWeekEnd}`}
      >
        <div className="modal-body">
          <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2">
              <Button
                size="sm"
                variant="secondary"
                onClick={() => setScheduleWeekStart((current) => addDays(current, -7))}
              >
                <ChevronLeft size={14} />
                Tuần trước
              </Button>
              <Field label="Tuần">
                <DateInput
                  value={scheduleWeekStart}
                  onChange={(value) => setScheduleWeekStart(startOfWeek(value || isoDay()))}
                />
              </Field>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => setScheduleWeekStart((current) => addDays(current, 7))}
              >
                Tuần sau
                <ChevronRight size={14} />
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setScheduleWeekStart(startOfWeek())}
              >
                Tuần này
              </Button>
            </div>
            <div className="flex flex-wrap justify-end gap-2">
              <Button
                variant="secondary"
                onClick={() => importInputRef.current?.click()}
              >
                <FileSpreadsheet size={16} />
                Nhập Excel
              </Button>
              {weeklyGridVisible && (
                <Button
                  onClick={submitWeeklySchedule}
                  loading={saveWeeklySchedule.isPending}
                  loadingText="Đang lưu..."
                  disabled={weeklyShifts.isLoading || allTrainers.isLoading}
                >
                  <Save size={16} />
                  Lưu lịch tuần
                </Button>
              )}
            </div>
          </div>
          {weeklyError && <div className="inline-error mb-4">{weeklyError}</div>}
          <div className="mb-3 grid grid-cols-3 gap-3 max-[780px]:grid-cols-1">
            <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">
              <span className="text-xs font-medium text-slate-500">Nhân viên</span>
              <strong className="mt-1 block text-xl text-slate-950">{weeklyRows.length}</strong>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">
              <span className="text-xs font-medium text-slate-500">Ca trong tuần</span>
              <strong className="mt-1 block text-xl text-emerald-700">{weekShiftCount}</strong>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">
              <span className="text-xs font-medium text-slate-500">Khoảng ngày</span>
              <strong className="mt-1 block text-sm text-slate-950">
                {scheduleWeekStart} - {scheduleWeekEnd}
              </strong>
            </div>
          </div>
          {weeklyShifts.isLoading || allTrainers.isLoading ? (
            <div className="rounded-lg border border-slate-200 bg-white px-4 py-10 text-center text-sm text-slate-500">
              Đang tải lịch tuần...
            </div>
          ) : !weeklyGridVisible ? (
            <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-4 py-10 text-center">
              <div className="text-sm font-semibold text-slate-950">Chưa cài đặt nào</div>
              <div className="mt-1 text-xs text-slate-500">
                Tuần này chưa có ca làm. Bạn có thể nhập Excel hoặc mở bảng trống để nhập tay.
              </div>
              <div className="mt-4 flex justify-center gap-2">
                <Button variant="secondary" onClick={() => setWeeklyGridVisible(true)}>
                  <Pencil size={14} />
                  Mở bảng trống
                </Button>
                <Button onClick={() => importInputRef.current?.click()}>
                  <FileSpreadsheet size={16} />
                  Nhập Excel
                </Button>
              </div>
            </div>
          ) : (
            <div className="overflow-auto rounded-lg border border-slate-200 bg-white">
              <table className="min-w-[1080px] w-full border-collapse text-[12px]">
                <thead>
                  <tr className="bg-slate-100 text-slate-700">
                    <th className="sticky left-0 z-20 w-64 border border-slate-200 bg-slate-100 px-2 py-2 text-left font-semibold">
                      Họ và tên
                    </th>
                    {scheduleDays.map((day) => (
                      <th key={day.workDate} className="w-32 border border-slate-200 px-2 py-2 text-center font-semibold">
                        <span className="block">{day.label}</span>
                        <span className="text-[11px] font-medium text-slate-500">{day.workDate.slice(8, 10)}</span>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {weeklyRows.map((row, rowIndex) => (
                    <tr key={row.employeeId} className="bg-white">
                      <td className="sticky left-0 z-10 border border-slate-200 bg-inherit px-2 py-2 align-top">
                        <div className="text-sm font-semibold leading-snug text-slate-950">{row.employeeName}</div>
                        <div className="mt-0.5 text-[11px] font-medium text-slate-500">{row.title || "Chưa có chức vụ"}</div>
                      </td>
                      {row.cells.map((cell, cellIndex) => {
                        const parsed = shiftsFromCell(cell, scheduleDays[cellIndex]?.workDate);
                        const hasError = parsed.errors.length > 0;
                        const isOff = ["OFF", "P"].includes(String(cell || "").trim().toUpperCase());
                        return (
                          <td
                            key={`${row.employeeId}-${cellIndex}`}
                            className={`border border-slate-200 p-1 align-top ${hasError ? "bg-red-50" : isOff ? "bg-red-100" : ""}`}
                          >
                            <textarea
                              className="min-h-[62px] w-full resize-y rounded border border-slate-200 bg-white px-2 py-1 text-center text-[12px] font-medium text-slate-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/10"
                              value={cell}
                              onChange={(event) => updateWeeklyCell(rowIndex, cellIndex, event.target.value)}
                            />
                            {hasError && <span className="mt-1 block text-[10px] text-red-700">{parsed.errors[0]}</span>}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Modal>
      <Modal
        open={importOpen}
        onClose={() => setImportOpen(false)}
        size="xl"
        dirty={importRows.length > 0}
        title={`Nhập Excel vào tuần ${scheduleWeekStart}`}
        description={`${importFileName || "File Excel"} · ${scheduleWeekStart} đến ${scheduleWeekEnd}`}
      >
        <div className="modal-body">
          <div className="mb-4 grid grid-cols-5 gap-3 max-[1100px]:grid-cols-3 max-[760px]:grid-cols-2 max-[520px]:grid-cols-1">
            <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">
              <span className="text-xs font-medium text-slate-500">Dòng nhân viên</span>
              <strong className="mt-1 block text-xl text-slate-950">{importSummary.rows}</strong>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">
              <span className="text-xs font-medium text-slate-500">Ca hợp lệ</span>
              <strong className="mt-1 block text-xl text-emerald-700">{importSummary.shifts}</strong>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">
              <span className="text-xs font-medium text-slate-500">Chưa khớp tên</span>
              <strong className="mt-1 block text-xl text-amber-700">{importSummary.unmatched}</strong>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">
              <span className="text-xs font-medium text-slate-500">Ô lỗi format</span>
              <strong className="mt-1 block text-xl text-red-700">{importSummary.errors}</strong>
            </div>
          </div>
          {importError && <div className="inline-error mb-4">{importError}</div>}
          <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
            <div className="text-xs text-slate-500">
              OFF, P và ô trống sẽ không tạo ca. Mỗi dòng trong ô là một ca, ví dụ 5H-12H hoặc 17H30-20H30.
            </div>
            <Button
              size="sm"
              variant="secondary"
              onClick={() =>
                setImportRows((rows) => [
                  ...rows,
                  {
                    id: `manual-${Date.now()}`,
                    employeeName: "",
                    position: "",
                    cells: importDays.map(() => ""),
                  },
                ])
              }
            >
              <Plus size={13} />
              Thêm dòng
            </Button>
          </div>
          <div className="overflow-auto rounded-lg border border-slate-200 bg-white">
            <table className="min-w-[1080px] w-full border-collapse text-[12px]">
              <thead>
                <tr className="bg-slate-100 text-slate-700">
                  <th className="sticky left-0 z-20 w-56 border border-slate-200 bg-slate-100 px-2 py-2 text-left font-semibold">
                    Họ và tên
                  </th>
                  {importDays.map((day) => (
                    <th key={day.workDate} className="w-32 border border-slate-200 px-2 py-2 text-center font-semibold">
                      <span className="block">{day.label}</span>
                      <span className="text-[11px] font-medium text-slate-500">{day.workDate.slice(8, 10)}</span>
                    </th>
                  ))}
                  <th className="w-14 border border-slate-200 px-2 py-2" />
                </tr>
              </thead>
              <tbody>
                {importRows.map((row, rowIndex) => {
                  const matched = row.employeeId
                    ? (allTrainers.data?.items || []).find((trainer) => trainer.id === Number(row.employeeId))
                    : trainerNameMap.get(normalizeText(row.employeeName));
                  const autoMatched = !row.employeeId && matched;
                  const selectableTrainers = (allTrainers.data?.items || []).filter((trainer) => {
                    if (row.employeeId && trainer.id === Number(row.employeeId)) return true;
                    return !lockedImportEmployeeIds.has(trainer.id);
                  });
                  return (
                    <tr key={row.id || rowIndex} className={matched ? "bg-white" : "bg-amber-50/60"}>
                      <td className="sticky left-0 z-10 border border-slate-200 bg-inherit p-1 align-top">
                        {autoMatched ? (
                          <div className="rounded-md border border-emerald-200 bg-emerald-50 px-2 py-1.5">
                            <div className="text-sm font-semibold leading-snug text-slate-950">{matched.name}</div>
                            <div className="mt-0.5 text-[11px] font-medium text-slate-500">
                              {matched.title || row.position || "Chưa có chức vụ"}
                            </div>
                            <div className="mt-1 text-[10px] font-medium text-emerald-700">Khớp {matched.code}</div>
                          </div>
                        ) : (
                          <>
                            <div className="rounded-md border border-amber-200 bg-amber-50 px-2 py-1.5">
                              <div className="text-sm font-semibold leading-snug text-slate-950">
                                {row.employeeName || "Chưa có tên"}
                              </div>
                              <div className="mt-0.5 text-[11px] font-medium text-slate-500">
                                {row.position || "Chưa có chức vụ"}
                              </div>
                            </div>
                            <Select
                              className="input mt-1 h-8 text-[12px]"
                              value={row.employeeId || ""}
                              onChange={(event) =>
                                setImportRows((rows) =>
                                  rows.map((item, index) =>
                                    index === rowIndex
                                      ? { ...item, employeeId: event.target.value ? Number(event.target.value) : null }
                                      : item,
                                  ),
                                )
                              }
                            >
                              <option value="">Chọn nhân viên...</option>
                              {selectableTrainers.map((trainer) => (
                                <option key={trainer.id} value={trainer.id}>
                                  {trainer.name} - {trainer.title || "Chưa có chức vụ"}
                                </option>
                              ))}
                            </Select>
                            {matched && <span className="mt-1 block text-[10px] text-blue-700">Đã chọn {matched.code}</span>}
                          </>
                        )}
                      </td>
                      {row.cells.map((cell, cellIndex) => {
                        const parsed = shiftsFromCell(cell, importDays[cellIndex]?.workDate);
                        const hasError = parsed.errors.length > 0;
                        const isOff = ["OFF", "P"].includes(String(cell || "").trim().toUpperCase());
                        return (
                          <td
                            key={`${row.id}-${cellIndex}`}
                            className={`border border-slate-200 p-1 align-top ${hasError ? "bg-red-50" : isOff ? "bg-red-100" : ""}`}
                          >
                            <textarea
                              className="min-h-[58px] w-full resize-y rounded border border-slate-200 bg-white px-2 py-1 text-center text-[12px] font-medium text-slate-900 outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-500/10"
                              value={cell}
                              onChange={(event) => updateImportCell(rowIndex, cellIndex, event.target.value)}
                            />
                            {hasError && <span className="mt-1 block text-[10px] text-red-700">{parsed.errors[0]}</span>}
                          </td>
                        );
                      })}
                      <td className="border border-slate-200 p-1 align-top text-center">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setImportRows((rows) => rows.filter((_, index) => index !== rowIndex))}
                        >
                          <Trash2 size={13} />
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
        <div className="form-actions">
          <Button variant="secondary" onClick={() => setImportOpen(false)}>
            Hủy
          </Button>
          <Button
            onClick={submitImport}
            loading={importShifts.isPending}
            loadingText="Đang nhập..."
            disabled={!importRows.length || importSummary.errors > 0}
          >
            <FileSpreadsheet size={16} />
            Nhập lịch đã duyệt
          </Button>
        </div>
      </Modal>
      <Modal
        open={!!scheduleTarget}
        onClose={() => setScheduleTarget(null)}
        title={`Lịch ca · ${scheduleTarget?.name || ""}`}
        description="Thiết lập ca theo ngày; DAH sẽ gom nhiều lần quét thành một phiên vào/ra theo ca."
      >
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (!shiftForm.workDate || !shiftForm.startTime || !shiftForm.endTime) {
              setShiftError("Ngày làm, giờ bắt đầu và giờ kết thúc là bắt buộc.");
              return;
            }
            saveShift.mutate(shiftForm);
          }}
        >
          <div className="modal-body space-y-5">
            <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3">
              <div>
                <div className="text-sm font-semibold text-slate-950">Tuần làm việc</div>
                <div className="mt-0.5 text-xs text-slate-500">
                  {shiftRangeStart} đến {shiftRangeEnd}
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  onClick={() => setEmployeeScheduleWeek(addDays(shiftRangeStart, -7))}
                >
                  <ChevronLeft size={14} />
                  Tuần trước
                </Button>
                <DateInput
                  value={shiftRangeStart}
                  onChange={(value) => setEmployeeScheduleWeek(value || isoDay())}
                />
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  onClick={() => setEmployeeScheduleWeek(addDays(shiftRangeStart, 7))}
                >
                  Tuần sau
                  <ChevronRight size={14} />
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => setEmployeeScheduleWeek(startOfWeek())}
                >
                  Tuần này
                </Button>
              </div>
            </div>
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold text-slate-950">Tạo nhanh tuần</h3>
                  <p className="mt-0.5 text-xs text-slate-500">
                    Chọn tuần, ngày làm và một khung giờ để tạo nhiều ca cùng lúc.
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => setBulkShiftForm({ ...bulkShiftForm, weekdays: [0, 1, 2, 3, 4, 5, 6] })}
                  >
                    Cả tuần
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => setBulkShiftForm({ ...bulkShiftForm, weekdays: [0, 1, 2, 3, 4] })}
                  >
                    T2-T6
                  </Button>
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => setBulkShiftForm({ ...bulkShiftForm, weekdays: [5, 6] })}
                  >
                    T7-CN
                  </Button>
                </div>
              </div>
              <div className="form-grid">
                <Field label="Tuần bắt đầu">
                  <DateInput
                    value={bulkShiftForm.weekStart}
                    onChange={(value) => {
                      const nextWeek = startOfWeek(value || isoDay());
                      setBulkShiftForm({ ...bulkShiftForm, weekStart: nextWeek });
                      setShiftForm((current) => ({ ...current, workDate: nextWeek }));
                    }}
                  />
                </Field>
                <Field label="Bắt đầu">
                  <Input
                    type="time"
                    value={bulkShiftForm.startTime}
                    onChange={(event) => setBulkShiftForm({ ...bulkShiftForm, startTime: event.target.value })}
                  />
                </Field>
                <Field label="Kết thúc">
                  <Input
                    type="time"
                    value={bulkShiftForm.endTime}
                    onChange={(event) => setBulkShiftForm({ ...bulkShiftForm, endTime: event.target.value })}
                  />
                </Field>
                <Field className="form-span" label="Ghi chú">
                  <Input
                    value={bulkShiftForm.note}
                    onChange={(event) => setBulkShiftForm({ ...bulkShiftForm, note: event.target.value })}
                    placeholder="Ví dụ: Ca tuần, ca sáng..."
                  />
                </Field>
              </div>
              <div className="mt-3 grid grid-cols-7 gap-2 max-[720px]:grid-cols-4">
                {weekDays.map((label, index) => {
                  const selectedDay = bulkShiftForm.weekdays.includes(index);
                  return (
                    <button
                      key={label}
                      type="button"
                      className={`rounded-md border px-2 py-2 text-xs font-semibold transition ${
                        selectedDay
                          ? "border-blue-600 bg-blue-600 text-white"
                          : "border-slate-200 bg-white text-slate-600 hover:border-blue-300"
                      }`}
                      onClick={() => {
                        const weekdays = selectedDay
                          ? bulkShiftForm.weekdays.filter((day) => day !== index)
                          : [...bulkShiftForm.weekdays, index].sort((a, b) => a - b);
                        setBulkShiftForm({ ...bulkShiftForm, weekdays });
                      }}
                    >
                      {label}
                    </button>
                  );
                })}
              </div>
              <div className="mt-4 flex justify-end">
                <Button
                  type="button"
                  loading={saveBulkShifts.isPending}
                  loadingText="Đang tạo..."
                  disabled={!bulkShiftForm.weekdays.length}
                  onClick={() => {
                    setShiftError("");
                    saveBulkShifts.mutate(bulkShiftForm);
                  }}
                >
                  <CalendarDays size={15} />
                  Tạo các ca đã chọn
                </Button>
              </div>
            </div>
            <div className="form-grid">
              <Field label="Ngày làm">
                <DateInput
                  value={shiftForm.workDate}
                  onChange={(value) => setShiftForm({ ...shiftForm, workDate: value || isoDay() })}
                />
              </Field>
              <Field label="Bắt đầu">
                <Input
                  type="time"
                  value={shiftForm.startTime}
                  onChange={(event) => setShiftForm({ ...shiftForm, startTime: event.target.value })}
                />
              </Field>
              <Field label="Kết thúc">
                <Input
                  type="time"
                  value={shiftForm.endTime}
                  onChange={(event) => setShiftForm({ ...shiftForm, endTime: event.target.value })}
                />
              </Field>
              <Field className="form-span" label="Ghi chú">
                <Input
                  value={shiftForm.note}
                  onChange={(event) => setShiftForm({ ...shiftForm, note: event.target.value })}
                  placeholder="Ví dụ: Ca sáng, trực lễ tân..."
                />
              </Field>
            </div>
            {shiftError && <div className="inline-error">{shiftError}</div>}
            <div className="flex flex-wrap justify-end gap-2">
              {editingShift && (
                <Button
                  variant="secondary"
                  onClick={() => {
                    setEditingShift(null);
                    setShiftForm((current) => ({ ...blankShift, workDate: current.workDate }));
                    setShiftError("");
                  }}
                >
                  Hủy sửa
                </Button>
              )}
              <Button loading={saveShift.isPending} loadingText="Đang lưu..." type="submit">
                <Plus size={15} />
                {editingShift ? "Lưu ca" : "Thêm ca"}
              </Button>
            </div>
            <div>
              <div className="mb-3 flex items-center justify-between gap-3">
                <div>
                  <h3 className="text-sm font-semibold text-slate-950">Ca trong tuần</h3>
                  <p className="mt-0.5 text-xs text-slate-500">
                    {shiftRangeStart} đến {shiftRangeEnd}
                  </p>
                </div>
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => shifts.refetch()}
                  loading={shifts.isFetching}
                  loadingText="Đang tải..."
                >
                  Làm mới
                </Button>
              </div>
              <DataTable
                density="compact"
                rows={shifts.data?.items}
                loading={shifts.isLoading}
                error={shifts.error}
                onRetry={shifts.refetch}
                emptyTitle="Chưa có ca làm"
                emptyDescription="Thêm ca để DAH tự phân check-in/check-out cho nhân viên."
                columns={[
                  {
                    key: "day",
                    label: "Ngày",
                    render: (row) => new Date(`${row.workDate}T00:00:00`).toLocaleDateString("vi-VN"),
                  },
                  {
                    key: "time",
                    label: "Khung giờ",
                    render: (row) => `${row.startTime} - ${row.endTime}`,
                  },
                  {
                    key: "note",
                    label: "Ghi chú",
                    render: (row) => row.note || "—",
                  },
                  {
                    key: "actions",
                    label: "",
                    sortable: false,
                    render: (row) => (
                      <div className="flex justify-end gap-1">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => {
                            setEditingShift(row);
                            setShiftForm({
                              workDate: row.workDate,
                              startTime: row.startTime,
                              endTime: row.endTime,
                              note: row.note || "",
                            });
                            setShiftError("");
                          }}
                        >
                          <Pencil size={13} />
                          Sửa
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => removeShift.mutate(row)}
                          loading={removeShift.isPending && removeShift.variables?.id === row.id}
                          loadingText="Đang xóa..."
                        >
                          <Trash2 size={13} />
                          Xóa
                        </Button>
                      </div>
                    ),
                  },
                ]}
              />
            </div>
          </div>
        </form>
      </Modal>
      <Modal
        open={reportOpen}
        onClose={() => { setReportOpen(false); setReportDetail(null); }}
        size="full"
        className="shift-report-modal"
        title="Báo cáo ca & chấm công"
        description={
          shiftReport.data
            ? `${dateLabel(shiftReport.data.dateFrom)} – ${dateLabel(shiftReport.data.dateTo)} · Cho phép check-in trễ ${shiftReport.data.lateGraceMinutes} phút`
            : "Đối chiếu lịch được giao với thời gian check-in/check-out thực tế."
        }
      >
        <div className="modal-body shift-report-workspace">
          <div className="shift-report-scope">
            <div className="shift-range-presets" role="group" aria-label="Khoảng báo cáo">
              {[["today", "Hôm nay"], ["yesterday", "Hôm qua"], ["this_week", "Tuần này"], ["last_week", "Tuần trước"]].map(([value, label]) => (
                <button type="button" key={value} className={reportRange === value ? "active" : ""} onClick={() => {
                  setReportRange(value);
                  if (value === "today") setReportDate(isoDay());
                  if (value === "yesterday") setReportDate(isoDay(-1));
                  if (value === "this_week") setReportWeekStart(startOfWeek());
                  if (value === "last_week") setReportWeekStart(addDays(startOfWeek(), -7));
                  setReportPage(1);
                }}>{label}</button>
              ))}
              <button type="button" className={["date", "week"].includes(reportRange) ? "active" : ""} onClick={() => setReportRange("date")}>Tùy chỉnh</button>
            </div>
            {reportRange === "date" && <DateInput value={reportDate} onChange={(value) => { setReportDate(value || isoDay()); setReportPage(1); }} />}
            {reportRange === "week" && <DateInput value={reportWeekStart} onChange={(value) => { setReportWeekStart(startOfWeek(value || isoDay())); setReportPage(1); }} />}
            {reportRange === "date" && <button type="button" className="shift-week-toggle" onClick={() => setReportRange("week")}>Chọn cả tuần</button>}
            <div className="shift-scope-actions">
              <span>{shiftReport.data ? `${dateLabel(shiftReport.data.dateFrom)} – ${dateLabel(shiftReport.data.dateTo)}` : ""}</span>
              <Button size="sm" variant="secondary" onClick={() => shiftReport.refetch()} loading={shiftReport.isFetching}>Làm mới</Button>
              <Button size="sm" onClick={() => exportCurrentReport.mutate()} loading={exportCurrentReport.isPending}><Download size={14} />Xuất theo bộ lọc</Button>
            </div>
          </div>

          <div className="shift-summary-strip" aria-label="Tóm tắt chấm công">
            <button type="button" onClick={() => { setReportView("all"); setReportStatus("all"); setReportPage(1); }}><span>Tổng ca</span><strong>{reportSummary.shifts}</strong><small>{reportSummary.employees} nhân viên</small></button>
            <button type="button" className="positive" onClick={() => { setReportView("all"); setReportStatus("on_time"); setReportPage(1); }}><span>Đúng giờ</span><strong>{reportSummary.onTime}</strong><small>{reportSummary.onTimeRate}% ca đã chấm</small></button>
            <button type="button" className="warning" onClick={() => { setReportView("exceptions"); setReportStatus("late"); setReportPage(1); }}><span>Đi trễ</span><strong>{reportSummary.late}</strong><small>Trên {shiftReport.data?.lateGraceMinutes || 10} phút</small></button>
            <button type="button" className="warning" onClick={() => { setReportView("exceptions"); setReportStatus("early_checkout"); setReportPage(1); }}><span>Về sớm</span><strong>{reportSummary.earlyCheckout}</strong><small>Cần đối chiếu</small></button>
            <button type="button" className="danger" onClick={() => { setReportView("exceptions"); setReportStatus("absent"); setReportPage(1); }}><span>Vắng mặt</span><strong>{reportSummary.absent}</strong><small>Ca đã kết thúc</small></button>
            <button type="button" className="danger" onClick={() => { setReportView("exceptions"); setReportStatus("missing_checkout"); setReportPage(1); }}><span>Thiếu check-out</span><strong>{reportSummary.missingCheckout}</strong><small>Cần rà soát</small></button>
            <div><span>Tỷ lệ đi làm</span><strong>{reportSummary.attendanceRate}%</strong><small>{reportSummary.pendingReview} ca chờ xử lý</small></div>
          </div>

          <div className="shift-report-tabs">
            <button type="button" className={reportView === "exceptions" ? "active" : ""} onClick={() => { setReportView("exceptions"); setReportStatus("anomaly"); setReportPage(1); }}><AlertCircle size={14} />Bất thường <strong>{reportSummary.pendingReview}</strong></button>
            <button type="button" className={reportView === "all" ? "active" : ""} onClick={() => { setReportView("all"); setReportStatus("all"); setReportPage(1); }}><Rows3 size={14} />Tất cả ca</button>
            <button type="button" className={reportView === "matrix" ? "active" : ""} onClick={() => { setReportView("matrix"); setReportStatus("all"); setReportPage(1); }}><LayoutGrid size={14} />Ma trận tuần</button>
          </div>

          <div className="shift-report-filters">
            <label className="shift-report-search"><Search size={15} /><input value={reportSearch} onChange={(event) => { setReportSearch(event.target.value); setReportPage(1); }} placeholder="Tìm tên hoặc mã nhân viên" />{reportSearch && <button type="button" onClick={() => setReportSearch("")} aria-label="Xóa tìm kiếm"><X size={13} /></button>}</label>
            <Select value={reportTitle} aria-label="Lọc theo chức vụ" onChange={(event) => { setReportTitle(event.target.value); setReportPage(1); }}><option value="all">Mọi chức vụ</option>{(shiftReport.data?.filters?.titles || []).map((title) => <option key={title}>{title}</option>)}</Select>
            <Select value={reportStatus} aria-label="Lọc theo trạng thái" onChange={(event) => { setReportStatus(event.target.value); setReportView(event.target.value === "all" ? "all" : "exceptions"); setReportPage(1); }}><option value="all">Mọi trạng thái</option><option value="anomaly">Chỉ bất thường</option><option value="late">Đi trễ</option><option value="early_checkout">Về sớm</option><option value="absent">Vắng mặt</option><option value="missing_checkout">Thiếu check-out</option><option value="on_time">Đúng giờ</option><option value="in_progress">Đang trong ca</option><option value="upcoming">Chưa đến ca</option></Select>
            <Select value={reportShiftKind} aria-label="Lọc theo loại ca" onChange={(event) => { setReportShiftKind(event.target.value); setReportPage(1); }}><option value="all">Mọi khung ca</option><option value="morning">Ca sáng</option><option value="afternoon">Ca chiều</option><option value="night">Ca tối</option></Select>
            <Select value={reportSort} aria-label="Sắp xếp" onChange={(event) => { setReportSort(event.target.value); setReportPage(1); }}><option value="severity">Nghiêm trọng trước</option><option value="late_desc">Trễ nhiều trước</option><option value="early_desc">Về sớm nhiều trước</option><option value="date_desc">Ngày mới trước</option><option value="employee">Nhân viên A-Z</option><option value="employee_desc">Nhân viên Z-A</option><option value="planned_asc">Giờ kế hoạch sớm nhất</option><option value="planned_desc">Giờ kế hoạch muộn nhất</option></Select>
            {(reportSearch || reportTitle !== "all" || reportStatus !== (reportView === "exceptions" ? "anomaly" : "all") || reportShiftKind !== "all" || reportSort !== "severity") && <button type="button" className="shift-filter-reset" onClick={() => { setReportSearch(""); setReportTitle("all"); setReportStatus(reportView === "exceptions" ? "anomaly" : "all"); setReportShiftKind("all"); setReportSort("severity"); setReportPage(1); }}><Filter size={13} />Xóa lọc</button>}
          </div>

          {shiftReport.error ? <div className="inline-error">{shiftReport.error.message}</div> : reportView === "matrix" ? (
            <div className="shift-matrix-shell">
              <div className="shift-matrix-grid" style={{ gridTemplateColumns: `220px repeat(${Math.max(reportMatrixDays.length, 1)}, minmax(145px, 1fr))` }}>
                <div className="shift-matrix-head employee">Nhân viên</div>
                {reportMatrixDays.map((day) => <div key={day} className="shift-matrix-head"><strong>{weekDays[(new Date(`${day}T00:00:00`).getDay() + 6) % 7]}</strong><span>{dateLabel(day)}</span></div>)}
                {reportMatrixEmployees.map((employee) => <div className="contents" key={employee.employeeId}>
                  <div className="shift-matrix-person"><strong>{employee.employeeName}</strong><span>{employee.title || "Chưa có chức vụ"}</span><small>{employee.employeeCode}</small></div>
                  {reportMatrixDays.map((day) => {
                    const dayData = employee.days.find((item) => item.workDate === day);
                    return <div className="shift-matrix-cell" key={day}>{(dayData?.shifts || []).map((shift) => <button type="button" key={shift.scheduleId} className={`tone-${reportStatusMeta[shift.displayStatus]?.tone || "neutral"}`} onClick={() => setReportDetail({ ...shift, workDate: day, employeeId: employee.employeeId, employeeName: employee.employeeName, employeeCode: employee.employeeCode, title: employee.title, dayEvents: dayData.events })}><span>{shift.startTime}–{shift.endTime}</span><ReportStatus row={shift} compact /></button>)}{!dayData?.shifts?.length && <span className="shift-matrix-off">—</span>}</div>;
                  })}
                </div>)}
              </div>
              {!reportMatrixEmployees.length && <div className="shift-report-empty">Không có nhân viên phù hợp bộ lọc.</div>}
            </div>
          ) : (
            <>
              <DataTable
                loading={shiftReport.isLoading}
                rows={shiftReport.data?.rows || []}
                rowKey="scheduleId"
                density="compact"
                selectedRowId={reportDetail?.scheduleId}
                onRowClick={setReportDetail}
                rowClassName={(row) => `shift-row tone-${reportStatusMeta[row.displayStatus]?.tone || "neutral"}`}
                columns={[
                  { key: "employee", label: "Nhân viên", sortable: false, className: "shift-employee-col", render: (row) => <span className="shift-person-cell"><strong>{row.employeeName}</strong><small>{row.title || "Chưa có chức vụ"} · {row.employeeCode}</small></span> },
                  { key: "workDate", label: "Ngày / ca", sortable: false, render: (row) => <span className="shift-date-cell"><strong>{dateLabel(row.workDate)}</strong><small>{row.shiftKind === "morning" ? "Ca sáng" : row.shiftKind === "afternoon" ? "Ca chiều" : "Ca tối"}</small></span> },
                  { key: "planned", label: "Giờ kế hoạch", sortable: false, render: (row) => <span className="shift-time-cell"><strong>{row.startTime}–{row.endTime}</strong>{row.hasOverride && <small className="override">Đã đổi · gốc {row.originalStartTime}–{row.originalEndTime}</small>}</span> },
                  { key: "actual", label: "Giờ thực tế", sortable: false, render: (row) => <span className="shift-actual-cell"><span><small>Vào</small><strong>{timeOnly(row.checkedInAt)}</strong></span><i /><span><small>Ra</small><strong>{timeOnly(row.checkedOutAt)}</strong></span></span> },
                  { key: "dahEvents", label: "Lịch DAH", sortable: false, render: (row) => <DahEventList events={row.dahEvents || row.dayEvents || []} /> },
                  { key: "variance", label: "Sai lệch", sortable: false, render: (row) => <span className="shift-variance">{row.lateMinutes > 0 ? <strong className={row.checkinStatus === "late" ? "warning" : "neutral"}>+{row.lateMinutes}p vào</strong> : <small>Đúng giờ vào</small>}{row.earlyCheckoutMinutes > 0 ? <strong className="warning">-{row.earlyCheckoutMinutes}p ra</strong> : row.checkedOutAt ? <small>Đúng giờ ra</small> : null}</span> },
                  { key: "status", label: "Tình trạng", sortable: false, render: (row) => <ReportStatus row={row} /> },
                  { key: "override", label: "Điều chỉnh", sortable: false, render: (row) => row.hasOverride ? <span className="shift-override-label"><CheckCircle2 size={12} />Đã duyệt</span> : <span className="text-xs text-slate-400">—</span> },
                  { key: "action", label: "", sortable: false, className: "text-right", render: (row) => <button type="button" className="icon-button" onClick={(event) => { event.stopPropagation(); setReportDetail(row); }} title="Rà soát ca" aria-label={`Rà soát ca của ${row.employeeName}`}><Eye size={15} /></button> },
                ]}
                emptyTitle={reportStatus === "anomaly" ? "Không có ca bất thường" : "Không có ca làm"}
                emptyDescription={reportStatus === "anomaly" ? "Các ca trong phạm vi hiện không cần rà soát." : "Không có ca phù hợp phạm vi và bộ lọc hiện tại."}
              />
              <Pagination data={shiftReport.data?.pagination} onPage={setReportPage} pageSize={reportPageSize} onPageSize={(value) => { setReportPageSize(value); setReportPage(1); }} pageSizeOptions={[20, 30, 50, 100]} />
            </>
          )}

          {reportDetail && (
            <aside className="shift-review-drawer" aria-label="Chi tiết rà soát ca">
              <header><div><span>Rà soát ca</span><h3>{reportDetail.employeeName}</h3><p>{reportDetail.title || "Chưa có chức vụ"} · {reportDetail.employeeCode} · {dateLabel(reportDetail.workDate)}</p></div><button type="button" className="icon-button" onClick={() => setReportDetail(null)} aria-label="Đóng chi tiết"><X size={17} /></button></header>
              <div className="shift-review-body">
                <section className="shift-review-result"><ReportStatus row={reportDetail} /><dl><div><dt>Lịch tính công</dt><dd>{reportDetail.startTime}–{reportDetail.endTime}</dd></div>{reportDetail.hasOverride && <div><dt>Lịch gốc</dt><dd>{reportDetail.originalStartTime}–{reportDetail.originalEndTime}</dd></div>}<div><dt>Check-in thực tế</dt><dd>{timeOnly(reportDetail.checkedInAt)}{reportDetail.lateMinutes > 0 && <small>+{reportDetail.lateMinutes} phút</small>}</dd></div><div><dt>Check-out thực tế</dt><dd>{timeOnly(reportDetail.checkedOutAt)}{reportDetail.earlyCheckoutMinutes > 0 && <small>-{reportDetail.earlyCheckoutMinutes} phút</small>}</dd></div></dl></section>
                {reportDetail.hasOverride && <section className="shift-review-note"><strong>Ca đã điều chỉnh</strong><p>{reportDetail.overrideReason || "Không có lý do"}</p></section>}
                {canAdjustShiftAttendance && (() => {
                  const options = shiftEventOptions(reportDetail);
                  const selectedCheckin = options.find((event) => String(event.id) === String(attendanceEventForm.checkinEventId));
                  const checkoutOptions = selectedCheckin
                    ? options.filter((event) => new Date(event.eventTime).getTime() > new Date(selectedCheckin.eventTime).getTime())
                    : options;
                  return (
                    <section className="shift-review-note">
                      <strong>Chỉnh giờ theo webhook</strong>
                      <div className="mt-3 space-y-3">
                        <Field label="Check-in" required>
                          <Select
                            value={attendanceEventForm.checkinEventId}
                            onChange={(event) => setAttendanceEventForm({ ...attendanceEventForm, checkinEventId: event.target.value, checkoutEventId: "" })}
                            disabled={!options.length || saveShiftAttendanceEvents.isPending}
                          >
                            <option value="">Chọn event check-in</option>
                            {options.map((event) => (
                              <option key={event.id} value={event.id}>
                                {shiftEventLabel(event)}
                              </option>
                            ))}
                          </Select>
                        </Field>
                        <Field label="Check-out" hint="Có thể để trống nếu ca thiếu check-out.">
                          <Select
                            value={attendanceEventForm.checkoutEventId}
                            onChange={(event) => setAttendanceEventForm({ ...attendanceEventForm, checkoutEventId: event.target.value })}
                            disabled={!options.length || saveShiftAttendanceEvents.isPending}
                          >
                            <option value="">Chưa chọn check-out</option>
                            {checkoutOptions.map((event) => (
                              <option key={event.id} value={event.id}>
                                {shiftEventLabel(event)}
                              </option>
                            ))}
                          </Select>
                        </Field>
                        <Button
                          size="sm"
                          loading={saveShiftAttendanceEvents.isPending}
                          loadingText="Đang lưu..."
                          disabled={!attendanceEventForm.checkinEventId || !options.length}
                          onClick={() => saveShiftAttendanceEvents.mutate({
                            shiftId: reportDetail.scheduleId,
                            payload: {
                              checkinEventId: attendanceEventForm.checkinEventId,
                              checkoutEventId: attendanceEventForm.checkoutEventId || null,
                            },
                          })}
                        >
                          <Save size={14} /> Lưu giờ chấm công
                        </Button>
                        {!options.length && <p>Không có event webhook trong ngày để chọn.</p>}
                      </div>
                    </section>
                  );
                })()}
                <section className="shift-event-timeline"><div className="shift-review-section-title"><span>Event chấm công</span><strong>{(reportDetail.events?.length || reportDetail.dayEvents?.length || 0)} event</strong></div>{(reportDetail.events?.length ? reportDetail.events : reportDetail.dayEvents || []).map((event) => <div key={event.id}><i /><time>{timeOnly(event.eventTime)}</time><span><strong>{event.action || "DAH event"}</strong><small>{event.status}{event.attendanceSessionId ? ` · Session #${event.attendanceSessionId}` : ""}</small></span></div>)}{!(reportDetail.events?.length || reportDetail.dayEvents?.length) && <p>Không có event trong ngày để đối chiếu.</p>}</section>
              </div>
              <footer><Button variant="secondary" onClick={() => setReportDetail(null)}>Đóng</Button><Button onClick={() => { openShiftOverride({ employeeId: reportDetail.employeeId, employeeName: reportDetail.employeeName, title: reportDetail.title }, { workDate: reportDetail.workDate }, reportDetail); setReportDetail(null); }}><Pencil size={14} />Duyệt đổi ca</Button></footer>
            </aside>
          )}
        </div>
      </Modal>
      <Modal
        open={!!overrideTarget}
        onClose={() => setOverrideTarget(null)}
        title="Duyệt đổi ca"
        description={overrideTarget ? `${overrideTarget.employee.employeeName} · ${dateLabel(overrideTarget.day.workDate)}` : ""}
      >
        <form
          onSubmit={(event) => {
            event.preventDefault();
            approveShiftOverride.mutate({
              shiftId: overrideTarget.shift.scheduleId,
              payload: overrideForm,
            });
          }}
        >
          <div className="modal-body space-y-4">
            {overrideTarget && (
              <div className="grid grid-cols-2 gap-3 max-[640px]:grid-cols-1">
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
                  <span className="text-xs font-medium text-slate-500">Ca gốc</span>
                  <strong className="mt-1 block text-sm text-slate-950">
                    {overrideTarget.shift.originalStartTime || overrideTarget.shift.startTime} - {overrideTarget.shift.originalEndTime || overrideTarget.shift.endTime}
                  </strong>
                </div>
                <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
                  <span className="text-xs font-medium text-slate-500">Chấm công thực tế</span>
                  <strong className="mt-1 block text-sm text-slate-950">
                    {timeOnly(overrideTarget.shift.checkedInAt)} - {timeOnly(overrideTarget.shift.checkedOutAt)}
                  </strong>
                </div>
              </div>
            )}
            <div className="form-grid">
              <Field label="Ngày làm">
                <DateInput
                  value={overrideForm.workDate}
                  onChange={(value) => setOverrideForm({ ...overrideForm, workDate: value || isoDay() })}
                />
              </Field>
              <Field label="Giờ bắt đầu duyệt">
                <Input
                  type="time"
                  value={overrideForm.startTime}
                  onChange={(event) => setOverrideForm({ ...overrideForm, startTime: event.target.value })}
                />
              </Field>
              <Field label="Giờ kết thúc duyệt">
                <Input
                  type="time"
                  value={overrideForm.endTime}
                  onChange={(event) => setOverrideForm({ ...overrideForm, endTime: event.target.value })}
                />
              </Field>
              <Field className="form-span" label="Lý do">
                <Input
                  value={overrideForm.reason}
                  onChange={(event) => setOverrideForm({ ...overrideForm, reason: event.target.value })}
                  placeholder="Ví dụ: Đổi ca với team sale"
                />
              </Field>
            </div>
            {overrideError && <div className="inline-error">{overrideError}</div>}
          </div>
          <div className="form-actions">
            <Button variant="secondary" onClick={() => setOverrideTarget(null)}>
              Hủy
            </Button>
            <Button
              type="submit"
              loading={approveShiftOverride.isPending}
              loadingText="Đang duyệt..."
              disabled={!overrideForm.workDate || !overrideForm.startTime || !overrideForm.endTime}
            >
              Duyệt đổi ca
            </Button>
          </div>
        </form>
      </Modal>
      <Modal
        open={!!confirm}
        onClose={() => setConfirm(null)}
        title="Xóa nhân viên?"
        description="Nhân viên đã có lịch sử sẽ được ẩn thay vì xóa dữ liệu."
      >
        <div className="modal-body">
          <p className="text-[13px] text-slate-600">
            Bạn đang xóa <strong>{confirm?.name}</strong>. Dữ liệu liên quan sẽ
            được bảo toàn.
          </p>
        </div>
        <div className="form-actions">
          <Button
            data-modal-close
            variant="secondary"
            onClick={() => setConfirm(null)}
          >
            Hủy
          </Button>
          <Button
            variant="danger"
            onClick={() => remove.mutate(confirm)}
            loading={remove.isPending}
            loadingText="Đang xóa…"
          >
            Xóa nhân viên
          </Button>
        </div>
      </Modal>
      <DahIdentityLinkModal
        open={!!identityTarget}
        onClose={() => setIdentityTarget(null)}
        memberId={identityTarget?.id}
        memberName={identityTarget?.name}
        targetType="employee"
        onLinked={() => {
          client.invalidateQueries({ queryKey: ["trainers"] });
          client.invalidateQueries({ queryKey: ["dah-events"] });
          client.invalidateQueries({ queryKey: ["checkins"] });
          setIdentityTarget(null);
          notify.success(`Đã liên kết DAH cho ${identityTarget?.name}.`);
        }}
      />
    </>
  );
}
