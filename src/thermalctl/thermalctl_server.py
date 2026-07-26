#!/usr/bin/env python3
"""thermalctl MCP Server - fan and RGB control for hosts on the LAN over restricted SSH."""

import os
import sys
import time
import json
import hashlib
import logging

import yaml
import paramiko

from mcp.server.fastmcp import FastMCP

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr,
)
logger = logging.getLogger("thermalctl-server")

mcp = FastMCP("thermalctl")

# === CONFIG (env only; nothing host-specific hardcoded) ===
HOSTS_FILE = os.environ.get("THERMALCTL_HOSTS_FILE", "/secrets/hosts.yaml")
KNOWN_HOSTS = os.environ.get("THERMALCTL_KNOWN_HOSTS", "/secrets/known_hosts")
DATA_DIR = os.environ.get("THERMALCTL_DATA_DIR", "/data")
CMD_TIMEOUT = int(os.environ.get("THERMALCTL_CMD_TIMEOUT", "90"))
MAX_OUTPUT = int(os.environ.get("THERMALCTL_MAX_OUTPUT", "20000"))
PLAN_TTL = int(os.environ.get("THERMALCTL_PLAN_TTL", "1800"))

_PENDING_PLANS = {}


# === UTILITIES ===
def _cap(text):
    if len(text) > MAX_OUTPUT:
        return text[:MAX_OUTPUT] + "\n...(truncated)"
    return text


def _load_hosts():
    with open(HOSTS_FILE) as fh:
        blob = yaml.safe_load(fh) or {}
    hosts = blob.get("hosts") or {}
    if not isinstance(hosts, dict):
        raise ValueError("hosts.yaml: 'hosts' must be a mapping")
    return hosts


def _resolve_host(name):
    """Resolve a caller-supplied host name to an inventory entry, tolerantly."""
    hosts = _load_hosts()
    if not hosts:
        raise ValueError("no hosts defined in hosts.yaml")
    key = (name or "").strip()
    if not key:
        if len(hosts) == 1:
            only = list(hosts)[0]
            return only, hosts[only]
        raise ValueError("host is required; known hosts: " + ", ".join(sorted(hosts)))
    # The caller is a language model: accept the alias, the hostname, or the IP,
    # case-insensitively, before giving up.
    for h in hosts:
        if h.lower() == key.lower():
            return h, hosts[h]
    for h, cfg in hosts.items():
        if str(cfg.get("host", "")).lower() == key.lower():
            return h, cfg
    matches = [h for h in hosts if key.lower() in h.lower()]
    if len(matches) == 1:
        return matches[0], hosts[matches[0]]
    if len(matches) > 1:
        raise ValueError("ambiguous host '%s' - matches: %s" % (key, ", ".join(sorted(matches))))
    raise ValueError("unknown host '%s'; known hosts: %s" % (key, ", ".join(sorted(hosts))))


def _agent(name, command):
    """Run one allowlisted verb via the host's forced-command SSH key."""
    alias, cfg = _resolve_host(name)
    client = paramiko.SSHClient()
    try:
        if os.path.exists(KNOWN_HOSTS):
            client.load_host_keys(KNOWN_HOSTS)
        # RejectPolicy, never AutoAdd: an unknown host key means something moved
        # or someone is in the middle, and silently trusting it defeats the point.
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        client.connect(
            cfg["host"],
            username=cfg.get("user", "root"),
            key_filename=cfg.get("key_file", "/secrets/id_ed25519"),
            timeout=min(CMD_TIMEOUT, 20),
            banner_timeout=20,
            auth_timeout=20,
            look_for_keys=False,
            allow_agent=False,
        )
        # The remote key is pinned to thermalctl-agent, so this string arrives as
        # SSH_ORIGINAL_COMMAND and is parsed against a verb allowlist - it is
        # never executed as a shell command on the far side.
        _, stdout, stderr = client.exec_command(command, timeout=CMD_TIMEOUT)
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        rc = stdout.channel.recv_exit_status()
        return alias, rc, out, err
    finally:
        try:
            client.close()
        except Exception:
            pass


