import { useEffect, useRef, useState } from "react";
import { CalendarDays, Clock3 } from "lucide-react";
import {
  ageFromDate,
  displayToIsoDate,
  formatMoneyInput,
  formatPhone,
  isoToDisplayDate,
  normalizePhone,
  parseMoney,
} from "../../utils/format";

function caretAfterDigitCount(text, count) {
  if (!count) return 0;
  let seen = 0;
  for (let index = 0; index < text.length; index += 1) {
    if (/\d/.test(text[index])) seen += 1;
    if (seen === count) return index + 1;
  }
  return text.length;
}

function useFormattedCaret(onValue) {
  const ref = useRef(null);
  const change = (event, parser) => {
    const digitCount = event.target.value
      .slice(0, event.target.selectionStart ?? 0)
      .replace(/\D/g, "").length;
    onValue(parser(event.target.value));
    requestAnimationFrame(() => {
      const input = ref.current;
      if (input && document.activeElement === input) {
        const caret = caretAfterDigitCount(input.value, digitCount);
        input.setSelectionRange(caret, caret);
      }
    });
  };
  return [ref, change];
}

export function PhoneInput({
  value = "",
  onChange,
  required = false,
  className = "",
  ...props
}) {
  const [touched, setTouched] = useState(false);
  const [ref, change] = useFormattedCaret(onChange);
  const digits = normalizePhone(value);
  const invalid =
    touched && ((required && !digits) || (digits && digits.length !== 10));
  return (
    <>
      <input
        ref={ref}
        className={`input ${className}`}
        type="tel"
        inputMode="numeric"
        autoComplete="tel"
        value={formatPhone(value)}
        onChange={(event) => change(event, normalizePhone)}
        onBlur={() => setTouched(true)}
        aria-invalid={invalid || undefined}
        {...props}
      />
      {invalid && (
        <span className="field-error" role="alert">
          Số điện thoại cần đủ 10 chữ số.
        </span>
      )}
    </>
  );
}

export function MoneyInput({
  value = 0,
  onChange,
  min = 0,
  max,
  className = "",
  ...props
}) {
  const [ref, change] = useFormattedCaret((next) =>
    onChange(Math.min(Math.max(next, min), max ?? Number.MAX_SAFE_INTEGER)),
  );
  return (
    <div className="smart-input">
      <input
        ref={ref}
        className={`input pr-9 text-right tabular-nums ${className}`}
        inputMode="numeric"
        value={formatMoneyInput(value)}
        onChange={(event) => change(event, parseMoney)}
        {...props}
      />
      <span className="input-unit">₫</span>
    </div>
  );
}

export function NumberUnitInput({
  value = "",
  onChange,
  unit,
  allowDecimal = false,
  className = "",
  ...props
}) {
  return (
    <div className="smart-input">
      <input
        className={`input pr-14 ${className}`}
        type="text"
        inputMode="decimal"
        value={value}
        onChange={(event) => {
          const normalized = event.target.value
            .replace(allowDecimal ? /[^\d.]/g : /\D/g, "")
            .replace(/(\..*)\./g, "$1");
          onChange(normalized);
        }}
        {...props}
      />
      {unit && <span className="input-unit">{unit}</span>}
    </div>
  );
}

function maskDate(value) {
  const digits = String(value).replace(/\D/g, "").slice(0, 8);
  return [digits.slice(0, 2), digits.slice(2, 4), digits.slice(4, 8)]
    .filter(Boolean)
    .join("/");
}

export function DateInput({
  value = "",
  onChange,
  min,
  max,
  autoFocus,
  className = "",
  ...props
}) {
  const [display, setDisplay] = useState(() => isoToDisplayDate(value));
  const [invalid, setInvalid] = useState(false);
  const picker = useRef(null);
  useEffect(() => {
    setDisplay(isoToDisplayDate(value));
    setInvalid(false);
  }, [value]);
  const commit = (text) => {
    if (!text) {
      onChange("");
      setInvalid(false);
      return;
    }
    const iso = displayToIsoDate(text);
    setInvalid(!iso);
    if (iso) onChange(iso);
  };
  return (
    <>
      <div className="smart-input">
        <input
          className={`input pr-10 tabular-nums ${className}`}
          type="text"
          inputMode="numeric"
          autoFocus={autoFocus}
          value={display}
          placeholder="dd/mm/yyyy"
          onChange={(event) => {
            const next = maskDate(event.target.value);
            setDisplay(next);
            if (next.length === 10) commit(next);
            if (!next) commit("");
          }}
          onBlur={() => commit(display)}
          aria-invalid={invalid || undefined}
          {...props}
        />
        <button
          type="button"
          className="input-action"
          onClick={() => picker.current?.showPicker?.()}
          aria-label="Mở lịch"
        >
          <CalendarDays size={15} />
        </button>
        <input
          ref={picker}
          className="pointer-events-none absolute bottom-0 right-0 h-0 w-0 opacity-0"
          tabIndex={-1}
          type="date"
          value={value}
          min={min}
          max={max}
          onChange={(event) => onChange(event.target.value)}
        />
      </div>
      {invalid && (
        <span className="field-error" role="alert">
          Ngày không hợp lệ. Dùng định dạng dd/mm/yyyy.
        </span>
      )}
    </>
  );
}

export function DateOfBirthInput(props) {
  const age = ageFromDate(props.value);
  return (
    <>
      <DateInput {...props} max={new Date().toISOString().slice(0, 10)} />
      {age != null && (
        <span className="field-hint">{age} tuổi · hệ thống tự tính</span>
      )}
    </>
  );
}

function maskTime(value) {
  const digits = String(value).replace(/\D/g, "").slice(0, 4);
  return digits.length > 2
    ? `${digits.slice(0, 2)}:${digits.slice(2)}`
    : digits;
}

export function TimeInput({ value = "", onChange, className = "", ...props }) {
  const [display, setDisplay] = useState(value);
  const [invalid, setInvalid] = useState(false);
  const picker = useRef(null);
  useEffect(() => {
    setDisplay(value || "");
    setInvalid(false);
  }, [value]);
  const commit = (text) => {
    const valid = /^([01]\d|2[0-3]):[0-5]\d$/.test(text);
    setInvalid(!!text && !valid);
    if (valid || !text) onChange(text);
  };
  return (
    <>
      <div className="smart-input">
        <input
          className={`input pr-10 tabular-nums ${className}`}
          type="text"
          inputMode="numeric"
          value={display}
          placeholder="HH:mm"
          onChange={(event) => {
            const next = maskTime(event.target.value);
            setDisplay(next);
            if (next.length === 5) commit(next);
            if (!next) commit("");
          }}
          onBlur={() => commit(display)}
          aria-invalid={invalid || undefined}
          {...props}
        />
        <button
          type="button"
          className="input-action"
          onClick={() => picker.current?.showPicker?.()}
          aria-label="Chọn giờ"
        >
          <Clock3 size={15} />
        </button>
        <input
          ref={picker}
          className="pointer-events-none absolute h-0 w-0 opacity-0"
          tabIndex={-1}
          type="time"
          step="1800"
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
      </div>
      {invalid && (
        <span className="field-error" role="alert">
          Giờ không hợp lệ. Dùng định dạng HH:mm.
        </span>
      )}
    </>
  );
}
