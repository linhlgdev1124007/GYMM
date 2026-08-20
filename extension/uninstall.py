from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk

try:
    import psutil
except ImportError:
    psutil = None


APP_NAME = "Gỡ cài đặt PulseFit DAH Agent"
TASK_NAME = "PulseFitDahAgent"


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def ensure_admin() -> bool:
    """
    Yêu cầu quyền Administrator trước khi thực hiện gỡ cài đặt.
    """
    if is_admin():
        return True
    try:
        if getattr(sys, "frozen", False):
            exe = sys.executable
            params = " ".join([f'"{arg}"' for arg in sys.argv[1:]])
        else:
            exe = sys.executable
            script_path = str(Path(__file__).resolve())
            params = f'"{script_path}" ' + " ".join([f'"{arg}"' for arg in sys.argv[1:]])

        ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
        if int(ret) > 32:
            sys.exit(0)
        else:
            return False
    except Exception:
        return False


def get_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


class UninstallerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("540x420")
        self.minsize(500, 380)
        self.resizable(False, False)

        self._build_ui()

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=16)
        root.pack(fill="both", expand=True)

        # Header Title
        title_label = tk.Label(
            root,
            text="Trình gỡ cài đặt PulseFit DAH Agent",
            font=("Segoe UI", 12, "bold"),
            fg="#DC2626"
        )
        title_label.pack(anchor="w", pady=(0, 4))

        desc_label = tk.Label(
            root,
            text="Công cụ này sẽ dừng toàn bộ tiến trình chạy ngầm, xóa tự khởi động\ncùng Windows (Task Scheduler) và dọn dẹp các tệp liên quan.",
            font=("Segoe UI", 9),
            fg="#4B5563",
            justify="left"
        )
        desc_label.pack(anchor="w", pady=(0, 12))

        # Checkboxes options
        options_frame = ttk.LabelFrame(root, text="Tùy chọn gỡ cài đặt", padding=10)
        options_frame.pack(fill="x", pady=(0, 12))

        self.var_kill_process = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="Dừng tiến trình PulseFitDahAgent đang chạy ngầm", variable=self.var_kill_process).pack(anchor="w", pady=2)

        self.var_remove_task = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="Xóa tác vụ khởi động cùng Windows (Task Scheduler & Startup)", variable=self.var_remove_task).pack(anchor="w", pady=2)

        self.var_delete_data = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="Xóa tệp cấu hình (agent-config.json) và nhật ký (agent.log)", variable=self.var_delete_data).pack(anchor="w", pady=2)

        self.var_delete_exe = tk.BooleanVar(value=True)
        ttk.Checkbutton(options_frame, text="Xóa tệp chương trình PulseFitDahAgent.exe", variable=self.var_delete_exe).pack(anchor="w", pady=2)

        # Progress / Log Box
        log_frame = ttk.LabelFrame(root, text="Tiến trình thực hiện", padding=6)
        log_frame.pack(fill="both", expand=True, pady=(0, 12))

        self.log_text = tk.Text(log_frame, wrap="word", height=6, font=("Consolas", 8))
        self.log_text.pack(fill="both", expand=True)

        # Action Buttons
        btn_frame = ttk.Frame(root)
        btn_frame.pack(fill="x")

        self.btn_uninstall = ttk.Button(btn_frame, text="Gỡ cài đặt ngay", command=self.start_uninstall)
        self.btn_uninstall.pack(side="right", padx=(6, 0))

        self.btn_close = ttk.Button(btn_frame, text="Đóng", command=self.destroy)
        self.btn_close.pack(side="right")

    def _log(self, message: str) -> None:
        self.log_text.insert("end", f"[{time.strftime('%H:%M:%S')}] {message}\n")
        self.log_text.see("end")

    def start_uninstall(self) -> None:
        confirm = messagebox.askyesno(
            APP_NAME,
            "Bạn có chắc chắn muốn gỡ cài đặt PulseFit DAH Agent khỏi máy tính?",
            icon="warning"
        )
        if not confirm:
            return

        self.btn_uninstall.config(state="disabled")
        self.btn_close.config(state="disabled")
        threading.Thread(target=self._run_uninstall_worker, daemon=True).start()

    def _run_uninstall_worker(self) -> None:
        app_dir = get_app_dir()
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)

        # 1. Dừng tiến trình đang chạy
        if self.var_kill_process.get():
            self._log("Đang kiểm tra và tắt tiến trình PulseFitDahAgent.exe...")
            if psutil:
                try:
                    for p in psutil.process_iter(["name"]):
                        if "pulsefit" in (p.info.get("name") or "").lower():
                            p.kill()
                except Exception:
                    pass
            try:
                subprocess.run(["taskkill", "/f", "/im", "PulseFitDahAgent.exe"], capture_output=True, creationflags=flags)
                time.sleep(1)
                self._log("-> Đã dừng tiến trình PulseFitDahAgent.")
            except Exception as exc:
                self._log(f"-> Lỗi khi tắt tiến trình: {exc}")

        # 2. Xóa Task Scheduler
        if self.var_remove_task.get():
            self._log("Đang xóa tác vụ trong Windows Task Scheduler...")
            try:
                res = subprocess.run(["schtasks", "/delete", "/tn", TASK_NAME, "/f"], capture_output=True, text=True, creationflags=flags)
                if res.returncode == 0:
                    self._log("-> Đã xóa thành công Task Scheduler 'PulseFitDahAgent'.")
                else:
                    self._log("-> Tác vụ Task Scheduler không tồn tại hoặc đã được xóa trước đó.")
            except Exception as exc:
                self._log(f"-> Lỗi xóa Task Scheduler: {exc}")

            # Xóa file Startup cũ trong Start Menu nếu còn
            try:
                startup = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
                cmd_script = startup / "PulseFitDahAgent.cmd"
                if cmd_script.exists():
                    cmd_script.unlink()
                    self._log("-> Đã xóa file khởi động trong thư mục Startup.")
            except Exception as exc:
                self._log(f"-> Lỗi xóa file Startup: {exc}")

        # 3. Xóa tệp dữ liệu & cấu hình
        if self.var_delete_data.get():
            self._log("Đang xóa tệp cấu hình và log...")
            for filename in ["agent-config.json", "agent.log"]:
                for target_path in [app_dir / filename, app_dir.parent / filename]:
                    try:
                        if target_path.exists():
                            target_path.unlink()
                            self._log(f"-> Đã xóa: {target_path.name}")
                    except Exception as exc:
                        self._log(f"-> Không thể xóa {target_path.name}: {exc}")

        # 4. Xóa file PulseFitDahAgent.exe
        if self.var_delete_exe.get():
            self._log("Đang xóa file chương trình PulseFitDahAgent.exe...")
            for target_exe in [app_dir / "PulseFitDahAgent.exe", app_dir.parent / "PulseFitDahAgent.exe", app_dir.parent / "app" / "PulseFitDahAgent.exe"]:
                try:
                    if target_exe.exists():
                        target_exe.unlink()
                        self._log(f"-> Đã xóa file: {target_exe}")
                except Exception as exc:
                    self._log(f"-> Không thể xóa {target_exe.name} (file có thể đang được mở): {exc}")

        self._log("=== HOÀN TẤT GỠ CÀI ĐẶT THÀNH CÔNG ===")
        self.after(0, self._on_finish)

    def _on_finish(self) -> None:
        self.btn_close.config(state="normal")
        messagebox.showinfo(APP_NAME, "Đã hoàn tất gỡ cài đặt PulseFit DAH Agent khỏi hệ thống!")


def main() -> None:
    ensure_admin()
    app = UninstallerApp()
    app.mainloop()


if __name__ == "__main__":
    main()
