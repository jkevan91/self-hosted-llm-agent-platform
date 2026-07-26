# hoststat — read-only host inspection

> A read-only look inside the agent's own host — memory, processes, disk, sockets, service status
> and logs — so the assistant can **explain** a problem, not just report the gauge reading.

**Risk class:** read-only · no write path exists, so no gate exists

---

## In plain English

The dashboard is like a car's dashboard: it shows the fuel gauge and the temperature light. Until
this server existed, when something looked wrong and you asked the assistant *"why?"*, it could only
reason from those gauges — it couldn't pop the hood.

`hoststat` lets it pop the hood: see which programs are using the most memory, which services are
running or crashing, how full the disks are, what's listening on the network. It's a **look-only**
hood latch — the assistant physically cannot start the engine, change the oil, or unplug anything.

## How it's used

- *"Why is memory high?"* → the biggest memory users, in plain language.
- *"Is the media service healthy?"* → that service's status and recent logs.
- *"What's running / what's listening / how full is the disk?"* → direct answers.

It's what turns the dashboard's *"memory is high on the agent host"* into *"and here's what's eating
it."*

## Architecture

It reaches the host the same way [thermalctl](thermalctl.md) reaches the hypervisor — an SSH key
**pinned to a forced command** — but the dispatcher on the far end knows only read-only verbs:

```
summary | mem | proc | disk | sockets | svc-status | svc-logs
```

The dispatcher parses its argument into an array with **no shell involved**, validates unit names by
charset, and clamps counts. It logs in as an **unprivileged** account — enough for "what's eating
memory," and deliberately not enough to inspect another user's process internals.

## Safety model

There is no verb that changes anything, so the server has **no two-phase gate — there is nothing to
gate.** That's the design goal stated in reverse: the safest write path is the one that was never
built. The security claim rests on the far-end dispatcher's grammar being small, read-only, and
shell-free — the same "small parser you can reason about in one sitting" property as the thermal
agent, minus any write verb to get wrong.

## Engineering notes

hoststat exists because a gauge that says *"memory is high"* and can't say *why* sends a human to SSH
in and start typing `ps`. Giving the *agent* that read-only view — behind the same forced-command
pattern already trusted elsewhere — let the dashboard's **Diagnose** feature become an actual
investigation instead of a restatement of the metric.

It's also the server that exposed a subtle failure that had nothing to do with the code
([debugging log #8](../05-debugging-log.md#8-a-tool-that-was-registered-healthy-and-invisible)):
after adding it, the agent insisted one of its tools "wasn't available" while every direct check
said it was. The cause was a runtime **tool-deferral** optimization — once the combined tool
definitions crossed a share of the model's context budget, tools were hidden behind a search bridge
the small local model couldn't drive. "The tool works" and "the model can use the tool" turned out
to be different claims needing separate tests.
