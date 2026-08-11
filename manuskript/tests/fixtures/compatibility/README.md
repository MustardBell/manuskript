# Project compatibility corpus

These are persisted-source fixtures, not templates. They define behaviours
that old Manuskript projects rely on and must remain stable across persistence
refactors. Tests materialize both folder and archive forms from these sources
and generate the deliberately large case without committing thousands of
near-identical files.

The corpus covers v0 model XML, minimal and complex v1 projects, Unicode and
duplicate titles, renamed legacy paths, revisions, old text kinds, arbitrary
character fields, plugin-owned data, malformed-but-recoverable input, and a
damaged project. Add a fixture before fixing any newly discovered historical
edge case.
