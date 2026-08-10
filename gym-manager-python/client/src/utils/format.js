import { format, parseISO } from 'date-fns'

export const money = (value) => new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND', maximumFractionDigits: 0 }).format(value || 0)
export const shortDate = (value) => value ? format(typeof value === 'string' ? parseISO(value) : value, 'dd/MM/yyyy') : '—'
export const dateTime = (value) => value ? format(parseISO(value), 'HH:mm · dd/MM/yyyy') : '—'
export const initials = (name = '') => name.trim().split(/\s+/).slice(-2).map((part) => part[0]).join('').toUpperCase() || '—'
export const statusLabel = { active: 'Đang hoạt động', lead: 'Tiềm năng', blocked: 'Đã khóa', inactive: 'Ngừng', frozen: 'Tạm dừng', pending: 'Chờ xử lý', expiring: 'Sắp hết hạn', expired: 'Hết hạn', completed: 'Hoàn thành', open: 'Đang ở phòng', closed: 'Đã rời phòng', paid: 'Đã thanh toán', online: 'Trực tuyến', offline: 'Ngoại tuyến', maintenance: 'Bảo trì' }
