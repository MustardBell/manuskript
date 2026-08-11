# Morphology providers

Manuskript morphology is deterministic assistance for explicit entity
identity. It does not infer who a prose surface refers to and it never turns
a probable match into an assertion automatically.

## Authority and storage

The author configures morphology on a generic entity. Format 2 stores the
configuration as inspectable `entity.metadata` in that entity's Markdown
frontmatter:

```yaml
entity:
  type: character
  metadata:
    - name: morphology
      value:
        version: 1
        provider: uk.personal-names
        components:
          - role: given-name
            lemma: Олена
            attributes:
              gender: feminine
            overrides: {}
          - role: surname
            lemma: Ковальська
            attributes:
              gender: feminine
            overrides:
              vocative: Ковальська
```

Generated forms and reverse indexes are disposable. Deleting them loses no
author data; Manuskript reconstructs them from entity files and registered
providers.

## Provider boundary

Core defines `MorphologyProvider`, `MorphologyProviderRegistry`, component,
profile, form, validation, and reverse-index contracts. A provider owns only
language rules. It declares a stable ID, language, editable name-component
roles and grammatical attributes, then implements:

- `generate(component)` for reviewable forms;
- `analyse(surface, component)` for exact reverse analysis;
- `validate(component)` for deterministic configuration diagnostics.

Providers never receive an entire manuscript and do not decide entity
identity, presence, POV, or story meaning. The project-scoped morphology
index maps an exact generated surface back to stable entity candidates. If
multiple entities share the surface, the ambiguity is retained for the
author to resolve.

## First-party providers

The initial providers cover common Ukrainian and Russian personal-name
patterns. They are deliberately small, transparent rule sets rather than
dictionaries or statistical models. Real names, invented names, indeclinable
forms, and exceptions are expected; the paradigm editor therefore exposes
every generated form and supports an author override for any component and
form.

Compound names are compositional. A title, given name, patronymic, surname,
and suffix can be reviewed independently, then combined into one generated
surface for each grammatical form. Components may be marked invariable.

## Reference behavior

Canonical titles and true aliases remain distinct from grammatical forms.
All three participate in deterministic selection matching and completion,
but a generated form is not silently promoted to a permanent alias. Choosing
a match still writes an ordinary authoritative wikilink such as:

```markdown
[[Characters/Олена Ковальська|Олени Ковальської]]
```

The visible prose supplies the exact surface; the target supplies identity.
