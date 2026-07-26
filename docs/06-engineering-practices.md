# Engineering practices

Conventions that made a multi-month, multi-repo project survivable — especially one built in
sessions separated by weeks.

---

## Dry-run by default

Every script that changes a system reports what it *would* do and exits. Writing requires
`--apply`.

```bash
./install-agent.sh --pubkey "ssh-ed25519 AAAA...EXAMPLE"     # prints a plan, changes nothing
./install-agent.sh --apply --pubkey "..."                    # writes
```

The dry run isn't a formality — it prints detected capabilities and the identifiers you're
about to commit to, so the plan itself is a diagnostic. Several misconfigurations were caught
in a dry run before touching anything.

Re-running is always safe: keys are replaced rather than appended, and existing config files
are backed up with a timestamp before modification, never silently overwritten.

---

## Three documents, three audiences

Every repository carries the same set, and collapsing them is not allowed:

| Document | Audience | Contains |
| --- | --- | --- |
| **README** | An engineer using it | What it is, full tool list, prerequisites, build/run, wiring, a quick test |
| **SUMMARY** | A non-technical reader | Plain-English "what we built", an everyday analogy, what it can do, the safety net. No jargon, no code. |
| **TECHNICAL** | Someone maintaining or debugging it | Architecture diagram, layer responsibilities, safety model, a gotchas-hit-and-resolved table, outstanding work |

The SUMMARY is the one that gets skipped in most projects and is the most valuable. Writing a
plain-English explanation of a security model is a good way to discover the model doesn't
actually make sense.

---

## Gotchas tables

Every TECHNICAL document ends with a table of problems hit and how they were resolved:

| # | Symptom | Cause | Fix |
| --- | --- | --- | --- |

This is the highest-value section in the entire repository set. Most debugging time in a long
project is spent rediscovering something already solved once, and a symptom-first table is
searchable by the thing you actually have — the symptom — rather than the cause you don't know
yet.

---

## Honest after-action reports

Each major phase ends with a written report covering what worked, what didn't, and what was
believed that turned out false. Two entries have been **withdrawn** as later evidence
contradicted them:

- A "fan curve validated under load" claim, retracted once measurement showed the controller
  never accepted a write — the original reading had assumed the correlation it was trying to
  prove.
- An "all data intact" claim about a migrated storage pool, walked back to "pool health
  verified, files not checked" — which is what had actually been done.

**Both corrections are in the repositories, next to the original claims, rather than quietly
edited out.** A document that only ever gained confident statements would be less trustworthy,
not more. Knowing which claims were checked and which were inferred is the difference between
documentation and marketing.

---

## Safety conventions that repeat

Patterns that showed up independently in several servers and became standard:

**Hard constraints stated as constraints.** Certain things must never happen — specific disks
never interpreted by the host, a particular firmware recovery option never accepted. These are
written as explicit "do not violate" lists rather than left implicit, because the cost of
rediscovering them empirically is unrecoverable data.

**Settled decisions marked as settled.** A "don't re-litigate" list prevents relitigating
resolved tradeoffs every time someone new — human or model — reads the project cold.

**Identify hardware by stable identifiers.** Serial or `by-id`, never device letters. Learned
after letters shifted during troubleshooting and a safety warning ended up pointing at the
wrong disk.

**Ship dangerous tools disabled.** State-changing tools are listed in the agent's exclusion
list until drilled by hand. Present in the code, absent from the model's toolbox.

---

## Verify the diagnostic before trusting it

Twice, a diagnostic tool produced a confidently wrong conclusion:

- `dmesg` returning empty output to a non-root user, so greps matched nothing and it read as
  "the feature isn't there" rather than "you can't see it."
- Two similarly-named temperature sensors, where reading the wrong one made a working control
  loop look frozen.

Both are now standing rules: prefer `sysfs` over `dmesg` for hardware facts, and when a
diagnostic returns nothing, first prove the diagnostic works.

---

## Measure effects, don't trust return codes

The single most repeated lesson in this project, stated once as a rule:

> An API that doesn't raise is not an API that worked. Where an effect can be cheaply measured,
> measure it. Where it can't, resolve inputs correctly up front rather than reporting a success
> you didn't verify.

Three separate vendor tools in this system return success while doing nothing. See
[the debugging log](05-debugging-log.md).
