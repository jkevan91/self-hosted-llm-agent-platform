# Foundation — the rules every MCP server here follows

Distilled from building six servers. Split into rules that are **mandatory for the protocol**,
rules that are **mandatory for safety**, and design guidance for the fact that the caller is a
language model.

---

## Protocol compatibility (violating these breaks loading)

1. No prompt decorators, and no prompt parameter to the server constructor
2. **No rich type hints** — no `Optional`, `Union`, `List[str]`
3. **Single-line docstrings only** — multi-line docstrings break the tool schema
4. Every parameter is `param: str = ""` — never `None`, never a complex type
5. **Every tool returns a string** — a formatted one, never a raw object
6. **Log to stderr.** stdout is the protocol transport; anything printed there corrupts it
7. **No exception may escape a tool.** Catch everything and return a readable error string

### Why everything is a string

Schema validation is strict in both directions: a tool declaring `int` and receiving `"7"`
fails, and a tool declaring `str` and receiving `7` also fails. Small local models are
inconsistent about which they emit. Declaring every parameter as a string and coercing
internally removes the whole class of failure for the cost of one helper:

```python
def _as_int(value, default, low, high):
    """Coerce a model-supplied value to a bounded int, tolerating junk."""
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        return default
    return max(low, min(high, n))
```

---

## Safety rules for anything touching the outside world

8. **Treat every argument as untrusted.** Validate addresses, hostnames and paths explicitly
9. **Build argument lists directly — never through a shell.** No `shell=True`, no string
   interpolation into a command line
10. **Bound every external command with a timeout** and cap output size before returning
11. **Never hardcode credentials, addresses or subnets.** Environment variables or mounted
    config only — the same image must run anywhere
12. **Redact secrets** from logs and from tool output
13. **Run non-root.** Opt into capabilities only where a tool genuinely needs them, and document
    which tool and why

```python
def is_valid_target(value):
    """Reject anything that isn't a plain address or hostname."""
    if not value or any(c in value for c in ';|&$`><\n'):
        return False
    try:
        ipaddress.ip_network(value, strict=False)
        return True
    except ValueError:
        return bool(re.fullmatch(r'[A-Za-z0-9._-]+', value))
```

---

## The two-phase gate — for state-changing servers only

```
plan_*   read-only. Computes target, diff, stated reason, and a one-time
         confirm token. Touches nothing.
apply_*  refuses without a matching, recent token. Commits before-state,
         applies, commits after-state.
```

Plus `list_*_history` and `rollback_*`, backed by a git repository on a mounted volume.

**Apply this only where a tool mutates persistent state.** A read-only or ephemeral-control
server must not carry the ceremony — friction on a "press pause" tool teaches people to click
through confirmations, which is worse than having none.

Ship `apply_*` and `rollback_*` in the agent's exclusion list until drilled by hand.

---

## Design for a language model caller

**Resolve human names to identifiers inside the tool.** The model passes what the person said —
`"Netflix"`, `"the living room TV"` — not a bundle identifier or a UUID. Fetch the real list,
match exact-ID → exact-name → substring (case-insensitive), and act on the resolved value.

**Return disambiguation errors that list the real options.** An error naming the valid choices
lets the model self-correct in one turn. An error saying "invalid identifier" produces another
guess.

**This matters most where the API no-ops on bad input.** Several do: they accept any string,
acknowledge it, and silently do nothing — so the tool reports success while nothing happened.

**Don't trust a non-raising call as proof of success.** Where the effect can be measured
cheaply, measure it and word the result honestly. Where it can't, resolve inputs correctly up
front rather than reporting a success you didn't verify.

**Use consistent output markers** — ✅ ❌ ⚠️ 📝 — so both the model and a human scanning the
transcript can tell a refusal from a failure at a glance.

---

## Testing over stdio

An MCP stdio server needs a real handshake: `initialize` → `notifications/initialized` → your
request.

**The trap:** `printf ... | docker run -i` closes stdin the moment printf finishes. The
transport reads that EOF as a client disconnect and starts shutting down — so any tool doing
async work (a scan, an SSH call, an HTTP fetch) has its response **dropped**. It looks exactly
like a broken tool.

Listing tools is fast enough to survive it. Anything else needs stdin held open:

```bash
{ printf '%s\n' \
   '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"t","version":"1"}}}' \
   '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
   '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"<tool>","arguments":{}}}'
  sleep 35
} | docker run -i --rm <args> <image> 2>/dev/null
```

If a call returns nothing, suspect the EOF race before suspecting the server.

---

## Checklist

- [ ] No rich type hints; all docstrings single-line; all params default to `""`
- [ ] Every tool returns a string; no exception can escape
- [ ] Logging to stderr only
- [ ] Inputs validated; no shell; timeouts and output caps everywhere
- [ ] Secrets never hardcoded, never logged
- [ ] Non-root image; capabilities documented
- [ ] State-changing tools gated and shipped disabled
- [ ] Name→ID resolution wherever the underlying API wants an identifier
- [ ] Smoke-tested over stdio with stdin held open
