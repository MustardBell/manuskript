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
