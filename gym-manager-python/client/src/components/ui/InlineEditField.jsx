import { useEffect, useState } from "react";
import { Check, CircleAlert, LoaderCircle, Pencil, X } from "lucide-react";
import { Input, Select } from "./Form";
import { PhoneInput } from "./SmartInputs";

export function InlineEditField({
  label,
  value,
  displayValue,
  type = "text",
  options = [],
  emptyAction = "Thêm",
  onSave,
  pending,
  className = "",
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value ?? "");
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  useEffect(() => setDraft(value ?? ""), [value]);
  const close = () => {
    setDraft(value ?? "");
    setEditing(false);
  };
  const save = async () => {
    setStatus("saving");
    setError("");
    try {
      await onSave(draft);
      setEditing(false);
      setStatus("saved");
      window.setTimeout(() => setStatus("idle"), 1800);
    } catch (reason) {
      setStatus("error");
      setError(reason?.message || "Không thể lưu. Vui lòng thử lại.");
    }
  };
  return (
    <div className={`inline-field ${className}`}>
      <dt>{label}</dt>
      <dd>
        {editing ? (
          <div className="inline-field-editor">
            {type === "select" ? (
              <Select
                autoFocus
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
              >
                {options.map((item) => (
                  <option key={item.value} value={item.value}>
                    {item.label}
                  </option>
                ))}
              </Select>
            ) : type === "tel" ? (
              <PhoneInput
                autoFocus
                value={draft}
                onChange={setDraft}
                onKeyDown={(e) => {
                  if (e.nativeEvent?.isComposing || e.isComposing) return;
                  if (e.key === "Enter") save();
                  if (e.key === "Escape") close();
                }}
              />
            ) : (
              <Input
                autoFocus
                type={type}
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.nativeEvent?.isComposing || e.isComposing) return;
                  if (e.key === "Enter") save();
                  if (e.key === "Escape") close();
                }}
              />
            )}
            <button
              type="button"
              onClick={save}
              disabled={pending}
              aria-label={`Lưu ${label}`}
            >
              {pending || status === "saving" ? (
                <LoaderCircle className="animate-spin" size={15} />
              ) : (
                <Check size={15} />
              )}
            </button>
            <button type="button" onClick={close} aria-label="Hủy">
              <X size={15} />
            </button>
          </div>
        ) : (
          <div>
            <button
              type="button"
              className="inline-field-value"
              onClick={() => setEditing(true)}
            >
              <span>{displayValue || value || <em>{emptyAction}</em>}</span>
              <Pencil size={12} />
            </button>
            {status === "saved" && (
              <small className="inline-save-state success">
                <Check size={12} /> Đã lưu
              </small>
            )}
          </div>
        )}
        {status === "error" && (
          <small className="inline-save-state error">
            <CircleAlert size={12} /> {error}
          </small>
        )}
      </dd>
    </div>
  );
}
