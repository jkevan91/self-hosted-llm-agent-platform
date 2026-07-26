# netadmin — network diagnostics and device management

> Discovery, scanning, and DNS for the LAN; managed configuration changes to network gear behind
> a show-the-diff-then-confirm gate that can always be rolled back.

**Risk class:** state-changing · two-phase gate · git-backed rollback

---

## In plain English

This is the assistant's **safe set of hands for the home network**. It can look around — what's on
the network, is a device reachable, is a service up, why is something slow — and it can make
configuration changes to network equipment, but only through a "show me the change first, then
confirm" process that can always be undone.

Picture a careful IT contractor. They can walk the building and check what's plugged in and whether
everything's up (diagnostics), and they *can* rewire a panel — but they never touch a wire without
first showing you exactly what they'll change, getting your OK, and photographing the panel before
and after so it can be put back the way it was.

## How it's used

- *"What's on my network? Is this device up? Why is this slow?"* → discovery and diagnostics.
- *"Read this device's config / check its firmware."* → read-only remote lookups.
- *"Change this setting."* → it drafts the change as a diff for you to approve; nothing happens
  until you confirm, and every applied change is saved so it can be rolled back.

## Architecture

netadmin is the one server that needs to see the raw LAN, so it's the only one that runs with host
networking and a raw-socket capability — every other server is more contained than this. Discovery
and scanning shell out to standard tooling with arguments built directly (never through a shell),
each call bounded by a timeout and an output cap.

Managed changes are backed by a **git repository on a mounted volume**: the before-state is
committed, the change applied, the after-state committed, so history and rollback are the same
mechanism rather than a bolt-on.

```
model ──► netadmin (host network, raw socket)
             ├── discovery / scan / DNS / connectivity   (read-only, free)
             ├── read device config                       (read-only, free)
             └── plan_* → confirm token → apply_*          (git-backed, gated)
                    └── list_*_history · rollback_*
```

## Safety model

- **Diagnostics run freely; changes never happen in one step.** A `plan_*` call computes the target
  and a diff and returns a one-time token; `apply_*` refuses without a matching, recent token — so
  a human always sees *what* and *why* first. This is the shared
  [two-phase gate](../02-mcp-servers.md#the-two-phase-gate).
- **The "run a command on a device" tool is read-only** — it refuses anything that would change
  state.
- **Every applied change is committed** to version history and can be rolled back.
- **The change tools ship disabled** in the agent configuration until they've been drilled against
  a throwaway target.

## Engineering notes

The interesting design tension is that a diagnostics tool wants to be frictionless and a
config-management tool wants ceremony — putting both in one server would have forced one discipline
onto both. Keeping them in the same server but splitting the *tools* by risk class (free reads,
gated writes) is what let the same assistant be both casual and careful depending on what it's
reaching for. The general rule that came out of it is in
[engineering practices](../06-engineering-practices.md): friction belongs on the dangerous path
only, because ceremony on a harmless action just trains people to click through it.
