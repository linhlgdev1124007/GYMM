import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarPlus,
  CheckCircle2,
  CreditCard,
  Dumbbell,
  ExternalLink,
  Pencil,
  TriangleAlert,
} from "lucide-react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { api } from "../../services/api";
import {
  dateTime,
  formatPhone,
  initials,
  money,
  shortDate,
} from "../../utils/format";
import { Drawer } from "../../components/ui/Drawer";
import { Button } from "../../components/ui/Button";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { InlineEditField } from "../../components/ui/InlineEditField";
import { MemberEditForm } from "../../components/forms/MemberEditForm";
import { MembershipForm } from "../../components/forms/MembershipForm";
import { TrainingForm } from "../../components/forms/TrainingForm";
import { QuickPaymentForm } from "../../components/forms/QuickPaymentForm";
import { DebtDeadlineForm } from "../../components/forms/DebtDeadlineForm";

export function MemberQuickDrawer({
  memberId,
  onClose,
  initialAction,
  onActionConsumed,
}) {
  const client = useQueryClient();
  const [dialog, setDialog] = useState(null);
  const [formError, setFormError] = useState("");
  const memberQuery = useQuery({
    queryKey: ["member", memberId],
    queryFn: () => api(`/api/members/${memberId}`),
    enabled: !!memberId,
  });
  const options = useQuery({
    queryKey: ["member-options"],
    queryFn: () => api("/api/members/options"),
    staleTime: 300000,
  });
  const member = memberQuery.data;
  const refresh = () => {
    client.invalidateQueries({ queryKey: ["member", memberId] });
    client.invalidateQueries({ queryKey: ["members"] });
    client.invalidateQueries({ queryKey: ["memberships"] });
    client.invalidateQueries({ queryKey: ["training"] });
    client.invalidateQueries({ queryKey: ["dashboard"] });
  };
  const update = useMutation({
    mutationFn: (payload) =>
      api(`/api/members/${memberId}`, { method: "PATCH", body: payload }),
    onSuccess: () => {
      refresh();
      setDialog(null);
      toast.success("Đã cập nhật hội viên.");
    },
    onError: (e) => setFormError(e.message),
  });
  const membershipSave = useMutation({
    mutationFn: ({ id, data }) =>
      api(id ? `/api/memberships/${id}` : "/api/memberships", {
        method: id ? "PATCH" : "POST",
        body: data,
      }),
    onSuccess: () => {
      refresh();
      setDialog(null);
      toast.success("Đã cập nhật gói và thanh toán.");
    },
    onError: (e) => setFormError(e.message),
  });
  const deadlineSave = useMutation({
    mutationFn: (payload) =>
      api(`/api/memberships/${current.id}/debt-due-date`, {
        method: "PATCH",
        body: payload,
      }),
    onSuccess: () => {
      refresh();
      setDialog(null);
      toast.success("Đã lưu hạn thanh toán.");
    },
    onError: (e) => setFormError(e.message),
  });
  const trainingSave = useMutation({
    mutationFn: ({ id, payload }) =>
      api(id ? `/api/training/${id}` : `/api/members/${memberId}/training`, {
        method: id ? "PATCH" : "POST",
        body: payload,
      }),
    onSuccess: () => {
      refresh();
      setDialog(null);
      toast.success("Đã lưu PT cho hội viên.");
    },
    onError: (e) => setFormError(e.message),
  });
  const checkin = useMutation({
    mutationFn: () =>
      api("/api/checkins", {
        method: "POST",
        body: { memberId: Number(memberId) },
      }),
    onSuccess: () => {
      refresh();
      toast.success("Check-in thành công.");
    },
    onError: (e) => toast.error(e.message),
  });
  const current = member?.memberships[0];
  const training = member?.training.find((row) => row.status === "active");
  const trainingCoaches = training?.coaches || [];
  const lastCheckin = member?.checkins[0];
  const daysLeft = current?.expiresAt
    ? Math.ceil((new Date(current.expiresAt) - new Date()) / 86400000)
    : null;
  const openDialog = (name) => {
    setFormError("");
    setDialog(name);
  };
  useEffect(() => {
    if (member && initialAction) {
      openDialog(initialAction);
      onActionConsumed?.();
    }
  }, [member, initialAction, onActionConsumed]);
  useEffect(() => {
    if (!memberId) setDialog(null);
  }, [memberId]);
  return (
    <>
      <Drawer
        open={!!memberId}
        onClose={onClose}
        title={member?.name || "Thông tin hội viên"}
        description={
          member
            ? `${member.code} · ${member.phone || "Chưa có số điện thoại"}`
            : "Đang tải…"
        }
        footer={
          member && (
            <>
              <span className="text-xs text-slate-400">
                Thông tin chi tiết và lịch sử
              </span>
              <Link
                className="inline-flex items-center gap-1 text-xs font-medium text-navy-800 hover:underline"
                to={`/members/${member.id}`}
              >
                Xem hồ sơ đầy đủ <ExternalLink size={12} />
              </Link>
            </>
          )
        }
      >
        {memberQuery.isLoading && (
          <div className="space-y-4 p-5">
            <div className="skeleton h-16" />
            <div className="skeleton h-48" />
            <div className="skeleton h-32" />
          </div>
        )}
        {memberQuery.isError && (
          <div className="m-5 inline-error">{memberQuery.error.message}</div>
        )}
        {member && (
          <>
            <div className="flex items-center gap-3 border-b border-slate-200 px-5 py-4">
              <div className="avatar h-11 w-11">{initials(member.name)}</div>
              <div className="min-w-0 flex-1">
                <strong className="block truncate text-[15px] font-semibold text-slate-950">
                  {member.name}
                </strong>
                <span className="text-xs text-slate-400">{member.code}</span>
              </div>
              <StatusBadge status={member.status} />
            </div>
            <div className="quick-action-bar">
              <button
                className="quick-action"
                onClick={() => checkin.mutate()}
                disabled={checkin.isPending}
              >
                <CheckCircle2 size={17} />
                <span>Check-in</span>
              </button>
              <button
                className="quick-action"
                onClick={() =>
                  current?.debtAmount
                    ? openDialog("payment")
                    : toast.info("Hội viên hiện không có công nợ.")
                }
              >
                <CreditCard size={17} />
                <span>Thu tiền</span>
              </button>
              <button
                className="quick-action"
                onClick={() => openDialog("renew")}
              >
                <CalendarPlus size={17} />
                <span>Gia hạn</span>
              </button>
              <button
                className="quick-action"
                onClick={() => openDialog("training")}
              >
                <Dumbbell size={17} />
                <span>{training ? "Đổi PT" : "Gán PT"}</span>
              </button>
              <button
                className="quick-action"
                onClick={() => openDialog("edit")}
              >
                <Pencil size={17} />
                <span>Chỉnh sửa</span>
              </button>
            </div>
            <section className="detail-section">
              {daysLeft != null && daysLeft <= 14 && (
                <div className="detail-alert">
                  <span className="flex items-center gap-2">
                    <TriangleAlert size={15} />
                    Gói{" "}
                    {daysLeft < 0
                      ? "đã hết hạn"
                      : `hết hạn sau ${daysLeft} ngày`}
                  </span>
                  <button onClick={() => openDialog("renew")}>Gia hạn</button>
                </div>
              )}
              {current?.debtAmount > 0 && (
                <div className="detail-alert debt">
                  <span className="flex items-center gap-2">
                    <TriangleAlert size={15} />
                    Công nợ {money(current.debtAmount)}
                  </span>
                  <button onClick={() => openDialog("payment")}>
                    Thu tiền
                  </button>
                </div>
              )}
              {!training && (
                <div className="detail-alert">
                  <span className="flex items-center gap-2">
                    <TriangleAlert size={15} />
                    Chưa đăng ký PT
                  </span>
                  <button onClick={() => openDialog("training")}>
                    Đăng ký PT
                  </button>
                </div>
              )}
              {training && !trainingCoaches.length && (
                <div className="detail-alert">
                  <span className="flex items-center gap-2">
                    <TriangleAlert size={15} />
                    Đăng ký PT chưa có Coach
                  </span>
                  <button onClick={() => openDialog("training")}>
                    Phân công
                  </button>
                </div>
              )}
              <h3 className="detail-section-title">Gói tập</h3>
              {current ? (
                <dl>
                  <div className="inline-field">
                    <dt>Gói hiện tại</dt>
                    <dd className="font-medium">{current.package.name}</dd>
                  </div>
                  <div className="inline-field">
                    <dt>Thời hạn</dt>
                    <dd>
                      {shortDate(current.startsAt)} →{" "}
                      {shortDate(current.expiresAt)}
                    </dd>
                  </div>
                  <div className="inline-field">
                    <dt>Còn lại</dt>
                    <dd>
                      {daysLeft == null
                        ? "—"
                        : daysLeft < 0
                          ? `Quá hạn ${Math.abs(daysLeft)} ngày`
                          : `${daysLeft} ngày`}
                    </dd>
                  </div>
                  <div className="inline-field">
                    <dt>Đã thanh toán</dt>
                    <dd>{money(current.paidAmount)}</dd>
                  </div>
                  <div className="inline-field">
                    <dt>Công nợ</dt>
                    <dd
                      className={
                        current.debtAmount
                          ? "font-medium text-red-700"
                          : "text-emerald-700"
                      }
                    >
                      {money(current.debtAmount)}
                      {current.debtAmount > 0 && (
                        <button
                          className="ml-3 text-xs font-medium text-blue-700"
                          onClick={() => openDialog("payment")}
                        >
                          Thu tiền
                        </button>
                      )}
                    </dd>
                  </div>
                  {current.debtAmount > 0 && (
                    <div className="inline-field">
                      <dt>Hạn thanh toán</dt>
                      <dd>
                        <button
                          className={
                            current.debtDueDate &&
                            new Date(`${current.debtDueDate}T23:59:59`) <
                              new Date()
                              ? "font-medium text-red-700 hover:underline"
                              : "font-medium text-blue-700 hover:underline"
                          }
                          onClick={() => openDialog("deadline")}
                        >
                          {current.debtDueDate
                            ? `${shortDate(current.debtDueDate)} · Đổi hạn`
                            : "+ Đặt hạn"}
                        </button>
                      </dd>
                    </div>
                  )}
                </dl>
              ) : (
                <div className="flex items-center justify-between text-sm">
                  <span className="text-slate-400">Chưa có gói tập</span>
                  <Button size="sm" onClick={() => openDialog("renew")}>
                    Đăng ký gói
                  </Button>
                </div>
              )}
            </section>
            <section className="detail-section">
              <h3 className="detail-section-title">Vận hành</h3>
              <dl>
                <div className="inline-field">
                  <dt>Check-in gần nhất</dt>
                  <dd>
                    {lastCheckin
                      ? dateTime(lastCheckin.checkedInAt)
                      : "Chưa có"}
                  </dd>
                </div>
                <div className="inline-field">
                  <dt>Check-in gần đây</dt>
                  <dd>{member.checkins.length} lượt được ghi nhận</dd>
                </div>
                <div className="inline-field">
                  <dt>PT hiện tại</dt>
                  <dd>
                    {training ? (
                      `${trainingCoaches.map((coach) => coach.name).join(", ") || "Chưa phân công"} · ${training.type}`
                    ) : (
                      <button
                        className="text-xs font-medium text-blue-700"
                        onClick={() => openDialog("training")}
                      >
                        + Gán PT
                      </button>
                    )}
                  </dd>
                </div>
                <div className="inline-field">
                  <dt>Lịch PT</dt>
                  <dd>
                    {training
                      ? `${training.scheduleDays.join(", ") || "Chưa chọn thứ"} · ${training.scheduleTime || "Chưa chọn giờ"}`
                      : "—"}
                  </dd>
                </div>
              </dl>
            </section>
            <section className="detail-section">
              <h3 className="detail-section-title">Liên hệ & phụ trách</h3>
              <dl>
                <InlineEditField
                  label="Điện thoại"
                  value={member.phone}
                  type="tel"
                  displayValue={formatPhone(member.phone)}
                  onSave={(phone) => update.mutateAsync({ phone })}
                  pending={update.isPending}
                />
                <InlineEditField
                  label="Email"
                  value={member.email}
                  type="email"
                  emptyAction="+ Thêm email"
                  onSave={(email) => update.mutateAsync({ email })}
                  pending={update.isPending}
                />
                <InlineEditField
                  label="Nguồn khách"
                  value={member.source}
                  onSave={(source) => update.mutateAsync({ source })}
                  pending={update.isPending}
                />
                <InlineEditField
                  label="Trạng thái"
                  value={member.status}
                  displayValue={<StatusBadge status={member.status} />}
                  type="select"
                  options={[
                    { value: "lead", label: "Tiềm năng" },
                    { value: "active", label: "Đang hoạt động" },
                    { value: "frozen", label: "Bảo lưu" },
                    { value: "blocked", label: "Đã khóa" },
                    { value: "inactive", label: "Tạm ngừng" },
                  ]}
                  onSave={(status) => update.mutateAsync({ status })}
                  pending={update.isPending}
                />
              </dl>
            </section>
            {member.notes && (
              <section className="detail-section">
                <h3 className="detail-section-title">
                  Ghi chú quan trọng{" "}
                  <button
                    className="normal-case text-blue-700"
                    onClick={() => openDialog("edit")}
                  >
                    Chỉnh sửa
                  </button>
                </h3>
                <p className="text-[13px] leading-5 text-slate-700">
                  {member.notes}
                </p>
              </section>
            )}
          </>
        )}
      </Drawer>
      {member && (
        <>
          <MemberEditForm
            member={member}
            options={options.data}
            open={dialog === "edit"}
            onClose={() => setDialog(null)}
            onSubmit={(payload) => update.mutate(payload)}
            pending={update.isPending}
            error={formError}
          />
          <MembershipForm
            memberId={member.id}
            options={options.data}
            open={dialog === "renew"}
            onClose={() => setDialog(null)}
            onSubmit={(data) => membershipSave.mutate({ data })}
            pending={membershipSave.isPending}
            error={formError}
          />
          <QuickPaymentForm
            membership={current}
            options={options.data}
            open={dialog === "payment"}
            onClose={() => setDialog(null)}
            onSubmit={(data) => membershipSave.mutate({ id: current.id, data })}
            pending={membershipSave.isPending}
            error={formError}
          />
          <DebtDeadlineForm
            membership={current}
            open={dialog === "deadline"}
            onClose={() => setDialog(null)}
            onSubmit={(payload) => deadlineSave.mutate(payload)}
            pending={deadlineSave.isPending}
            error={formError}
          />
          <TrainingForm
            enrollment={training}
            options={options.data}
            open={dialog === "training"}
            onClose={() => setDialog(null)}
            onSubmit={(payload) =>
              trainingSave.mutate({ id: training?.id, payload })
            }
            pending={trainingSave.isPending}
            error={formError}
          />
        </>
      )}
    </>
  );
}
