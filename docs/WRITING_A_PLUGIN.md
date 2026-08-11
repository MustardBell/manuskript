# Writing a Manuskript plugin

A guide for people writing their first one. It walks a working plugin from
an empty directory to something you can enable and see, then points at the
two rules that catch everybody.

For the complete surface — every contribution kind, every service, every
rule — see [PLUGIN_API.md](PLUGIN_API.md). That document is the contract.
This one is the happy path.

---

## What a plugin is

A directory with a `plugin.json` and some Python. Manuskript finds it,
reads the manifest without running any of your code, and only imports the
code once the reader has enabled it.

A plugin adds things Manuskript then owns the presentation of: an
exporter, a panel, a page type, a markup dialect. You describe what you
are contributing; core decides where it appears.

You never import Manuskript internals. Everything you need comes from
`manuskript.plugins`, and there is a test in the repository that fails any
plugin reaching past it.

---

## The smallest plugin that loads

Two files. Put them in a directory named after your plugin id, inside
Manuskript's plugin folder — `manuskript/plugins/vendor.hello/`.

`plugin.json`:

```json
{
  "id": "vendor.hello",
  "name": "Hello",
  "version": "1.0.0",
  "api_version": 1,
  "entry_point": "plugin:register",
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

That is a complete plugin. `entry_point` says "in `plugin.py`, call
`register`". `register` is handed an `api` object and describes one panel.

Two naming rules, both enforced at load:

- the plugin `id` is reverse-DNS and must not collide
- every `ExtensionDescriptor` `id` needs at least one dot and should start
  with your plugin's name, so `vendor.hello.panel`, never `panel`

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
| **Incompatible** | your `api_version` is not this Manuskript's. |
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

## Where to go next

- [PLUGIN_API.md](PLUGIN_API.md) — the full contract: every contribution
  kind, the services you can request, media types in depth, and what is
  deliberately not published.
- `manuskript/plugins/structured_pages/` in the repository — a real plugin that
  uses a page type, two renderers, a settings panel and a service.
