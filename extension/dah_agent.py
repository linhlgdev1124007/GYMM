from __future__ import annotations

import base64
import ctypes
import json
import os
import queue
import random
import re
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

from PIL import Image, ImageDraw
import pystray
import requests
import tkinter as tk
from tkinter import messagebox, ttk


APP_NAME = "PulseFit DAH Agent"
DEFAULT_DAH_USERNAME = "system"
DEFAULT_DAH_PASSWORD = "admin"
TASK_NAME = "PulseFitDahAgent"


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


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def ensure_admin() -> bool:
    """
    Tự động xin quyền Administrator thông qua Windows UAC nếu chưa có.
    """
    if is_admin():
        return True
    try:
        if getattr(sys, "frozen", False):
            exe = sys.executable
            params = " ".join([f'"{arg}"' for arg in sys.argv[1:]]) if len(sys.argv) > 1 else ""
        else:
            exe = sys.executable
            script_path = str(Path(__file__).resolve())
            extra_args = " ".join([f'"{arg}"' for arg in sys.argv[1:]]) if len(sys.argv) > 1 else ""
            params = f'"{script_path}" {extra_args}'.strip()

        # Gọi ShellExecuteW với động từ "runas" để mở bảng UAC xác nhận
        ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params or None, None, 1)
        if int(ret) > 32:
            # Đã mở tiến trình quyền Admin mới, kết thúc tiến trình hiện tại
            sys.exit(0)
        else:
            log(f"Người dùng từ chối cấp quyền Admin (mã lỗi: {ret}). Chạy với quyền Standard User.")
            return False
    except Exception as exc:
        log(f"Lỗi khi xin quyền Administrator: {exc}")
        return False


def setup_startup_task(enable: bool = True) -> bool:
    """
    Đăng ký tự động khởi chạy cùng Windows thông qua Task Scheduler
    với quyền Admin cao nhất (/rl highest) khi người dùng logon (/sc onlogon).
    """
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        if enable:
            if getattr(sys, "frozen", False):
                target_exe = str(Path(sys.executable).resolve())
                target_cmd = f'\\"{target_exe}\\"'
            else:
                pythonw = Path(sys.executable).parent / "pythonw.exe"
                exe_to_use = str(pythonw if pythonw.exists() else Path(sys.executable).resolve())
                script_path = str(Path(__file__).resolve())
                target_cmd = f'\\"{exe_to_use}\\" \\"{script_path}\\"'

            cmd = [
                "schtasks", "/create",
                "/tn", TASK_NAME,
                "/tr", target_cmd,
                "/sc", "onlogon",
                "/rl", "highest",
                "/f"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, creationflags=flags)
            if res.returncode == 0:
                log("Đã đăng ký tự khởi động cùng Windows (Task Scheduler - Highest Privileges).")
                return True
            else:
                # Nếu chạy ở quyền thường không đặt được /rl highest, thử quyền thông thường
                log(f"Thông báo đăng ký Task Scheduler (/rl highest): {res.stderr.strip() or res.stdout.strip()}")
                cmd_fallback = [
                    "schtasks", "/create",
                    "/tn", TASK_NAME,
                    "/tr", target_cmd,
                    "/sc", "onlogon",
                    "/f"
                ]
                res2 = subprocess.run(cmd_fallback, capture_output=True, text=True, creationflags=flags)
                if res2.returncode == 0:
                    log("Đã đăng ký tự khởi động cùng Windows (Task Scheduler - Standard).")
                    return True
                return False
        else:
            cmd = ["schtasks", "/delete", "/tn", TASK_NAME, "/f"]
            subprocess.run(cmd, capture_output=True, text=True, creationflags=flags)
            log("Đã gỡ bỏ tác vụ tự khởi động trong Task Scheduler.")
            return True
    except Exception as exc:
        log(f"Lỗi cấu hình Task Scheduler: {exc}")
    return False


def create_tray_icon_image() -> Image.Image:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Background rounded circle
    draw.ellipse((2, 2, 62, 62), fill="#1E40AF", outline="#60A5FA", width=3)
    # Pulse waveform
    points = [(10, 32), (20, 32), (26, 16), (36, 48), (42, 24), (48, 32), (54, 32)]
    draw.line(points, fill="#10B981", width=5, joint="round")
    return img


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
    sync_interval_seconds: int = 1800
    lookback_hours: int = 24
    scan_start_date: str = "2026-08-19"
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
        profile_ref = image_ref(row, "dwfile")
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
            "profileImageRef": profile_ref,
            "profileKey": profile_key(profile_ref),
            "raw": row,
        })
    return meta, items


