#!/usr/bin/env python3
from __future__ import annotations

import fcntl
import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

from flask import Flask, jsonify, redirect, render_template, request, url_for


BASE_DIR = Path(__file__).resolve().parent.parent
LOG_DIR = BASE_DIR / "webadmin_logs"
LOCK_FILE = BASE_DIR / ".wg_routes_admin.lock"

EDITABLE_FILES: Dict[str, Path] = {
    "ruantiblock": BASE_DIR / "Ruantiblock.input",
    "bypass": BASE_DIR / "wg_bypass_routes.txt",
}

SCRIPT_CONFIG = {
    "update": {
        "script": BASE_DIR / "update_wg_routes.sh",
        "modes": ["all", "update", "apply"],
        "default_mode": "all",
    },
    "install": {
        "script": BASE_DIR / "install_awg.sh",
        "modes": ["default"],
        "default_mode": "default",
    },
}


def empty_stats() -> Dict[str, int]:
    return {
        "wg_ipv4_total": 0,
        "wg_ipv6_total": 0,
        "dns_failed": 0,
        "bypass_ipv4_total": 0,
    }


def count_bypass_entries() -> int:
    path = EDITABLE_FILES["bypass"]
    if not path.exists():
        return 0

    total = 0
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        total += 1
    return total


@dataclass
class JobState:
    status: str = "idle"
    script: str = "none"
    mode: str = "none"
    stage: str = "none"
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    exit_code: Optional[int] = 0
    message: str = "Готов к запуску"
    log_path: str = "нет"
    stats: Dict[str, Optional[int]] = field(default_factory=empty_stats)

    def to_dict(self) -> Dict[str, object]:
        duration_sec = 0.0
        if self.started_at is not None:
            end = self.finished_at if self.finished_at is not None else time.time()
            duration_sec = round(end - self.started_at, 2)

        merged_stats = empty_stats()
        merged_stats.update(self.stats)
        # Bypass count should reflect current config file, not only last apply log.
        merged_stats["bypass_ipv4_total"] = count_bypass_entries()

        return {
            "status": self.status,
            "script": self.script,
            "mode": self.mode,
            "stage": self.stage,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_sec": duration_sec,
            "exit_code": self.exit_code,
            "message": self.message,
            "log_path": self.log_path,
            "stats": merged_stats,
        }


app = Flask(__name__)
state_lock = threading.Lock()
state = JobState()
lock_fd: Optional[int] = None


