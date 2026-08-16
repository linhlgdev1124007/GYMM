import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, ChevronLeft, ChevronRight, ClipboardList, Download, FileSpreadsheet, Link2, Pencil, Plus, Save, Trash2 } from "lucide-react";
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

function checkStatusClass(status) {
  if (status === "late" || status === "early_checkout") return "border-amber-200 bg-amber-50 text-amber-800";
  if (status === "on_time") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (status === "missing_checkout") return "border-slate-200 bg-slate-50 text-slate-600";
  return "border-slate-200 bg-slate-50 text-slate-600";
}


export function TrainersPage() {
  const client = useQueryClient();
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
  const [attendanceOpen, setAttendanceOpen] = useState(false);
  const [attendancePreset, setAttendancePreset] = useState("today");
  const [attendanceDate, setAttendanceDate] = useState(isoDay());
  const [attendanceWeekStart, setAttendanceWeekStart] = useState(startOfWeek());
  const [reportOpen, setReportOpen] = useState(false);
  const [reportRange, setReportRange] = useState("today");
  const [reportDate, setReportDate] = useState(isoDay());
  const [reportWeekStart, setReportWeekStart] = useState(startOfWeek());
  const [overrideTarget, setOverrideTarget] = useState(null);
  const [overrideForm, setOverrideForm] = useState({ workDate: isoDay(), startTime: "08:00", endTime: "12:00", reason: "" });
  const [overrideError, setOverrideError] = useState("");
  const [confirm, setConfirm] = useState(null);
  const [form, setForm] = useState(blank);
  const [error, setError] = useState("");
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
    queryKey: ["trainer-shift-report", reportRange, reportDate, reportWeekStart],
    queryFn: () =>
      api(`/api/trainers/shift-report?${queryString({
        rangeType: reportRange,
        day: reportDate,
        weekStart: reportWeekStart,
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
  const reportSummary = useMemo(() => {
    const summary = { employees: 0, shifts: 0, late: 0, earlyCheckout: 0, notChecked: 0 };
    (shiftReport.data?.items || []).forEach((employee) => {
      summary.employees += 1;
      employee.days.forEach((day) => {
        day.shifts.forEach((shift) => {
          summary.shifts += 1;
          if (shift.status === "late" || shift.status === "late_early_checkout") summary.late += 1;
          if (shift.status === "early_checkout" || shift.status === "late_early_checkout") summary.earlyCheckout += 1;
          if (shift.status === "not_checked") summary.notChecked += 1;
        });
      });
    });
    return summary;
  }, [shiftReport.data?.items]);
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
  const attendanceRangeType = attendancePreset === "custom" ? "date" : attendancePreset;
  const exportAttendance = useMutation({
    mutationFn: () =>
      api(`/api/trainers/shift-report?${queryString({
        rangeType: attendanceRangeType,
        day: attendanceDate,
        weekStart: attendanceWeekStart,
      })}`),
    onSuccess: (data) => {
      const rows = [];
      (data.items || []).forEach((employee) => {
        employee.days.forEach((day) => {
          day.shifts.forEach((shift) => {
            const events = (shift.events.length ? shift.events : day.events)
              .map((event) => `${timeOnly(event.eventTime)} ${event.action || "event"} ${event.status}`)
              .join(" | ");
            rows.push({
              workDate: day.workDate,
              employeeCode: employee.employeeCode,
              employeeName: employee.employeeName,
              title: employee.title,
              shiftTime: `${shift.startTime} - ${shift.endTime}`,
              originalShiftTime: `${shift.originalStartTime || shift.startTime} - ${shift.originalEndTime || shift.endTime}`,
              hasOverride: shift.hasOverride ? "Có" : "",
              overrideReason: shift.overrideReason || "",
              checkedInAt: shift.checkedInAt,
              checkinStatusLabel: shift.checkinStatusLabel,
              checkedOutAt: shift.checkedOutAt,
              checkoutStatusLabel: shift.checkoutStatusLabel,
              lateMinutes: shift.lateMinutes || "",
              earlyCheckoutMinutes: shift.earlyCheckoutMinutes || "",
              events,
            });
          });
        });
      });
      const csv = [
        "Ngày,Mã nhân viên,Họ tên,Chức vụ,Ca tính công,Ca gốc,Đã duyệt đổi ca,Lý do đổi ca,Check-in,Trạng thái check-in,Check-out,Trạng thái check-out,Trễ phút,Checkout sớm phút,Event rà soát",
        ...rows.map((row) =>
          [
            row.workDate,
            row.employeeCode,
            row.employeeName,
            row.title,
            row.shiftTime,
            row.originalShiftTime,
            row.hasOverride,
            row.overrideReason,
            row.checkedInAt ? new Date(row.checkedInAt).toLocaleString("vi-VN") : "",
            row.checkinStatusLabel,
            row.checkedOutAt ? new Date(row.checkedOutAt).toLocaleString("vi-VN") : "",
            row.checkoutStatusLabel,
            row.lateMinutes,
            row.earlyCheckoutMinutes,
            row.events,
          ].map(csvValue).join(","),
        ),
      ].join("\n");
      const url = URL.createObjectURL(
        new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" }),
      );
      const link = document.createElement("a");
      link.href = url;
      link.download = `pulsefit-shift-attendance-${data.dateFrom}-${data.dateTo}.csv`;
      link.click();
      URL.revokeObjectURL(url);
      notify.success(`Đã tải ${rows.length} dòng chấm công theo ca.`);
      setAttendanceOpen(false);
    },
    onError: (e) =>
      notify.errorFrom(e, "Không thể tải chấm công nhân viên."),
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
                setReportOpen(true);
              }}
            >
              <ClipboardList size={16} />
              Report ca
            </Button>
            <Button
              variant="secondary"
              onClick={() => setAttendanceOpen(true)}
              loading={exportAttendance.isPending}
              loadingText="Đang tải..."
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
        onClose={() => setReportOpen(false)}
        size="xl"
        title="Report ca làm việc"
        description={
          shiftReport.data
            ? `${dateLabel(shiftReport.data.dateFrom)} đến ${dateLabel(shiftReport.data.dateTo)} · Cho phép trễ ${shiftReport.data.lateGraceMinutes} phút`
            : "Đối chiếu lịch ca với check-in/check-out thực tế."
        }
      >
        <div className="modal-body">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
            <div className="flex flex-wrap items-end gap-3">
              <Field label="Khoảng report">
                <Select
                  className="input min-w-48"
                  value={reportRange}
                  onChange={(event) => {
                    const value = event.target.value;
                    setReportRange(value);
                    if (value === "today") setReportDate(isoDay());
                    if (value === "yesterday") setReportDate(isoDay(-1));
                    if (value === "this_week") setReportWeekStart(startOfWeek());
                    if (value === "last_week") setReportWeekStart(addDays(startOfWeek(), -7));
                  }}
                >
                  <option value="today">Hôm nay</option>
                  <option value="yesterday">Hôm qua</option>
                  <option value="date">Ngày cụ thể</option>
                  <option value="this_week">Tuần này</option>
                  <option value="last_week">Tuần trước</option>
                  <option value="week">Tuần cụ thể</option>
                </Select>
              </Field>
              {reportRange === "date" && (
                <Field label="Ngày">
                  <DateInput value={reportDate} onChange={(value) => setReportDate(value || isoDay())} />
                </Field>
              )}
              {reportRange === "week" && (
                <Field label="Tuần bắt đầu">
                  <DateInput value={reportWeekStart} onChange={(value) => setReportWeekStart(startOfWeek(value || isoDay()))} />
                </Field>
              )}
            </div>
            <Button
              variant="secondary"
              onClick={() => shiftReport.refetch()}
              loading={shiftReport.isFetching}
              loadingText="Đang tải..."
            >
              Làm mới
            </Button>
          </div>
          <div className="mb-4 grid grid-cols-4 gap-3 max-[900px]:grid-cols-2 max-[640px]:grid-cols-1">
            <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">
              <span className="text-xs font-medium text-slate-500">Nhân viên có ca</span>
              <strong className="mt-1 block text-xl text-slate-950">{reportSummary.employees}</strong>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">
              <span className="text-xs font-medium text-slate-500">Tổng ca</span>
              <strong className="mt-1 block text-xl text-slate-950">{reportSummary.shifts}</strong>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">
              <span className="text-xs font-medium text-slate-500">Ca trễ</span>
              <strong className="mt-1 block text-xl text-amber-700">{reportSummary.late}</strong>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">
              <span className="text-xs font-medium text-slate-500">Checkout sớm</span>
              <strong className="mt-1 block text-xl text-amber-700">{reportSummary.earlyCheckout}</strong>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">
              <span className="text-xs font-medium text-slate-500">Chưa chấm công</span>
              <strong className="mt-1 block text-xl text-slate-700">{reportSummary.notChecked}</strong>
            </div>
          </div>
          {shiftReport.isLoading ? (
            <div className="rounded-lg border border-slate-200 bg-white px-4 py-10 text-center text-sm text-slate-500">
              Đang tải report...
            </div>
          ) : shiftReport.error ? (
            <div className="inline-error">{shiftReport.error.message}</div>
          ) : !(shiftReport.data?.items || []).length ? (
            <div className="rounded-lg border border-dashed border-slate-300 bg-slate-50 px-4 py-10 text-center">
              <div className="text-sm font-semibold text-slate-950">Không có ca làm trong khoảng này</div>
              <div className="mt-1 text-xs text-slate-500">Report chỉ hiển thị các ca đã được setup trong lịch ca.</div>
            </div>
          ) : (
            <div className="space-y-4">
              {(shiftReport.data?.items || []).map((employee) => (
                <div key={employee.employeeId} className="rounded-lg border border-slate-200 bg-white">
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-4 py-3">
                    <div>
                      <div className="text-sm font-semibold text-slate-950">{employee.employeeName}</div>
                      <div className="mt-0.5 text-xs text-slate-500">{employee.title || "Chưa có chức vụ"}</div>
                    </div>
                    <div className="text-xs font-medium text-slate-500">{employee.employeeCode}</div>
                  </div>
                  <div className="overflow-auto">
                    <table className="min-w-[1040px] w-full border-collapse text-[12px]">
                      <thead>
                        <tr className="bg-slate-50 text-slate-600">
                          <th className="w-28 border-b border-slate-200 px-3 py-2 text-left font-semibold">Ngày</th>
                          <th className="w-32 border-b border-slate-200 px-3 py-2 text-left font-semibold">Ca làm</th>
                          <th className="w-28 border-b border-slate-200 px-3 py-2 text-left font-semibold">Check-in</th>
                          <th className="w-28 border-b border-slate-200 px-3 py-2 text-left font-semibold">Check-out</th>
                          <th className="w-40 border-b border-slate-200 px-3 py-2 text-left font-semibold">Trạng thái check-in</th>
                          <th className="w-40 border-b border-slate-200 px-3 py-2 text-left font-semibold">Trạng thái check-out</th>
                          <th className="border-b border-slate-200 px-3 py-2 text-left font-semibold">Event rà soát</th>
                        </tr>
                      </thead>
                      <tbody>
                        {employee.days.flatMap((day) =>
                          day.shifts.map((shift, shiftIndex) => (
                            <tr key={`${day.workDate}-${shift.scheduleId}`} className="align-top">
                              <td className="border-b border-slate-100 px-3 py-2 text-slate-700">
                                {shiftIndex === 0 ? dateLabel(day.workDate) : ""}
                              </td>
                              <td className="border-b border-slate-100 px-3 py-2 font-medium text-slate-950">
                                {shift.startTime} - {shift.endTime}
                                {shift.hasOverride && (
                                  <div className="mt-1 text-[11px] font-medium text-blue-700">
                                    Đã duyệt đổi ca · gốc {shift.originalStartTime} - {shift.originalEndTime}
                                  </div>
                                )}
                              </td>
                              <td className="border-b border-slate-100 px-3 py-2 text-slate-700">{timeOnly(shift.checkedInAt)}</td>
                              <td className="border-b border-slate-100 px-3 py-2 text-slate-700">{timeOnly(shift.checkedOutAt)}</td>
                              <td className="border-b border-slate-100 px-3 py-2">
                                <span className={`inline-flex rounded-full border px-2 py-1 text-[11px] font-semibold ${checkStatusClass(shift.checkinStatus || shift.status)}`}>
                                  {shift.checkinStatusLabel || shift.statusLabel}
                                  {shift.checkinStatus === "late" && shift.lateMinutes ? ` ${shift.lateMinutes}p` : ""}
                                </span>
                              </td>
                              <td className="border-b border-slate-100 px-3 py-2">
                                <span className={`inline-flex rounded-full border px-2 py-1 text-[11px] font-semibold ${checkStatusClass(shift.checkoutStatus)}`}>
                                  {shift.checkoutStatusLabel || "Chưa chấm công"}
                                  {shift.checkoutStatus === "early_checkout" && shift.earlyCheckoutMinutes ? ` ${shift.earlyCheckoutMinutes}p` : ""}
                                </span>
                              </td>
                              <td className="border-b border-slate-100 px-3 py-2">
                                <div className="flex flex-col gap-2">
                                  <Button size="sm" variant="secondary" onClick={() => openShiftOverride(employee, day, shift)}>
                                    <Pencil size={13} />
                                    Duyệt đổi ca
                                  </Button>
                                  <details>
                                    <summary className="cursor-pointer text-xs font-medium text-blue-700">
                                      {shift.events.length || day.events.length} event
                                    </summary>
                                    <div className="mt-2 space-y-1">
                                      {(shift.events.length ? shift.events : day.events).map((event) => (
                                        <div key={event.id} className="rounded border border-slate-200 bg-slate-50 px-2 py-1 text-[11px] text-slate-600">
                                          <span className="font-semibold text-slate-900">{timeOnly(event.eventTime)}</span>
                                          <span> · {event.action || "event"}</span>
                                          <span> · {event.status}</span>
                                          {event.attendanceSessionId && <span> · session #{event.attendanceSessionId}</span>}
                                        </div>
                                      ))}
                                      {!(shift.events.length || day.events.length) && (
                                        <div className="text-[11px] text-slate-500">Không có event trong ngày.</div>
                                      )}
                                    </div>
                                  </details>
                                </div>
                              </td>
                            </tr>
                          )),
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
        <div className="form-actions">
          <Button variant="secondary" onClick={() => setReportOpen(false)}>
            Đóng
          </Button>
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
        open={attendanceOpen}
        onClose={() => setAttendanceOpen(false)}
        title="Tải chấm công nhân viên"
        description="Xuất file chấm công theo lịch ca, check-in/check-out và trạng thái đúng giờ."
      >
        <div className="modal-body">
          <div className="form-grid">
            <Field className="form-span" label="Khoảng report">
              <Select
                value={attendancePreset}
                onChange={(event) => {
                  const value = event.target.value;
                  setAttendancePreset(value);
                  if (value === "today") setAttendanceDate(isoDay());
                  if (value === "yesterday") setAttendanceDate(isoDay(-1));
                  if (value === "this_week") setAttendanceWeekStart(startOfWeek());
                  if (value === "last_week") setAttendanceWeekStart(addDays(startOfWeek(), -7));
                }}
              >
                <option value="today">Hôm nay</option>
                <option value="yesterday">Hôm qua</option>
                <option value="custom">Ngày cụ thể</option>
                <option value="this_week">Tuần này</option>
                <option value="last_week">Tuần trước</option>
                <option value="week">Tuần cụ thể</option>
              </Select>
            </Field>
            {attendancePreset === "custom" && (
              <Field className="form-span" label="Ngày cụ thể">
                <DateInput
                  value={attendanceDate}
                  onChange={setAttendanceDate}
                />
              </Field>
            )}
            {attendancePreset === "week" && (
              <Field className="form-span" label="Tuần bắt đầu">
                <DateInput
                  value={attendanceWeekStart}
                  onChange={(value) => setAttendanceWeekStart(startOfWeek(value || isoDay()))}
                />
              </Field>
            )}
          </div>
        </div>
        <div className="form-actions">
          <Button
            data-modal-close
            variant="secondary"
            onClick={() => setAttendanceOpen(false)}
          >
            Hủy
          </Button>
          <Button
            onClick={() => exportAttendance.mutate()}
            loading={exportAttendance.isPending}
            loadingText="Đang tải..."
            disabled={(attendancePreset === "custom" && !attendanceDate) || (attendancePreset === "week" && !attendanceWeekStart)}
          >
            <Download size={16} />
            Tải file
          </Button>
        </div>
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
