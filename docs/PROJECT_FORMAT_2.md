# Manuskript Project Format 2

Status: implemented specification, version 2

Format 2 is an inspectable Markdown/YAML project. The `.msk` marker contains
`2`; archive projects also contain a `MANUSKRIPT` member containing `2`.

## Layout and identity

`project.yaml` is the project manifest. Its `manuskript.format` value is `2`.
It contains ordered project metadata and the ordered outline. Each outline
entry records a stable ID, a relative Markdown path, and children. Directories
such as `Manuscript`, `Characters`, or `Places` are conventions only: moving a
file does not change what it is.

Every Markdown document carries YAML frontmatter:

```yaml
---
manuskript:
  id: 018f1f42-c546-7d20-bf25-b8d70433c123
  type: document
  title: Opening
  metadata: []
---
```

`manuskript.id` is identity and remains stable across renames. Type is explicit
metadata, never inferred from a directory name. Unknown manifest and document
frontmatter keys must survive a decode/encode round trip.

Project-local application settings live in `.manuskript/settings.json`.
Legacy concepts that have not yet been migrated to generic entity documents
are represented losslessly in `.manuskript/legacy.yaml`; that is a transitional
codec representation, not a second authoritative story database. Plugin-owned
portable data remains under `plugins/<plugin-id>/`.

## Generic entities

Entities are ordinary Markdown documents listed separately from the manuscript
outline in `project.yaml`. Identity and document type stay under `manuskript`;
the generic entity layer adds an open type string, structured metadata, and
Obsidian-compatible top-level aliases:

```yaml
---
aliases: [Mara, Ms Vale]
entity:
  type: character
  metadata: []
manuskript:
  id: 018f1f42-c546-7d20-bf25-b8d70433c123
  type: entity
  title: Mara Vale
  metadata: []
---
```

Core does not infer fiction meaning from `entity.type`. Optional schemas supply
labels and readable path conventions for character, place, object,
organization, concept, event, plot, and user-defined types. Legacy Character,
World, and Plot records are exposed through a read-only generic adapter; they
are not silently migrated or duplicated in Format 1 storage.

### Morphology metadata

An entity may carry an author-reviewed morphology profile inside its generic
structured metadata. The profile names a provider and decomposes a compound
name into components with grammatical attributes and per-form overrides.
See [Morphology providers](MORPHOLOGY_PROVIDERS.md) for the schema and
authority rules. Provider output and lookup indexes are derived state and are
never required to recover what the author configured.

## Markdown and DSL

Ordinary Markdown is valid Format 2 source. The first core DSL primitive is an
Obsidian-order wikilink: `[[target]]` or `[[target|display text]]`. A reference
asserts identity only. It does not assert that an entity is present, owns an
object, knows a fact, or has any other story role.

Malformed DSL remains editable prose and produces diagnostics. Code spans and
fenced code blocks do not create references. Indexes and backlinks are derived
and disposable. The parser exposes stable source spans, recovers extension
failures as diagnostics, and reparses only the affected lines where Markdown
block state makes that safe. Extensions may add generic syntax nodes, but do
not own or rewrite the source.

The reference index resolves targets as `resolved`, `ambiguous`, `missing`, or
`external`, and supplies deterministic path completion, backlinks,
co-occurrence, broken-link reporting, and source-span path refactors. It is
rebuilt from source and never persisted as authoritative project state.
While the caret is inside a wikilink target, `Ctrl+Space` opens the same
deterministic completion as an accessible keyboard menu; choosing an entry
replaces only that target span.

Explicit story meaning uses source-owned `manuskript-assertion` fenced blocks.
Each assertion has stable identity, subject, predicate, reference or scalar
object, open qualifiers, provenance, and an explicit canon state. Relationship
assertions use a reference object; they are not copied into a separate
relationship database. Valid blocks are stripped from Reading and native
exports, while malformed blocks remain visible Markdown with diagnostics.
The assertion index and typed structural query engine are disposable. See
[Explicit story assertions](STORY_ASSERTIONS.md) for the syntax, candidate
comparison, authority rules, and query nodes.

Selecting prose and invoking `Reference…` offers deterministic exact
title/alias matches, grouped explicit choices, and `Create new…`. Choosing an
entry writes `[[path|selected surface]]` into the source. Exact scanners ignore
code and existing links, prefer the longest surface at an overlap, preserve
ambiguity for the writer to decide, and never infer pronouns or story roles.

Editor projections never replace DSL annotations with hidden model entries.
Live Preview hides delimiters outside the active block, Clean Editing hides
them in every block while retaining the canonical editable `QTextDocument`,
and Reading uses a separate rendered sibling view. Source and Formatted Source
remain available when an author wants to see all syntax.

## Preservation and validation

Untouched source is emitted byte-for-byte. A changed project retains unknown
files and structured metadata. Stable IDs and document paths must be unique.
Missing files, mismatched IDs, invalid YAML, and unlisted recovered Markdown
documents are reported rather than silently discarded. Ordinary Markdown with
no Manuskript identity frontmatter remains an unknown author-owned vault file.

## Current authoring boundary

Format 2 projects can be opened, edited, and saved without being normalized to
Format 1. Creating an upgraded copy from an older project is intentionally a
separate migration operation: opening or saving a Format 1 project never opts
it into Format 2 implicitly.
