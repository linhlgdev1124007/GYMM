from __future__ import annotations

import base64
import json
import os
import queue
import random
import re
import sys
import threading
import time
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests
import tkinter as tk
from tkinter import messagebox, ttk


APP_NAME = "PulseFit DAH Agent"
DEFAULT_DAH_USERNAME = "system"
DEFAULT_DAH_PASSWORD = "admin"


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


CONFIG_PATH = app_dir() / "agent-config.json"
LOG_PATH = app_dir() / "agent.log"


def log(message: str) -> None:
    line = f"{datetime.now().isoformat(timespec='seconds')} {message}"
    try:
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass
    print(line)


@dataclass
class AgentConfig:
    server_host: str = "127.0.0.1"
    server_port: int = 8100
    server_scheme: str = "http"
    agent_id: str = "pulsefit-dah-agent-1"
    agent_token: str = ""
    dah_host: str = "192.168.1.60"
    dah_port: int = 80
    dah_username: str = DEFAULT_DAH_USERNAME
    dah_password: str = DEFAULT_DAH_PASSWORD
    auto_start: bool = True
    sync_interval_seconds: int = 300
    lookback_hours: int = 24
    browser_warmup: bool = True

    @property
    def server_base_url(self) -> str:
        host = self.server_host.strip().rstrip("/")
        if host.startswith("http://") or host.startswith("https://"):
            return host
        return f"{self.server_scheme}://{host}:{int(self.server_port)}"

    @property
    def dah_base_url(self) -> str:
        host = self.dah_host.strip().rstrip("/")
        if host.startswith("http://") or host.startswith("https://"):
            return host
        return f"http://{host}:{int(self.dah_port)}"


def load_config() -> AgentConfig:
    if not CONFIG_PATH.exists():
        return AgentConfig()
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        defaults = asdict(AgentConfig())
        defaults.update({k: v for k, v in data.items() if k in defaults})
        return AgentConfig(**defaults)
    except Exception as exc:
        log(f"CONFIG load failed: {exc}")
        return AgentConfig()


def save_config(config: AgentConfig) -> None:
    CONFIG_PATH.write_text(json.dumps(asdict(config), ensure_ascii=False, indent=2), encoding="utf-8")


def auth_headers(config: AgentConfig) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if config.agent_token.strip():
        headers["Authorization"] = f"Bearer {config.agent_token.strip()}"
    return headers


def parse_root_kv_response(text: str) -> dict[str, str]:
    return dict(re.findall(r"root\.([A-Za-z0-9_.]+)=([^\r\n<]*)", text or ""))


