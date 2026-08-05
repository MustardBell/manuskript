# Manuskript plugin contract

**API version 1.**

Core decides what it presents. A plugin declares what it wants to create and
what it needs to work. Nothing else is available, and nothing else is
promised.

This is enforced, not merely documented:
`manuskript/tests/plugins/test_api_boundary.py` walks the runtime modules of
every installed plugin and fails if one imports a Manuskript module outside
the published surface.

---

## The three routes

| kind | what it is | how you get it |
|---|---|---|
| **Contract** | data you construct | `from manuskript.plugins import …` |
| **Base** | a class you subclass | `from manuskript.plugins.ui import …` |
| **Service** | something you call | declare in `requires`, take from `api.capability()` |

Contracts are plain frozen dataclasses and carry no Qt, so tooling can import
them without a GUI. Bases necessarily bring Qt, which is why they live apart
rather than letting Qt into the contract module. Services are negotiated,
because they are the ones core might not be able to provide.

Anything not listed below is internal. It may move or vanish in any release,
and the boundary test will refuse a plugin that reaches for it.

---

## The manifest

`plugin.json`, beside your entry module:

```json
{
  "id": "vendor.thing",
  "name": "Thing",
  "version": "1.0.0",
  "api_version": 1,
  "entry_point": "plugin:register",
  "description": "One sentence.",
  "author": "You",
  "homepage": "https://example.com/thing",
  "requires": ["markup.bbcode"],

  "media_types": [
    "text/markdown",
    "text/x-bbcode",
    {"id": "application/x-fictionbook+xml",
     "label": "FictionBook 2", "textual": false}
  ],
  "produces":   ["text/markdown"],
  "consumes":   ["text/x-bbcode"],
  "transforms": []
}
```

`id` is reverse-DNS by author and must match
`^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$`. Contribution IDs follow the
same convention; the registry **refuses** a duplicate and names the plugin
that already owns it, so collisions are a load error rather than a surprise.

`api_version` gates the whole surface. `requires` names individual services.
The difference matters:

- wrong `api_version` → **Incompatible**: this Manuskript is not for you
- unmet `requires` → **Unsatisfied**: everything else is fine, one service is
  absent

A malformed `requires` is rejected during discovery, so a typo is reported
against the manifest rather than surfacing later as a missing service.

---

## Media types: declaring and promising

These are two different acts and the difference is the whole design.

### `media_types` — declaring

Declaring says a format exists and **you have an interest in it**. It is not
a promise to produce it, consume it, or use it at all.

Declaration is global, non-exclusive, and expected to be repeated. Declare
`text/x-bbcode` even though Manuskript already does: you did not invent it,
but if you have a BBCode processor you care what that name resolves to, and
being on record is what lets the user be warned before they change it.

- a **bare string** re-declares a format somebody already named
- an **object** introduces one, and supplies `label`, optionally `base`, and
  `textual`

`base` names the format yours is a kind of — `text/vnd.reddit+markdown` bases
on `text/markdown` — which seeds what stands in for it when nothing produces
it yet. Whoever names a format first supplies its attributes; a later
declaration of the same identifier keeps them and is not an error.

Declaring a format nobody has introduced is fine. The identifier goes on
record and the attributes arrive when their owner does.

### `produces` / `consumes` / `transforms` — promising

| promise | meaning | needs an existing producer |
|---|---|---|
| `produces` | you convert the raw manuscript into this format yourself | no — you *are* one |
| `consumes` | you grab an existing producer of it rather than implementing it | yes |
| `transforms` | you are middleware: you grab an existing producer and add things on the way out | yes |

SAMPLE Pages is the worked example. It *consumes* `text/x-bbcode`, because its
renderer takes Manuskript's BBCode converter rather than implementing
Markdown→BBCode itself, and it *produces* `text/markdown`, which it builds
from its own page model. One plugin, different promises, different formats.

**Every format you promise must appear in your own `media_types`, or the
plugin does not activate.** Both facts are in the manifest, so this is
settled at discovery and your code is never imported.

A `consumes` or `transforms` entry that nothing currently provides is **not**
an error. That is the *unassigned* state: the route waits for a plugin, and
the export includes the page source unrendered rather than failing.