def _run(name, command):
    """_agent() wrapped so every failure becomes a friendly string, never a raise."""
    try:
        alias, rc, out, err = _agent(name, command)
    except paramiko.ssh_exception.SSHException as e:
        return None, "SSH error: %s" % e
    except FileNotFoundError as e:
        return None, "missing file: %s" % e
    except Exception as e:
        return None, "%s" % e
    body = out.strip()
    if err.strip():
        body += ("\n[stderr] " + err.strip()) if body else ("[stderr] " + err.strip())
    if rc != 0 and not body:
        body = "agent exited %d with no output" % rc
    return alias, body


def _history_path():
    os.makedirs(DATA_DIR, exist_ok=True)
    return os.path.join(DATA_DIR, "curve_history.json")


def _append_history(entry):
    path = _history_path()
    try:
        blob = json.load(open(path)) if os.path.exists(path) else []
    except Exception:
        blob = []
    blob.append(entry)
    with open(path, "w") as fh:
        json.dump(blob[-200:], fh, indent=2)


# === MCP TOOLS: inventory and read ===
@mcp.tool()
async def list_hosts() -> str:
    """List every host thermalctl can reach, with its description and reported capabilities."""
    try:
        hosts = _load_hosts()
    except Exception as e:
        logger.error("list_hosts: %s", e)
        return "❌ Error: %s" % e
    if not hosts:
        return "❌ Error: no hosts configured in hosts.yaml"
    lines = ["🌐 %d host(s)" % len(hosts), ""]
    for alias in sorted(hosts):
        cfg = hosts[alias]
        lines.append("  %s — %s (%s@%s)" % (
            alias, cfg.get("description", "no description"),
            cfg.get("user", "root"), cfg.get("host", "?")))
        _, body = _run(alias, "caps")
        lines.append("      caps: %s" % (body or "unreachable").splitlines()[0])
    return _cap("\n".join(lines))


@mcp.tool()
async def get_thermal_status(host: str = "") -> str:
    """Show temperatures, fan speeds, GPU state, RGB devices and service state for a host."""
    alias, body = _run(host, "status")
    if alias is None:
        logger.error("get_thermal_status: %s", body)
        return "❌ Error: %s" % body
    return _cap("🌡️ %s\n\n%s" % (alias, body))


@mcp.tool()
async def get_fan_curve(host: str = "") -> str:
    """Show the automatic fan curve currently in effect on a host."""
    alias, body = _run(host, "curve get")
    if alias is None:
        return "❌ Error: %s" % body
    return _cap("📈 %s fan curve\n\n%s" % (alias, body))


# === MCP TOOLS: ephemeral control (floor-clamped, auto-reverting) ===
@mcp.tool()
async def set_fan_speed(host: str = "", percent: str = "", minutes: str = "") -> str:
    """Temporarily set case fans to a percent for N minutes, then automatic control resumes."""
    if not str(percent).strip():
        return "❌ Error: percent is required (the host clamps anything below its floor)"
    ttl = str(minutes).strip() or "15"
    alias, body = _run(host, "fan set %s %s" % (str(percent).strip(), ttl))
    if alias is None:
        return "❌ Error: %s" % body
    if body.startswith("ERR"):
        return "❌ %s refused: %s" % (alias, body[3:].strip())
    return "🌀 %s: %s" % (alias, body[2:].strip() if body.startswith("OK") else body)


@mcp.tool()
async def resume_fan_auto(host: str = "") -> str:
    """Cancel any manual fan override immediately and hand control back to the fan curve."""
    alias, body = _run(host, "fan auto")
    if alias is None:
        return "❌ Error: %s" % body
    if body.startswith("ERR"):
        return "❌ %s refused: %s" % (alias, body[3:].strip())
    return "✅ %s: %s" % (alias, body[2:].strip() if body.startswith("OK") else body)


@mcp.tool()
async def set_rgb(host: str = "", color: str = "", minutes: str = "") -> str:
    """Temporarily set RGB lighting to a hex colour or 'off' for N minutes, then policy resumes."""
    want = (color or "").strip().lstrip("#")
    if not want:
        return "❌ Error: color is required — 6 hex digits (e.g. 00aaff) or 'off'"
    ttl = str(minutes).strip() or "60"
    alias, body = _run(host, "rgb set %s %s" % (want, ttl))
    if alias is None:
        return "❌ Error: %s" % body
    if body.startswith("ERR"):
        return "❌ %s refused: %s" % (alias, body[3:].strip())
    return "💡 %s: %s" % (alias, body[2:].strip() if body.startswith("OK") else body)


