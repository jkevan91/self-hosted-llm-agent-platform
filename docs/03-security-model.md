# Security model

The premise of this system is uncomfortable if you say it plainly: **a language model has
authenticated access to infrastructure.** Language models can be manipulated by content they
read — a web page, an email, a filename. So the design question is not "will the model behave"
but "what can it reach when it doesn't."

Everything here follows from that.

---

## Principle 1 — capability, not access

The naive way to let an agent in a VM control hardware on the hypervisor beneath it is an SSH
key for `root`. That works on the first try and is indefensible: any injection that reaches the
agent inherits the hypervisor.

Instead the key is pinned to a **forced command**:

```
command="/usr/local/sbin/thermalctl-agent",no-pty,no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-user-rc ssh-ed25519 AAAA...EXAMPLE
```

`sshd` discards whatever the client asked to run and executes the agent instead, handing the
requested string over in `$SSH_ORIGINAL_COMMAND`. The agent parses it against a fixed verb list:

```
ping | caps | status | fan set <pct> [ttl] | fan auto
                     | curve get | curve set <points>
                     | rgb set <hex|off> [ttl] | rgb auto
```

Anything else is refused. Every argument is validated by regex before use. Nothing is passed
to a shell — no `eval`, no `bash -c`, no redirects built from input.

### Why this is stronger than sudoers

A scoped `sudoers` file constrains *which binaries* run as root, but the account still has a
shell — and the binaries a fan controller needs (`systemctl`, a device CLI) are rich enough to
be repurposed into general execution. A forced command removes the shell from the equation
entirely. The remaining attack surface is the agent's own parser: about twenty lines of regex
validation that can be read and reasoned about in one sitting.

### Verified, not assumed

Run against a live host:

| Sent | Result |
| --- | --- |
| `ping` | ✅ `OK agent alive` |
| `id` | ❌ `unknown verb 'id'` |
| `cat /etc/shadow` | ❌ `unknown verb 'cat'` |
| `fan set 50; rm -rf /tmp/x` | ❌ `illegal characters in command` |
| `` status `id` `` | ❌ `illegal characters in command` |
| `bash -i` | ❌ `unknown verb 'bash'` |
| *(no command — interactive shell)* | ❌ `no command` |

A security control you haven't attacked is a hypothesis, not a control.

---

## Principle 2 — the safest capability is one that doesn't exist

The mail server can search, read, label, archive, star, and draft. It **cannot send and cannot
delete** — not because those tools are disabled, but because they were never written. There is
no code path to enable, no flag to flip, no prompt that unlocks them.

The label tool additionally refuses `TRASH` and `SPAM` targets, so "archive this" can't become
"destroy this" through a creative label choice.

### Being honest about the limit

The OAuth scope granted (`gmail.modify`) *does* technically permit sending. Google offers no
scope granting labels and drafts while withholding send. **So the no-send guarantee is
code-level, not scope-level** — an attacker who could replace the server binary could send
mail.

That's a real limitation and it's documented as one rather than glossed. The alternative
(`gmail.readonly`) makes the restriction scope-enforced but removes labeling, archiving and
drafts — most of the value. The tradeoff was made deliberately and written down.

---

## Principle 3 — persistent changes need a second step

Two classes of action, treated differently on purpose.

**Ephemeral** — set a fan to 60% for ten minutes, turn the lights blue, press pause. Bounded by:

- a **floor clamp**: fan values below a threshold are raised to it; zero is refused outright,
  so no phrasing silences the cooling
- a **mandatory TTL**: every override arms a timer that restores automatic control. Max 12
  hours. A forgotten override cannot persist.

The TTL is enforced by a systemd transient timer, not a backgrounded `sleep` — the SSH session
ends the moment the agent returns, which would take a `sleep` with it. Small detail, load-bearing.

**Persistent** — rewrite a fan curve, change a device configuration. These use a two-phase gate:

```
plan_fan_curve(host, curve, reason)  →  shows current vs proposed, returns a one-time token
                                        ...changes nothing...
apply_fan_curve(confirm_token)       →  refuses without a matching token under 30 minutes old
```

The model cannot reach the second call without surfacing the first to a human. Plans are held
in memory, so a restart invalidates them — a stale plan should not survive.

Change tools ship listed in the agent's `tools.exclude` until they've been drilled by hand.

---

## Principle 4 — least privilege everywhere else

| Control | Applied |
| --- | --- |
| Containers | Non-root (uid 1000), no added capabilities, no host networking unless a server genuinely needs LAN discovery |
| Credentials | Per-server; only declared environment keys are forwarded — one server's secrets are not visible to another |
| Host keys | Pinned; the SSH client uses a reject-on-unknown policy, never auto-add |
| Lighting daemon | Bound to loopback (its default is all-interfaces, which would expose unauthenticated hardware control to the LAN) |
| Chat access | Explicit numeric-ID allowlist; deny by default |
| Secrets in output | Redacted from logs and tool responses |

### One that bit

The vendor default for the lighting control daemon is to listen on **all interfaces with no
authentication**. Anyone on the network could drive the hardware. Binding it to loopback was a
one-line fix — and a reminder to read what a daemon's defaults actually are rather than
assuming a sensible one.

---

## Deliberate residual risks

Documented rather than hidden:

1. **Code-level, not scope-level, mail restrictions** — as above.
2. **The agent can still read a lot.** Constraining *writes* is where the effort went. A
   prompt-injected agent could exfiltrate what it can read into a reply it drafts. Mitigated by
   the allowlist and by drafts requiring a human to send, not eliminated.
3. **The forced-command agent runs as root.** It has to, to drive hardware. The security claim
   rests entirely on its parser being small and correct — which is why it's deliberately short
   and why every argument is regex-validated rather than "cleaned".
4. **Local model, local trust.** Inference never leaves the house, which removes a
   third-party-data-handling question but adds a supply-chain one for model weights.
