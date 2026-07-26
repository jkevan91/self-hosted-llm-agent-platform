# mediactl — AV device control

> Discover and control the streaming players on the network — power, transport, app launch,
> volume — from a text message.

**Risk class:** ephemeral only · no gate (nothing it does is permanent)

---

## In plain English

This gives the assistant a set of hands for the living-room AV devices. I can message it *"what's
playing in the living room?"*, *"pause the bedroom TV,"* or *"put Netflix on the living-room
player,"* and it does it — no remote, no getting up, nothing leaving the house.

The assistant already knew how to look at the network. This adds a new capability aimed
specifically at the AV devices, speaking their own remote-control protocol over the home Wi-Fi via
a well-known open-source library.

## How it's used

- See every AV device on the network.
- Ask what's currently playing on any of them.
- Act as the remote: play, pause, arrows, select, menu, home.
- Power a device on or off, set volume.
- Launch a specific app.
- Send a video URL to a device to play.

## Architecture

Discovery is multicast — the server asks the network who's out there, which is one of the reasons
this server needs real network adjacency rather than a virtualized private namespace (see
[Principle 5](../03-security-model.md#principle-5--the-sandbox-must-not-be-the-host)). Control calls
go through the library's own session to each device.

The device protocol wants stable identifiers — a device UUID and a reverse-DNS bundle ID for apps —
but the model passes what the person *said* ("living room", "Netflix"). So the server resolves
human names to identifiers **inside the tool**: it fetches the real device and app lists, matches
exact-ID → exact-name → substring, and returns a disambiguation error naming the real options when
the match is empty or ambiguous. That resolution is not a nicety — it's a bug fix, see below.

## Safety model

**Why there's deliberately no approval gate here.** The rest of the system has a strict
show-me-the-change-first rule for anything important. AV control doesn't get it, on purpose: the
worst it can do is pause the wrong show, which is undone by pressing play. Adding ceremony to a
"press pause" tool is friction that trains people to click through prompts — worse than none. The
one manual step is **pairing**: each device shows a PIN on screen once, typed in during setup. That
stays a human step rather than something automated around.

## Engineering notes

This server is the origin of one of the project's signature bugs
([debugging log #3](../05-debugging-log.md#3-a-device-api-that-acks-invalid-identifiers)):

> The "launch app" tool reported ✅ while the device sat idle. The device's remote protocol
> **accepts any string as an app identifier, acknowledges it with no error, and does nothing** when
> it doesn't match — while the model was passing the human name "Netflix" because that's what a
> person says, and the device wanted an exact reverse-DNS bundle ID.

The fix — resolve names to IDs inside the tool, and return an error listing the real options — became
a rule in the [shared foundation](../../src/foundation), because *any* tool wrapping an API that
needs stable identifiers has this problem the moment a language model is the caller. It will guess,
and if the API no-ops on a bad guess, the tool lies about succeeding.
