export class ApiError extends Error {
  constructor(message, status, data, requestId) {
    super(message);
    this.status = status;
    this.data = data;
    this.requestId = requestId || data?.requestId || null;
  }
}

export async function api(path, options = {}) {
  const headers = new Headers(options.headers || {});
  const isForm = options.body instanceof FormData;
  const method = String(options.method || "GET").toUpperCase();
  if (options.body && !isForm) headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const csrf = document.cookie
      .split("; ")
      .find((item) => item.startsWith("gym_csrf="))
      ?.split("=")
      .slice(1)
      .join("=");
    if (csrf) headers.set("X-CSRF-Token", decodeURIComponent(csrf));
  }
  const response = await fetch(path, {
    credentials: "include",
    ...options,
    headers,
    body: options.body && !isForm ? JSON.stringify(options.body) : options.body,
  });
  const data =
    response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok)
    throw new ApiError(
      data?.detail || "Không thể hoàn tất yêu cầu. Vui lòng thử lại.",
      response.status,
      data,
      response.headers.get("x-request-id"),
    );
  return data;
}

export const queryString = (values) => {
  const search = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => {
    if (value !== "" && value != null) search.set(key, value);
  });
  return search.toString();
};
