import { useEffect, useRef, useState } from "react";
import { Search, X } from "lucide-react";

export function SearchInput({ value, onChange, placeholder = "Tìm kiếm…" }) {
  const [draft, setDraft] = useState(value || "");
  const composing = useRef(false);

  useEffect(() => {
    if (!composing.current) setDraft(value || "");
  }, [value]);

  const commit = (next) => {
    setDraft(next);
    if (!composing.current) onChange(next);
  };

  return (
    <div className="search-input">
      <Search size={16} />
      <input
        value={draft}
        onCompositionStart={() => {
          composing.current = true;
        }}
        onCompositionEnd={(event) => {
          composing.current = false;
          commit(event.currentTarget.value);
        }}
        onChange={(event) => commit(event.target.value)}
        placeholder={placeholder}
      />
      {draft && (
        <button
          type="button"
          onClick={() => {
            composing.current = false;
            setDraft("");
            onChange("");
          }}
          aria-label="Xóa tìm kiếm"
        >
          <X size={15} />
        </button>
      )}
    </div>
  );
}
