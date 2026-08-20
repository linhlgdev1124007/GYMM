import { useState } from "react";
import { ClipboardPaste, FileImage, Paperclip, X } from "lucide-react";

const MAX_FILES = 10;
const ACCEPTED_IMAGE_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);
const IMAGE_EXTENSIONS = {
  "image/jpeg": "jpg",
  "image/png": "png",
  "image/webp": "webp",
};

export function ReceiptPicker({ files = [], onChange, disabled = false }) {
  const [message, setMessage] = useState("");
  const addFiles = (incoming, source = "upload") => {
    const incomingFiles = Array.from(incoming || []).filter((file) =>
      ACCEPTED_IMAGE_TYPES.has(file.type),
    );
    if (!incomingFiles.length) {
      setMessage(source === "paste" ? "Clipboard không có ảnh JPG, PNG hoặc WebP." : "");
      return;
    }
    const remaining = MAX_FILES - files.length;
    if (remaining <= 0) {
      setMessage(`Đã đủ tối đa ${MAX_FILES} ảnh.`);
      return;
    }
    const nextFiles = incomingFiles.slice(0, remaining);
    onChange([...files, ...nextFiles]);
    setMessage(source === "paste" ? `Đã dán ${nextFiles.length} ảnh từ clipboard.` : "");
  };
  const pasteImages = (event) => {
    if (disabled) return;
    event.stopPropagation();
    const pastedFiles = Array.from(event.clipboardData?.items || [])
      .filter((item) => item.kind === "file" && ACCEPTED_IMAGE_TYPES.has(item.type))
      .map((item, index) => {
        const file = item.getAsFile();
        if (!file) return null;
        const extension = IMAGE_EXTENSIONS[file.type] || "png";
        return new File([file], `receipt-clipboard-${Date.now()}-${index + 1}.${extension}`, {
          type: file.type,
          lastModified: Date.now(),
        });
      })
      .filter(Boolean);
    if (pastedFiles.length) event.preventDefault();
    addFiles(pastedFiles, "paste");
  };
  return (
    <div className="receipt-picker" onClick={(event) => event.stopPropagation()}>
      <label className={`receipt-dropzone ${disabled ? "disabled" : ""}`}>
        <Paperclip size={17} />
        <span>
          <strong>Chọn ảnh chứng từ</strong>
          <small>
            JPG, PNG, WebP · tối đa 5 MB/ảnh · tối đa {MAX_FILES} ảnh
          </small>
        </span>
        <input
          type="file"
          multiple
          accept="image/jpeg,image/png,image/webp"
          disabled={disabled}
          onChange={(event) => {
            addFiles(event.target.files);
            event.target.value = "";
          }}
        />
      </label>
      <div
        className={`receipt-pastezone ${disabled ? "disabled" : ""}`}
        tabIndex={disabled ? -1 : 0}
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          event.currentTarget.focus();
        }}
        onPaste={pasteImages}
      >
        <ClipboardPaste size={16} />
        <span>
          <strong>Dán ảnh từ clipboard</strong>
          <small>Click vào đây rồi nhấn Ctrl+V sau khi chụp màn hình hoặc copy ảnh</small>
        </span>
      </div>
      {message && <p className="receipt-picker-message">{message}</p>}
      {!!files.length && (
        <div className="receipt-file-list">
          {files.map((file, index) => (
            <div key={`${file.name}-${file.lastModified}-${index}`}>
              <FileImage size={15} />
              <span>
                <strong>{file.name}</strong>
                <small>{(file.size / 1024 / 1024).toFixed(2)} MB</small>
              </span>
              <button
                type="button"
                onClick={() =>
                  onChange(files.filter((_, itemIndex) => itemIndex !== index))
                }
                aria-label={`Bỏ ${file.name}`}
              >
                <X size={14} />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
