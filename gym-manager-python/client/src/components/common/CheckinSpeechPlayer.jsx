import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Volume2, VolumeX } from "lucide-react";
import { api } from "../../services/api";
import { speakVietnamese } from "../../services/speech";

const STORAGE_KEY = "pulsefit-checkin-speaker-enabled";

export function CheckinSpeechPlayer({ enabled = true }) {
  const [localEnabled, setLocalEnabled] = useState(() => localStorage.getItem(STORAGE_KEY) !== "false");
  const [connected, setConnected] = useState(false);
  const lastEventId = useRef(0);
  const config = useQuery({
    queryKey: ["checkin-speech-config"],
    queryFn: () => api("/api/checkin-speech/config"),
    enabled,
    refetchInterval: 15_000,
    staleTime: 10_000,
  });
  const globallyEnabled = !!config.data?.enabled;

  useEffect(() => {
    if (!globallyEnabled || !localEnabled) {
      setConnected(false);
      return undefined;
    }
    const source = new EventSource("/api/checkin-speech/events", { withCredentials: true });
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    source.addEventListener("checkin", (event) => {
      const eventId = Number(event.lastEventId || 0);
      if (eventId && eventId <= lastEventId.current) return;
      try {
        const payload = JSON.parse(event.data);
        lastEventId.current = eventId || lastEventId.current;
        speakVietnamese(payload.message, {
          voiceUri: config.data?.voiceUri,
          voiceName: config.data?.voiceName,
          volume: config.data?.volume,
          rate: config.data?.rate,
          pitch: config.data?.pitch,
        });
      } catch {
        // Ignore malformed realtime events; EventSource remains connected.
      }
    });
    return () => source.close();
  }, [config.data?.pitch, config.data?.rate, config.data?.voiceName, config.data?.voiceUri, config.data?.volume, globallyEnabled, localEnabled]);

  if (!enabled || !globallyEnabled) return null;
  const toggle = () => {
    const next = !localEnabled;
    setLocalEnabled(next);
    localStorage.setItem(STORAGE_KEY, String(next));
    if (next && "speechSynthesis" in window) {
      speakVietnamese(".", { interrupt: true, volume: 0 });
    } else if (!next && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
  };
  return (
    <button
      type="button"
      className={`checkin-speech-toggle ${localEnabled ? "active" : ""} ${connected ? "connected" : ""}`}
      onClick={toggle}
      aria-label={localEnabled ? "Tắt loa chào check-in trên máy này" : "Bật loa chào check-in trên máy này"}
      title={localEnabled ? (connected ? "Loa check-in đang trực tuyến" : "Loa check-in đang kết nối") : "Loa check-in đang tắt trên máy này"}
    >
      {localEnabled ? <Volume2 size={17} /> : <VolumeX size={17} />}
      {localEnabled && <i />}
    </button>
  );
}
