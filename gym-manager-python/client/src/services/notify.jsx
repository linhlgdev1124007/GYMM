import { toast } from "sonner";

const recent = new Map();
const durations = { success: 4000, info: 5000, warning: 7000, error: 9000 };

function normalize(input, options = {}) {
  if (typeof input === "string") return { title: input, ...options };
  return { ...(input || {}), ...options };
}

function toastOptions(type, config) {
  const key =
    config.id || `${type}:${config.title}:${config.description || ""}`;
  const now = Date.now();
  if (!config.id && now - (recent.get(key) || 0) < 1500) return null;
  recent.set(key, now);
  window.setTimeout(() => recent.delete(key), 2000);
  return {
    id: key,
    description: config.description,
    duration: config.duration ?? durations[type],
    dismissible: config.dismissible ?? true,
    action: config.action
      ? {
          label: config.action.label,
          onClick: config.action.onClick,
        }
      : undefined,
  };
}

function show(type, input, options) {
  const config = normalize(input, options);
  const toastConfig = toastOptions(type, config);
  if (!toastConfig) return undefined;
  return toast[type](config.title, toastConfig);
}

function safeError(error, fallback) {
  if (!navigator.onLine) {
    return "Không có kết nối mạng. Vui lòng kiểm tra kết nối rồi thử lại.";
  }
  const message = String(error?.message || "").trim();
  if (
    !message ||
    /HTTP \d|SQLITE|stack|trace|fetch failed|failed to fetch|networkerror/i.test(
      message,
    )
  ) {
    return fallback;
  }
  return message;
}

export const notify = {
  success: (input, options) => show("success", input, options),
  error: (input, options) => show("error", input, options),
  warning: (input, options) => show("warning", input, options),
  info: (input, options) => show("info", input, options),
  errorFrom(
    error,
    fallback = "Không thể hoàn tất yêu cầu. Vui lòng thử lại.",
    options = {},
  ) {
    return show("error", {
      title: safeError(error, fallback),
      description: error?.requestId ? `Mã hỗ trợ: ${error.requestId}` : options.description,
      ...options,
    });
  },
  loading(input, options = {}) {
    const config = normalize(input, options);
    return toast.loading(config.title, {
      id: config.id,
      description: config.description,
      duration: Infinity,
    });
  },
  promise(promise, messages) {
    return toast.promise(promise, messages);
  },
  dismiss: toast.dismiss,
};
