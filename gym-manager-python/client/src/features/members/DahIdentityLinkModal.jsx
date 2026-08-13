import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { RefreshCw, ScanFace, TriangleAlert } from "lucide-react";
import { api } from "../../services/api";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import { dateTime } from "../../utils/format";

export function DahIdentityLinkModal({
  open,
  onClose,
  memberId,
  memberName,
  currentPersonUuid,
  currentAvatarImageData,
  onLinked,
  onSelect,
  targetType = "member",
  error,
}) {
  const [selectedCandidate, setSelectedCandidate] = useState(null);
  const [confirmationText, setConfirmationText] = useState("");
  const isMemberRelink = targetType === "member" && Boolean(memberId && currentPersonUuid);
  const confirmationPhrase = "tôi xác nhận thay đổi";
  const candidates = useQuery({
    queryKey: ["dah-identity-candidates", targetType, isMemberRelink],
    queryFn: () =>
      api(
        `/api/dah/identity-candidates?limit=12&targetType=${targetType}${
          isMemberRelink ? "&includeAssigned=true" : ""
        }`,
      ),
    enabled: open,
    refetchInterval: open ? 4000 : false,
  });
  const assign = useMutation({
    mutationFn: ({ eventId, replace = false }) =>
      api(`/${targetType === "employee" ? "api/employees" : "api/members"}/${memberId}/dah-identity`, {
        method: "POST",
        body: { eventId, replace, confirmationText },
      }),
    onSuccess: (result) => {
      onLinked?.(result);
      closeModal();
    },
  });
  const closeModal = () => {
    setSelectedCandidate(null);
    setConfirmationText("");
    onClose();
  };
  const selectCandidate = (row) => {
    if (memberId) {
      const replace = Boolean(currentPersonUuid && currentPersonUuid !== row.personUuid);
      if (replace) {
        setSelectedCandidate(row);
        setConfirmationText("");
        return;
      }
      assign.mutate({ eventId: row.eventId, replace: false });
      return;
    }
    onSelect?.(row);
    closeModal();
  };
  const confirmRelink = () => {
    if (!selectedCandidate) return;
    assign.mutate({ eventId: selectedCandidate.eventId, replace: true });
  };
  return (
    <Modal
      open={open}
      onClose={closeModal}
      title={isMemberRelink ? "Gán lại định danh DAH" : "Liên kết định danh DAH"}
      description={memberName || `Chọn PersonUUID chưa gán cho ${targetType === "employee" ? "nhân viên" : "hội viên"} nào`}
      size="lg"
    >
      <div className="modal-body">
        {isMemberRelink && (
          <div className="identity-link-summary mb-3">
            <div className="identity-face">
              {currentAvatarImageData ? (
                <img src={currentAvatarImageData} alt="" />
              ) : (
                <ScanFace size={22} />
              )}
            </div>
            <div>
              <strong>Định danh DAH hiện tại</strong>
              <span className="font-mono">{currentPersonUuid}</span>
              <small>Chọn face mới bên dưới để thay thế.</small>
            </div>
          </div>
        )}
        <div className="identity-link-toolbar">
          <div>
            <strong>Face mới quét gần đây</strong>
            <span>Danh sách tự cập nhật mỗi vài giây.</span>
          </div>
          <Button
            type="button"
            variant="secondary"
            onClick={() => candidates.refetch()}
            loading={candidates.isFetching}
            loadingText="Đang tải..."
          >
            <RefreshCw size={14} /> Làm mới
          </Button>
        </div>
        {(assign.error || candidates.error || error) && (
          <div className="inline-error mt-3">
            {assign.error?.message || candidates.error?.message || error}
          </div>
        )}
        {candidates.isLoading ? (
          <div className="identity-candidate-list mt-4">
            <div className="skeleton h-20" />
            <div className="skeleton h-20" />
            <div className="skeleton h-20" />
          </div>
        ) : candidates.data?.items?.length ? (
          <div className="identity-candidate-list mt-4">
            {candidates.data.items.map((row) => (
              <button
                key={row.eventId}
                type="button"
                className={`identity-candidate ${
                  selectedCandidate?.eventId === row.eventId ? "selected" : ""
                }`}
                disabled={assign.isPending}
                onClick={() => selectCandidate(row)}
              >
                <div className="identity-face">
                  {row.imageData ? (
                    <img src={row.imageData} alt="" />
                  ) : (
                    <ScanFace size={22} />
                  )}
                </div>
                <div>
                  <strong>{row.name || "Khách vừa quét"}</strong>
                  <span>{row.personUuid}</span>
                  <small>
                    {row.device || "DAH"} · {dateTime(row.eventTime)}
                    {row.similarity ? ` · ${Number(row.similarity).toFixed(1)}%` : ""}
                  </small>
                </div>
              </button>
            ))}
          </div>
        ) : (
          <div className="empty-state compact mt-4">
            <ScanFace size={28} />
            <strong>Chưa có face mới chưa gán</strong>
            <p>Cho người cần liên kết quét mặt trên DAH rồi bấm làm mới.</p>
          </div>
        )}
        {selectedCandidate && (
          <div className="identity-confirm-panel mt-4">
            <div className="identity-confirm-warning">
              <TriangleAlert size={16} />
              <strong>Xác nhận gán lại DAH cho {memberName}</strong>
            </div>
            <div className="identity-compare">
              <div>
                <span>Avatar hiện tại</span>
                <div className="identity-face identity-face-large">
                  {currentAvatarImageData ? (
                    <img src={currentAvatarImageData} alt="" />
                  ) : (
                    <ScanFace size={26} />
                  )}
                </div>
                <small className="font-mono">{currentPersonUuid}</small>
              </div>
              <div>
                <span>Face sẽ gán</span>
                <div className="identity-face identity-face-large">
                  {selectedCandidate.imageData ? (
                    <img src={selectedCandidate.imageData} alt="" />
                  ) : (
                    <ScanFace size={26} />
                  )}
                </div>
                <small className="font-mono">{selectedCandidate.personUuid}</small>
              </div>
            </div>
            <label className="form-field">
              <span>
                Nhập <strong>{confirmationPhrase}</strong>
              </span>
              <input
                value={confirmationText}
                onChange={(event) => setConfirmationText(event.target.value)}
                placeholder={confirmationPhrase}
              />
            </label>
            <div className="form-actions tight">
              <Button
                type="button"
                variant="secondary"
                onClick={() => {
                  setSelectedCandidate(null);
                  setConfirmationText("");
                }}
              >
                Chọn lại
              </Button>
              <Button
                type="button"
                onClick={confirmRelink}
                loading={assign.isPending}
                loadingText="Đang gán..."
                disabled={confirmationText.trim().toLowerCase() !== confirmationPhrase}
              >
                Xác nhận gán lại
              </Button>
            </div>
          </div>
        )}
      </div>
      <div className="form-actions">
        <Button data-modal-close variant="secondary" onClick={closeModal}>
          Đóng
        </Button>
      </div>
    </Modal>
  );
}