Your contributions must stay inside your promises. A renderer, converter or
transform naming a format you did not promise to produce, consume or
transform rejects registration — atomically, so nothing installs.

---

## Registering

Your entry point receives a registrar. Call it `api`:

```python
from manuskript.plugins import ExtensionDescriptor, PageTypeContribution


def register(api):
    markup = api.capability("markup.bbcode")   # only if you declared it
    api.register_page_type(PageTypeContribution(...))
```

Nothing you register takes effect until every contribution validates.
Registration is atomic: one rejected contribution installs none of them.

Returning an object with a `deactivate()` method gets that method called when
the plugin is disabled.

### What you may register

| method | contribution |
|---|---|
| `register_exporter` | `ExportContribution` |
| `register_importer` | `ImportContribution` |
| `register_converter` | `ConversionContribution` |
| `register_page_type` | `PageTypeContribution` |
| `register_page_renderer` | `PageRendererContribution` |
| `register_markup` | `MarkupContribution` |
| `register_project_panel` | `ProjectPanelContribution` |
| `register_settings_panel` | `PluginSettingsContribution` |
| `register_editor_workspace` | `EditorWorkspaceContribution` |
| `register_index_card_style` | `IndexCardStyleContribution` |
| `register_transform` | `TransformContribution` |

---

## Services (`requires` + `api.capability`)

| name | you receive | when |
|---|---|---|
| `markup.bbcode` | a `BBCodeConverter` | at registration |
| `ui.export_routing` | an `ExportRoutingService` | in your settings panel |
| `media.registry` | a read-only vocabulary view | in your settings panel |

`api.capability(name)` raises `PluginScopeError` for anything you did not
declare, even a name core has. The surface you touch is the intersection of
what core publishes and what your manifest advertises.

Some services arrive later than others. A UI service needs a running
application and a plugin to be scoped to, and neither exists while plugins
are loading, so you take those from `PluginSettingsContext.capability`
inside your panel factory rather than from `api.capability` during
registration. `requires` still gates them: a name core does not have leaves
you **Unsatisfied** before your code runs either way.

### `ui.export_routing`

```python
def build_settings_panel(context, parent=None):
    routing = context.capability("ui.export_routing")
    return routing.panel(
        "vendor.my-page", parent=parent,
        intro="Render my pages as…",
    )
```

Core owns this widget, so its faults are fixed once for everyone, and core
never places it: the details pane is yours. Asking for a page type you did
not register raises `PluginScopeError`.

Each row is one export destination, in one of three states:

| state | row |
|---|---|
| renderers produce the format exactly | a plain choice |
| only renderers producing a stand-in | the choice names what really comes out |
| nothing at all | *Unassigned*, inert, tooltip naming what was searched |

Every choice includes **Automatic**, which is what an unchosen route reads
as and what selecting it restores. A route you have not decided never
displays a renderer as though you had picked it.

### `markup.bbcode`

```python
markup = api.capability("markup.bbcode")
markup.convert("**bold**")                  # '[b]bold[/b]'
```

Extendable, privately:

```python
import re

from manuskript.plugins import MarkupRule

mine = markup.extended(
    MarkupRule(r"@(\w+)", r"[i]\1[/i]", re.IGNORECASE),
    MarkupRule("...", "\u2026", literal=True),
)
mine.convert("@someone")                    # '[i]someone[/i]'
markup.convert("@someone")                  # '@someone', unchanged
```

`extended()` returns a **new** converter. You cannot change what core
produces for anyone else. A `literal=True` rule is a plain string
replacement; otherwise `pattern` is a regular expression and `replacement`
may be a template or a callable.

---

## Recognising your own documents

A page type must be identified before any stored property marks an item as
yours, and only you know your format. Declare it rather than inspect it:

```python
from manuskript.plugins import ContentSignature, PageTypeContribution

SIGNATURE = ContentSignature(
    starts_with=r"^SAMPLE Interlude",
    ends_with=r"^END SAMPLE Interlude",
)
```

Core compiles and matches this. **Your code is never handed the text of a
document that is not yours.** All declared parts must match; patterns are
regular expressions applied with `MULTILINE` against newline-normalised text.

