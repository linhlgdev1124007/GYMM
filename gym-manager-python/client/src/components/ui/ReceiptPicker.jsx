import { FileImage, Paperclip, X } from "lucide-react";

const MAX_FILES = 10;

export function ReceiptPicker({ files = [], onChange, disabled = false }) {
  const addFiles = (incoming) =>
    onChange([...files, ...Array.from(incoming)].slice(0, MAX_FILES));
  return (
    <div className="receipt-picker">
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