@mcp.tool()
async def resume_rgb_auto(host: str = "") -> str:
    """Cancel any manual RGB override immediately and hand control back to the automatic policy."""
    alias, body = _run(host, "rgb auto")
    if alias is None:
        return "❌ Error: %s" % body
    if body.startswith("ERR"):
        return "❌ %s refused: %s" % (alias, body[3:].strip())
    return "✅ %s: %s" % (alias, body[2:].strip() if body.startswith("OK") else body)


# === MCP TOOLS: persistent change (two-phase plan -> apply) ===
@mcp.tool()
async def plan_fan_curve(host: str = "", curve: str = "", reason: str = "") -> str:
    """Preview a permanent fan-curve change and get a confirm token; changes nothing."""
    want = (curve or "").strip()
    if not want:
        return "❌ Error: curve is required, e.g. '45:35 52:45 58:65 63:85 66:100'"
    if not (reason or "").strip():
        return "❌ Error: reason is required — say why this curve should change"
    alias, current = _run(host, "curve get")
    if alias is None:
        return "❌ Error: %s" % current
    token = hashlib.sha256(("%s|%s|%s" % (alias, want, time.time())).encode()).hexdigest()[:16]
    _PENDING_PLANS[token] = {
        "host": alias, "curve": want, "reason": reason.strip(), "created": time.time(),
        "previous": current,
    }
    return _cap(
        "📝 Planned fan-curve change on %s\n\n"
        "Current:\n%s\n\n"
        "Proposed:\n  CURVE=%s\n\n"
        "Reason: %s\n\n"
        "⚠️ Nothing has changed yet. To apply, call apply_fan_curve with:\n"
        "  confirm_token=%s\n"
        "(token expires in %d minutes)"
        % (alias, current, want, reason.strip(), token, PLAN_TTL // 60))


@mcp.tool()
async def apply_fan_curve(confirm_token: str = "") -> str:
    """Apply a fan-curve change previously previewed by plan_fan_curve; requires its token."""
    token = (confirm_token or "").strip()
    if not token:
        return "❌ Error: confirm_token is required — run plan_fan_curve first"
    plan = _PENDING_PLANS.pop(token, None)
    if plan is None:
        return "❌ Error: unknown or already-used token — run plan_fan_curve again"
    if time.time() - plan["created"] > PLAN_TTL:
        return "❌ Error: token expired — run plan_fan_curve again"
    alias, body = _run(plan["host"], "curve set %s" % plan["curve"])
    if alias is None:
        return "❌ Error: %s" % body
    if body.startswith("ERR"):
        return "❌ %s refused: %s" % (alias, body[3:].strip())
    _append_history({
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "host": alias,
        "curve": plan["curve"], "reason": plan["reason"], "previous": plan["previous"],
    })
    return "✅ %s: %s\n🕓 recorded in curve history (use list_curve_history to review)" % (
        alias, body[2:].strip() if body.startswith("OK") else body)


@mcp.tool()
async def list_curve_history(host: str = "") -> str:
    """Show past fan-curve changes made through thermalctl, newest last."""
    path = _history_path()
    if not os.path.exists(path):
        return "🕓 No fan-curve changes recorded yet."
    try:
        blob = json.load(open(path))
    except Exception as e:
        return "❌ Error: could not read history: %s" % e
    want = (host or "").strip().lower()
    rows = [r for r in blob if not want or r.get("host", "").lower() == want]
    if not rows:
        return "🕓 No fan-curve changes recorded for '%s'." % host
    lines = ["🕓 %d change(s)" % len(rows), ""]
    for r in rows:
        lines.append("  %s | %s | CURVE=%s" % (r.get("ts"), r.get("host"), r.get("curve")))
        lines.append("      reason: %s" % r.get("reason", ""))
    return _cap("\n".join(lines))


# === SERVER STARTUP ===
if __name__ == "__main__":
    logger.info("Starting thermalctl MCP server (hosts=%s data=%s)...", HOSTS_FILE, DATA_DIR)
    try:
        mcp.run(transport='stdio')
    except Exception as e:
        logger.error("Server error: %s", e, exc_info=True)
        sys.exit(1)
