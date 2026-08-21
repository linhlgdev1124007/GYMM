import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Eye, Pencil, Plus, RefreshCw, Save, Trash2, Upload, Volume2, X } from "lucide-react";
import { api } from "../../services/api";
import { notify } from "../../services/notify";
import { PageHeader } from "../../components/common/PageHeader";
import { Button } from "../../components/ui/Button";
import { DataTable } from "../../components/ui/DataTable";
import { Field, Input, Select } from "../../components/ui/Form";
import { Modal } from "../../components/ui/Modal";
import { StatusBadge } from "../../components/ui/StatusBadge";
import { dateTime } from "../../utils/format";
import { availableSpeechVoices, speakVietnamese } from "../../services/speech";

const blankTitle = { name: "", isPtRole: false, active: true };
const blankAccount = {
  bank: "",
  accountName: "",
  accountNumber: "",
  visibility: "public",
  status: "active",
};

function titleForm(row) {
  return row
    ? { name: row.name || "", isPtRole: !!row.isPtRole, active: row.active !== false }
    : blankTitle;
}

function accountForm(row) {
  return row
    ? {
        bank: row.bank || "",
        accountName: row.accountName || "",
        accountNumber: row.accountNumber || "",
        visibility: row.visibility || "public",
        status: row.status || "active",
      }
    : blankAccount;
}

function canSyncDahEvent(event) {
  return event?.willSync === true || event?.status === "matched" || event?.status === "unknown";
}

