# Obsidian interoperability target

Project Format 2 is a Markdown vault that Manuskript and Obsidian can inspect
without either application becoming the other's storage engine. The executable
fixture under `manuskript/tests/fixtures/obsidian_vault` defines the supported
intersection.

Manuskript promises:

- Obsidian-order `[[target|display]]` links and top-level YAML `aliases`;
- ordinary Markdown, attachments, `.obsidian` settings, and unknown YAML remain
  author-owned files rather than silently becoming manuscript documents;
- stable `manuskript.id` identity recovers a listed document after an external
  file rename and reports the stale address;
- entity and outline paths remain readable addresses, not type inference;
- untouched vault files round-trip byte-for-byte;
- edits to Markdown bodies and aliases made by Obsidian remain loadable;
- generated derived indexes never pollute the vault as authoritative data.

Manuskript does not promise every Obsidian extension, embed, block identifier,
or plugin convention. Unsupported constructs remain Markdown source. Where an
Obsidian convention would weaken stable identity or loss preservation,
Manuskript's explicit metadata wins.
