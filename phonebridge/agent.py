#!/data/data/com.termux/files/usr/bin/python
from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

OWNER = "keepinitkrispy"
REPO = "antiLLM"
STATE_ISSUE = 1
COMMAND_ISSUE = 2
BASE = Path.home() / ".phonebridge"
STATE_FILE = BASE / "agent_state.json"
LOG_FILE = BASE / "agent.log"
POLL_SECONDS = 20
HEARTBEAT_SECONDS = 300
MAX_CAPTURE = 60000
ALLOWED_OPS = {"snapshot", "battery", "calls", "notifications", "sms", "location", "device", "apps"}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def log(msg: str) -> None:
    BASE.mkdir(parents=True, exist_ok=True)
    line = f"{now_iso()} {msg}"
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    try:
        print(line, flush=True)
    except Exception:
        pass


def run(argv: list[str], timeout: int = 12) -> dict:
    try:
        cp = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
        return {
            "ok": cp.returncode == 0,
            "code": cp.returncode,
            "stdout": cp.stdout[:MAX_CAPTURE].strip(),
            "stderr": cp.stderr[:8000].strip(),
        }
    except subprocess.TimeoutExpired as e:
        return {"ok": False, "code": 124, "stdout": (e.stdout or "")[:MAX_CAPTURE], "stderr": "timeout"}
    except FileNotFoundError:
        return {"ok": False, "code": 127, "stdout": "", "stderr": f"not installed: {argv[0]}"}
    except Exception as e:
        return {"ok": False, "code": 1, "stdout": "", "stderr": repr(e)}


def parse_json_result(result: dict):
    if not result.get("ok"):
        return result
    text = result.get("stdout", "")
    try:
        return json.loads(text) if text else None
    except Exception:
        return result


def load_local_state() -> dict:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"last_comment_id": 0, "last_heartbeat": 0}


def save_local_state(st: dict) -> None:
    BASE.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=2), encoding="utf-8")
    tmp.replace(STATE_FILE)
    os.chmod(STATE_FILE, 0o600)


def gh_api(path: str, method: str = "GET", payload=None):
    cmd = ["gh", "api", path, "-X", method]
    stdin = None
    if payload is not None:
        cmd += ["--input", "-"]
        stdin = json.dumps(payload)
    try:
        cp = subprocess.run(cmd, input=stdin, capture_output=True, text=True, timeout=20, check=False)
    except Exception as e:
        return {"ok": False, "error": repr(e)}
    if cp.returncode != 0:
        return {"ok": False, "error": cp.stderr.strip() or cp.stdout.strip(), "code": cp.returncode}
    try:
        return {"ok": True, "data": json.loads(cp.stdout) if cp.stdout.strip() else None}
    except json.JSONDecodeError:
        return {"ok": True, "data": cp.stdout.strip()}


def capabilities() -> dict:
    checks = {}
    commands = {
        "battery": ["termux-battery-status"],
        "calls": ["termux-call-log", "-l", "1"],
        "notifications": ["termux-notification-list"],
        "sms": ["termux-sms-list", "-l", "1", "-t", "all"],
        "location": ["termux-location", "-p", "network", "-r", "last"],
        "device": ["termux-telephony-deviceinfo"],
    }
    for name, argv in commands.items():
        r = run(argv, timeout=8)
        checks[name] = {
            "ok": bool(r.get("ok")),
            "error": None if r.get("ok") else (r.get("stderr") or r.get("stdout") or f"exit {r.get('code')}")[:500],
        }
    r = run(["pm", "list", "packages", "-3"], timeout=8)
    checks["apps"] = {"ok": bool(r.get("ok")), "error": None if r.get("ok") else (r.get("stderr") or r.get("stdout"))[:500]}
    rr = run(["rish", "-c", "id"], timeout=5)
    checks["shizuku"] = {"ok": bool(rr.get("ok")), "error": None if rr.get("ok") else (rr.get("stderr") or rr.get("stdout"))[:500]}
    return checks


