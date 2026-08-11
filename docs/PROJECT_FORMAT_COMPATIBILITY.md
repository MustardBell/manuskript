# Project format compatibility

This table is a contract backed by the permanent compatibility corpus. “Old
client” means an unmodified Manuskript release that predates Project Format 2
and the plugin API in this fork. Readability, editability, and save safety are
separate promises: an old client can ignore a file and still delete it while
rebuilding a project.

| Feature | Format 1 in this Manuskript | Old-client round trip | Format 2 |
| --- | --- | --- | --- |
| Plain Markdown | native | full | native |
| Outline, characters, world, plots | native | full | native/adapted |
| Wikilink references | compatible inline text | save-safe as text | native |
| Backlinks and indexes | derived | not applicable | derived |
| Character custom metadata | compatible fields | save-safe | native |
| Morphology on legacy characters | compatible fields | save-safe | native |
| Plugin project files | overlay | not save-safe | native namespace |
| Generic entities | limited/overlay | representation-dependent | native |
| Explicit story assertions | overlay | not save-safe | native |
| Temporal story state | overlay | not save-safe | native |
| Queries and continuity reports | derived | not applicable | derived |

Format 0 and Format 1 remain readable. Format 1 remains writable without a
mandatory upgrade. Existing Format 2 projects remain Format 2 when saved. The
planned migration command will write and validate a separate upgraded copy;
ordinary open/save never replaces a source project or changes its format.