def parse_control_items(text: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    pairs = parse_root_kv_response(text)
    meta = {
        "sessionId": pairs.get("CONTROL.sessionid"),
        "totalCount": safe_int(pairs.get("CONTROL.totalcount"), 0),
        "beginNo": safe_int(pairs.get("CONTROL.beginno"), 0),
        "responseCount": safe_int(pairs.get("CONTROL.rspcount"), 0),
    }
    by_index: dict[int, dict[str, str]] = {}
    for key, value in pairs.items():
        match = re.match(r"CONTROL\.ITEM(\d+)\.(.+)", key)
        if not match:
            continue
        index = int(match.group(1))
        field = match.group(2)
        by_index.setdefault(index, {})[field] = value

    items = []
    for index in sorted(by_index):
        row = by_index[index]
        items.append({
            "dahUid": row.get("uid"),
            "eventTime": parse_dah_time(row.get("utime")),
            "rawEventTime": row.get("utime"),
            "status": safe_int(row.get("ustatus"), None),
            "similarity": safe_float(row.get("usimilarity"), None),
            "personType": safe_int(row.get("utype"), None),
            "name": clean_null(row.get("uname")),
            "mjCardNo": clean_null(row.get("MjCardNo")),
            "gender": safe_int(row.get("usex"), None),
            "birthDate": clean_null(row.get("ubirth")),
            "phone": clean_null(row.get("uphone")),
            "captureImageRef": image_ref(row, "cfile"),
            "profileImageRef": image_ref(row, "dwfile"),
            "raw": row,
        })
    return meta, items


def image_ref(row: dict[str, str], prefix: str) -> dict[str, int] | None:
    ftype = safe_int(row.get(f"{prefix}type"), None)
    findex = safe_int(row.get(f"{prefix}index"), None)
    fpos = safe_int(row.get(f"{prefix}pos"), None)
    if ftype is None or findex is None or fpos is None or fpos <= 0:
        return None
    return {"fileType": ftype, "fileIndex": findex, "filePos": fpos}


def clean_null(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text or text.lower() in {"null", "none", "undefined"}:
        return None
    return text


def safe_int(value: Any, default: int | None = 0) -> int | None:
    try:
        return int(str(value).strip())
    except Exception:
        return default


def safe_float(value: Any, default: float | None = 0.0) -> float | None:
    try:
        return float(str(value).strip())
    except Exception:
        return default


def parse_dah_time(value: str | None) -> str | None:
    text = clean_null(value)
    if not text:
        return None
    # DAH format from HAR: 2026-08-19/21:25:18. Treat as Vietnam local time.
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d/%H:%M:%S")
        return parsed.isoformat()
    except ValueError:
        return text.replace("/", "T", 1)


class DahClient:
    def __init__(self, config: AgentConfig):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "PulseFitDahAgent/1.0",
            "Content-Type": "text/html; charset=UTF-8",
        })
        basic = base64.b64encode(f"{config.dah_username}:{config.dah_password}".encode()).decode()
        self.session.headers.update({"Authorization": f"Basic {basic}"})

    def warmup_browser(self) -> None:
        if not self.config.browser_warmup:
            return
        try:
            from selenium import webdriver
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
        except Exception as exc:
            log(f"Browser warmup skipped: selenium unavailable: {exc}")
            return

        driver = None
        try:
            options = webdriver.ChromeOptions()
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--window-size=1280,900")
            driver = webdriver.Chrome(options=options)
            wait = WebDriverWait(driver, 12)
            driver.get(f"{self.config.dah_base_url}/login.asp")
            self._switch_to_element_frame(driver, By.ID, "username")
            self._set_value(driver, By.ID, "username", self.config.dah_username)
            self._set_value(driver, By.ID, "password", self.config.dah_password)
            self._click(driver, By.ID, "b_login")
            time.sleep(1.5)
            self._switch_to_element_frame(driver, By.ID, "b_control")
            self._click(driver, By.ID, "b_control")
            time.sleep(1.0)
            self._switch_to_element_frame(driver, By.ID, "laSearch")
            self._click(driver, By.ID, "laSearch")
            time.sleep(1.0)
            for cookie in driver.get_cookies():
                if cookie.get("name"):
                    self.session.cookies.set(cookie["name"], cookie.get("value", ""), domain=cookie.get("domain"))
            log("DAH browser warmup completed")
        except Exception as exc:
            log(f"DAH browser warmup failed; continuing direct API pull: {exc}")
        finally:
            if driver:
                driver.quit()

    def _switch_to_element_frame(self, driver, by, value: str) -> bool:
        driver.switch_to.default_content()
        if driver.find_elements(by, value):
            return True
        frames = driver.find_elements("tag name", "frame") + driver.find_elements("tag name", "iframe")
        for frame in frames:
            driver.switch_to.default_content()
            driver.switch_to.frame(frame)
            if driver.find_elements(by, value):
                return True
        driver.switch_to.default_content()
        return False

    def _set_value(self, driver, by, value: str, text: str) -> None:
        element = driver.find_element(by, value)
        element.clear()
        element.send_keys(text)

    def _click(self, driver, by, value: str) -> None:
        element = driver.find_element(by, value)
        element.click()

    def get_control_page(self, begin_time: datetime, end_time: datetime, begin_no: int, req_count: int, session_id: int = 0) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        begin = quote(begin_time.strftime("%Y-%m-%d/%H:%M:%S"), safe="/:")
        end = quote(end_time.strftime("%Y-%m-%d/%H:%M:%S"), safe="/:")
        url = (
            f"{self.config.dah_base_url}/webs/getControl"
            f"?action=list&group=CONTROL"
            f"&ustatus=0&usex=2&uage=0-100&MjCardNo=0"
            f"&begintime={begin}&endtime={end}"
            f"&utype=0&sequence=1&beginno={int(begin_no)}&reqcount={int(req_count)}"
            f"&sessionid={int(session_id or 0)}&RanId={random.randint(10000000,99999999)}"
        )
        response = self.session.get(url, timeout=25)
        response.raise_for_status()
        return parse_control_items(response.text)

    def fetch_events(self, lookback_hours: int | None = None, req_count: int = 20) -> dict[str, Any]:
        self.warmup_browser()
        end = datetime.now()
        begin = end - timedelta(hours=max(int(lookback_hours or self.config.lookback_hours or 24), 1))
        all_items: list[dict[str, Any]] = []
        first_meta, first_items = self.get_control_page(begin, end, 0, req_count, 0)
        all_items.extend(first_items)
        total = int(first_meta.get("totalCount") or len(first_items))
        session_id = int(first_meta.get("sessionId") or 0)
        begin_no = len(first_items)
        while begin_no < total:
            meta, items = self.get_control_page(begin, end, begin_no, req_count, session_id)
            all_items.extend(items)
            if not items:
                break
            begin_no += len(items)
        return {
            "deviceCode": f"DAH-{self.config.dah_host}",
            "dahBaseUrl": self.config.dah_base_url,
            "pulledAt": datetime.now().isoformat(),
            "range": {"begin": begin.isoformat(), "end": end.isoformat()},
            "totalCount": total,
            "events": all_items,
        }


