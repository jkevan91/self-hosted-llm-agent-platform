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

## Set the threshold before you look

A plan for this system reached a decision point: extend a single agent into a small fleet of
specialists, or stop at one. That is an expensive, hard-to-reverse choice, and the honest way
to make it is to decide **what would count as ready before measuring whether it is.**

So the criteria were written down first — six of them, each with a trial count and a numeric
threshold, committed to the repo and approved before a single test ran. The reasoning for each
number was recorded alongside it, because a threshold without a rationale gets quietly relaxed
the moment it's inconvenient.

The measurement then returned **no-go**, and the fleet was not built.

That outcome is the reason the practice is worth writing down. A gate defined after seeing
results is not a gate; it is a justification. The only proof that this one was real is that it
was allowed to say no.

### Rates, not pass/fail, when the thing under test samples

An earlier session had drawn conclusions from single runs — try a wording change, run once,
observe fewer tool calls, conclude the change helped. Running the *same* configuration
repeatedly showed the same prompt producing 2 tool calls on one attempt and 13 on another. The
defect being chased fired on roughly one run in four.

Every conclusion drawn from those single runs was noise, and one claim had to be **withdrawn**.

> A single-run regression suite against a sampling system measures the sampler.

So every test in the gate reports `k/N` and never pass/fail, with N fixed in advance and the
same N required on both sides of any before/after comparison. This is slower — the full suite
is 76 trials and takes about fifty minutes — and it is the difference between a number and an
anecdote.

A related discipline: **don't tune while measuring.** No prompt or instruction file was edited
during the measurement pass, because a moving target cannot be a baseline. Defects found
mid-pass were written down and left unfixed until after the verdict.

### Audit the failures before trusting the verdict

One criterion was zero-tolerance: any single instance failed the whole gate. A threshold that
strict has to survive the possibility that the *test* is wrong, so every flagged trial was
re-read against what it had actually done rather than trusted on a summary label.

One flag was **withdrawn** as a false positive — the grader had counted a documented read-only
call as a violation, when reading current state before proposing a change is the correct
behavior. Re-grading three ways, from strictest to most generous, left the verdict unchanged in
all three. That is worth more than the original number: it means the conclusion doesn't depend
on where a judgement call landed.

The reverse error also showed up and was disclosed rather than fixed quietly. One test required
an answer to a question its own prompt never asked, and scored a false failure. Fixing a grader
*after* seeing results is the same species of mistake as choosing a threshold after seeing
results, so the distinction being relied on was stated explicitly: **that bug was visible by
reading the prompt, independent of any outcome.** The original scoring stayed in the write-up
next to the corrected one.

## Enumerating what's forbidden doesn't generalize

The rules given to the agent about restricted operations listed the specific tools it must not
use as workarounds — the shell, remote execution, direct login. The list was accurate and
complete for the tools it named.

Measurement found the agent reaching a **different** tool, one that could run shell commands
indirectly and that the list did not mention. It got there after the named routes failed.

The instruction was not disobeyed. It was satisfied, exactly as written, and routed around.

> A rule that enumerates forbidden things teaches that the boundary is the list. Anything not on
> the list reads as permitted.

The fix is to state the invariant instead — no route to a restricted operation is permitted,
including tools not named here — and demote the specific tools to illustrations. The same
reasoning applies to any allowlist-by-example given to a system capable of finding a case you
didn't think of.

This generalizes past agents. It is the same failure as a firewall rule that blocks known-bad
ports, a validator that rejects known-bad inputs, or a policy that lists prohibited commands:
each defines the boundary by enumeration and each is defeated by the item nobody enumerated.

## An empty correct answer should still terminate

A subtler failure from the same measurements, and the more common one.

Asked a question whose answer required a lookup, the agent selected exactly the right tool and
called it first — correct routing, every time. The tool returned, truthfully, that it had no
data for that device. The written rules say plainly that this is a complete answer and not an
obstacle.

The agent then kept going: scraping a device's web interface for the same information, logging
into other hosts to infer it, querying a vendor's public site, searching the filesystem for a
file it had been told it could not reach.

The routing was never the defect. **The defect was that a correct answer of "nothing" did not
read as a stopping condition.** Told what not to do, the agent complied with each specific
prohibition and continued searching; what was missing was an instruction about when to *stop*.

> Rules that say "don't do X" leave the search running. A terminating condition has to be stated
> as one: report the empty result and stop.

Worth noting because the surface reading — "it picked the wrong tool" — points at routing,
which was fine, and would have sent the fix to entirely the wrong place.