export function SettingsPage() {
  const client = useQueryClient();
  const [titleModal, setTitleModal] = useState(null);
  const [accountModal, setAccountModal] = useState(null);
  const [titleDraft, setTitleDraft] = useState(blankTitle);
  const [accountDraft, setAccountDraft] = useState(blankAccount);
  const [error, setError] = useState("");
  const [speechError, setSpeechError] = useState("");
  const [speechDraft, setSpeechDraft] = useState({ enabled: false, voiceUri: "", voiceName: "", volume: 1, rate: 1, pitch: 1, patterns: [] });
  const [speechVoices, setSpeechVoices] = useState([]);
  const [speechSampleName, setSpeechSampleName] = useState("Khải Hoàn");
  const [syncModal, setSyncModal] = useState(null);
  const [selectedSyncEvents, setSelectedSyncEvents] = useState({});
  const [agentReleaseVersion, setAgentReleaseVersion] = useState("");
  const [agentReleaseFile, setAgentReleaseFile] = useState(null);
  const query = useQuery({
    queryKey: ["settings"],
    queryFn: () => api("/api/settings"),
  });
  const dahAgentStatus = useQuery({
    queryKey: ["dah-local-agent-status"],
    queryFn: () => api("/api/dah/local-agent/status"),
    refetchInterval: 15000,
  });
  const pendingSyncBatches = useQuery({
    queryKey: ["dah-local-agent-pending-batches"],
    queryFn: () => api("/api/dah/local-agent/pending-batches"),
    refetchInterval: 10000,
  });
  const dahScanDays = useQuery({
    queryKey: ["dah-local-agent-scan-days"],
    queryFn: () => api("/api/dah/local-agent/scan-days"),
    refetchInterval: 30000,
  });
  const syncBatchDetail = useQuery({
    queryKey: ["dah-local-agent-pending-batch", syncModal?.id],
    queryFn: () => api(`/api/dah/local-agent/pending-batches/${syncModal.id}`),
    enabled: !!syncModal?.id,
  });
  const data = query.data;
  const syncDetail = syncBatchDetail.data?.item;

  useEffect(() => {
    if (data?.checkinSpeech) {
      setSpeechDraft({
        enabled: !!data.checkinSpeech.enabled,
        voiceUri: data.checkinSpeech.voiceUri || "",
        voiceName: data.checkinSpeech.voiceName || "",
        volume: Number(data.checkinSpeech.volume ?? 1),
        rate: Number(data.checkinSpeech.rate ?? 1),
        pitch: Number(data.checkinSpeech.pitch ?? 1),
        patterns: data.checkinSpeech.patterns.map((row) => ({ ...row })),
      });
      setSpeechError("");
    }
  }, [data?.checkinSpeech]);

  useEffect(() => {
    if (!("speechSynthesis" in window)) return undefined;
    const refreshVoices = () => setSpeechVoices(availableSpeechVoices());
    refreshVoices();
    window.speechSynthesis.addEventListener("voiceschanged", refreshVoices);
    return () => window.speechSynthesis.removeEventListener("voiceschanged", refreshVoices);
  }, []);

  useEffect(() => {
    setTitleDraft(titleForm(titleModal));
    setError("");
  }, [titleModal]);
  useEffect(() => {
    setAccountDraft(accountForm(accountModal));
    setError("");
  }, [accountModal]);
  useEffect(() => {
    if (!syncDetail?.events) return;
    setSelectedSyncEvents(Object.fromEntries(syncDetail.events.map((event) => [event.eventKey, canSyncDahEvent(event)])));
  }, [syncDetail?.id]);

  const saveJobTitle = useMutation({
    mutationFn: (payload) =>
      api(
        titleModal?.id
          ? `/api/settings/job-titles/${titleModal.id}`
          : "/api/settings/job-titles",
        { method: titleModal?.id ? "PATCH" : "POST", body: payload },
      ),
    onSuccess: (row) => {
      client.invalidateQueries({ queryKey: ["settings"] });
      client.invalidateQueries({ queryKey: ["trainers"] });
      client.invalidateQueries({ queryKey: ["member-options"] });
      setTitleModal(null);
      notify.success(`Đã lưu chức vụ ${row.name}.`);
    },
    onError: (reason) => setError(reason.message),
  });
  const saveAccount = useMutation({
    mutationFn: (payload) =>
      api(
        accountModal?.id
          ? `/api/settings/bank-accounts/${accountModal.id}`
          : "/api/settings/bank-accounts",
        { method: accountModal?.id ? "PATCH" : "POST", body: payload },
      ),
    onSuccess: (row) => {
      client.invalidateQueries({ queryKey: ["settings"] });
      client.invalidateQueries({ queryKey: ["member-options"] });
      setAccountModal(null);
      notify.success(`Đã lưu tài khoản ${row.bank}.`);
    },
    onError: (reason) => setError(reason.message),
  });
  const deleteJobTitle = useMutation({
    mutationFn: (row) =>
      api(`/api/settings/job-titles/${row.id}`, { method: "DELETE" }),
    onSuccess: (_, row) => {
      client.invalidateQueries({ queryKey: ["settings"] });
      client.invalidateQueries({ queryKey: ["trainers"] });
      client.invalidateQueries({ queryKey: ["member-options"] });
      notify.success(`Đã xóa chức vụ ${row.name}.`);
    },
    onError: (reason) => notify.error(reason.message),
  });
  const deleteAccount = useMutation({
    mutationFn: (row) =>
      api(`/api/settings/bank-accounts/${row.id}`, { method: "DELETE" }),
    onSuccess: (_, row) => {
      client.invalidateQueries({ queryKey: ["settings"] });
      client.invalidateQueries({ queryKey: ["member-options"] });
      notify.success(`Đã xóa tài khoản ${row.bank}.`);
    },
    onError: (reason) => notify.error(reason.message),
  });
  const saveSpeech = useMutation({
    mutationFn: () => api("/api/checkin-speech/config", { method: "PUT", body: speechDraft }),
    onSuccess: (saved) => {
      client.setQueryData(["checkin-speech-config"], saved);
      client.invalidateQueries({ queryKey: ["settings"] });
      setSpeechError("");
      notify.success("Đã lưu lời chào check-in.");
    },
    onError: (reason) => setSpeechError(reason.message),
  });
  const requestDahSync = useMutation({
    mutationFn: (payload = { lookbackHours: 24 }) => api("/api/dah/local-agent/sync-request", { method: "POST", body: payload }),
    onSuccess: (_, payload) => {
      client.invalidateQueries({ queryKey: ["dah-local-agent-status"] });
      client.invalidateQueries({ queryKey: ["dah-local-agent-pending-batches"] });
      client.invalidateQueries({ queryKey: ["dah-local-agent-scan-days"] });
      notify.success(payload?.workDate ? `Đã gửi yêu cầu quét lại ngày ${payload.workDate}.` : "Đã gửi yêu cầu sync tới DAH agent.");
    },
    onError: (reason) => notify.error(reason.message),
  });
  const uploadAgentRelease = useMutation({
    mutationFn: () => {
      const form = new FormData();
      form.set("version", agentReleaseVersion.trim());
      form.set("mandatory", "false");
      form.set("file", agentReleaseFile);
      return api("/api/dah/local-agent/releases", { method: "POST", body: form });
    },
    onSuccess: (release) => {
      client.invalidateQueries({ queryKey: ["dah-local-agent-status"] });
      setAgentReleaseFile(null);
      notify.success(`Đã upload Agent ${release.version}. Agent sẽ tự cập nhật trong vòng 1 phút.`);
    },
    onError: (reason) => notify.error(reason.message),
  });
  const approveDahSync = useMutation({
    mutationFn: ({ batchId, eventKeys }) =>
      api(`/api/dah/local-agent/pending-batches/${batchId}/approve`, {
        method: "POST",
        body: { eventKeys },
      }),
    onSuccess: (result) => {
      client.invalidateQueries({ queryKey: ["dah-local-agent-status"] });
      client.invalidateQueries({ queryKey: ["dah-local-agent-pending-batches"] });
      client.invalidateQueries({ queryKey: ["dah-local-agent-scan-days"] });
      client.invalidateQueries({ queryKey: ["dah-events"] });
      client.invalidateQueries({ queryKey: ["dashboard"] });
      setSyncModal(null);
      notify.success(`Đã đồng bộ ${result?.result?.imported || 0} event DAH.`);
    },
    onError: (reason) => notify.error(reason.message),
  });
  const rejectDahSync = useMutation({
    mutationFn: (batchId) => api(`/api/dah/local-agent/pending-batches/${batchId}/reject`, { method: "POST", body: {} }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["dah-local-agent-status"] });
      client.invalidateQueries({ queryKey: ["dah-local-agent-pending-batches"] });
      setSyncModal(null);
      notify.success("Đã bỏ batch sync.");
    },
    onError: (reason) => notify.error(reason.message),
  });

  const previewSpeech = (pattern) => {
    const message = String(pattern.text || "").replaceAll("{name}", speechSampleName.trim() || "Khải Hoàn");
    if (!speakVietnamese(message, { ...speechDraft, interrupt: true })) {
      notify.error("Trình duyệt này không hỗ trợ đọc văn bản.");
    }
  };
  const vietnameseVoices = speechVoices.filter((voice) => voice.lang?.toLowerCase().startsWith("vi"));
  const otherVoices = speechVoices.filter((voice) => !voice.lang?.toLowerCase().startsWith("vi"));
  const selectedVoiceAvailable = !speechDraft.voiceUri || speechVoices.some((voice) => voice.voiceURI === speechDraft.voiceUri);
  const pendingBatches = pendingSyncBatches.data?.items || [];
  const scanDays = dahScanDays.data?.items || [];
  const agent = dahAgentStatus.data?.agent;
  const agentRelease = dahAgentStatus.data?.release;
  const recentDahJobs = dahAgentStatus.data?.recentJobs || [];
  const selectableSyncEventKeys = new Set((syncDetail?.events || []).filter(canSyncDahEvent).map((event) => event.eventKey));
  const selectedEventKeys = Object.entries(selectedSyncEvents)
    .filter(([key, checked]) => checked && selectableSyncEventKeys.has(key))
    .map(([key]) => key);

  const handleDeleteTitle = (row) => {
    const confirmed = window.confirm(
      `Xóa chức vụ "${row.name}"?\n\nChức vụ đang có nhân viên hoạt động sẽ không thể xóa.`,
    );
    if (confirmed) deleteJobTitle.mutate(row);
  };
  const handleDeleteAccount = (row) => {
    const confirmed = window.confirm(
      `Xóa tài khoản "${row.bank} · ${row.accountNumber}"?\n\nTài khoản đã có giao dịch sẽ được ẩn để giữ lịch sử thanh toán.`,
    );
    if (confirmed) deleteAccount.mutate(row);
  };
  const canUploadAgentRelease = agentReleaseVersion.trim() && agentReleaseFile && !uploadAgentRelease.isPending;

  return (
    <>
      <PageHeader
        eyebrow="Hệ thống"
        title="Cài đặt"
        description="Quản lý tài khoản nhận tiền, chức vụ nhân sự và trạng thái thiết bị."
      />
      <section>
        <div className="section-header">
          <div>
            <h2>Chức vụ & quyền PT</h2>
            <p>Đánh dấu chức vụ nào được chọn làm Coach/PT trong lịch tập.</p>
          </div>
          <Button size="sm" onClick={() => setTitleModal({})}>
            <Plus size={14} />
            Thêm chức vụ
          </Button>
        </div>
        <DataTable
          rows={data?.jobTitles}
          loading={query.isLoading}
          error={query.error}
          onRetry={query.refetch}
          columns={[
            {
              key: "name",
              label: "Chức vụ",
              render: (row) => <span className="cell-primary">{row.name}</span>,
            },
            {
              key: "pt",
              label: "Được chọn làm PT",
              render: (row) =>
                row.isPtRole ? (
                  <StatusBadge status="active" />
                ) : (
                  <span className="text-xs text-slate-400">Không</span>
                ),
            },
            {
              key: "status",
              label: "Trạng thái",
              render: (row) => (
                <StatusBadge status={row.active ? "active" : "inactive"} />
              ),
            },
            {
              key: "actions",
              label: "",
              className: "text-right",
              render: (row) => (
                <div className="flex justify-end gap-2">
                  <Button size="sm" variant="ghost" onClick={() => setTitleModal(row)}>
                    <Pencil size={13} />
                    Sửa
                  </Button>
                  <Button
                    size="sm"
                    variant="danger"
                    disabled={deleteJobTitle.isPending}
                    onClick={() => handleDeleteTitle(row)}
                  >
                    <Trash2 size={13} />
                    Xóa
                  </Button>
                </div>
              ),
            },
          ]}
        />
      </section>
      <section className="mt-7">
        <div className="section-header checkin-speech-section-header">
          <div>
            <h2>Lời chào check-in</h2>
            <p>Phát ngẫu nhiên khi khách hoặc nhân viên check-in hợp lệ.</p>
          </div>
          <div className="checkin-speech-master-control">
            <span>{speechDraft.enabled ? "Đang bật" : "Đang tắt"}</span>
            <label className="switch-control">
              <input type="checkbox" checked={speechDraft.enabled} onChange={(event) => setSpeechDraft({ ...speechDraft, enabled: event.target.checked })} />
              <i />
            </label>
            <Button size="sm" onClick={() => saveSpeech.mutate()} loading={saveSpeech.isPending}>
              <Save size={14} />Lưu cài đặt
            </Button>
          </div>
        </div>
        <div className="checkin-speech-settings">
          <div className="checkin-speech-voice-panel">
            <Field label="Giọng đọc" hint="Danh sách giọng do máy và trình duyệt hiện tại cung cấp.">
              <Select
                value={speechDraft.voiceUri}
                onChange={(event) => {
                  const voice = speechVoices.find((row) => row.voiceURI === event.target.value);
                  setSpeechDraft({ ...speechDraft, voiceUri: voice?.voiceURI || "", voiceName: voice?.name || "" });
                }}
              >
                <option value="">Tự động chọn giọng tiếng Việt</option>
                {!selectedVoiceAvailable && <option value={speechDraft.voiceUri}>{speechDraft.voiceName || "Giọng đã lưu"} (không có trên máy này)</option>}
                {vietnameseVoices.length > 0 && <optgroup label="Tiếng Việt">
                  {vietnameseVoices.map((voice) => <option key={voice.voiceURI} value={voice.voiceURI}>{voice.name} · {voice.lang}{voice.localService ? " · Trên máy" : " · Trực tuyến"}</option>)}
                </optgroup>}
                {otherVoices.length > 0 && <optgroup label="Ngôn ngữ khác">
                  {otherVoices.map((voice) => <option key={voice.voiceURI} value={voice.voiceURI}>{voice.name} · {voice.lang}{voice.localService ? " · Trên máy" : " · Trực tuyến"}</option>)}
                </optgroup>}
              </Select>
            </Field>
            <Field label={`Âm lượng · ${Math.round(speechDraft.volume * 100)}%`}>
              <input className="checkin-speech-range" type="range" min="0" max="1" step="0.05" value={speechDraft.volume} onChange={(event) => setSpeechDraft({ ...speechDraft, volume: Number(event.target.value) })} />
            </Field>
            <Field label={`Tốc độ · ${speechDraft.rate.toFixed(2)}x`}>
              <input className="checkin-speech-range" type="range" min="0.5" max="2" step="0.05" value={speechDraft.rate} onChange={(event) => setSpeechDraft({ ...speechDraft, rate: Number(event.target.value) })} />
            </Field>
            <Field label={`Cao độ · ${speechDraft.pitch.toFixed(2)}`}>
              <input className="checkin-speech-range" type="range" min="0.5" max="2" step="0.05" value={speechDraft.pitch} onChange={(event) => setSpeechDraft({ ...speechDraft, pitch: Number(event.target.value) })} />
            </Field>
          </div>
          <div className="checkin-speech-preview-name">
            <Field label="Tên dùng khi nghe thử">
              <Input value={speechSampleName} onChange={(event) => setSpeechSampleName(event.target.value)} />
            </Field>
            <button type="button" onClick={() => setSpeechSampleName("Khải Hoàn")}>Đặt lại</button>
          </div>
          <div className="checkin-speech-patterns">
            {(speechDraft.patterns || []).map((pattern, index) => (
              <div className={`checkin-speech-pattern ${pattern.active ? "" : "inactive"}`} key={pattern.id || `new-${index}`}>
                <label className="checkin-speech-pattern-toggle" title={pattern.active ? "Tắt câu này" : "Bật câu này"}>
                  <input type="checkbox" checked={pattern.active} onChange={(event) => setSpeechDraft({ ...speechDraft, patterns: speechDraft.patterns.map((row, rowIndex) => rowIndex === index ? { ...row, active: event.target.checked } : row) })} />
                </label>
                <Input value={pattern.text} maxLength={500} onChange={(event) => setSpeechDraft({ ...speechDraft, patterns: speechDraft.patterns.map((row, rowIndex) => rowIndex === index ? { ...row, text: event.target.value } : row) })} />
                <button type="button" className="checkin-token-button" title="Chèn tên người check-in" onClick={() => setSpeechDraft({ ...speechDraft, patterns: speechDraft.patterns.map((row, rowIndex) => rowIndex === index ? { ...row, text: `${row.text}${row.text.endsWith(" ") || !row.text ? "" : " "}{name}` } : row) })}>{"{name}"}</button>
                <Button size="sm" variant="secondary" onClick={() => previewSpeech(pattern)}><Volume2 size={13} />Nghe thử</Button>
                <button type="button" className="icon-button danger" aria-label={`Xóa câu số ${index + 1}`} onClick={() => setSpeechDraft({ ...speechDraft, patterns: speechDraft.patterns.filter((_, rowIndex) => rowIndex !== index) })}><Trash2 size={14} /></button>
              </div>
            ))}
            <button type="button" className="checkin-speech-add" onClick={() => setSpeechDraft({ ...speechDraft, patterns: [...speechDraft.patterns, { text: "Chào {name}, chúc bạn có một buổi tập thật tốt!", active: true }] })}><Plus size={14} />Thêm câu nói</button>
          </div>
          {speechError && <div className="inline-error">{speechError}</div>}
        </div>
      </section>
      <section className="mt-7">
        <div className="section-header">
          <div>
            <h2>Tài khoản nhận tiền</h2>
            <p>Các tài khoản hiển thị trong luồng thu tiền và đăng ký gói.</p>
          </div>
          <Button size="sm" onClick={() => setAccountModal({})}>
            <Plus size={14} />
            Thêm tài khoản
          </Button>
        </div>
        <DataTable
          rows={data?.bankAccounts}
          loading={query.isLoading}
          error={query.error}
          onRetry={query.refetch}
          columns={[
            {
              key: "bank",
              label: "Ngân hàng",
              render: (row) => (
                <div>
                  <span className="cell-primary">{row.bank}</span>
                  <div className="cell-secondary">{row.accountNumber}</div>
                </div>
              ),
            },
            { key: "accountName", label: "Chủ tài khoản" },
            { key: "visibility", label: "Phạm vi" },
            {
              key: "status",
              label: "Trạng thái",
              render: (row) => <StatusBadge status={row.status} />,
            },
            {
              key: "actions",
              label: "",
              className: "text-right",
              render: (row) => (
                <div className="flex justify-end gap-2">
                  <Button size="sm" variant="ghost" onClick={() => setAccountModal(row)}>
                    <Pencil size={13} />
                    Sửa
                  </Button>
                  <Button
                    size="sm"
                    variant="danger"
                    disabled={deleteAccount.isPending}
                    onClick={() => handleDeleteAccount(row)}
                  >
                    <Trash2 size={13} />
                    Xóa
                  </Button>
                </div>
              ),
            },
          ]}
        />
      </section>
      <section className="mt-7">
        <div className="section-header">
          <div>
            <h2>Thiết bị</h2>
            <p>Chỉ theo dõi DAH1017; trạng thái online dựa trên heartbeat gần nhất.</p>
          </div>
        </div>
        <div className="mb-5 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="text-sm font-semibold text-slate-900">DAH local agent</h3>
              <p className="text-sm text-slate-500">
                Agent: {agent?.agentId || "—"} · Version: {agent?.version || agent?.lastHeartbeat?.version || "—"} · Trạng thái: {agent?.status === "online" ? "online" : "offline"} · Batch chờ duyệt: {pendingBatches.length}
              </p>
              <p className="text-xs text-slate-400">
                Heartbeat cuối: {dateTime(agent?.lastSeenAt)} · Sync cuối: {dateTime(agent?.lastSyncAt)}
                {agent?.lastSyncStatus ? ` · ${agent.lastSyncStatus === "completed" ? "đã đồng bộ" : agent.lastSyncStatus === "pending_approval" ? "chờ duyệt" : agent.lastSyncStatus}` : ""}
              </p>
              <p className="text-xs text-slate-400">
                Kết quả sync cuối: nhận {agent?.lastSyncSummary?.received ?? "—"} · miss {agent?.lastSyncSummary?.matched ?? "—"} · trùng {agent?.lastSyncSummary?.duplicates ?? "—"} · chưa khớp {agent?.lastSyncSummary?.unknown ?? "—"} · fail {agent?.lastSyncSummary?.failCount ?? "—"}
              </p>
              <p className={`text-xs ${agentRelease?.updateAvailable ? "text-amber-700" : "text-slate-400"}`}>
                Cập nhật Agent: {agentRelease?.configured ? (agentRelease.updateAvailable ? `có bản ${agentRelease.version} đang chờ Agent tự cập nhật` : "đang dùng bản mới nhất") : "server chưa cấu hình gói update"}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                size="sm"
                variant="secondary"
                onClick={() => {
                  dahAgentStatus.refetch();
                  pendingSyncBatches.refetch();
                  dahScanDays.refetch();
                }}
              >
                <RefreshCw size={14} />
                Làm mới
              </Button>
              <Button size="sm" loading={requestDahSync.isPending} onClick={() => requestDahSync.mutate({ lookbackHours: 24 })}>
                <RefreshCw size={14} />
                Yêu cầu sync
              </Button>
            </div>
          </div>
          <div className="mt-4 grid gap-3 rounded-lg border border-slate-100 bg-slate-50 p-3 md:grid-cols-[160px_1fr_auto]">
            <Field label="Version mới">
              <Input
                value={agentReleaseVersion}
                onChange={(event) => setAgentReleaseVersion(event.target.value)}
                placeholder="1.2.1"
              />
            </Field>
            <Field label="File PulseFitDahAgent.exe">
              <input
                type="file"
                accept=".exe,application/x-msdownload,application/vnd.microsoft.portable-executable"
                className="input"
                onChange={(event) => setAgentReleaseFile(event.target.files?.[0] || null)}
              />
            </Field>
            <div className="flex items-end">
              <Button
                loading={uploadAgentRelease.isPending}
                disabled={!canUploadAgentRelease}
                onClick={() => uploadAgentRelease.mutate()}
              >
                <Upload size={14} />
                Upload bản mới
              </Button>
            </div>
            <p className="text-xs text-slate-400 md:col-span-3">
              Server sẽ lưu file, tự tính SHA256 và công bố bản mới cho Agent. Agent đang chạy sẽ kiểm tra mỗi 1 phút, tải file bằng token, verify hash rồi tự restart.
            </p>
          </div>
          {pendingBatches.length > 0 && (
            <div className="mt-4 overflow-x-auto">
              <div className="mb-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
                Phát hiện batch cần duyệt: bị miss {pendingBatches.reduce((sum, batch) => sum + (batch.summary?.matched || 0), 0)} event,
                chưa khớp {pendingBatches.reduce((sum, batch) => sum + (batch.summary?.unknown || 0), 0)},
                lỗi {pendingBatches.reduce((sum, batch) => sum + (batch.summary?.rejected || 0), 0)}.
              </div>
              <table className="min-w-full text-sm">
                <thead className="text-left text-xs uppercase tracking-wide text-slate-400">
                  <tr>
                    <th className="py-2 pr-4">Ngày</th>
                    <th className="py-2 pr-4">Thời gian</th>
                    <th className="py-2 pr-4">Thiết bị</th>
                    <th className="py-2 pr-4 text-right">Miss sync được</th>
                    <th className="py-2 pr-4 text-right">Trùng</th>
                    <th className="py-2 pr-4 text-right">Chưa khớp/lỗi</th>
                    <th className="py-2 text-right">Thao tác</th>
                  </tr>
                </thead>
                <tbody>
                  {pendingBatches.map((batch) => (
                    <tr key={batch.id} className="border-t border-slate-100">
                      <td className="py-2 pr-4">{batch.workDate || "—"}</td>
                      <td className="py-2 pr-4">{dateTime(batch.createdAt)}</td>
                      <td className="py-2 pr-4">{batch.deviceCode || "DAH local"}</td>
                      <td className="py-2 pr-4 text-right text-emerald-700">{batch.summary?.matched || 0}</td>
                      <td className="py-2 pr-4 text-right text-slate-500">{batch.summary?.duplicates || 0}</td>
                      <td className="py-2 pr-4 text-right text-amber-700">{(batch.summary?.unknown || 0) + (batch.summary?.rejected || 0)}</td>
                      <td className="py-2 text-right">
                        <Button size="sm" variant="secondary" onClick={() => setSyncModal(batch)}>
                          <Eye size={14} />
                          Xem & duyệt
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {!pendingBatches.length && <p className="mt-3 text-sm text-slate-400">Chưa có batch sync nào đang chờ duyệt.</p>}
          {recentDahJobs.length > 0 && (
            <div className="mt-4 overflow-x-auto rounded-lg border border-slate-100">
              <table className="min-w-full text-xs">
                <thead className="bg-slate-50 text-left uppercase tracking-wide text-slate-400">
                  <tr>
                    <th className="px-3 py-2">Job gần đây</th>
                    <th className="px-3 py-2">Ngày</th>
                    <th className="px-3 py-2">Trạng thái</th>
                    <th className="px-3 py-2 text-right">Miss</th>
                    <th className="px-3 py-2 text-right">Trùng</th>
                    <th className="px-3 py-2 text-right">Chưa khớp</th>
                    <th className="px-3 py-2 text-right">Fail</th>
                  </tr>
                </thead>
                <tbody>
                  {recentDahJobs.slice(0, 5).map((job) => (
                    <tr key={job.id} className="border-t border-slate-100">
                      <td className="px-3 py-2">{dateTime(job.createdAt)}</td>
                      <td className="px-3 py-2">{job.workDate || "24h gần nhất"}</td>
                      <td className="px-3 py-2">
                        {job.status === "pending_approval" ? "Chờ duyệt" : job.status === "completed" ? "Đã xong" : job.status === "running" ? "Đang chạy" : job.status === "pending" ? "Đang chờ agent" : job.status}
                      </td>
                      <td className="px-3 py-2 text-right text-emerald-700">{job.result?.matched || 0}</td>
                      <td className="px-3 py-2 text-right">{job.result?.duplicates || 0}</td>
                      <td className="px-3 py-2 text-right text-amber-700">{job.result?.unknown || 0}</td>
                      <td className="px-3 py-2 text-right text-red-700">{job.result?.failCount || 0}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {scanDays.length > 0 && (
            <div className="mt-4 overflow-x-auto rounded-lg border border-slate-100">
              <table className="min-w-full text-xs">
                <thead className="bg-slate-50 text-left uppercase tracking-wide text-slate-400">
                  <tr>
                    <th className="px-3 py-2">Ngày scan</th>
                    <th className="px-3 py-2">Lần quét cuối</th>
                    <th className="px-3 py-2 text-right">Tổng</th>
                    <th className="px-3 py-2 text-right">Đã có</th>
                    <th className="px-3 py-2 text-right">Miss</th>
                    <th className="px-3 py-2 text-right">Chưa khớp</th>
                    <th className="px-3 py-2 text-right">Fail</th>
                    <th className="px-3 py-2 text-right">Thao tác</th>
                  </tr>
                </thead>
                <tbody>
                  {scanDays.map((day) => (
                    <tr key={day.workDate} className="border-t border-slate-100">
                      <td className="px-3 py-2">{day.workDate}</td>
                      <td className="px-3 py-2">{dateTime(day.lastScannedAt)}</td>
                      <td className="px-3 py-2 text-right">{day.total || 0}</td>
                      <td className="px-3 py-2 text-right">{day.duplicates || 0}</td>
                      <td className="px-3 py-2 text-right text-emerald-700">{day.matchedMissUnapproved || 0}</td>
                      <td className="px-3 py-2 text-right text-amber-700">{day.unknown || 0}</td>
                      <td className="px-3 py-2 text-right text-red-700">{day.failCount || 0}</td>
                      <td className="px-3 py-2 text-right">
                        <Button
                          size="sm"
                          variant="secondary"
                          loading={requestDahSync.isPending}
                          onClick={() => requestDahSync.mutate({ workDate: day.workDate })}
                        >
                          <RefreshCw size={14} />
                          Quét lại
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
        <DataTable
          rows={data?.devices}
          loading={query.isLoading}
          error={query.error}
          onRetry={query.refetch}
          columns={[
            {
              key: "device",
              label: "Thiết bị",
              render: (row) => (
                <div>
                  <span className="cell-primary">{row.name}</span>
                  <div className="cell-secondary">
                    {row.code} · {row.model}
                  </div>
                </div>
              ),
            },
            { key: "ip", label: "IP" },
            {
              key: "pendingJobs",
              label: "Chờ đồng bộ",
              className: "text-right",
            },
            { key: "errors24h", label: "Lỗi 24h", className: "text-right" },
            {
              key: "lastHeartbeat",
              label: "Heartbeat",
              render: (row) => dateTime(row.lastHeartbeat),
            },
            {
              key: "status",
              label: "Trạng thái",
              render: (row) => <StatusBadge status={row.status} />,
            },
          ]}
        />
      </section>
      <Modal
        open={!!syncModal}
        onClose={() => setSyncModal(null)}
        title="Duyệt batch sync DAH"
        description="Chỉ những event được chọn mới được ghi vào check-in/check-out. Event không khớp person id hoặc đã có trên server sẽ bị khóa."
        size="xl"
      >
        <div className="modal-body">
          {syncBatchDetail.isLoading && <p className="text-sm text-slate-500">Đang tải batch…</p>}
          {syncBatchDetail.error && <div className="inline-error">{syncBatchDetail.error.message}</div>}
          {syncDetail && (
            <>
              <div className="grid gap-3 md:grid-cols-4">
                <div className="rounded-lg bg-slate-50 p-3">
                  <div className="text-xs text-slate-400">Tổng event</div>
                  <div className="text-lg font-semibold">{syncDetail.summary?.received || syncDetail.eventCount || 0}</div>
                </div>
                <div className="rounded-lg bg-emerald-50 p-3 text-emerald-800">
                  <div className="text-xs opacity-70">Miss sync được</div>
                  <div className="text-lg font-semibold">{syncDetail.summary?.matched || 0}</div>
                </div>
                <div className="rounded-lg bg-slate-50 p-3">
                  <div className="text-xs text-slate-400">Bị trùng</div>
                  <div className="text-lg font-semibold">{syncDetail.summary?.duplicates || 0}</div>
                </div>
                <div className="rounded-lg bg-amber-50 p-3 text-amber-800">
                  <div className="text-xs opacity-70">Không khớp / lỗi</div>
                  <div className="text-lg font-semibold">{(syncDetail.summary?.unknown || 0) + (syncDetail.summary?.rejected || 0)}</div>
                </div>
              </div>
              <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm text-slate-500">Đang chọn {selectedEventKeys.length} event để đồng bộ.</p>
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => setSelectedSyncEvents(Object.fromEntries((syncDetail.events || []).map((event) => [event.eventKey, canSyncDahEvent(event)])))}
                  >
                    Chọn event đồng bộ được
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setSelectedSyncEvents(Object.fromEntries((syncDetail.events || []).map((event) => [event.eventKey, false])))}
                  >
                    Bỏ chọn hết
                  </Button>
                </div>
              </div>
              <div className="mt-3 max-h-[52vh] overflow-auto rounded-lg border border-slate-200">
                <table className="min-w-full text-sm">
                  <thead className="sticky top-0 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-400">
                    <tr>
                      <th className="w-10 px-3 py-2"></th>
                      <th className="px-3 py-2">Thời gian</th>
                      <th className="px-3 py-2">Tên DAH</th>
                      <th className="px-3 py-2">Khớp vào hệ thống</th>
                      <th className="px-3 py-2">Trạng thái</th>
                      <th className="px-3 py-2 text-right">Similarity</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(syncDetail.events || []).map((event) => {
                      const disabled = !canSyncDahEvent(event);
                      return (
                      <tr key={event.eventKey} className={`border-t border-slate-100 ${disabled ? "bg-slate-50 opacity-55" : ""}`}>
                        <td className="px-3 py-2">
                          <input
                            type="checkbox"
                            className="h-4 w-4 accent-navy-900 disabled:cursor-not-allowed"
                            disabled={disabled}
                            checked={!!selectedSyncEvents[event.eventKey]}
                            onChange={(change) => !disabled && setSelectedSyncEvents({ ...selectedSyncEvents, [event.eventKey]: change.target.checked })}
                          />
                        </td>
                        <td className="px-3 py-2 whitespace-nowrap">{dateTime(event.eventTime)}</td>
                        <td className="px-3 py-2">
                          <div className="font-medium text-slate-800">{event.name || "—"}</div>
                          <div className="text-xs text-slate-400">Event UID: {event.dahUid || "—"} · Person UID: {event.dahPersonUid || "—"} · Card: {event.mjCardNo || "—"}</div>
                          <div className="text-xs text-slate-400">Profile: {event.profileKey || "—"} · Phone: {event.registeredPhone || "—"}</div>
                        </td>
                        <td className="px-3 py-2">
                          {event.customerName && <div>Hội viên: {event.customerName}</div>}
                          {event.employeeName && <div>Nhân viên: {event.employeeName}</div>}
                          {!event.customerName && !event.employeeName && <span className="text-slate-400">Không khớp person id</span>}
                          {event.matchSource && <div className="text-xs text-slate-400">Match theo: {event.matchSource}</div>}
                        </td>
                        <td className="px-3 py-2">
                          {event.status === "matched" && <span className="text-emerald-700">Hợp lệ</span>}
                          {event.status === "duplicate" && (
                            <div>
                              <span className="text-slate-500">Bị trùng</span>
                              <div className="text-xs text-slate-400">Đã có trên server</div>
                            </div>
                          )}
                          {event.status === "unknown" && <span className="text-amber-700">Không khớp</span>}
                          {event.status === "rejected" && <span className="text-red-700">DAH báo fail</span>}
                        </td>
                        <td className="px-3 py-2 text-right">{event.similarity ?? "—"}</td>
                      </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </div>
        <div className="form-actions">
          <Button variant="danger" loading={rejectDahSync.isPending} onClick={() => rejectDahSync.mutate(syncModal.id)}>
            <X size={14} />
            Bỏ batch này
          </Button>
          <Button data-modal-close variant="secondary" onClick={() => setSyncModal(null)}>
            Đóng
          </Button>
          <Button
            loading={approveDahSync.isPending}
            disabled={!selectedEventKeys.length}
            onClick={() => approveDahSync.mutate({ batchId: syncModal.id, eventKeys: selectedEventKeys })}
          >
            <Check size={14} />
            Duyệt & đồng bộ
          </Button>
        </div>
      </Modal>
      <Modal
        open={!!titleModal}
        onClose={() => setTitleModal(null)}
        title={titleModal?.id ? "Sửa chức vụ" : "Thêm chức vụ"}
        dirty={JSON.stringify(titleDraft) !== JSON.stringify(titleForm(titleModal))}
      >
        <form
          onSubmit={(event) => {
            event.preventDefault();
            setError("");
            saveJobTitle.mutate({
              ...titleDraft,
              name: titleDraft.name.trim(),
              renameEmployees: true,
            });
          }}
        >
          <div className="modal-body">
            <div className="form-grid">
              <Field className="form-span" label="Tên chức vụ" required>
                <Input
                  autoFocus
                  value={titleDraft.name}
                  onChange={(event) =>
                    setTitleDraft({ ...titleDraft, name: event.target.value })
                  }
                  placeholder="Sale, Coach, Marketing, CSKH…"
                />
              </Field>
              <label className="flex items-start gap-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-3 text-sm">
                <input
                  type="checkbox"
                  className="mt-0.5 h-4 w-4 accent-navy-900"
                  checked={titleDraft.isPtRole}
                  onChange={(event) =>
                    setTitleDraft({
                      ...titleDraft,
                      isPtRole: event.target.checked,
                    })
                  }
                />
                <span>
                  <strong className="block text-slate-800">
                    Cho phép chọn làm PT/Coach
                  </strong>
                  <small className="text-xs text-slate-500">
                    Nhân viên thuộc chức vụ này sẽ xuất hiện trong form đăng ký PT.
                  </small>
                </span>
              </label>
              <Field label="Trạng thái">
                <Select
                  value={titleDraft.active ? "active" : "inactive"}
                  onChange={(event) =>
                    setTitleDraft({
                      ...titleDraft,
                      active: event.target.value === "active",
                    })
                  }
                >
                  <option value="active">Đang dùng</option>
                  <option value="inactive">Ẩn</option>
                </Select>
              </Field>
            </div>
            {error && <div className="inline-error mt-4">{error}</div>}
          </div>
          <div className="form-actions">
            <Button data-modal-close variant="secondary" onClick={() => setTitleModal(null)}>
              Hủy
            </Button>
            <Button type="submit" loading={saveJobTitle.isPending} loadingText="Đang lưu…">
              Lưu chức vụ
            </Button>
          </div>
        </form>
      </Modal>
      <Modal
        open={!!accountModal}
        onClose={() => setAccountModal(null)}
        title={accountModal?.id ? "Sửa tài khoản nhận tiền" : "Thêm tài khoản nhận tiền"}
        dirty={JSON.stringify(accountDraft) !== JSON.stringify(accountForm(accountModal))}
      >
        <form
          onSubmit={(event) => {
            event.preventDefault();
            setError("");
            saveAccount.mutate({
              ...accountDraft,
              bank: accountDraft.bank.trim(),
              accountName: accountDraft.accountName.trim(),
              accountNumber: accountDraft.accountNumber.trim(),
            });
          }}
        >
          <div className="modal-body">
            <div className="form-grid">
              <Field label="Ngân hàng" required>
                <Input
                  autoFocus
                  value={accountDraft.bank}
                  onChange={(event) =>
                    setAccountDraft({ ...accountDraft, bank: event.target.value })
                  }
                  placeholder="VCB, ACB, Techcombank…"
                />
              </Field>
              <Field label="Chủ tài khoản" required>
                <Input
                  value={accountDraft.accountName}
                  onChange={(event) =>
                    setAccountDraft({
                      ...accountDraft,
                      accountName: event.target.value,
                    })
                  }
                />
              </Field>
              <Field label="Số tài khoản" required>
                <Input
                  value={accountDraft.accountNumber}
                  onChange={(event) =>
                    setAccountDraft({
                      ...accountDraft,
                      accountNumber: event.target.value,
                    })
                  }
                />
              </Field>
              <Field label="Phạm vi">
                <Select
                  value={accountDraft.visibility}
                  onChange={(event) =>
                    setAccountDraft({
                      ...accountDraft,
                      visibility: event.target.value,
                    })
                  }
                >
                  <option value="public">Public</option>
                  <option value="private">Private</option>
                </Select>
              </Field>
              <Field label="Trạng thái">
                <Select
                  value={accountDraft.status}
                  onChange={(event) =>
                    setAccountDraft({ ...accountDraft, status: event.target.value })
                  }
                >
                  <option value="active">Đang dùng</option>
                  <option value="inactive">Tạm ngừng</option>
                </Select>
              </Field>
            </div>
            {error && <div className="inline-error mt-4">{error}</div>}
          </div>
          <div className="form-actions">
            <Button data-modal-close variant="secondary" onClick={() => setAccountModal(null)}>
              Hủy
            </Button>
            <Button type="submit" loading={saveAccount.isPending} loadingText="Đang lưu…">
              Lưu tài khoản
            </Button>
          </div>
        </form>
      </Modal>
    </>
  );
}