class ServerClient:
    def __init__(self, config: AgentConfig):
        self.config = config
        self.session = requests.Session()

    def heartbeat(self) -> None:
        payload = {
            "agentId": self.config.agent_id,
            "status": "online",
            "dahBaseUrl": self.config.dah_base_url,
            "version": "1.0.0",
        }
        self.session.post(
            f"{self.config.server_base_url}/api/dah/local-agent/heartbeat",
            json=payload,
            headers=auth_headers(self.config),
            timeout=15,
        ).raise_for_status()

    def next_job(self) -> dict[str, Any] | None:
        response = self.session.get(
            f"{self.config.server_base_url}/api/dah/local-agent/jobs/next",
            params={"agentId": self.config.agent_id, "timeout": 55},
            headers=auth_headers(self.config),
            timeout=70,
        )
        if response.status_code == 204:
            return None
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) and data.get("id") else None

    def post_result(self, job_id: str, result: dict[str, Any]) -> None:
        self.session.post(
            f"{self.config.server_base_url}/api/dah/local-agent/jobs/{job_id}/result",
            json=result,
            headers=auth_headers(self.config),
            timeout=60,
        ).raise_for_status()


class AgentWorker:
    def __init__(self, config: AgentConfig, events: queue.Queue[str]):
        self.config = config
        self.events = events
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.sync_now_event = threading.Event()

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, name="PulseFitDahAgentWorker", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.sync_now_event.set()

    def trigger_sync(self) -> None:
        self.sync_now_event.set()

    def _emit(self, message: str) -> None:
        log(message)
        self.events.put(message)

    def _run(self) -> None:
        server = ServerClient(self.config)
        next_auto = time.monotonic()
        self._emit("Agent started")
        while not self.stop_event.is_set():
            try:
                try:
                    server.heartbeat()
                    self._emit("Heartbeat sent")
                except Exception as exc:
                    self._emit(f"Heartbeat failed: {exc}")

                try:
                    job = server.next_job()
                except Exception as exc:
                    self._emit(f"Long polling failed: {exc}")
                    job = None

                should_auto_sync = time.monotonic() >= next_auto
                should_manual_sync = self.sync_now_event.is_set()
                if job or should_auto_sync or should_manual_sync:
                    self.sync_now_event.clear()
                    if should_auto_sync:
                        next_auto = time.monotonic() + max(int(self.config.sync_interval_seconds), 60)
                    self._run_sync(server, job)
                self.stop_event.wait(3)
            except Exception:
                self._emit("Worker loop error:\n" + traceback.format_exc())
                self.stop_event.wait(10)
        self._emit("Agent stopped")

    def _run_sync(self, server: ServerClient, job: dict[str, Any] | None) -> None:
        job_id = str(job.get("id")) if job else f"local-{int(time.time())}"
        lookback = safe_int((job or {}).get("lookbackHours"), self.config.lookback_hours)
        self._emit(f"Sync started: {job_id}")
        try:
            result = DahClient(self.config).fetch_events(lookback_hours=lookback)
            result.update({"agentId": self.config.agent_id, "jobId": job_id, "ok": True})
            self._emit(f"Sync pulled {len(result.get('events', []))} events")
        except Exception as exc:
            result = {
                "agentId": self.config.agent_id,
                "jobId": job_id,
                "ok": False,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
            self._emit(f"Sync failed: {exc}")
        if job:
            try:
                server.post_result(job_id, result)
                self._emit(f"Sync result posted: {job_id}")
            except Exception as exc:
                self._emit(f"Post result failed: {exc}")
        else:
            # Server may not have job endpoints yet. Try a conventional result endpoint anyway.
            try:
                server.post_result(job_id, result)
                self._emit(f"Local sync result posted: {job_id}")
            except Exception as exc:
                self._emit(f"Local sync result not posted: {exc}")


class AgentApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("760x560")
        self.minsize(720, 520)
        self.config_data = load_config()
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.worker: AgentWorker | None = None
        self.vars: dict[str, tk.Variable] = {}
        self._build_ui()
        self._load_vars()
        self.after(300, self._drain_logs)
        if self.config_data.auto_start:
            self.start_worker()

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)
        form = ttk.LabelFrame(root, text="Settings", padding=10)
        form.pack(fill="x")

        self._add_entry(form, "Server scheme", "server_scheme", 0, width=8)
        self._add_entry(form, "Server host", "server_host", 1, width=32)
        self._add_entry(form, "Server port", "server_port", 2, width=8)
        self._add_entry(form, "Agent ID", "agent_id", 3, width=32)
        self._add_entry(form, "Agent token", "agent_token", 4, width=48, show="*")
        self._add_entry(form, "DAH host", "dah_host", 5, width=32)
        self._add_entry(form, "DAH port", "dah_port", 6, width=8)
        self._add_entry(form, "DAH username", "dah_username", 7, width=20)
        self._add_entry(form, "DAH password", "dah_password", 8, width=20, show="*")
        self._add_entry(form, "Sync interval seconds", "sync_interval_seconds", 9, width=8)
        self._add_entry(form, "Lookback hours", "lookback_hours", 10, width=8)

        self.vars["auto_start"] = tk.BooleanVar()
        ttk.Checkbutton(form, text="Auto start worker when app opens", variable=self.vars["auto_start"]).grid(row=11, column=1, sticky="w", pady=3)
        self.vars["browser_warmup"] = tk.BooleanVar()
        ttk.Checkbutton(form, text="Use hidden browser warmup/login before pulling API", variable=self.vars["browser_warmup"]).grid(row=12, column=1, sticky="w", pady=3)

        actions = ttk.Frame(root)
        actions.pack(fill="x", pady=10)
        ttk.Button(actions, text="Save", command=self.save).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Start", command=self.start_worker).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Stop", command=self.stop_worker).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Sync now", command=self.sync_now).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Install Startup", command=self.install_startup).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Remove Startup", command=self.remove_startup).pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Open log file", command=self.open_log).pack(side="left")

        self.status_var = tk.StringVar(value="Stopped")
        ttk.Label(root, textvariable=self.status_var).pack(anchor="w", pady=(0, 6))

        log_frame = ttk.LabelFrame(root, text="Log", padding=8)
        log_frame.pack(fill="both", expand=True)
        self.log_text = tk.Text(log_frame, wrap="word", height=12)
        self.log_text.pack(fill="both", expand=True)

    def _add_entry(self, parent, label: str, key: str, row: int, width: int = 24, show: str | None = None) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="e", padx=(0, 8), pady=3)
        var = tk.StringVar()
        self.vars[key] = var
        entry = ttk.Entry(parent, textvariable=var, width=width, show=show or "")
        entry.grid(row=row, column=1, sticky="w", pady=3)

    def _load_vars(self) -> None:
        for key, value in asdict(self.config_data).items():
            var = self.vars.get(key)
            if isinstance(var, tk.BooleanVar):
                var.set(bool(value))
            elif var is not None:
                var.set(str(value))

    def _read_config_from_vars(self) -> AgentConfig:
        data = asdict(self.config_data)
        for key, var in self.vars.items():
            value = var.get()
            if key in {"server_port", "dah_port", "sync_interval_seconds", "lookback_hours"}:
                data[key] = safe_int(value, data[key])
            elif key in {"auto_start", "browser_warmup"}:
                data[key] = bool(value)
            else:
                data[key] = str(value).strip()
        return AgentConfig(**data)

    def save(self) -> None:
        self.config_data = self._read_config_from_vars()
        save_config(self.config_data)
        self._append_log(f"Saved config to {CONFIG_PATH}")

    def start_worker(self) -> None:
        self.save()
        if self.worker:
            self.worker.stop()
        self.worker = AgentWorker(self.config_data, self.log_queue)
        self.worker.start()
        self.status_var.set("Running")

    def stop_worker(self) -> None:
        if self.worker:
            self.worker.stop()
        self.status_var.set("Stopping")

    def sync_now(self) -> None:
        if not self.worker:
            self.start_worker()
        if self.worker:
            self.worker.trigger_sync()
            self._append_log("Manual sync requested")

    def open_log(self) -> None:
        try:
            os.startfile(LOG_PATH)
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))

    def startup_script_path(self) -> Path:
        startup = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
        return startup / "PulseFitDahAgent.cmd"

    def install_startup(self) -> None:
        try:
            self.save()
            target = Path(sys.executable).resolve() if getattr(sys, "frozen", False) else Path(__file__).resolve()
            script = self.startup_script_path()
            script.parent.mkdir(parents=True, exist_ok=True)
            if getattr(sys, "frozen", False):
                content = f'@echo off\r\nstart "" "{target}"\r\n'
            else:
                content = f'@echo off\r\nstart "" pythonw "{target}"\r\n'
            script.write_text(content, encoding="utf-8")
            self._append_log(f"Installed Windows Startup launcher: {script}")
            messagebox.showinfo(APP_NAME, "Đã cài khởi chạy cùng Windows.")
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))

    def remove_startup(self) -> None:
        try:
            script = self.startup_script_path()
            if script.exists():
                script.unlink()
            self._append_log(f"Removed Windows Startup launcher: {script}")
            messagebox.showinfo(APP_NAME, "Đã gỡ khởi chạy cùng Windows.")
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))

    def _drain_logs(self) -> None:
        while True:
            try:
                message = self.log_queue.get_nowait()
            except queue.Empty:
                break
            self._append_log(message)
        self.after(300, self._drain_logs)

    def _append_log(self, message: str) -> None:
        self.log_text.insert("end", f"{datetime.now().strftime('%H:%M:%S')} {message}\n")
        self.log_text.see("end")


def main() -> None:
    app = AgentApp()
    app.mainloop()


if __name__ == "__main__":
    main()
