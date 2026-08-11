import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CalendarPlus,
  CreditCard,
  Dumbbell,
  ExternalLink,
  Pencil,
  ScanFace,
  TriangleAlert,
} from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "../../services/api";
import { notify } from "../../services/notify";
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
import { ScheduleSummary } from "../../components/ui/ScheduleSummary";
import { InlineEditField } from "../../components/ui/InlineEditField";
import { MemberEditForm } from "../../components/forms/MemberEditForm";
import { MembershipForm } from "../../components/forms/MembershipForm";
import { TrainingForm } from "../../components/forms/TrainingForm";
import { QuickPaymentForm } from "../../components/forms/QuickPaymentForm";
import { DebtDeadlineForm } from "../../components/forms/DebtDeadlineForm";
import { useAuth } from "../../app/AuthContext";
import { DahIdentityLinkModal } from "./DahIdentityLinkModal";

export function MemberQuickDrawer({
  memberId,
  onClose,
  initialAction,
  onActionConsumed,
}) {
  const { user } = useAuth();
  const canFinancial = ["admin", "manager", "receptionist"].includes(
    user?.role,
  );
  const client = useQueryClient();
  const [dialog, setDialog] = useState(null);
  const [identityLinkOpen, setIdentityLinkOpen] = useState(false);
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
    mutationFn: ({ payload }) =>
      api(`/api/members/${memberId}`, { method: "PATCH", body: payload }),
    onSuccess: (_data, variables) => {
      refresh();
      if (!variables.silent) {
        setDialog(null);
        notify.success(`Đã lưu hồ sơ ${member.name}.`);
      }
    },
    onError: (e, variables) => {
      if (!variables.silent) setFormError(e.message);
    },
  });
  const membershipSave = useMutation({
    mutationFn: ({ id, data }) =>
      api(id ? `/api/memberships/${id}` : "/api/memberships", {
        method: id ? "PATCH" : "POST",
        body: data,
      }),
    onSuccess: (_data, variables) => {
      refresh();
      setDialog(null);
      if (variables.feedback?.amount) {
        notify.success(
          `Đã ghi nhận ${money(variables.feedback.amount)} cho ${member.name}.`,
        );
      } else if (variables.feedback?.expiresAt) {
        notify.success(
          `Đã lưu ${variables.feedback.planName} đến ${shortDate(variables.feedback.expiresAt)} cho ${member.name}.`,
        );
      } else {
        notify.success(`Đã cập nhật gói tập của ${member.name}.`);
      }
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
      notify.success(`Đã lưu hạn thanh toán cho ${member.name}.`);
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
      notify.success(`Đã cập nhật đăng ký PT của ${member.name}.`);
    },
    onError: (e) => setFormError(e.message),
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
    if (!memberId) {
      setDialog(null);
      setIdentityLinkOpen(false);
    }
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
                data-member-full-profile="true"
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
              <div className="avatar h-11 w-11">
                {member.avatarImageData ? (
                  <img src={member.avatarImageData} alt="" />
                ) : (
                  initials(member.name)
                )}
              </div>
              <div className="min-w-0 flex-1">
                <strong className="block truncate text-[15px] font-semibold text-slate-950">
                  {member.name}
                </strong>
                <span className="text-xs text-slate-400">{member.code}</span>
              </div>
              <StatusBadge status={member.status} />
            </div>
            {canFinancial && <div className="quick-action-bar">
              <button
                className="quick-action"
                onClick={() => openDialog("edit")}
              >
                <Pencil size={17} />
                <span>Sửa hồ sơ</span>
              </button>
              <button
                className="quick-action"
                onClick={() =>
                  current?.debtAmount
                    ? openDialog("payment")
                    : notify.info("Hội viên hiện không có công nợ.")
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
            </div>}
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
                  {canFinancial && <button onClick={() => openDialog("renew")}>Gia hạn</button>}
                </div>
              )}
              {current?.debtAmount > 0 && (
                <div className="detail-alert debt">
                  <span className="flex items-center gap-2">
                    <TriangleAlert size={15} />
                    Công nợ {money(current.debtAmount)}
                  </span>
                  {canFinancial && <button onClick={() => openDialog("payment")}>
                    Thu tiền
                  </button>}
                </div>
              )}
              {!training && (
                <div className="detail-alert">
                  <span className="flex items-center gap-2">
                    <TriangleAlert size={15} />
                    Chưa đăng ký PT
                  </span>
                  {canFinancial && <button onClick={() => openDialog("training")}>
                    Đăng ký PT
                  </button>}
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
                      {canFinancial && current.debtAmount > 0 && (
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
                        {canFinancial ? <button
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
                        </button> : (current.debtDueDate ? shortDate(current.debtDueDate) : "Chưa đặt hạn")}
                      </dd>
                    </div>
                  )}
                </dl>
              ) : (
                <div className="flex items-center justify-between text-sm">
                  <span className="text-slate-400">Chưa có gói tập</span>
                  {canFinancial && <Button size="sm" onClick={() => openDialog("renew")}>
                    Đăng ký gói
                  </Button>}
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
                    ) : canFinancial ? (
                      <button
                        className="text-xs font-medium text-blue-700"
                        onClick={() => openDialog("training")}
                      >
                        + Gán PT
                      </button>
                    ) : "Chưa đăng ký"}
                  </dd>
                </div>
                <div className="inline-field">
                  <dt>Lịch PT</dt>
                  <dd>
                    {training
                      ? (
                        <ScheduleSummary
                          schedule={training.schedule}
                          scheduleDays={training.scheduleDays}
                          scheduleTime={training.scheduleTime}
                          emptyText="Chưa chọn thứ"
                          compact
                        />
                      )
                      : "—"}
                  </dd>
                </div>
              </dl>
            </section>
            <section className="detail-section">
              <h3 className="detail-section-title">Liên hệ & phụ trách</h3>
              <dl>
                {canFinancial ? (
                  <>
                    <InlineEditField label="Điện thoại" value={member.phone} type="tel" displayValue={formatPhone(member.phone)} onSave={(phone) => update.mutateAsync({ payload: { phone }, silent: true })} pending={update.isPending} />
                    <InlineEditField label="Email" value={member.email} type="email" emptyAction="+ Thêm email" onSave={(email) => update.mutateAsync({ payload: { email }, silent: true })} pending={update.isPending} />
                    <InlineEditField label="Nguồn khách" value={member.source} onSave={(source) => update.mutateAsync({ payload: { source }, silent: true })} pending={update.isPending} />
                    <div className="inline-field"><dt>Sale phụ trách</dt><dd>{member.salesEmployee || "Chưa gán"}</dd></div>
                    <div className="inline-field">
                      <dt>Định danh DAH</dt>
                      <dd>
                        {member.personUuid ? (
                          <span className="font-mono text-[12px]">{member.personUuid}</span>
                        ) : (
                          <button className="inline-flex items-center gap-1 text-xs font-medium text-blue-700" onClick={() => setIdentityLinkOpen(true)}>
                            <ScanFace size={13} /> Liên kết định danh
                          </button>
                        )}
                      </dd>
                    </div>
                    <InlineEditField label="Trạng thái" value={member.status} displayValue={<StatusBadge status={member.status} />} type="select" options={[{ value: "lead", label: "Tiềm năng" }, { value: "active", label: "Đang hoạt động" }, { value: "frozen", label: "Bảo lưu" }, { value: "blocked", label: "Đã khóa" }, { value: "inactive", label: "Tạm ngừng" }]} onSave={(status) => update.mutateAsync({ payload: { status }, silent: true })} pending={update.isPending} />
                  </>
                ) : (
                  <>
                    <div className="inline-field"><dt>Điện thoại</dt><dd>{formatPhone(member.phone) || "—"}</dd></div>
                    <div className="inline-field"><dt>Email</dt><dd>{member.email || "—"}</dd></div>
                    <div className="inline-field"><dt>Nguồn khách</dt><dd>{member.source || "—"}</dd></div>
                    <div className="inline-field"><dt>Sale phụ trách</dt><dd>{member.salesEmployee || "Chưa gán"}</dd></div>
                    <div className="inline-field"><dt>Định danh DAH</dt><dd>{member.personUuid || "Chưa liên kết"}</dd></div>
                    <div className="inline-field"><dt>Trạng thái</dt><dd><StatusBadge status={member.status} /></dd></div>
                  </>
                )}
              </dl>
            </section>
            {member.notes && (
              <section className="detail-section">
                <h3 className="detail-section-title">
                  Ghi chú quan trọng{" "}
                  {canFinancial && <button
                    className="normal-case text-blue-700"
                    onClick={() => openDialog("edit")}
                  >
                    Chỉnh sửa
                  </button>}
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
            onSubmit={(payload) => update.mutate({ payload })}
            pending={update.isPending}
            error={formError}
          />
          <MembershipForm
            memberId={member.id}
            member={member}
            currentMembership={current}
            options={options.data}
            open={dialog === "renew"}
            onClose={() => setDialog(null)}
            onSubmit={(data, feedback) =>
              membershipSave.mutate({ data, feedback })
            }
            pending={membershipSave.isPending}
            error={formError}
          />
          <QuickPaymentForm
            membership={current}
            options={options.data}
            open={dialog === "payment"}
            onClose={() => setDialog(null)}
            onSubmit={(data, feedback) =>
              membershipSave.mutate({ id: current.id, data, feedback })
            }
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
          <DahIdentityLinkModal
            open={identityLinkOpen}
            onClose={() => setIdentityLinkOpen(false)}
            memberId={member.id}
            memberName={member.name}
            onLinked={() => {
              refresh();
              notify.success(`Đã liên kết định danh DAH cho ${member.name}.`);
            }}
          />
        </>
      )}
    </>
  );
}
