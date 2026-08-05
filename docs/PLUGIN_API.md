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
  "requires": ["markup.bbcode"]
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

---

## Services (`requires` + `api.capability`)

| name | you receive |
|---|---|
| `markup.bbcode` | a `BBCodeConverter` |

`api.capability(name)` raises `PluginScopeError` for anything you did not
declare, even a name core has. The surface you touch is the intersection of
what core publishes and what your manifest advertises.

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

`PluginSettingsContext.page_routing` exposes only the page types **you**
registered and raises `PluginScopeError` for anyone else's, so the scoping is
enforced by the host rather than trusted to you.

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
