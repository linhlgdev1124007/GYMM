import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../../services/api";
import { notify } from "../../services/notify";

const WATCH_ROLES = new Set(["admin", "manager", "receptionist"]);
const TOAST_ID = "dah-agent-offline";
const WARNING_REPEAT_MS = 5 * 60 * 1000;

export function DahAgentWatcher({ role }) {
  const navigate = useNavigate();
  const lastWarningAt = useRef(0);
  const enabled = WATCH_ROLES.has(role);
  const status = useQuery({
    queryKey: ["dah-local-agent-status"],
    queryFn: () => api("/api/dah/local-agent/status"),
    enabled,
    refetchInterval: 60_000,
    retry: false,
    staleTime: 30_000,
  });

  useEffect(() => {
    if (!enabled) return;
    const agent = status.data?.agent;
    if (!agent) return;
    if (agent.status === "online") {
      lastWarningAt.current = 0;
      notify.dismiss(TOAST_ID);
      return;
    }

    const now = Date.now();
    if (now - lastWarningAt.current < WARNING_REPEAT_MS) return;
    lastWarningAt.current = now;
    notify.warning({
      id: TOAST_ID,
      title: "DAH Agent đang offline",
      description: "Không nhận heartbeat quá 3 phút. Cần bật PulseFit DAH Agent trên máy kết nối DAH.",
      duration: 15000,
      action: {
        label: "Mở điểm danh",
        onClick: () => navigate("/check-in"),
      },
    });
  }, [enabled, navigate, status.data]);

  return null;
}
