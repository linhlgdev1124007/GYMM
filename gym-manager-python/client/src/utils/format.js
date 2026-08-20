import { format, parseISO } from "date-fns";

export const money = (value) =>
  new Intl.NumberFormat("vi-VN", {
    style: "currency",
    currency: "VND",
    maximumFractionDigits: 0,
  }).format(value || 0);
export const shortDate = (value) =>
  value
    ? format(typeof value === "string" ? parseISO(value) : value, "dd/MM/yyyy")
    : "—";
export const dateTime = (value) =>
  value ? format(parseISO(value), "HH:mm · dd/MM/yyyy") : "—";
export const initials = (name = "") =>
  name
    .trim()
    .split(/\s+/)
    .slice(-2)
    .map((part) => part[0])
    .join("")
    .toUpperCase() || "—";
export const statusLabel = {
  active: "Đang hoạt động",
  lead: "Tiềm năng",
  blocked: "Đã khóa",
  inactive: "Tạm ngừng",
  frozen: "Bảo lưu",
  pending: "Chờ kích hoạt",
  suspended: "Tạm dừng",
  expiring: "Sắp hết hạn",
  expired: "Hết hạn",
  completed: "Hoàn thành",
  cancelled: "Đã hủy",
  open: "Đang ở phòng",
  closed: "Đã rời phòng",
  paid: "Đã thanh toán",
  refund: "Hoàn tiền",
  converted: "Đã chuyển đổi",
  refunded: "Đã hoàn tiền",
  void: "Đã hủy",
  online: "Trực tuyến",
  offline: "Ngoại tuyến",
  maintenance: "Bảo trì",
};

export const normalizePhone = (value = "") =>
  String(value).replace(/\D/g, "").slice(0, 15);
export const formatPhone = (value = "") => {
  const digits = normalizePhone(value);
  if (!digits) return "";
  if (digits.startsWith("0"))
    return [digits.slice(0, 3), digits.slice(3, 6), digits.slice(6, 10)]
      .filter(Boolean)
      .join(" ");
  return [
    digits.slice(0, 3),
    digits.slice(3, 6),
    digits.slice(6, 10),
    digits.slice(10, 15),
  ]
    .filter(Boolean)
    .join(" ");
};
export const parseMoney = (value) =>
  Math.max(Number(String(value ?? "").replace(/[^\d]/g, "")) || 0, 0);
export const formatMoneyInput = (value) =>
  new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 0 }).format(
    parseMoney(value),
  );
export const isoToDisplayDate = (value) =>
  value && /^\d{4}-\d{2}-\d{2}$/.test(value)
    ? `${value.slice(8, 10)}/${value.slice(5, 7)}/${value.slice(0, 4)}`
    : "";
export const displayToIsoDate = (value) => {
  const match = String(value).match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
  if (!match) return null;
  const [, day, month, year] = match;
  const date = new Date(Number(year), Number(month) - 1, Number(day));
  return date.getFullYear() === Number(year) &&
    date.getMonth() === Number(month) - 1 &&
    date.getDate() === Number(day)
    ? `${year}-${month}-${day}`
    : null;
};
export const ageFromDate = (value) => {
  if (!value) return null;
  const birth = parseISO(value);
  const today = new Date();
  let age = today.getFullYear() - birth.getFullYear();
  if (
    today.getMonth() < birth.getMonth() ||
    (today.getMonth() === birth.getMonth() && today.getDate() < birth.getDate())
  )
    age -= 1;
  return age >= 0 && age < 130 ? age : null;
};
