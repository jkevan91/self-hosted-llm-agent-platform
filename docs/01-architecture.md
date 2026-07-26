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
│ Capability     four MCP servers, stdio JSON-RPC              │
│                one container each, non-root                  │
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
| `mediaserver` | Separate box. Media services; managed by the agent. |

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

MCP servers attach over **stdio**, each launched as a container by the agent runtime and
supervised by a watchdog process. No network listeners, no ports, no service discovery — the
transport is the process's own stdin/stdout.

Consequences worth knowing:

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
