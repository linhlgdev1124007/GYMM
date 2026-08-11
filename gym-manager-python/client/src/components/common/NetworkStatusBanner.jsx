import { useEffect, useRef, useState } from "react";
import { WifiOff } from "lucide-react";
import { notify } from "../../services/notify";

export function NetworkStatusBanner() {
  const [online, setOnline] = useState(() => navigator.onLine);
  const wasOffline = useRef(!navigator.onLine);

  useEffect(() => {
    const handleOffline = () => {
      wasOffline.current = true;
      setOnline(false);
    };
    const handleOnline = () => {
      setOnline(true);
      if (wasOffline.current) {
        notify.success("Đã kết nối lại.", { id: "network-restored" });
        wasOffline.current = false;
      }
    };
    window.addEventListener("offline", handleOffline);
    window.addEventListener("online", handleOnline);
    return () => {
      window.removeEventListener("offline", handleOffline);
      window.removeEventListener("online", handleOnline);
    };
  }, []);

  if (online) return null;
  return (
    <div className="system-banner" role="status" aria-live="polite">
      <WifiOff size={16} />
      <div>
        <strong>Mất kết nối mạng.</strong>
        <span>Một số thao tác có thể không thực hiện được.</span>
      </div>
    </div>
  );
}
