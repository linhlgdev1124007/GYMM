import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ScanFace, TriangleAlert } from "lucide-react";
import { api } from "../../services/api";
import { Button } from "../../components/ui/Button";
import { Field, Input } from "../../components/ui/Form";
import { Modal } from "../../components/ui/Modal";

const CONFIRMATION_PHRASE = "Tôi xác nhận xóa";

export function DahIdentityDeleteModal({
  open,
  onClose,
  memberId,
  memberName,
  personUuid,
  onDeleted,
}) {
  const [confirmationText, setConfirmationText] = useState("");
  const removeIdentity = useMutation({
    mutationFn: () =>
      api(`/api/members/${memberId}/dah-identity`, {
        method: "DELETE",
        body: { confirmationText },
      }),
    onSuccess: (result) => {
      onDeleted?.(result);
      closeModal();
    },
  });
  const closeModal = () => {
    setConfirmationText("");
    onClose();
  };
  return (
    <Modal
      open={open}
      onClose={closeModal}
      title="Xóa FaceID hội viên"
      description={memberName || "Hội viên"}
      size="sm"
      dirty={!!confirmationText}
    >
      <div className="modal-body space-y-4">
        <div className="identity-confirm-warning">
          <TriangleAlert size={16} />
          <strong>FaceID sẽ bị gỡ khỏi hồ sơ hội viên.</strong>
        </div>
        <div className="identity-link-summary">
          <div className="identity-face">
            <ScanFace size={22} />
          </div>
          <div>
            <strong>Định danh hiện tại</strong>
            <span className="font-mono">{personUuid || "Chưa liên kết"}</span>
            <small>Thao tác này được ghi vào nhật ký hệ thống.</small>
          </div>
        </div>
        {removeIdentity.error && (
          <div className="inline-error">{removeIdentity.error.message}</div>
        )}
        <Field label={<>Nhập <strong>{CONFIRMATION_PHRASE}</strong></>} required>
          <Input
            autoFocus
            value={confirmationText}
            onChange={(event) => setConfirmationText(event.target.value)}
            placeholder={CONFIRMATION_PHRASE}
          />
        </Field>
      </div>
      <div className="form-actions">
        <Button variant="secondary" onClick={closeModal}>
          Hủy
        </Button>
        <Button
          variant="danger"
          loading={removeIdentity.isPending}
          loadingText="Đang xóa..."
          disabled={confirmationText.trim() !== CONFIRMATION_PHRASE}
          onClick={() => removeIdentity.mutate()}
        >
          Xóa FaceID
        </Button>
      </div>
    </Modal>
  );
}
