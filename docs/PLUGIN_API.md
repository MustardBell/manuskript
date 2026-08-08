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

### What the user may change under you

`Tools ▸ Developer ▸ Media types…` lists every format, who declared it, and
what each declarer promised. From there a user may **declare** a format you
have never heard of, choose what **stands in** for one nothing produces, and
**override** an identifier — remapping it, for a plugin that named its output
wrongly.

An override is why declaring an interest is worth doing. Before it is applied
the user is shown who declared that format, so your plugin is named as
affected rather than silently broken; the plugin manager then shows a count
against you for as long as the override stands.

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

Every `ExtensionDescriptor` ID must be a dotted name — letters, digits,
`.`, `_` and `-`, with at least one dot — and should start with your
plugin's namespace: `vendor.notes.panel`, not `panel`. IDs are addressed
globally (routing selections persist them, other plugins may name them),
so two plugins claiming the same ID for the same kind of contribution is
a conflict, and the second one to load is refused.

Returning an object from your entry point gives the plugin a lifecycle.
Both methods are optional, and returning nothing stays valid:

- `activate(context)` runs once install has succeeded. Side effects —
  connecting signals, starting timers, touching the world — belong here,
  not in the entry point, which can still be refused after it runs. The
  context carries `plugin_id` and the same `capability(name)` accessor
  the registrar has. An activate that raises unwinds the whole load and
  the plugin reports **Failed**.
- `deactivate()` runs when the plugin is disabled or unloaded, and also
  when a load fails after the entry point already ran — so it must be
  safe to call whether or not `activate` ever happened.

### What you may register

| method | contribution |
|---|---|
| `register_exporter` | `ExportContribution` |
| `register_importer` | `ImportContribution` |
| `register_converter` | `ConversionContribution` |
| `register_page_type` | `PageTypeContribution` |
| `register_page_renderer` | `PageRendererContribution` |
| `register_markup` | `MarkupContribution` |
| `register_html_augmentation` | `HtmlAugmentationContribution` |
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
| `outline.read` | a manuscript you can read | in your editor workspace |
| `outline.write` | a manuscript you can change | in your editor workspace |
| `editor.control` | an editor pane factory | in your editor workspace |

`api.capability(name)` raises `PluginScopeError` for anything you did not
declare, even a name core has. The surface you touch is the intersection of
what core publishes and what your manifest advertises.

The three workspace services are not asked for by name — they arrive as
fields of your `EditorWorkspaceContext`, or arrive as `None`. Declaring is
still what decides which.

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
the type and reports a failure against your plugin rather than crashing —
in the status bar and the log, never a dialog, so a panel that cannot be
built costs the reader a line rather than blocking them:

- `ProjectPanelContribution.widget_factory(context, parent)`
- `PluginSettingsContribution.widget_factory(context, parent)`
- `EditorWorkspaceContribution.workspace_factory(context, parent)`
- `PageTypeContribution.wizard_factory` — becomes the Live Preview view

The `context` objects (`PluginSettingsContext`, `EditorWorkspaceContext`) are
capability-scoped by design: you receive your own file namespace, a guarded
outline gateway, an editor factory — never the main window or raw models.

### What an editor workspace is given

`EditorWorkspaceContext.outline` and `.editors` are what your manifest asked
for, and `None` otherwise. Registering the contribution is not the request.

| you declare | `context.outline` | `context.editors` |
|---|---|---|
| nothing | `None` | `None` |
| `outline.read` | reads only: `document`, `documents`, `selected_item_ids`, and the change signals | `None` |
| `outline.write` | all of the above plus `set_text`, `set_title`, `set_compile`, `set_compile_many`, `create_text_document`, `duplicate_text_document` | `None` |
| `editor.control` | as above | the editor pane factory |

`outline.write` includes reading, so declare one or the other, not both.

A read-only outline does not have the writing methods — they are absent
rather than disabled, so `hasattr(context.outline, "set_text")` tells you
the truth and calling one raises `AttributeError` naming what you called.

`context.selected_item_ids` arrives whatever you declared: it is what your
workspace was opened on, the argument of the call rather than a view of the
manuscript.

Ask for the least you need. What a plugin may touch is shown to the reader
who installs it, and a workspace that only compares scenes should not be
able to rewrite the book.

`PluginSettingsContext.capability` is how a panel reaches a UI service, and
what it hands back is scoped to you: routing exposes only the page types
**you** registered and raises `PluginScopeError` for anyone else's. The
scoping is enforced by the host rather than trusted to you.

## HTML augmentations

Something Markdown should mean, once it becomes HTML.

```python
registrar.register_html_augmentation(HtmlAugmentationContribution(
    descriptor=ExtensionDescriptor(id="vendor.lists", name="Parenthesis lists"),
    extension_factory=ParenthesisLists,   # a markdown.Extension subclass
))
```

`extension_factory` returns a `markdown.Extension`, because the conversion is
python-markdown and extending it is what that library is for. Your addition
participates in the conversion rather than smuggling tags through it.

It is neither a transform nor an exporter, and the difference matters. A
transform is middleware over one media type and would have to be told where
its output is going — a `<ol>` is only safe if HTML is the destination. An
exporter produces a whole document. An augmentation says one thing more about
what Markdown means, and **every route that renders Markdown as HTML picks it
up**: the HTML export, the preview beside it, and a page type's reading view.

| field | means |
|---|---|
| `extension_factory` | builds the `markdown.Extension`, called per rendering |
| `page_types` | empty applies to every document; naming page types narrows it to documents of those types |
| `applies_to(page_type)` | answers whether it is wanted here — the rule lives with the scope that declares it, not in the registry |
| `priority` | higher runs first, for an addition that must see the source before another |

An extension that will not build is reported in the status bar and skipped.
Your fault must not be the difference between an export happening and not.

### One widget per window

Manuskript can show one project in several windows at once. A project panel
is **declared once** for the application and **built once per window**, so:

- `widget_factory` is called once for every window that opens your panel.
  Two calls means two widgets, both live, both showing the same project.
- Keep per-widget state on the widget. Module-level or class-level state is
  shared by every window and will read as one window changing another.
- Your widget may be **reparented** after it is built: moved to another
  window, or torn off into a floating dock. Do not assume the parent you
  were given is the parent you keep, and do not cache `widget.window()`.
- Both copies see the same models and the same file namespace, because those
  belong to the project rather than to a window. Editing in one is editing
  the project.

Settings panels are built per plugin-manager dialog, and each window has its
own dialog, so the same applies to them.

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
