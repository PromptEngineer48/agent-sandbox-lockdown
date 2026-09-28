"""A small tool-using agent with four guardrails:

1. Least privilege  - read tools run freely, write tools need a human "y".
2. Egress control   - all web traffic goes through an allowlist proxy + DNS.
3. Audit log        - every tool call is appended to /logs/tool_calls.jsonl.
4. Kill switch      - touch control/KILL (or hit MAX_STEPS) and the loop stops.
"""
import json
import os
import re
import socket
import sys
import time
import urllib.request
from pathlib import Path

OLLAMA = os.environ.get("OLLAMA_URL", "http://ollama:11434")
MODEL = os.environ.get("MODEL", "qwen3:4b")
MAX_STEPS = int(os.environ.get("MAX_STEPS", "12"))
WORKSPACE = Path("/workspace")
OUTBOX = Path("/outbox")
KILL = Path("/control/KILL")
LOG = Path("/logs/tool_calls.jsonl")

C = {"dim": "\033[2m", "red": "\033[91m", "grn": "\033[92m", "yel": "\033[93m",
     "cyn": "\033[96m", "off": "\033[0m"}


def say(color, tag, msg):
    print(f"{C[color]}[{tag}]{C['off']} {msg}", flush=True)


# ---------------------------------------------------------------- tools
def _safe(base: Path, rel: str) -> Path:
    p = (base / rel).resolve()
    if base.resolve() not in p.parents and p != base.resolve():
        raise PermissionError(f"path escapes {base}")
    return p


def list_files(path="."):
    return "\n".join(sorted(x.name for x in _safe(WORKSPACE, path).iterdir()))


def read_file(path):
    return _safe(WORKSPACE, path).read_text(errors="replace")[:4000]


def http_get(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return r.read(2000).decode(errors="replace")


def dns_lookup(hostname):
    return socket.gethostbyname(hostname)


def write_file(path, content):
    p = _safe(OUTBOX, path)
    p.write_text(content)
    return f"wrote {len(content)} bytes to outbox/{path}"


TOOLS = {
    # name: (fn, needs_approval, description, params)
    "list_files": (list_files, False, "List files in the workspace", {"path": "string"}),
    "read_file": (read_file, False, "Read a text file from the workspace", {"path": "string"}),
    "http_get": (http_get, False, "Fetch a URL", {"url": "string"}),
    "dns_lookup": (dns_lookup, False, "Resolve a hostname to an IP", {"hostname": "string"}),
    "write_file": (write_file, True, "Write a file to the outbox", {"path": "string", "content": "string"}),
}

SCHEMA = [{
    "type": "function",
    "function": {
        "name": n, "description": d,
        "parameters": {"type": "object",
                       "properties": {k: {"type": t} for k, t in ps.items()},
                       "required": list(ps)},
    }} for n, (_, _, d, ps) in TOOLS.items()]


def log(entry):
    entry["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    with LOG.open("a") as f:
        f.write(json.dumps(entry) + "\n")


def run_tool(name, args):
    if name not in TOOLS:
        return "error: unknown tool", "denied"
    fn, needs_ok, _, _ = TOOLS[name]
    if needs_ok:
        say("yel", "APPROVAL", f"{name}({json.dumps(args)[:160]})  allow? [y/N] ")
        try:
            answer = input().strip().lower()
        except EOFError:
            answer = ""
        if answer != "y":
            return "error: human denied this action", "denied"
    try:
        return str(fn(**args)), "ok"
    except Exception as e:  # blocked egress shows up here
        return f"error: {type(e).__name__}: {e}", "error"


# ---------------------------------------------------------------- loop
def chat(messages):
    body = json.dumps({"model": MODEL, "messages": messages, "tools": SCHEMA,
                       "stream": False, "think": False}).encode()
    req = urllib.request.Request(f"{OLLAMA}/api/chat", body,
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())["message"]


def main(task):
    say("cyn", "TASK", task)
    messages = [
        {"role": "system", "content": "You are a helpful assistant with tools. "
         "Use tools to complete the task, then give a short final answer."},
        {"role": "user", "content": task},
    ]
    for step in range(1, MAX_STEPS + 1):
        if KILL.exists():
            say("red", "KILL", "kill switch is set - stopping now")
            log({"event": "killed", "step": step})
            return
        msg = chat(messages)
        messages.append(msg)
        calls = msg.get("tool_calls") or []
        if not calls:
            text = re.sub(r"(?s)^.*</think>", "", msg.get("content", "")).strip()
            say("grn", "DONE", text)
            return
        for c in calls:
            name = c["function"]["name"]
            args = c["function"].get("arguments") or {}
            if isinstance(args.get("arguments"), dict):  # small models nest args
                args = args["arguments"]
            say("dim", f"step {step}", f"{name}({json.dumps(args)[:160]})")
            out, status = run_tool(name, args)
            color = {"ok": "grn", "error": "red", "denied": "yel"}[status]
            say(color, status.upper(), out[:200].replace("\n", " | "))
            log({"step": step, "tool": name, "args": args, "status": status,
                 "result": out[:300]})
            messages.append({"role": "tool", "content": out, "tool_name": name})
    say("red", "LIMIT", f"hit MAX_STEPS={MAX_STEPS} - stopping")
    log({"event": "max_steps"})


if __name__ == "__main__":
    main(" ".join(sys.argv[1:]) or "Summarise the files in the workspace.")