Once an item carries your property, the stored answer is used and nothing
inspects the text at all — in either direction, so a user's explicit "this is
not one of yours" is honoured.

`detector=` (a callable) remains for formats no pattern can express. It
receives a **bounded window** — the first and last 4096 characters — not the
document. Prefer a signature.

---

## Bases (`manuskript.plugins.ui`)

Classes you subclass. These import Qt but need no running `QApplication`.

| name | for |
|---|---|
| `IndexCardStyle` | cork board card styles |
| `CardLayout` | the geometry a style returns |
| `CardContext` | per-paint state a style reads |

`IndexCardStyle` owns the order every card is drawn in. You supply geometry
and only the phases that make your card look like itself; phases you ignore
draw nothing, so a style cannot skip one by accident.

---

## Widgets you provide

Several contributions take a factory returning a `QWidget`. The host checks
the type and reports a failure against your plugin rather than crashing:

- `ProjectPanelContribution.widget_factory(context, parent)`
- `PluginSettingsContribution.widget_factory(context, parent)`
- `EditorWorkspaceContribution.workspace_factory(context, parent)`
- `PageTypeContribution.wizard_factory` — becomes the Live Preview view

The `context` objects (`PluginSettingsContext`, `EditorWorkspaceContext`) are
capability-scoped by design: you receive your own file namespace, a guarded
outline gateway, an editor factory — never the main window or raw models.

`PluginSettingsContext.capability` is how a panel reaches a UI service, and
what it hands back is scoped to you: routing exposes only the page types
**you** registered and raises `PluginScopeError` for anyone else's. The
scoping is enforced by the host rather than trusted to you.

---

## Deliberately not published

| | why |
|---|---|
| `manuskript.converters.*` | ask for `markup.bbcode` |
| `manuskript.ui.*` (except the bases above) | internal layout, freely changed |
| `manuskript.models.*` | you get snapshots and gateways, not live models |
| `manuskript.settings*` | project settings are the application's |
| `manuskript.functions` | grab bag, no stable shape |

If you need something here, that is a request for a **new capability**, not a
reason to import it. Opening an issue naming what you need and why is the
supported route.

---

## Status meanings

| status | means |
|---|---|
| Disabled | present, not run |
| Enabled | loaded, contributions installed |
| Incompatible | `api_version` mismatch |
| Unsatisfied | a `requires` entry core does not provide |
| Failed | discovery, import or registration error — see the details pane |

A promise about a format you did not declare, and a contribution naming a
format you did not promise, both land in **Failed** with the offending
media type named. The first happens before your code is imported.

An unsatisfied plugin's code is **never imported**. Refusal happens before
the entry point loads.

---

## Worked example

```python
# plugin.json: {"requires": ["markup.bbcode"], ...}
from functools import partial

from manuskript.plugins import (
    ContentSignature,
    ExtensionDescriptor,
    PageRendererContribution,
    PageTypeContribution,
)

from .renderers import MyBBCodeRenderer
from .wizard import MyWizard

SIGNATURE = ContentSignature(starts_with=r"^MY DOC")


def register(api):
    markup = api.capability("markup.bbcode")
    api.register_page_type(PageTypeContribution(
        descriptor=ExtensionDescriptor(id="vendor.my-page", name="My page"),
        property_label="My page",
        signature=SIGNATURE,
        wizard_factory=MyWizard,
        renderer_factory=MyBBCodeRenderer,
    ))
    api.register_page_renderer(PageRendererContribution(
        descriptor=ExtensionDescriptor(
            id="vendor.my-page.bbcode", name="My page as BBCode"),
        page_type_id="vendor.my-page",
        renderer_factory=partial(MyBBCodeRenderer, markup),
        target_formats=("bbcode",),
    ))
```

Note the `partial`: renderer factories take no arguments, so a service is
bound at registration rather than imported at module scope.

---

## Notes

`PLUGIN_ROADMAP.md` in the repository root predates this and proposes an
inheritance-based design (`BasePlugin`, role interfaces) that was not built.
The system is declarative instead: you describe contributions, core
constructs. This document is the contract; the roadmap is history.

Plugin **tests** may import core freely — test helpers and fixtures are not
part of this contract, and the boundary test excludes them.