def read_text_file(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def parse_log_stats(log_path: Path) -> Dict[str, Optional[int]]:
    stats: Dict[str, Optional[int]] = empty_stats()

    if not log_path.exists():
        return stats

    rx_ipv4_total = re.compile(r"IPv4/подсетей (?:сгенерировано в WG‑файл|в WG‑файле):\s*(\d+)")
    rx_ipv6_total = re.compile(r"IPv6/подсетей в WG‑файле:\s*(\d+)")
    rx_dns_failed = re.compile(r"Ошибки/пустые резолвы DNS:\s*(\d+)")
    rx_bypass_total = re.compile(r"bypass IPv4-подсетей:\s*(\d+)")

    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = rx_ipv4_total.search(line)
        if m:
            stats["wg_ipv4_total"] = int(m.group(1))
            continue

        m = rx_ipv6_total.search(line)
        if m:
            stats["wg_ipv6_total"] = int(m.group(1))
            continue

        m = rx_dns_failed.search(line)
        if m:
            stats["dns_failed"] = int(m.group(1))
            continue

        m = rx_bypass_total.search(line)
        if m:
            stats["bypass_ipv4_total"] = int(m.group(1))

    return stats


def build_command(script_key: str, mode: str) -> list[str]:
    cfg = SCRIPT_CONFIG[script_key]
    script = str(cfg["script"])
    if script_key == "update":
        return ["/bin/bash", script, mode]
    return ["/bin/bash", script]


def initial_stage(script_key: str, mode: str) -> str:
    if script_key == "update":
        if mode == "apply":
            return "apply"
        return "update"
    if script_key == "install":
        return "install"
    return "none"


def detect_stage_from_line(script_key: str, line: str) -> Optional[str]:
    if script_key != "update":
        return None

    if "=== 1. Обновление списков" in line or "=== 1. ПРОПУСК обновления списков" in line:
        return "update"
    if "=== 2. Применение маршрутов" in line or "=== 2. ПРОПУСК применения маршрутов" in line:
        return "apply"
    return None


def start_job(script_key: str, mode: str) -> tuple[bool, str]:
    global lock_fd

    cfg = SCRIPT_CONFIG.get(script_key)
    if cfg is None:
        return False, "Неизвестный сценарий"

    if mode not in cfg["modes"]:
        return False, "Неподдерживаемый режим"

    fd = os.open(LOCK_FILE, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return False, "Уже есть активный запуск"

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    job_ts = time.strftime("%Y%m%d-%H%M%S")
    log_path = LOG_DIR / f"job-{script_key}-{mode}-{job_ts}.log"
    command = build_command(script_key, mode)

    with state_lock:
        state.status = "running"
        state.script = script_key
        state.mode = mode
        state.stage = initial_stage(script_key, mode)
        state.started_at = time.time()
        state.finished_at = None
        state.exit_code = None
        state.message = "Выполняется"
        state.log_path = str(log_path.relative_to(BASE_DIR))
        state.stats = empty_stats()

    lock_fd = fd
    worker = threading.Thread(
        target=run_job_worker,
        args=(command, script_key, mode, log_path, fd),
        daemon=True,
    )
    worker.start()
    return True, "Запуск принят"


def run_job_worker(command: list[str], script_key: str, mode: str, log_path: Path, fd: int) -> None:
    global lock_fd

    exit_code = 1
    error_message = ""
    try:
        with log_path.open("w", encoding="utf-8") as log_file:
            log_file.write(f"# command: {' '.join(command)}\n")
            log_file.write(f"# cwd: {BASE_DIR}\n")
            log_file.flush()

            process = subprocess.Popen(
                command,
                cwd=BASE_DIR,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            if process.stdout is not None:
                for line in process.stdout:
                    log_file.write(line)
                    stage = detect_stage_from_line(script_key, line)
                    if stage:
                        with state_lock:
                            state.stage = stage
            exit_code = process.wait()
    except Exception as exc:
        error_message = str(exc)
        try:
            with log_path.open("a", encoding="utf-8") as log_file:
                log_file.write(f"\n[webadmin] exception: {exc}\n")
        except OSError:
            pass
    finally:
        stats = parse_log_stats(log_path)
        with state_lock:
            state.script = script_key
            state.mode = mode
            state.finished_at = time.time()
            state.exit_code = exit_code
            state.stats = stats
            if exit_code == 0 and not error_message:
                state.status = "ok"
                state.stage = "done"
                state.message = "Завершено успешно"
            else:
                state.status = "fail"
                state.message = error_message or "Завершено с ошибкой"

        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)
            lock_fd = None


@app.get("/")
def index():
    with state_lock:
        current = state.to_dict()

    return render_template(
        "index.html",
        ruantiblock_content=read_text_file(EDITABLE_FILES["ruantiblock"]),
        bypass_content=read_text_file(EDITABLE_FILES["bypass"]),
        script_config=SCRIPT_CONFIG,
        state=current,
    )


@app.post("/save/<file_key>")
def save_file(file_key: str):
    target = EDITABLE_FILES.get(file_key)
    if target is None:
        return jsonify({"ok": False, "message": "Неизвестный файл"}), 404

    content = request.form.get("content", "")
    target.write_text(content, encoding="utf-8")
    return redirect(url_for("index"))


@app.post("/run/<script_key>")
def run_script(script_key: str):
    cfg = SCRIPT_CONFIG.get(script_key)
    if cfg is None:
        return jsonify({"ok": False, "message": "Неизвестный сценарий"}), 404

    mode = request.form.get("mode", cfg["default_mode"])
    ok, message = start_job(script_key, mode)
    code = 200 if ok else 409
    return jsonify({"ok": ok, "message": message}), code


@app.get("/job/status")
def job_status():
    with state_lock:
        current = state.to_dict()
    return jsonify(current)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8081, debug=False)