def parse_list_items(text: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    pairs = parse_root_kv_response(text)
    meta = {
        "sessionId": pairs.get("LIST.sessionid"),
        "totalCount": safe_int(pairs.get("LIST.totalcount"), 0),
        "beginNo": safe_int(pairs.get("LIST.beginno"), 0),
        "responseCount": safe_int(pairs.get("LIST.rspcount"), 0),
    }
    by_index: dict[int, dict[str, str]] = {}
    for key, value in pairs.items():
        match = re.match(r"LIST\.ITEM(\d+)\.(.+)", key)
        if not match:
            continue
        index = int(match.group(1))
        field = match.group(2)
        by_index.setdefault(index, {})[field] = value

    items = []
    for index in sorted(by_index):
        row = by_index[index]
        profile_ref = image_ref(row, "dwfile")
        items.append({
            "dahPersonUid": clean_null(row.get("uid")),
            "personType": safe_int(row.get("utype"), None),
            "name": clean_null(row.get("uname")),
            "mjCardNo": clean_null(row.get("MjCardNo")),
            "gender": safe_int(row.get("usex"), None),
            "birthDate": clean_null(row.get("ubirth")),
            "phone": clean_null(row.get("uphone")),
            "profileImageRef": profile_ref,
            "profileKey": profile_key(profile_ref),
            "registeredAt": parse_dah_time(row.get("utime")),
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


def profile_key(ref: dict[str, int] | None) -> str | None:
    if not ref:
        return None
    return f"dah_profile:{ref['fileType']}/{ref['fileIndex']}/{ref['filePos']}"


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
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d/%H:%M:%S")
        return parsed.isoformat()
    except ValueError:
        return text.replace("/", "T", 1)


def parse_iso_datetime(value: Any) -> datetime:
    text = clean_null(value)
    if not text:
        return datetime.now()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo:
            parsed = parsed.astimezone().replace(tzinfo=None)
        return parsed
    except ValueError:
        return datetime.now()


class DahClient:
    def __init__(self, config: AgentConfig):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "PulseFitDahAgent/1.1",
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
            options.add_argument("--log-level=3")
            options.add_experimental_option("excludeSwitches", ["enable-logging"])
            driver = webdriver.Chrome(options=options)
            driver.set_page_load_timeout(20)
            driver.implicitly_wait(4)

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
                try:
                    driver.quit()
                except Exception:
                    pass

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

    def get_whitelist_page(self, begin_no: int, req_count: int, session_id: int = 0) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        begin = quote("2020-01-01/00:00:00", safe="/:")
        end = quote("2038-08-19/23:59:59", safe="/:")
        url = (
            f"{self.config.dah_base_url}/webs/getWhitelist"
            f"?action=list&group=LIST"
            f"&uflag=0&usex=2&uage=0-100&MjCardNo=0&pfsel=0&bIsPicNormal=0"
            f"&begintime={begin}&endtime={end}&utype=3"
            f"&sequence=1&beginno={int(begin_no)}&reqcount={int(req_count)}"
            f"&sessionid={int(session_id or 0)}&RanId={random.randint(10000000,99999999)}"
        )
        response = self.session.get(url, timeout=25)
        response.raise_for_status()
        return parse_list_items(response.text)

    def fetch_whitelist(self, req_count: int = 20) -> list[dict[str, Any]]:
        all_items: list[dict[str, Any]] = []
        first_meta, first_items = self.get_whitelist_page(0, req_count, 0)
        all_items.extend(first_items)
        total = int(first_meta.get("totalCount") or 0)
        session_id = int(first_meta.get("sessionId") or 0)
        begin_no = len(first_items)
        max_pages = 500
        pages = 1
        while True:
            if total and begin_no >= total:
                break
            if len(first_items) < req_count and not total:
                break
            if pages >= max_pages:
                log(f"Whitelist pagination stopped at safety limit: {len(all_items)} items")
                break
            meta, items = self.get_whitelist_page(begin_no, req_count, session_id)
            all_items.extend(items)
            if not items:
                break
            pages += 1
            begin_no += len(items)
            if len(items) < req_count and not total:
                break
            if not session_id:
                session_id = int(meta.get("sessionId") or 0)
        log(f"DAH whitelist pulled {len(all_items)} people")
        return all_items

    def fetch_events_range(self, begin: datetime, end: datetime, whitelist: list[dict[str, Any]] | None = None, req_count: int = 20) -> dict[str, Any]:
        whitelist = whitelist if whitelist is not None else self.fetch_whitelist()
        whitelist_by_profile = {row.get("profileKey"): row for row in whitelist if row.get("profileKey")}
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
        for item in all_items:
            registered = whitelist_by_profile.get(item.get("profileKey"))
            if registered:
                item["dahPersonUid"] = registered.get("dahPersonUid")
                item["registeredName"] = registered.get("name")
                item["registeredPhone"] = registered.get("phone")
                item["registeredAt"] = registered.get("registeredAt")
        return {
            "deviceCode": f"DAH-{self.config.dah_host}",
            "dahBaseUrl": self.config.dah_base_url,
            "pulledAt": datetime.now().isoformat(),
            "range": {"begin": begin.isoformat(), "end": end.isoformat()},
            "totalCount": total,
            "whitelistCount": len(whitelist),
            "events": all_items,
        }

    def fetch_events(self, lookback_hours: int | None = None, req_count: int = 20) -> dict[str, Any]:
        self.warmup_browser()
        end = datetime.now()
        begin = end - timedelta(hours=max(int(lookback_hours or self.config.lookback_hours or 24), 1))
        return self.fetch_events_range(begin, end, req_count=req_count)


class ServerClient:
    def __init__(self, config: AgentConfig):
        self.config = config
        self.session = requests.Session()

    def heartbeat(self) -> None:
        payload = {
            "agentId": self.config.agent_id,
            "status": "online",
            "dahBaseUrl": self.config.dah_base_url,
            "version": "1.1.0",
            "isAdmin": is_admin(),
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

    def scan_plan(self) -> list[dict[str, Any]]:
        response = self.session.post(
            f"{self.config.server_base_url}/api/dah/local-agent/scan-plan",
            json={"agentId": self.config.agent_id, "from": self.config.scan_start_date},
            headers=auth_headers(self.config),
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("items") if isinstance(data, dict) and isinstance(data.get("items"), list) else []

    def post_day_scan_result(self, result: dict[str, Any]) -> None:
        self.session.post(
            f"{self.config.server_base_url}/api/dah/local-agent/day-scan-result",
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
        self._emit("PulseFit Worker started")
        while not self.stop_event.is_set():
            try:
                # 1. Heartbeat
                try:
                    server.heartbeat()
                    self._emit("Heartbeat sent")
                except Exception as exc:
                    self._emit(f"Heartbeat failed: {exc}")

                # 2. Long polling next job
                job = None
                try:
                    job = server.next_job()
                except Exception as exc:
                    self._emit(f"Long polling failed: {exc}")

                # 3. Handle Job / Periodic Sync / Manual Sync
                should_auto_sync = time.monotonic() >= next_auto
                should_manual_sync = self.sync_now_event.is_set()

                if job:
                    self._run_sync(server, job)
                elif should_manual_sync or should_auto_sync:
                    self.sync_now_event.clear()
                    if should_auto_sync:
                        interval = max(int(self.config.sync_interval_seconds or 1800), 300)
                        next_auto = time.monotonic() + interval
                    # Chạy đồng bộ thông thường theo lookback_hours
                    self._run_sync(server, None)
                    # Quét bù các ngày còn thiếu nếu có kế hoạch
                    self._run_day_scans(server)

                self.stop_event.wait(3)
            except Exception:
                self._emit("Worker loop error:\n" + traceback.format_exc())
                self.stop_event.wait(10)
        self._emit("PulseFit Worker stopped")

    def _run_sync(self, server: ServerClient, job: dict[str, Any] | None) -> None:
        job_id = str(job.get("id")) if job else f"local-{int(time.time())}"
        lookback = safe_int((job or {}).get("lookbackHours"), self.config.lookback_hours)
        self._emit(f"Sync started: {job_id} (lookback={lookback}h)")
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

        try:
            server.post_result(job_id, result)
            self._emit(f"Sync result posted: {job_id}")
        except Exception as exc:
            self._emit(f"Post result failed ({job_id}): {exc}")

    def _run_day_scans(self, server: ServerClient) -> None:
        try:
            plan = server.scan_plan()
        except Exception as exc:
            self._emit(f"Day scan plan notice: {exc}")
            return
        if not plan:
            return

        self._emit(f"Day scan plan: {len(plan)} day(s)")
        client = DahClient(self.config)
        try:
            client.warmup_browser()
            whitelist = client.fetch_whitelist()
        except Exception as exc:
            self._emit(f"Day scan setup failed: {exc}")
            return

        for item in plan:
            if self.stop_event.is_set():
                return
            work_date = clean_null(item.get("workDate")) or "unknown"
            range_payload = item.get("range") if isinstance(item.get("range"), dict) else {}
            begin = parse_iso_datetime(range_payload.get("begin"))
            end = parse_iso_datetime(range_payload.get("end"))
            self._emit(f"Day scan started: {work_date}")
            try:
                result = client.fetch_events_range(begin, end, whitelist=whitelist)
                result.update({
                    "agentId": self.config.agent_id,
                    "jobId": f"scan-{work_date}-{int(time.time())}",
                    "ok": True,
                    "workDate": work_date,
                    "range": {"begin": begin.isoformat(), "end": end.isoformat()},
                })
                server.post_day_scan_result(result)
                self._emit(f"Day scan posted: {work_date}, {len(result.get('events', []))} events")
            except Exception as exc:
                self._emit(f"Day scan failed {work_date}: {exc}")


class AgentApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("780x620")
        self.minsize(740, 560)
        self.config_data = load_config()
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.worker: AgentWorker | None = None
        self.vars: dict[str, tk.Variable] = {}
        self.tray_icon: pystray.Icon | None = None

        self._build_ui()
        self._load_vars()
        self._setup_tray()

        # Chặn sự kiện tắt cửa sổ -> Ẩn xuống khay hệ thống (System Tray)
        self.protocol("WM_DELETE_WINDOW", self.hide_to_tray)

        self.after(300, self._drain_logs)

        # Tự động cấu hình Auto-Startup với Task Scheduler (quyền Admin cao nhất)
        setup_startup_task(True)

        # Tự động kích hoạt Worker ngay khi bật App
        if self.config_data.auto_start:
            self.start_worker()

    def _setup_tray(self) -> None:
        try:
            menu = pystray.Menu(
                pystray.MenuItem("Mở giao diện PulseFit Agent", self._tray_open, default=True),
                pystray.MenuItem("Đồng bộ ngay (Sync now)", self._tray_sync),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Trạng thái: Đang bảo vệ & Chạy ngầm", lambda icon, item: None, enabled=False),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("Thoát ứng dụng (Yêu cầu xác nhận)", self._tray_exit),
            )
            self.tray_icon = pystray.Icon("PulseFitDahAgent", create_tray_icon_image(), APP_NAME, menu)
            threading.Thread(target=self.tray_icon.run, name="PulseFitTrayThread", daemon=True).start()
        except Exception as exc:
            log(f"Không thể khởi tạo khay hệ thống System Tray: {exc}")

    def _tray_open(self, icon=None, item=None) -> None:
        self.after(0, self.show_from_tray)

    def _tray_sync(self, icon=None, item=None) -> None:
        self.after(0, self.sync_now)

    def _tray_exit(self, icon=None, item=None) -> None:
        self.after(0, self.confirm_exit)

    def hide_to_tray(self) -> None:
        self.withdraw()
        self._append_log("Ứng dụng đã được ẩn xuống khay hệ thống (System Tray). Tiến trình vẫn hoạt động ngầm.")
        try:
            if self.tray_icon and getattr(self.tray_icon, "visible", False):
                self.tray_icon.notify("PulseFit DAH Agent đang chạy ngầm để tiếp tục đồng bộ máy DAH.", APP_NAME)
        except Exception:
            pass

    def show_from_tray(self) -> None:
        self.deiconify()
        self.state("normal")
        self.lift()
        self.focus_force()
        self.attributes("-topmost", True)
        self.attributes("-topmost", False)

    def confirm_exit(self) -> None:
        self.show_from_tray()
        confirm = messagebox.askyesno(
            APP_NAME,
            "CẢNH BÁO: Tắt ứng dụng sẽ ngắt toàn bộ tiến trình đồng bộ dữ liệu máy chấm công DAH về máy chủ PulseFit!\n\nBạn có chắc chắn muốn thoát hoàn toàn?",
            icon="warning"
        )
        if confirm:
            if self.worker:
                self.worker.stop()
            if self.tray_icon:
                try:
                    self.tray_icon.stop()
                except Exception:
                    pass
            self.destroy()
            sys.exit(0)

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)

        # Header Banner hiển thị quyền Admin & Trạng thái bảo vệ
        admin_status = "ĐÃ CẤP QUYỀN ADMINISTRATOR (CAO NHẤT)" if is_admin() else "QUYỀN STANDARD USER"
        admin_color = "#047857" if is_admin() else "#B45309"

        header_frame = tk.Frame(root, bg="#F3F4F6", relief="solid", bd=1, padx=8, pady=6)
        header_frame.pack(fill="x", pady=(0, 10))

        tk.Label(
            header_frame,
            text=f"🛡️ Trạng thái: {admin_status}",
            font=("Segoe UI", 9, "bold"),
            fg=admin_color,
            bg="#F3F4F6"
        ).pack(side="left")

        tk.Label(
            header_frame,
            text="🚀 Tự chạy ngầm (Chống tắt / System Tray)",
            font=("Segoe UI", 9),
            fg="#4B5563",
            bg="#F3F4F6"
        ).pack(side="right")

        form = ttk.LabelFrame(root, text="Cài đặt kết nối & Đồng bộ", padding=10)
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
        self._add_entry(form, "Scan start date", "scan_start_date", 11, width=12)

        self.vars["auto_start"] = tk.BooleanVar()
        ttk.Checkbutton(form, text="Tự động start worker khi mở app (Luôn bật)", variable=self.vars["auto_start"]).grid(row=12, column=1, sticky="w", pady=3)
        self.vars["browser_warmup"] = tk.BooleanVar()
        ttk.Checkbutton(form, text="Sử dụng browser ẩn đăng nhập DAH trước khi kéo API", variable=self.vars["browser_warmup"]).grid(row=13, column=1, sticky="w", pady=3)

        actions = ttk.Frame(root)
        actions.pack(fill="x", pady=10)
        ttk.Button(actions, text="Lưu cấu hình", command=self.save).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="Bắt đầu", command=self.start_worker).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="Tạm dừng", command=self.stop_worker).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="Đồng bộ ngay", command=self.sync_now).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="Ẩn xuống Tray", command=self.hide_to_tray).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="Cài Auto Startup", command=self.install_startup).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="Gỡ Auto Startup", command=self.remove_startup).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="Xem Log file", command=self.open_log).pack(side="left")

        self.status_var = tk.StringVar(value="Đang hoạt động")
        ttk.Label(root, textvariable=self.status_var, font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(0, 6))

        log_frame = ttk.LabelFrame(root, text="Nhật ký hoạt động (Log)", padding=8)
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
        setup_startup_task(True)
        self._append_log(f"Đã lưu cấu hình vào {CONFIG_PATH} & cập nhật Auto Startup.")

    def start_worker(self) -> None:
        self.save()
        if self.worker:
            self.worker.stop()
        self.worker = AgentWorker(self.config_data, self.log_queue)
        self.worker.start()
        self.status_var.set("Trạng thái: Đang chạy (Running)")

    def stop_worker(self) -> None:
        if self.worker:
            self.worker.stop()
        self.status_var.set("Trạng thái: Tạm dừng (Stopped)")

    def sync_now(self) -> None:
        if not self.worker:
            self.start_worker()
        if self.worker:
            self.worker.trigger_sync()
            self._append_log("Đã kích hoạt đồng bộ thủ công (Manual sync).")

    def open_log(self) -> None:
        try:
            os.startfile(LOG_PATH)
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))

    def install_startup(self) -> None:
        self.save()
        success = setup_startup_task(True)
        if success:
            messagebox.showinfo(APP_NAME, "Đã cài đặt tự khởi động cùng Windows (Task Scheduler).")
        else:
            messagebox.showwarning(APP_NAME, "Không thể cài đặt Task Scheduler. Hãy đảm bảo chạy với quyền Administrator.")

    def remove_startup(self) -> None:
        success = setup_startup_task(False)
        if success:
            messagebox.showinfo(APP_NAME, "Đã gỡ bỏ tự khởi động cùng Windows.")
        else:
            messagebox.showwarning(APP_NAME, "Không thể gỡ bỏ tác vụ khởi động.")

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
        try:
            num_lines = int(self.log_text.index("end-1c").split(".")[0])
            if num_lines > 1500:
                self.log_text.delete("1.0", "200.0")
        except Exception:
            pass
        self.log_text.see("end")


def main() -> None:
    ensure_admin()
    app = AgentApp()
    app.mainloop()


if __name__ == "__main__":
    main()