def collect(op: str, args: dict | None = None):
    args = args or {}
    if op == "battery":
        return parse_json_result(run(["termux-battery-status"], 8))
    if op == "calls":
        limit = max(1, min(int(args.get("limit", 50)), 200))
        return parse_json_result(run(["termux-call-log", "-l", str(limit)], 12))
    if op == "notifications":
        return parse_json_result(run(["termux-notification-list"], 12))
    if op == "sms":
        limit = max(1, min(int(args.get("limit", 30)), 100))
        return parse_json_result(run(["termux-sms-list", "-l", str(limit), "-t", "all"], 15))
    if op == "location":
        provider = args.get("provider", "network")
        if provider not in {"network", "gps", "passive"}:
            provider = "network"
        return parse_json_result(run(["termux-location", "-p", provider, "-r", "once"], 25))
    if op == "device":
        return parse_json_result(run(["termux-telephony-deviceinfo"], 10))
    if op == "apps":
        r = run(["pm", "list", "packages", "-3"], 10)
        if r.get("ok"):
            return sorted(x.split(":", 1)[-1] for x in r.get("stdout", "").splitlines() if x.strip())
        return r
    if op == "snapshot":
        return {"battery": collect("battery"), "device": collect("device"), "capabilities": capabilities()}
    return {"ok": False, "error": "unsupported operation"}


def publish_state(kind: str, request_id: str | None, op: str, data) -> bool:
    body_obj = {
        "phone_bridge": 1,
        "updated_at": now_iso(),
        "kind": kind,
        "request_id": request_id,
        "operation": op,
        "data": data,
    }
    body = "Private Android Phone Bridge — current state/result only.\n\n```json\n" + json.dumps(body_obj, indent=2, ensure_ascii=False)[:62000] + "\n```"
    res = gh_api(f"repos/{OWNER}/{REPO}/issues/{STATE_ISSUE}", "PATCH", {"body": body})
    if not res.get("ok"):
        log(f"publish failed: {res}")
        return False
    return True


def fetch_commands(last_id: int) -> list[dict]:
    res = gh_api(f"repos/{OWNER}/{REPO}/issues/{COMMAND_ISSUE}/comments?per_page=100")
    if not res.get("ok") or not isinstance(res.get("data"), list):
        return []
    out = []
    for c in res["data"]:
        cid = int(c.get("id") or 0)
        if cid <= last_id:
            continue
        user = ((c.get("user") or {}).get("login") or "").lower()
        if user != OWNER.lower():
            continue
        body = (c.get("body") or "").strip()
        if not body.startswith("PB_CMD "):
            continue
        try:
            cmd = json.loads(body[len("PB_CMD "):])
        except Exception:
            continue
        if not isinstance(cmd, dict):
            continue
        op = cmd.get("op")
        if op not in ALLOWED_OPS:
            continue
        cmd["_comment_id"] = cid
        out.append(cmd)
    out.sort(key=lambda x: x["_comment_id"])
    return out


def main() -> int:
    BASE.mkdir(parents=True, exist_ok=True)
    st = load_local_state()
    auth = run(["gh", "auth", "status"], 10)
    if not auth.get("ok"):
        log("GitHub auth missing; run bridge-setup again")
        return 2
    caps = capabilities()
    publish_state("heartbeat", None, "startup", {"status": "online", "capabilities": caps})
    log("agent online")
    while True:
        try:
            commands = fetch_commands(int(st.get("last_comment_id", 0)))
            for cmd in commands:
                cid = int(cmd["_comment_id"])
                req_id = str(cmd.get("id") or cid)
                op = str(cmd["op"])
                args = cmd.get("args") if isinstance(cmd.get("args"), dict) else {}
                log(f"processing {op} request {req_id}")
                data = collect(op, args)
                publish_state("result", req_id, op, data)
                st["last_comment_id"] = cid
                save_local_state(st)
            now = time.time()
            if now - float(st.get("last_heartbeat", 0)) >= HEARTBEAT_SECONDS:
                publish_state("heartbeat", None, "status", {"status": "online", "capabilities": capabilities()})
                st["last_heartbeat"] = now
                save_local_state(st)
        except Exception as e:
            log(f"loop error: {e!r}")
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    raise SystemExit(main())
