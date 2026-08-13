# Manuskript Plugin API 1 protocol package

This directory is the language-neutral developer deliverable for Manuskript
Plugin API 1. It is not an installed plugin, a generated plugin template, or
application content. Manuskript does not discover anything in this directory.

The files under `schema/` are the contract:

- `api-1.json` defines every portable value record and enum.
- `manifest-1.schema.json` defines discovery and compatibility declarations.
- `protocol-1.json` defines RPC framing, lifecycle, limits, contribution
  portability, and operation names.

Python dataclasses in Manuskript are bindings to `api-1.json`. At runtime the
host refuses to advertise them if those bindings drift from the checked-in
wire document. The process driver also takes protocol versions, limits,
portability, and operation tables from `protocol-1.json`.

Every manifest must declare `project_formats`. `tested_through` is explicit
support, an absent `maximum` is tentative forward permission with a visible
warning, and a present `maximum` is a hard stop. This is independent of API 1.

## Conformance profile

`conformance/run.py` executes a small command-contribution profile against an
external process. It checks byte-counted UTF-8 framing, API/protocol identity,
the tagged value model, initialization, activation, contribution invocation,
project-change notification, deactivation, shutdown, and exit. It has no Qt
or Manuskript import and uses only the Python standard library.

For example:

```sh
python3 plugin_api/conformance/run.py \
  --plugin-id org.manuskript.reference.python \
  --language python \
  --cwd plugin_api/reference/python \
  -- python3 plugin.py
```

The implementations under `reference/` deliberately do not use an SDK. Each
shows the complete minimum protocol in its language. SDKs may wrap this work,
but an SDK is never required to implement API 1.

Run every reference for which a toolchain is installed (C and Rust are built
in a temporary directory):

```sh
python3 plugin_api/conformance/run_all.py
```

CI uses `--require` after provisioning its language tools, so a missing
toolchain cannot turn a promised conformance check into a silent skip.
The Erlang reference configures `standard_io` as Latin-1 and uses the bytewise
`file` API because JSON-RPC `Content-Length` counts UTF-8 bytes, not Unicode
characters.

These references are protocol fixtures, not examples of how to structure a
real feature. Real plugins belong in their own repositories and declare their
runtime plus project-format compatibility in `plugin.json`.
