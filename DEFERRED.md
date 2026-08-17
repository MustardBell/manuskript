# Deferred decisions

Questions that were asked deliberately, answered "not yet", and would
otherwise have to be re-derived from scratch when they come back. A decision
lives here when it has been thought about and postponed, not when it has been
overlooked. Settled decisions belong in `docs/architecture/decisions/`.

## Declaring a presentation mode versus realizing one

A plugin may declare its own presentation mode, and the declaration carries a
view factory: core asks the factory for the widget that shows the mode. That
is what makes an in-process Python plugin able to contribute a mode today.

The deferred question is whether declaration and realization should be split,
so that a process plugin can declare a mode without being able to hand core a
widget at all. A widget cannot cross a process boundary; a description of one
can. Splitting the two would mean a declaration says what the mode is and what
it is called, while realization is answered either by a local factory or, for
a process plugin, by host-rendered declarative UI over RPC.

Deferred rather than rejected. Taking it now would mean designing the
declarative surface for editor views before there is a plugin asking for one,
and the factory is the shape that works for the plugins that exist.

The wider version of the same question: the python/process distinction is
itself a development artifact. The intended end state is that everything goes
through RPC and no plugin is handed Qt. Variant Workspaces is the hard case —
it is built on native editor endpoints — and rewriting it against a wire
contract is a substantial piece of work in its own right.

**Revisit when:** a plugin wants to contribute a presentation mode from a
process runtime, or when the RPC-only boundary is taken up in earnest.

## Waiting on a plugin process by polling for a file

`test_process_driver_negotiates_and_installs_atomically` waits up to five
seconds for the plugin subprocess to write an `initialized` marker, checking
every ten milliseconds. This is a dirty fix and is marked as one.

Why it is dirty: five seconds is arbitrary, polling is a guess dressed as a
wait, and the failure mode it buys is a slow false failure instead of a fast
one. On a runner slower than any we have seen, it fails for the same reason
it failed before.

Why it was taken anyway: there is nothing to await. `initialized` is a
notification in RPC protocol 1 — the host sends it and does not expect an
answer — so no observable event says the plugin has acted on it.

The clean fix is not in the test. The protocol has no readiness
acknowledgement, which means the *host* also cannot know when a plugin has
finished activating and is able to receive calls. It proceeds regardless.
Today that is invisible because contributions are declared during
`initialize`, before the notification; it stops being invisible as soon as a
plugin needs to do work on activation. Giving protocol 1 a readiness signal
would remove the guess from the test and the assumption from the host at the
same time.

**Revisit when:** protocol 1's lifecycle is next opened, or when a plugin
needs to do work in response to `initialized`.
