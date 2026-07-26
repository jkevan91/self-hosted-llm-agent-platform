# Architecture

## Layers

```
┌──────────────────────────────────────────────────────────────┐
│ Surface        chat client on a phone                        │
│                allowlisted user IDs, deny by default         │
├──────────────────────────────────────────────────────────────┤
│ Agent          agent runtime — tool orchestration, context   │
│                management, session state                     │
├──────────────────────────────────────────────────────────────┤
│ Inference      local OpenAI-compatible model server          │
│                24 GB GPU · 14B-class tool-calling model      │
│                64k context                                   │
├──────────────────────────────────────────────────────────────┤
│ Capability     six MCP servers, JSON-RPC over stdio or       │
│                loopback HTTP · one container each, non-root  │
├──────────────────────────────────────────────────────────────┤
│ Target         LAN hosts · AV devices · SaaS APIs ·          │
│                hypervisor + media server hardware            │
└──────────────────────────────────────────────────────────────┘
```

## Physical and virtual layout

| Node | Role |
| --- | --- |
| `hypervisor` | Bare metal. Proxmox host. Owns the fan and lighting hardware. |
| `gaming-vm` | Windows guest. Holds the GPU on demand. |
| `llm-vm` | Linux guest. Model server, agent runtime, all MCP servers. |
| `mediaserver` | Separate box. Media services; monitored read-only by the agent. |

Addresses in this repository are placeholders in `10.0.0.0/24`.

## Why the agent lives in a guest, not on the host

It would be simpler to run everything directly on the hypervisor. It would also mean a
compromised agent runtime is a compromised hypervisor.

Keeping the agent in a guest means crossing a boundary to control host hardware — which forces
the question "what is the minimum capability that works?" and produced the forced-command design
in [the security model](03-security-model.md). The constraint improved the result.

## Inference choices

**Local, not cloud.** No conversation, mail content, or network topology leaves the house.

**Context length is the setting that matters most.** The default 4k context makes a tool-using
agent effectively amnesiac — it loses the thread mid-task in a way that reads like the model
being stupid rather than truncated. Raised to 64k, which for this model requires overriding the
native limit explicitly; the runtime needs the same value set independently, and a mismatch
degrades tool use silently.

**Not every model can call tools.** Of the candidates tested at similar size, some emit clean
structured tool calls and others produce *prose describing* the call they would make. That
difference is invisible in casual chat and fatal for an agent, so it's verified explicitly
before a model is wired in rather than assumed from a model card.

## Transport

The system runs **two transports**, and which one is used is itself a security decision.

**Originally, stdio.** Each server was launched as a container by the agent runtime and spoke
JSON-RPC over its own stdin/stdout — no network listeners, no ports, no service discovery. Simple
and textbook-correct, but it has a hidden cost: **the agent account needs container-daemon access
to launch the servers.** When the host was hardened so that account holds no container privilege at
all ([security model, Principle 5](03-security-model.md#principle-5--the-sandbox-must-not-be-the-host)),
that launch model had to change.

**Now, loopback HTTP for the long-running servers.** Each runs as an independent, root-managed
system service and speaks MCP over streamable-HTTP bound to host loopback; the agent attaches by URL
instead of spawning a process. The code needed one backward-compatible change — honour a transport
environment variable, defaulting to stdio — so the same image runs either way, and the agent's own
throwaway command sandboxes still use stdio on the rootless daemon. The lesson is in
[docs/02](02-mcp-servers.md#transport-from-stdio-subprocesses-to-loopback-services): *a transport
choice can be a security boundary.*

The stdio consequences below still matter — they governed the original design and still govern the
sandbox transport and any stdio smoke test:

- **stdout is sacred.** Anything a server prints to stdout corrupts the protocol stream. All
  logging goes to stderr.
- **Testing by pipe is misleading.** `printf ... | docker run -i` closes stdin immediately;
  the transport reads that as a disconnect and begins shutting down, so any tool doing real
  network work has its response dropped. This looks exactly like a broken tool. Hold stdin open
  past the work when testing by hand.
- **Sessions cache the tool registry.** Adding a server requires restarting the gateway *and*
  resetting any live chat session, or the new tools appear absent — with the model
  confabulating an explanation for why it can't do the thing.

## Configuration and state

| Path | Contents |
| --- | --- |
| `<config>/config.yaml` | Model, transport, MCP server definitions, per-server tool exclusions |
| `<config>/.env` | Secrets. Only declared keys are forwarded into each container. |
| `~/<server>-secrets/` | Mounted read-only: SSH keys, inventories, pinned host keys |
| `~/<server>-data/` | Mounted read-write: change history, watchlists, git-backed config repos |

Servers hold no host-specific paths in code. Everything arrives via environment variables and
mounted volumes, so the same image runs anywhere.
