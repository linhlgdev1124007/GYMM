import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { addDays, format } from "date-fns";
import {
  BookmarkPlus,
  CalendarPlus,
  CreditCard,
  Plus,
  ScanFace,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { useSearchParams } from "react-router-dom";
import { api, queryString } from "../../services/api";
import { notify } from "../../services/notify";
import { useDebouncedValue } from "../../hooks/useDebouncedValue";
import { PageHeader } from "../../components/common/PageHeader";
import { SearchInput } from "../../components/common/SearchInput";
import { Button } from "../../components/ui/Button";
import { DataTable } from "../../components/ui/DataTable";
import { Field, Input, Select, Textarea } from "../../components/ui/Form";
import { Modal } from "../../components/ui/Modal";
import { DateInput, DateOfBirthInput, MoneyInput, PhoneInput } from "../../components/ui/SmartInputs";
import { SearchableSelect } from "../../components/ui/SearchableSelect";
import { Pagination } from "../../components/ui/Pagination";
import { StatusBadge } from "../../components/ui/StatusBadge";
import {
  emptyTrainingForm,
  TrainingFields,
} from "../../components/forms/TrainingForm";
import { MemberQuickDrawer } from "./MemberQuickDrawer";
import { DahIdentityLinkModal } from "./DahIdentityLinkModal";
import { useAuth } from "../../app/AuthContext";
import {
  formatPhone,
  initials,
  money,
  normalizePhone,
  dateTime,
  shortDate,
} from "../../utils/format";

const createInitialForm = () => ({
  name: "",
  phone: "",
  email: "",
  gender: "",
  dateOfBirth: "",
  mbsCode: "",
  personUuid: "",
  dahEventId: "",
  dahIdentityName: "",
  dahIdentityImageData: "",
  dahIdentityTime: "",
  salesEmployeeId: "",
  notes: "",
  status: "active",
  registerMembership: false,
  membership: {
    planId: "",
    startsAt: format(new Date(), "yyyy-MM-dd"),
    expiresAt: "",
    finalPrice: 0,
    paidAmount: 0,
    debtDueDate: "",
    paymentMethod: "cash",
    bankAccountId: "",
  },
  registerPt: false,
  pt: emptyTrainingForm(),
});
const initialForm = createInitialForm();
const views = [
  ["all", "Tất cả"],
  ["active", "Đang hoạt động"],
  ["expiring", "Sắp hết hạn"],
  ["debt", "Có công nợ"],
  ["no_pt", "Chưa có PT"],
];
const statusFilters = {
  all: "Tất cả",
  active: "Đang hoạt động",
  expired: "Hết hạn",
  expiring: "Sắp hết hạn",
  frozen: "Bảo lưu",
  inactive: "Tạm ngừng",
};
const paramDefaults = {
  view: "all",
  status: "all",
  expiringDays: "14",
  paymentStatus: "all",
  overdueDays: "7",
  sort: "newest",
};

function readTablePrefs(key) {
  try {
    return JSON.parse(localStorage.getItem(key) || "{}");
  } catch {
    return {};
  }
}

export function MembersPage() {
  const { user } = useAuth();
  const canOperate = ["admin", "manager", "receptionist"].includes(user?.role);
  const tablePrefsKey = `pulsefit-member-table-${user?.id || user?.username || "local"}`;
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const [createOpen, setCreateOpen] = useState(false);
  const [saveViewOpen, setSaveViewOpen] = useState(false);
  const [viewName, setViewName] = useState("");
  const [savedViews, setSavedViews] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem("pulsefit-member-views") || "[]");
    } catch {
      return [];
    }
  });
  const [density, setDensity] = useState(() => {
    return readTablePrefs(tablePrefsKey).density || "standard";
  });
  const [hiddenColumns, setHiddenColumns] = useState(() => {
    return readTablePrefs(tablePrefsKey).hiddenColumns || [];
  });
  const [tableOptionsOpen, setTableOptionsOpen] = useState(false);
  const [tableOptionsPosition, setTableOptionsPosition] = useState({
    top: 0,
    left: 0,
  });
  const tableOptionsRef = useRef(null);
  const [form, setForm] = useState(initialForm);
  const [identityLinkOpen, setIdentityLinkOpen] = useState(false);
  const [error, setError] = useState("");
  const [selection, setSelection] = useState([]);
  const search = params.get("q") || "";
  const q = useDebouncedValue(search);
  const status = params.get("status") || "all";
  const expiringDays = Number(params.get("expiringDays") || 14);
  const paymentStatus = params.get("paymentStatus") || "all";
  const overdueDays = Number(params.get("overdueDays") || 7);
  const view = params.get("view") || "all";
  const sort = params.get("sort") || "newest";
  const packageId = params.get("packageId") || "";
  const trainerId = params.get("trainerId") || "";
  const page = Number(params.get("page") || 1);
  const pageSize = Number(params.get("pageSize") || readTablePrefs(tablePrefsKey).pageSize || 20);
  const memberId = params.get("member");
  const action = params.get("action");
  const createRequested = params.get("create") === "1";
  const updateParams = useCallback(
    (changes, options = {}) =>
      setParams((current) => {
        const next = new URLSearchParams(current);
        Object.entries(changes).forEach(([key, value]) =>
          value === "" || value == null || (value === "all" && key !== "view")
            ? next.delete(key)
            : next.set(key, value),
        );
        return next;
      }, options),
    [setParams],
  );
  const members = useQuery({
    queryKey: [
      "members",
      q,
      status,
      expiringDays,
      paymentStatus,
      overdueDays,
      view,
      packageId,
      trainerId,
      sort,
      page,
      pageSize,
    ],
    queryFn: () =>
      api(
        `/api/members?${queryString({ q, status, expiringDays, paymentStatus, overdueDays, view, packageId, trainerId, sort, page, pageSize })}`,
      ),
  });
  const options = useQuery({
    queryKey: ["member-options"],
    queryFn: () => api("/api/members/options"),
    staleTime: 5 * 60_000,
  });
  const create = useMutation({
    mutationFn: (payload) =>
      api("/api/members", { method: "POST", body: payload }),
    onSuccess: (member) => {
      client.invalidateQueries({ queryKey: ["members"] });
      client.invalidateQueries({ queryKey: ["training"] });
      client.invalidateQueries({ queryKey: ["dashboard"] });
      setCreateOpen(false);
      setForm(createInitialForm());
      updateParams({ member: member.id });
      notify.success({
        title: `Đã tạo hội viên ${member.name}.`,
        action: {
          label: "Xem hồ sơ",
          onClick: () => updateParams({ member: member.id }),
        },
      });
    },
    onError: (reason) => setError(reason.message),
  });
  useEffect(() => {
    if (!createRequested || !canOperate) return;
    setCreateOpen(true);
    updateParams({ create: "" }, { replace: true });
  }, [canOperate, createRequested, updateParams]);
  useEffect(() => {
    const focus = (event) => {
      if (
        event.key === "/" &&
        !["INPUT", "TEXTAREA", "SELECT"].includes(
          document.activeElement?.tagName,
        )
      ) {
        event.preventDefault();
        document.querySelector(".members-search input")?.focus();
      }
    };
    document.addEventListener("keydown", focus);
    return () => document.removeEventListener("keydown", focus);
  }, []);
  useEffect(() => {
    localStorage.setItem(
      tablePrefsKey,
      JSON.stringify({ density, hiddenColumns, pageSize }),
    );
  }, [density, hiddenColumns, pageSize, tablePrefsKey]);
  useEffect(() => {
    if (!tableOptionsOpen) return undefined;
    const close = (event) => {
      if (!tableOptionsRef.current?.contains(event.target)) {
        setTableOptionsOpen(false);
      }
    };
    const reposition = () => setTableOptionsOpen(false);
    document.addEventListener("pointerdown", close);
    window.addEventListener("resize", reposition);
    window.addEventListener("scroll", reposition, true);
    return () => {
      document.removeEventListener("pointerdown", close);
      window.removeEventListener("resize", reposition);
      window.removeEventListener("scroll", reposition, true);
    };
  }, [tableOptionsOpen]);
  const openMember = useCallback(
    (row, nextAction) =>
      updateParams({ member: row.id, action: nextAction || "" }),
    [updateParams],
  );
  const applySystemView = useCallback(
    (nextView) => {
      updateParams({
        view: nextView,
        q: "",
        status: "",
        expiringDays: "",
        paymentStatus: "",
        overdueDays: "",
        packageId: "",
        trainerId: "",
        page: "",
      });
      setSelection([]);
    },
    [updateParams],
  );
  const clearMemberAction = useCallback(
    () => updateParams({ action: "" }, { replace: true }),
    [updateParams],
  );
  const columns = useMemo(
    () => [
      {
        key: "member",
        label: "Hội viên",
        sortValue: (row) => row.name,
        render: (row) => (
          <button
            className="member-cell text-left"
            onClick={(event) => {
              event.stopPropagation();
              openMember(row);
            }}
          >
            <div className="avatar avatar-md">
              {row.avatarImageData ? (
                <img src={row.avatarImageData} alt="" />
              ) : (
                initials(row.name)
              )}
            </div>
            <div>
              <div className="cell-primary hover:text-blue-700">{row.name}</div>
              <div className="cell-secondary">{row.code}</div>
            </div>
          </button>
        ),
      },
      {
        key: "phone",
        label: "Điện thoại",
        className: "whitespace-nowrap max-[640px]:hidden",
        sortValue: (row) => row.phone,
        render: (row) => formatPhone(row.phone) || "—",
      },
      {
        key: "sale",
        label: "Sale",
        className: "max-[768px]:hidden",
        sortValue: (row) => row.salesEmployee?.name || "",
        render: (row) =>
          row.salesEmployee ? (
            <div>
              <span className="cell-primary">{row.salesEmployee.name}</span>
              <div className="cell-secondary">
                {row.salesEmployee.code || "Phụ trách"}
              </div>
            </div>
          ) : (
            <button
              className="text-xs font-medium text-blue-700"
              onClick={(event) => {
                event.stopPropagation();
                openMember(row, "edit");
              }}
            >
              + Gán Sale
            </button>
          ),
      },
      {
        key: "membership",
        label: "Gói & hết hạn",
        sortValue: (row) => row.membership?.expiresAt || "",
        render: (row) =>
          row.membership ? (
            <div>
              <span className="cell-primary">
                {row.membership.package.name}
              </span>
              <div className="cell-secondary">
                {shortDate(row.membership.expiresAt)}
              </div>
            </div>
          ) : (
            <span className="text-slate-400">Chưa có gói</span>
          ),
      },
      {
        key: "debt",
        label: "Công nợ",
        className: "text-right",
        sortValue: (row) => row.membership?.debtAmount || 0,
        render: (row) =>
          row.membership?.debtAmount ? (
            <div>
              <button
                className="font-medium text-red-700 hover:underline"
                onClick={(event) => {
                  event.stopPropagation();
                  openMember(row, "payment");
                }}
              >
                {money(row.membership.debtAmount)}
              </button>
              <div className="cell-secondary hidden max-[640px]:block">
                Hạn {shortDate(row.membership.debtDueDate)}
              </div>
            </div>
          ) : canOperate ? (
            "—"
          ) : (
            <span className="text-slate-400">—</span>
          ),
      },
      {
        key: "debtDueDate",
        label: "Hạn thanh toán",
        className: "max-[640px]:hidden",
        sortValue: (row) => row.membership?.debtDueDate || "",
        render: (row) => {
          if (!row.membership?.debtAmount) return "—";
          if (!row.membership.debtDueDate)
            return (
              <button
                className="font-medium text-blue-700 hover:underline"
                onClick={(event) => {
                  event.stopPropagation();
                  openMember(row, "deadline");
                }}
              >
                + Đặt hạn
              </button>
            );
          const overdue =
            new Date(`${row.membership.debtDueDate}T23:59:59`) < new Date();
          return (
            <button
              className="text-left hover:underline"
              onClick={(event) => {
                event.stopPropagation();
                openMember(row, "deadline");
              }}
            >
              <span className={overdue ? "font-medium text-red-700" : ""}>
                {shortDate(row.membership.debtDueDate)}
              </span>
              <div
                className={`cell-secondary ${overdue ? "!text-red-600" : ""}`}
              >
                {overdue ? "Quá hạn · Đổi hạn" : "Chưa đến hạn · Đổi hạn"}
              </div>
            </button>
          );
        },
      },
      {
        key: "trainer",
        label: "PT",
        className: "max-[640px]:hidden",
        sortValue: (row) => row.trainers?.map((trainer) => trainer.name).join(", ") || "",
        render: (row) =>
          row.trainers?.length ? (
            <div className="flex max-w-48 flex-wrap gap-1">
              {row.trainers.map((trainer) => (
                <span
                  key={trainer.id}
                  className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-medium text-slate-700"
                >
                  {trainer.name}
                </span>
              ))}
            </div>
          ) : (
            <button
              className="text-xs font-medium text-blue-700"
              onClick={(event) => {
                event.stopPropagation();
                openMember(row, "training");
              }}
            >
              + Gán PT
            </button>
          ),
      },
      {
        key: "status",
        label: "Trạng thái",
        className: "max-[640px]:hidden",
        sortValue: (row) => row.membership?.status || row.status,
        render: (row) => (
          <StatusBadge status={row.membership?.status || row.status} />
        ),
      },
      {
        key: "actions",
        label: "Thao tác nhanh",
        className: "member-quick-cell",
        sortable: false,
        render: (row) => canOperate ? (
          <div className="member-row-actions">
            <button
              className="row-action-primary"
              title={row.membership ? "Gia hạn gói" : "Đăng ký gói"}
              aria-label={`${row.membership ? "Gia hạn" : "Đăng ký"} gói cho ${row.name}`}
              onClick={(event) => {
                event.stopPropagation();
                openMember(row, "renew");
              }}
            >
              <CalendarPlus size={15} />
              <span>{row.membership ? "Gia hạn" : "Đăng ký"}</span>
            </button>
            <button
              className="row-action-secondary"
              title="Thu tiền"
              aria-label={`Thu tiền ${row.name}`}
              onClick={(event) => {
                event.stopPropagation();
                openMember(row, "payment");
              }}
            >
              <CreditCard size={15} />
              <span>Thu tiền</span>
            </button>
          </div>
        ) : (
          <span className="text-xs text-slate-400">Chỉ xem</span>
        ),
      },
    ],
    [canOperate, openMember],
  );
  const activeFilters = [
    status !== "all" && [
      "Trạng thái",
      status === "expiring"
        ? `${statusFilters[status]} trong ${expiringDays} ngày`
        : statusFilters[status],
      "status",
    ],
    paymentStatus === "overdue" && [
      "Thanh toán",
      `Quá hạn trong ${overdueDays} ngày`,
      "paymentStatus",
    ],
    packageId && [
      "Gói",
      options.data?.plans.find((row) => String(row.id) === packageId)?.name,
      "packageId",
    ],
    trainerId && [
      "PT",
      options.data?.employees.find((row) => String(row.id) === trainerId)?.name,
      "trainerId",
    ],
  ].filter(Boolean);
  const displayColumns = columns.filter(
    (column) => !hiddenColumns.includes(column.key),
  );
  const exportSelected = () => {
    const rows =
      members.data?.items.filter((row) => selection.includes(row.id)) || [];
    const csv = [
      "Mã hội viên,Họ tên,Điện thoại,Sale,Gói tập,Công nợ,Hạn thanh toán,PT,Trạng thái",
      ...rows.map((row) =>
        [
          row.code,
          row.name,
          row.phone || "",
          row.salesEmployee?.name || "",
          row.membership?.package.name || "",
          row.membership?.debtAmount || 0,
          row.membership?.debtDueDate || "",
          row.trainer?.name || "",
          row.status,
        ]
          .map((value) => `"${String(value).replaceAll('"', '""')}"`)
          .join(","),
      ),
    ].join("\n");
    const url = URL.createObjectURL(
      new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8" }),
    );
    const link = document.createElement("a");
    link.href = url;
    link.download = "pulsefit-members.csv";
    link.click();
    URL.revokeObjectURL(url);
    notify.success(`Đã xuất danh sách ${rows.length} hội viên.`);
  };
  const closeCreate = () => {
    setCreateOpen(false);
    setForm(createInitialForm());
    setError("");
  };
  const updateMembershipDraft = (changes) =>
    setForm((current) => ({
      ...current,
      membership: { ...current.membership, ...changes },
    }));
  const selectMembershipPlan = (planId) => {
    const plan = options.data?.plans.find((row) => String(row.id) === String(planId));
    const startsAt = form.membership.startsAt || format(new Date(), "yyyy-MM-dd");
    updateMembershipDraft({
      planId,
      finalPrice: plan?.price || 0,
      expiresAt: plan?.durationDays
        ? format(addDays(new Date(`${startsAt}T00:00:00`), plan.durationDays), "yyyy-MM-dd")
        : "",
    });
  };
  const savedViewMatches = useCallback(
    (saved) =>
      Object.entries(saved.filters).every(
        ([key, value]) => (params.get(key) || paramDefaults[key] || "") === value,
      ),
    [params],
  );
  const activeSavedViewId = savedViews.find(savedViewMatches)?.id;
  const deleteSavedView = (saved) => {
    const next = savedViews.filter((item) => item.id !== saved.id);
    setSavedViews(next);
    localStorage.setItem("pulsefit-member-views", JSON.stringify(next));
    notify.success(`Đã xóa chế độ xem “${saved.name}”.`);
  };
  const saveView = (event) => {
    event.preventDefault();
    const name = viewName.trim();
    if (!name) return;
    const next = [
      ...savedViews,
      {
        id: Date.now(),
        name,
        filters: {
          view,
          status,
          expiringDays: String(expiringDays),
          paymentStatus,
          overdueDays: String(overdueDays),
          packageId,
          trainerId,
          sort,
          pageSize: String(pageSize),
        },
        hiddenColumns,
        density,
      },
    ];
    setSavedViews(next);
    localStorage.setItem("pulsefit-member-views", JSON.stringify(next));
    setViewName("");
    setSaveViewOpen(false);
    notify.success(`Đã lưu chế độ xem “${viewName.trim()}”.`);
  };
  return (
    <>
      <div className="members-page">
        <PageHeader
          eyebrow="Quản lý"
          title="Hội viên"
          description="Không gian vận hành hội viên — xem và xử lý mà không rời danh sách."
          action={canOperate ? (
            <Button onClick={() => setCreateOpen(true)}>
              <Plus size={16} />
              Thêm hội viên
            </Button>
          ) : null}
        />
        <div className="workspace-views">
          {views.map(([key, label]) => (
            <button
              key={key}
              className={`workspace-view ${!activeSavedViewId && view === key ? "active" : ""}`}
              onClick={() => applySystemView(key)}
            >
              {label}
            </button>
          ))}
          {savedViews.map((saved) => {
            const active = saved.id === activeSavedViewId;
            return (
              <span
                key={saved.id}
                className={`saved-workspace-view ${active ? "active" : ""}`}
              >
                <button
                  className="saved-workspace-open"
                  onClick={() => {
                    updateParams({
                      status: "",
                      expiringDays: "",
                      paymentStatus: "",
                      overdueDays: "",
                      packageId: "",
                      trainerId: "",
                      ...saved.filters,
                      page: "",
                    });
                    setHiddenColumns(saved.hiddenColumns || []);
                    setDensity(saved.density || "standard");
                  }}
                >
                  {saved.name}
                </button>
                <button
                  className="saved-workspace-delete"
                  aria-label={`Xóa chế độ xem ${saved.name}`}
                  onClick={(event) => {
                    event.stopPropagation();
                    deleteSavedView(saved);
                  }}
                >
                  <X size={12} />
                </button>
              </span>
            );
          })}
          <button
            className="workspace-view ml-auto inline-flex items-center gap-1"
            onClick={() => setSaveViewOpen(true)}
          >
            <BookmarkPlus size={13} />
            Lưu chế độ xem
          </button>
        </div>
        {canOperate && selection.length ? (
          <div className="bulk-bar">
            <strong>{selection.length} hội viên đã chọn</strong>
            <Button size="sm" variant="secondary" onClick={exportSelected}>
              Xuất danh sách
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setSelection([])}>
              Bỏ chọn
            </Button>
          </div>
        ) : (
          <div className="toolbar">
            <div className="members-search">
              <SearchInput
                value={search}
                onChange={(value) =>
                  updateParams({ q: value, page: "" }, { replace: true })
                }
                placeholder="Tên, điện thoại, mã hội viên…  /"
              />
            </div>
            <Select
              className="input w-48"
              value={status}
              onChange={(e) =>
                updateParams({
                  status: e.target.value,
                  expiringDays: e.target.value === "expiring" ? expiringDays : "",
                  page: "",
                })
              }
            >
              <option value="all">Tất cả</option>
              <option value="active">Đang hoạt động</option>
              <option value="expired">Hết hạn</option>
              <option value="expiring">Sắp hết hạn trong X ngày</option>
              <option value="frozen">Bảo lưu</option>
              <option value="inactive">Tạm ngừng</option>
            </Select>
            {status === "expiring" && (
              <label className="expiry-days-field">
                <span>Trong</span>
                <Input
                  type="number"
                  min="1"
                  max="365"
                  value={expiringDays}
                  onChange={(event) =>
                    updateParams(
                      {
                        expiringDays: Math.min(
                          Math.max(Number(event.target.value) || 1, 1),
                          365,
                        ),
                        page: "",
                      },
                      { replace: true },
                    )
                  }
                />
                <span>ngày</span>
              </label>
            )}
            <Select
              className="input w-52"
              value={paymentStatus}
              onChange={(event) =>
                updateParams({
                  paymentStatus: event.target.value,
                  overdueDays:
                    event.target.value === "overdue" ? overdueDays : "",
                  page: "",
                })
              }
            >
              <option value="all">Mọi hạn thanh toán</option>
              <option value="overdue">Quá hạn thanh toán trong X ngày</option>
            </Select>
            {paymentStatus === "overdue" && (
              <label className="expiry-days-field">
                <span>Trong</span>
                <Input
                  type="number"
                  min="1"
                  max="365"
                  value={overdueDays}
                  onChange={(event) =>
                    updateParams(
                      {
                        overdueDays: Math.min(
                          Math.max(Number(event.target.value) || 1, 1),
                          365,
                        ),
                        page: "",
                      },
                      { replace: true },
                    )
                  }
                />
                <span>ngày</span>
              </label>
            )}
            <Select
              className="input w-44"
              value={packageId}
              onChange={(e) =>
                updateParams({ packageId: e.target.value, page: "" })
              }
            >
              <option value="">Mọi gói tập</option>
              {options.data?.plans.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.name}
                </option>
              ))}
            </Select>
            <Select
              className="input w-40"
              value={trainerId}
              onChange={(e) =>
                updateParams({ trainerId: e.target.value, page: "" })
              }
            >
              <option value="">Mọi PT</option>
              {options.data?.employees
                .filter((row) => row.isPtRole)
                .map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.name}
                  </option>
                ))}
            </Select>
            <Select
              className="input w-36"
              value={sort}
              onChange={(e) => updateParams({ sort: e.target.value, page: "" })}
            >
              <option value="newest">Mới nhất</option>
              <option value="name">Tên A–Z</option>
              <option value="status">Trạng thái</option>
            </Select>
            <div className="table-options" ref={tableOptionsRef}>
              <button
                type="button"
                className="table-options-trigger"
                aria-expanded={tableOptionsOpen}
                onClick={(event) => {
                  const rect = event.currentTarget.getBoundingClientRect();
                  const width = 224;
                  setTableOptionsPosition({
                    top: rect.bottom + 4,
                    left: Math.max(
                      8,
                      Math.min(rect.left, window.innerWidth - width - 8),
                    ),
                  });
                  setTableOptionsOpen((open) => !open);
                }}
              >
                <SlidersHorizontal size={14} />
                Hiển thị
              </button>
              {tableOptionsOpen && <div
                className="table-options-panel"
                style={tableOptionsPosition}
              >
                <strong>Mật độ bảng</strong>
                <label>
                  <input
                    type="radio"
                    name="density"
                    checked={density === "standard"}
                    onChange={() => {
                      setDensity("standard");
                    }}
                  />
                  Tiêu chuẩn
                </label>
                <label>
                  <input
                    type="radio"
                    name="density"
                    checked={density === "compact"}
                    onChange={() => {
                      setDensity("compact");
                    }}
                  />
                  Thu gọn
                </label>
                <hr />
                <strong>Cột hiển thị</strong>
                {[
                  ["phone", "Điện thoại"],
                  ["sale", "Sale"],
                  ["membership", "Gói & hết hạn"],
                  ["debt", "Công nợ"],
                  ["debtDueDate", "Hạn thanh toán"],
                  ["trainer", "PT"],
                  ["status", "Trạng thái"],
                ].map(([key, label]) => (
                  <label key={key}>
                    <input
                      type="checkbox"
                      checked={!hiddenColumns.includes(key)}
                      onChange={() =>
                        setHiddenColumns((current) =>
                          current.includes(key)
                            ? current.filter((item) => item !== key)
                            : [...current, key],
                        )
                      }
                    />
                    {label}
                  </label>
                ))}
              </div>}
            </div>
            <div className="toolbar-spacer" />
            <span className="text-xs text-slate-400">
              {members.data?.pagination.total || 0} hội viên
            </span>
          </div>
        )}
        {!!activeFilters.length && (
          <div className="active-filter-bar">
            {activeFilters.map(([label, value, key]) => (
              <button
                key={key}
                className="filter-chip"
                onClick={() =>
                  updateParams({
                    [key]: "",
                    ...(key === "status" ? { expiringDays: "" } : {}),
                    ...(key === "paymentStatus" ? { overdueDays: "" } : {}),
                    page: "",
                  })
                }
              >
                {label}: {value} ×
              </button>
            ))}
            <button
              className="text-xs text-slate-500 hover:text-slate-900"
              onClick={() =>
                updateParams({
                  status: "",
                  expiringDays: "",
                  paymentStatus: "",
                  overdueDays: "",
                  packageId: "",
                  trainerId: "",
                  page: "",
                })
              }
            >
              Xóa bộ lọc
            </button>
          </div>
        )}
        <DataTable
          columns={displayColumns}
          rows={members.data?.items}
          loading={members.isLoading}
          error={members.error}
          onRetry={members.refetch}
          selection={canOperate ? selection : undefined}
          onSelectionChange={canOperate ? setSelection : undefined}
          onRowClick={openMember}
          selectedRowId={Number(memberId)}
          density={density}
          emptyTitle={
            search || activeFilters.length || view !== "all"
              ? "Không có hội viên phù hợp"
              : "Chưa có hội viên"
          }
          emptyDescription={
            search || activeFilters.length || view !== "all"
              ? "Xóa bớt bộ lọc hoặc thử từ khóa khác."
              : "Thêm hội viên đầu tiên để bắt đầu vận hành."
          }
          emptyAction={
            search || activeFilters.length || view !== "all" ? (
              <Button
                size="sm"
                variant="secondary"
                onClick={() => {
                  applySystemView("all");
                  updateParams({ q: "", sort: "" });
                }}
              >
                Xóa tìm kiếm và bộ lọc
              </Button>
            ) : canOperate ? (
              <Button size="sm" onClick={() => setCreateOpen(true)}>
                <Plus size={14} /> Thêm hội viên
              </Button>
            ) : null
          }
        />
        <Pagination
          data={members.data?.pagination}
          onPage={(value) => updateParams({ page: value })}
          pageSize={pageSize}
          onPageSize={(value) => updateParams({ pageSize: value, page: "" })}
        />
      </div>
      <MemberQuickDrawer
        memberId={memberId}
        onClose={() => updateParams({ member: "", action: "" })}
        initialAction={action}
        onActionConsumed={clearMemberAction}
      />
      <Modal
        open={saveViewOpen}
        onClose={() => setSaveViewOpen(false)}
        title="Lưu chế độ xem"
        description="Lưu bộ lọc và thứ tự hiện tại cho lần làm việc sau."
      >
        <form onSubmit={saveView}>
          <div className="modal-body">
            <Field label="Tên chế độ xem" required>
              <Input
                autoFocus
                value={viewName}
                onChange={(event) => setViewName(event.target.value)}
                placeholder="Ví dụ: Khách cần gọi hôm nay"
              />
            </Field>
          </div>
          <div className="form-actions">
            <Button
              data-modal-close
              variant="secondary"
              onClick={() => setSaveViewOpen(false)}
            >
              Hủy
            </Button>
            <Button type="submit" disabled={!viewName.trim()}>
              Lưu
            </Button>
          </div>
        </form>
      </Modal>
      <Modal
        open={createOpen}
        onClose={closeCreate}
        dirty={JSON.stringify(form) !== JSON.stringify(initialForm)}
        title="Thêm hội viên"
        description="Tạo hồ sơ và có thể đăng ký lịch PT ngay trong một lần lưu."
      >
        <form
          onSubmit={(event) => {
            event.preventDefault();
            setError("");
            if (!form.name.trim()) {
              setError("Họ tên không được để trống.");
              return;
            }
            if (normalizePhone(form.phone).length !== 10) {
              setError("Số điện thoại cần đủ 10 chữ số.");
              return;
            }
            if (form.registerMembership) {
              const debt =
                Number(form.membership.finalPrice || 0) -
                Number(form.membership.paidAmount || 0);
              if (!form.membership.planId) {
                setError("Vui lòng chọn gói tập.");
                return;
              }
              if (debt > 0 && !form.membership.debtDueDate) {
                setError("Vui lòng chọn hạn thanh toán cho phần công nợ.");
                return;
              }
              if (
                Number(form.membership.paidAmount || 0) > 0 &&
                form.membership.paymentMethod === "bank_transfer" &&
                !form.membership.bankAccountId
              ) {
                setError("Vui lòng chọn tài khoản nhận tiền khi thanh toán chuyển khoản.");
                return;
              }
            }
            const {
              registerPt,
              pt,
              registerMembership,
              membership,
              dahIdentityName,
              dahIdentityImageData,
              dahIdentityTime,
              ...memberForm
            } = form;
            create.mutate({
              ...memberForm,
              name: form.name.trim(),
              phone: normalizePhone(form.phone),
              email: form.email.trim(),
              membership: registerMembership ? membership : undefined,
              ptEnrollment: registerPt ? pt : undefined,
            });
          }}
        >
          <div className="modal-body space-y-5">
            <section className="form-section">
              <h3 className="form-section-title">Thông tin cá nhân</h3>
              <div className="form-grid">
                <Field label="Họ tên" required>
                  <Input
                    autoFocus
                    autoComplete="name"
                    value={form.name}
                    onChange={(e) => setForm({ ...form, name: e.target.value })}
                  />
                </Field>
                <Field label="Điện thoại" required>
                  <PhoneInput
                    required
                    value={form.phone}
                    onChange={(phone) => setForm({ ...form, phone })}
                  />
                </Field>
                <Field label="Email">
                  <Input
                    type="email"
                    autoComplete="email"
                    value={form.email}
                    onChange={(e) =>
                      setForm({ ...form, email: e.target.value })
                    }
                  />
                </Field>
                <Field label="Giới tính">
                  <Select
                    value={form.gender}
                    onChange={(e) =>
                      setForm({ ...form, gender: e.target.value })
                    }
                  >
                    <option value="">Chưa chọn</option>
                    <option>Nam</option>
                    <option>Nữ</option>
                    <option>Khác</option>
                  </Select>
                </Field>
                <Field label="Ngày sinh">
                  <DateOfBirthInput
                    value={form.dateOfBirth}
                    onChange={(dateOfBirth) =>
                      setForm({ ...form, dateOfBirth })
                    }
                  />
                </Field>
                <Field label="Mã thẻ MBS">
                  <Input
                    value={form.mbsCode}
                    onChange={(e) =>
                      setForm({ ...form, mbsCode: e.target.value })
                    }
                  />
                </Field>
              </div>
            </section>
            <section className="form-section">
              <h3 className="form-section-title">Định danh DAH</h3>
              <div className="identity-link-summary">
                <div className="identity-face">
                  {form.dahIdentityImageData ? (
                    <img src={form.dahIdentityImageData} alt="" />
                  ) : (
                    <ScanFace size={22} />
                  )}
                </div>
                <div>
                  <strong>
                    {form.personUuid ? "Đã chọn định danh" : "Chưa liên kết"}
                  </strong>
                  <span>
                    {form.personUuid ||
                      "Quét mặt trên DAH rồi chọn PersonUUID mới."}
                  </span>
                  {form.dahIdentityName && (
                    <small>
                      {form.dahIdentityName} · {dateTime(form.dahIdentityTime)}
                    </small>
                  )}
                </div>
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => setIdentityLinkOpen(true)}
                >
                  <ScanFace size={15} />
                  {form.personUuid ? "Đổi định danh" : "Liên kết định danh"}
                </Button>
              </div>
            </section>
            <section className="form-section">
              <h3 className="form-section-title">Phụ trách</h3>
              <div className="form-grid">
                <Field label="Nhân viên phụ trách">
                  <SearchableSelect
                    value={form.salesEmployeeId}
                    onChange={(salesEmployeeId) =>
                      setForm({ ...form, salesEmployeeId })
                    }
                    clearable
                    placeholder="Chưa phân công"
                    searchPlaceholder="Tên hoặc mã nhân viên…"
                    options={
                      options.data?.salesEmployees.map((row) => ({
                        value: row.id,
                        label: row.name,
                        meta: `${row.code} · ${row.title || "Nhân viên"}`,
                      })) || []
                    }
                  />
                </Field>
                <Field className="form-span" label="Ghi chú">
                  <Textarea
                    value={form.notes}
                    onChange={(e) =>
                      setForm({ ...form, notes: e.target.value })
                    }
                  />
                </Field>
              </div>
            </section>
            <section className="form-section">
              <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
                <input
                  type="checkbox"
                  className="mt-0.5 h-4 w-4 accent-navy-900"
                  checked={form.registerMembership}
                  onChange={(event) =>
                    setForm({ ...form, registerMembership: event.target.checked })
                  }
                />
                <span>
                  <strong className="block text-sm text-slate-800">
                    Đăng ký gói tập và thu tiền ngay
                  </strong>
                  <small className="mt-0.5 block text-xs text-slate-500">
                    Hồ sơ, gói tập và giao dịch thu tiền sẽ được lưu cùng lúc.
                  </small>
                </span>
              </label>
              {form.registerMembership && (
                <div className="mt-4 space-y-4">
                  <div className="form-grid">
                    <Field className="form-span" label="Gói tập" required>
                      <SearchableSelect
                        value={form.membership.planId}
                        onChange={selectMembershipPlan}
                        placeholder="Chọn gói tập"
                        searchPlaceholder="Tìm theo tên hoặc danh mục..."
                        options={
                          options.data?.plans.map((row) => ({
                            value: row.id,
                            label: row.name,
                            meta: `${row.category} · ${money(row.price)} · ${row.durationDays} ngày`,
                          })) || []
                        }
                      />
                    </Field>
                    <Field label="Ngày bắt đầu">
                      <DateInput
                        value={form.membership.startsAt}
                        onChange={(startsAt) => {
                          const plan = options.data?.plans.find(
                            (row) => String(row.id) === String(form.membership.planId),
                          );
                          updateMembershipDraft({
                            startsAt,
                            expiresAt:
                              plan?.durationDays && startsAt
                                ? format(addDays(new Date(`${startsAt}T00:00:00`), plan.durationDays), "yyyy-MM-dd")
                                : form.membership.expiresAt,
                          });
                        }}
                      />
                    </Field>
                    <Field label="Ngày hết hạn">
                      <DateInput
                        value={form.membership.expiresAt}
                        onChange={(expiresAt) => updateMembershipDraft({ expiresAt })}
                      />
                    </Field>
                    <Field label="Tổng tiền">
                      <MoneyInput
                        value={form.membership.finalPrice}
                        onChange={(finalPrice) => updateMembershipDraft({ finalPrice })}
                      />
                    </Field>
                    <Field label="Thanh toán lần này">
                      <MoneyInput
                        value={form.membership.paidAmount}
                        max={Number(form.membership.finalPrice) || 0}
                        onChange={(paidAmount) => updateMembershipDraft({ paidAmount })}
                      />
                    </Field>
                    {Number(form.membership.finalPrice || 0) - Number(form.membership.paidAmount || 0) > 0 && (
                      <Field label="Hạn công nợ">
                        <DateInput
                          value={form.membership.debtDueDate}
                          onChange={(debtDueDate) => updateMembershipDraft({ debtDueDate })}
                        />
                      </Field>
                    )}
                    <Field label="Phương thức">
                      <Select
                        value={form.membership.paymentMethod}
                        onChange={(event) =>
                          updateMembershipDraft({
                            paymentMethod: event.target.value,
                            bankAccountId:
                              event.target.value === "cash"
                                ? ""
                                : form.membership.bankAccountId,
                          })
                        }
                      >
                        <option value="cash">Tiền mặt</option>
                        <option value="bank_transfer">Chuyển khoản</option>
                        <option value="card">Thẻ</option>
                      </Select>
                    </Field>
                    {form.membership.paymentMethod !== "cash" && (
                      <Field label="Tài khoản nhận" required={form.membership.paymentMethod === "bank_transfer"}>
                        <Select
                          value={form.membership.bankAccountId}
                          onChange={(event) =>
                            updateMembershipDraft({ bankAccountId: event.target.value })
                          }
                        >
                          <option value="">Chọn tài khoản</option>
                          {options.data?.bankAccounts.map((row) => (
                            <option key={row.id} value={row.id}>
                              {row.label}
                            </option>
                          ))}
                        </Select>
                      </Field>
                    )}
                  </div>
                  <div className="rounded-md border border-slate-200 bg-white px-3 py-2 text-xs">
                    <span className="text-slate-500">Công nợ sau khi tạo</span>
                    <strong className={`ml-2 ${Number(form.membership.finalPrice || 0) - Number(form.membership.paidAmount || 0) > 0 ? "text-red-700" : "text-emerald-700"}`}>
                      {money(Math.max(Number(form.membership.finalPrice || 0) - Number(form.membership.paidAmount || 0), 0))}
                    </strong>
                  </div>
                </div>
              )}
            </section>
            <section className="form-section">
              <label className="flex cursor-pointer items-start gap-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
                <input
                  type="checkbox"
                  className="mt-0.5 h-4 w-4 accent-navy-900"
                  checked={form.registerPt}
                  onChange={(event) =>
                    setForm({ ...form, registerPt: event.target.checked })
                  }
                />
                <span>
                  <strong className="block text-sm text-slate-800">
                    Đăng ký PT cho hội viên này
                  </strong>
                  <small className="mt-0.5 block text-xs text-slate-500">
                    Hồ sơ hội viên và đăng ký PT sẽ được lưu cùng lúc.
                  </small>
                </span>
              </label>
              {form.registerPt && (
                <div className="mt-4">
                  <TrainingFields
                    form={form.pt}
                    setForm={(pt) => setForm((current) => ({ ...current, pt }))}
                    options={options.data}
                  />
                </div>
              )}
            </section>
            {error && <div className="inline-error">{error}</div>}
          </div>
          <div className="form-actions">
            <Button data-modal-close variant="secondary" onClick={closeCreate}>
              Hủy
            </Button>
            <Button
              type="submit"
              loading={create.isPending}
              loadingText="Đang tạo…"
            >
              Tạo hội viên
            </Button>
          </div>
        </form>
      </Modal>
      <DahIdentityLinkModal
        open={identityLinkOpen}
        onClose={() => setIdentityLinkOpen(false)}
        onSelect={(candidate) =>
          setForm((current) => ({
            ...current,
            personUuid: candidate.personUuid,
            dahEventId: candidate.eventId,
            dahIdentityName: candidate.name || "",
            dahIdentityImageData: candidate.imageData || "",
            dahIdentityTime: candidate.eventTime || "",
          }))
        }
      />
    </>
  );
}
