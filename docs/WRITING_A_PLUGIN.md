# Writing a Manuskript Plugin API 1 plugin

This guide describes the draft API 1. The language-neutral schemas
and conformance runner live under `plugin_api/`; the Python surface is one
binding to the same contract used by external processes.

A guide for people writing their first one. It walks a working plugin from
an empty directory to something you can enable and see, then points at the
two rules that catch everybody.

For the complete surface — every contribution kind, every service, every
rule — see [PLUGIN_API.md](PLUGIN_API.md). That document is the contract.
This one is the happy path.

---

## What a plugin is

A plugin is a directory with a `plugin.json` and one declared runtime.
Manuskript reads the manifest without running any plugin code and only starts
the runtime once the reader has enabled it. The runtime may be an in-process
Python module or an external process written in any language that implements
RPC protocol 1.

A plugin adds things Manuskript then owns the presentation of: an
exporter, a panel, a page type, a markup dialect. You describe what you
are contributing; core decides where it appears.

An in-process plugin may also declare a native presentation mode: a separate
editor widget selected only by page types that plugin owns. Give it its own
dotted ID and list that ID in `PageTypeContribution.presentation_modes`.
Do not take over `live-preview` or another built-in mode. The complete widget
bridge and ownership rules are in the presentation-mode section of
[PLUGIN_API.md](PLUGIN_API.md#declaring-a-page-specific-editor).

An in-process Python plugin never imports Manuskript internals. Everything it
needs comes from `manuskript.plugins`, and there is a test in the repository
that fails any plugin reaching past it. A process plugin imports no Manuskript
code at all; it exchanges only the records defined in
`plugin_api/schema/api-1.json`.

---

## The smallest in-process Python plugin

Two files. Put them in a directory named after your plugin id, inside
Manuskript's plugin folder — `manuskript/plugins/vendor.hello/`.

`plugin.json`:

```json
{
  "id": "vendor.hello",
  "name": "Hello",
  "version": "1.0.0",
  "api_version": 1,
  "project_formats": {"minimum": 0, "tested_through": 2},
  "runtime": {
    "kind": "python",
    "module": "plugin",
    "callable": "register"
  },
  "description": "Adds a panel that says hello.",
  "author": "You"
}
```

`plugin.py`:

```python
from PyQt5.QtWidgets import QLabel

from manuskript.plugins import (
    ExtensionDescriptor,
    ProjectPanelContribution,
)


def build_panel(context, parent):
    """The widget the reader sees. One of these per window."""
    return QLabel("Hello from a plugin.", parent)


def register(api):
    api.register_project_panel(ProjectPanelContribution(
        descriptor=ExtensionDescriptor(
            id="vendor.hello.panel",
            name="Hello",
            description="Says hello beside your manuscript.",
        ),
        widget_factory=build_panel,
        default_file="hello/notes.txt",
    ))
```

That is a complete plugin. `runtime` says to use the in-process Python driver
and, in `plugin.py`, call `register`. `register` is handed an `api` object and
describes one panel.

A tool panel normally keeps one visibility choice for the workspace. To make
the example accompany the Editor, add
`visible_with_surfaces=("core.editor",)` to its
`ProjectPanelContribution`. The panel then starts visible on that surface and
hidden on the others.
Manuskript remembers later show/hide choices separately as the reader moves
between surfaces. Omitting the field leaves the panel independent; plugins do
not need to know or special-case this routing in their widget code. A
`preferred_extent=280` can provide an initial dock width without preventing
the reader from resizing it later.

Two naming rules, both enforced at load:

- the plugin `id` is reverse-DNS and must not collide
- every `ExtensionDescriptor` `id` needs at least one dot and should start
  with your plugin's name, so `vendor.hello.panel`, never `panel`

`project_formats` is a separate compatibility promise. `minimum` and
`tested_through` say which project formats you explicitly support. With no
`maximum`, later formats are tentatively allowed and Manuskript shows a
compatibility warning until you publish a plugin version that tests them.
Omitting `project_formats` is a manifest error. API 1 requires an author to
state what project semantics were tested; it never guesses from the plugin's
runtime language or contribution kinds.
Use a hard maximum when compatibility ends:

```json
"project_formats": {"minimum": 0, "tested_through": 1, "maximum": 1}
```

That plugin runs for formats 0 and 1 and is not imported or activated for a
format 2 project. This is independent of `api_version`: one describes the
host/plugin API, the other describes project data and semantics.

## An external-process plugin

Use a process runtime when the plugin is written in Node.js, Rust, C, Erlang,
or another language, or when process crash isolation is preferable to loading
code into Manuskript. Commands are argument arrays and are never interpreted
by a shell:

```json
{
  "id": "vendor.remote-hello",
  "name": "Remote hello",
  "version": "1.0.0",
  "api_version": 1,
  "project_formats": {"minimum": 0, "tested_through": 2},
  "runtime": {
    "kind": "process",
    "protocol_version": 1,
    "commands": {
      "linux": ["node", "plugin.mjs"],
      "macos": ["node", "plugin.mjs"],
      "windows": ["node", "plugin.mjs"]
    }
  },
  "description": "Adds a host-rendered command.",
  "author": "You"
}
```

The process speaks JSON-RPC 2.0 with byte-counted `Content-Length` framing on
standard input and output. Standard output is protocol-only; write diagnostics
to standard error. After `initialize`, return the complete contribution
declaration set. Manuskript validates it atomically before publishing anything.
Portable panels use host-rendered declarative UI; a process cannot return a
`QWidget`, painter, Qt highlighter, or other native object.

No SDK is required. `plugin_api/reference/` contains complete minimal Python,
Node.js, Rust, C, and Erlang implementations that use only their language's
normal I/O and JSON facilities. Validate a process against the independent
runner while developing it:

```sh
python3 plugin_api/conformance/run.py \
  --plugin-id vendor.remote-hello \
  --language node \
  --cwd path/to/plugin \
  -- node plugin.mjs
```

The runner and the host consume the same files in `plugin_api/schema/`. An SDK
may make those records more convenient, but it cannot redefine API 1.

---

## Seeing it work

Start Manuskript, open a project, then **Tools ▸ Plugins ▸ Manage
Plugins…**. Your plugin is listed but disabled — nothing of yours has run
yet. Select it, choose Enable, and confirm the trust prompt.

Your panel now appears under **Tools ▸ Plugins**. Open it and the label
shows up in a dock beside the manuscript.

If something is wrong, the manager tells you which of five states you are
in rather than failing silently:

| state | meaning |
|---|---|
| **Disabled** | found, not run. The normal starting state. |
| **Loaded** | running. |
| **Incompatible** | your `api_version` or hard project-format range excludes this project. |
| **Unsatisfied** | you asked for a service this Manuskript lacks. |
| **Failed** | something went wrong; the manager shows the message. |

A panel whose widget factory raises does not crash anything: the reader
gets a line in the status bar, the log gets the exception, and the panel
simply does not open.

---

## Keeping data in the project

A panel usually wants to store something. Your plugin gets a private file
namespace inside the project file, which survives your plugin being
uninstalled:

```python
def build_panel(context, parent):
    editor = QPlainTextEdit(parent)
    editor.setPlainText(context.files.read(context.default_file) or "")

    def remember():
        context.files.write(context.default_file, editor.toPlainText())

    editor.textChanged.connect(remember)
    return editor
```

`context.files` is scoped to your plugin id — you cannot read anybody
else's, and nobody can read yours. Writing marks the project as modified,
so the reader's normal save keeps it.

Because those files are plain text inside the project, a reader whose
plugin has gone away can still recover the content through **Tools ▸
Plugins ▸ Raw Plugin Data…**. Prefer a readable format over a packed one.

---

## Two rules that catch everybody

### One widget per window

Manuskript can show one project in several windows. Your panel is
described once and **built once per window**, so `build_panel` may be
called more than once, and both widgets are live at the same time showing
the same project.

- keep state on the widget, never at module level
- your widget may be moved to another window or torn off into a floating
  dock after it is built, so do not cache the parent you were given

### Declare a format before you promise anything about it

If you touch export formats, name them in `media_types` first:

```json
"media_types": ["text/markdown", "text/x-bbcode"],
"produces":    ["text/markdown"],
"consumes":    ["text/x-bbcode"]
```

`produces` means you write that format yourself. `consumes` means you use
somebody else's writer for it. Promising a format you did not declare
stops the plugin activating — and it is caught in the manifest, so your
code never runs.

---

## Asking for story data

Put a service in `requires` when the plugin cannot run without it. Put it in
`optional` when the plugin has a useful read-only or reduced mode:

```json
"requires": ["entities.read", "query.execute"],
"optional": ["assertions.write"]
```

Inside a project panel or editor workspace, resolve it from the context that
was handed to that widget:

```python
query = context.capability("query.execute")
results = query.execute(EntitiesWhere(entity_type="character"))
```

Import `EntitiesWhere` and other contract values from `manuskript.plugins`.
Do not import the entity catalog, assertion store, or Qt models. The service
returns immutable snapshots and stable IDs; writes go through a separately
declared write capability and preserve the Markdown source as authority.

Formats 0, 1, and 2 use the same editing surface. That does not make their
persistence semantics identical. Formats 0 and 1 cannot persist format-2
references, assertions, morphology, or similar structured story data, so the
corresponding write capabilities are unavailable there. Do not encode those
features into ordinary Markdown as a workaround: that would make new metadata
leak into a legacy project that never opted into it.

Morphology is data-driven. Request `morphology.schemas` to inspect the
available schema snapshots or register a namespaced XML pack. Packs describe
all roles, fields, forms, rules, and lexical exceptions; core does not have
special English, Ukrainian, Russian, or fictional-language branches. A user
can also drop a `*.morphology.xml` pack into Manuskript's morphology data
directory without changing application code.

## Where to go next

- [PLUGIN_API.md](PLUGIN_API.md) — the full contract: every contribution
  kind, the services you can request, media types in depth, and what is
  deliberately not published.
- `plugin_api/README.md` — the canonical schemas, conformance runner, and
  zero-SDK cross-language reference implementations.
