"""Reviewable rule-based Ukrainian and Russian personal-name paradigms."""

from manuskript.domain.morphology import (
    GrammaticalForm,
    MorphologyComponent,
    MorphologyProviderRegistry,
)


class _SlavicNameMorphology:
    component_roles = (
        ("title", "Title"),
        ("given-name", "Given name"),
        ("patronymic", "Patronymic"),
        ("surname", "Surname"),
        ("suffix", "Suffix"),
    )
    genders = (
        ("feminine", "Feminine"),
        ("masculine", "Masculine"),
        ("invariable", "Invariable"),
    )
    cases = ()

    def generate(self, component):
        lemma = component.lemma.strip()
        gender = component.attribute("gender", "invariable")
        values = self._forms(lemma, component.role, gender)
        return tuple(
            GrammaticalForm(
                key,
                label,
                component.override(key) or values.get(key, lemma),
                (("case", key),),
            )
            for key, label in self.cases
        )

    def analyse(self, surface, component):
        normalized = self._normalize(surface)
        return tuple(
            form for form in self.generate(component)
            if self._normalize(form.text) == normalized
        )

    def validate(self, component):
        issues = []
        if not component.lemma.strip():
            issues.append("A name component may not be empty.")
        if component.role not in dict(self.component_roles):
            issues.append("Unsupported name component role: {}".format(
                component.role
            ))
        if component.attribute("gender", "invariable") not in dict(
            self.genders
        ):
            issues.append("Unsupported grammatical gender.")
        return tuple(issues)

    def _forms(self, lemma, role, gender):
        if gender == "invariable" or role in ("title", "suffix"):
            return {key: lemma for key, _label in self.cases}
        if gender == "feminine":
            return self._feminine(lemma, role)
        return self._masculine(lemma, role)

    @staticmethod
    def _normalize(value):
        return " ".join(str(value).split()).casefold()


class UkrainianNameMorphology(_SlavicNameMorphology):
    id = "uk.personal-names"
    label = "Ukrainian personal names"
    language = "uk"
    cases = (
        ("nominative", "Nominative"),
        ("genitive", "Genitive"),
        ("dative", "Dative"),
        ("accusative", "Accusative"),
        ("instrumental", "Instrumental"),
        ("locative", "Locative"),
        ("vocative", "Vocative"),
    )

    def _feminine(self, lemma, role):
        lower = lemma.casefold()
        if role == "surname" and lower.endswith(("ська", "цька", "зька")):
            stem = lemma[:-1]
            return self._case_map(
                lemma, stem + "ої", stem + "ій", stem + "у",
                stem + "ою", stem + "ій", lemma,
            )
        if lower.endswith("я"):
            stem = lemma[:-1]
            join = "ї" if stem.endswith(("і", "ї", "й")) else "і"
            return self._case_map(
                lemma, stem + join, stem + "ї", stem + "ю",
                stem + "єю", stem + "ї", stem + "є",
            )
        if lower.endswith("а"):
            stem = lemma[:-1]
            genitive = "і" if stem.casefold().endswith(
                ("г", "к", "х", "ж", "ч", "ш", "щ")
            ) else "и"
            return self._case_map(
                lemma, stem + genitive, stem + "і", stem + "у",
                stem + "ою", stem + "і", stem + "о",
            )
        return {key: lemma for key, _label in self.cases}

    def _masculine(self, lemma, role):
        lower = lemma.casefold()
        if role == "surname" and lower.endswith(("ський", "цький", "зький")):
            stem = lemma[:-2]
            return self._case_map(
                lemma, stem + "ого", stem + "ому", stem + "ого",
                stem + "им", stem + "ому", lemma,
            )
        if lower.endswith("й"):
            stem = lemma[:-1]
            return self._case_map(
                lemma, stem + "я", stem + "єві", stem + "я",
                stem + "єм", stem + "єві", stem + "ю",
            )
        if lower.endswith("ь"):
            stem = lemma[:-1]
            return self._case_map(
                lemma, stem + "я", stem + "еві", stem + "я",
                stem + "ем", stem + "еві", stem + "ю",
            )
        if lower.endswith("о"):
            stem = lemma[:-1]
            return self._case_map(
                lemma, stem + "а", stem + "ові", stem + "а",
                stem + "ом", stem + "ові", stem + "е",
            )
        if lower and lower[-1].isalpha():
            instrumental = "ем" if lower.endswith(
                ("ж", "ч", "ш", "щ")
            ) else "ом"
            return self._case_map(
                lemma, lemma + "а", lemma + "ові", lemma + "а",
                lemma + instrumental, lemma + "ові", lemma + "е",
            )
        return {key: lemma for key, _label in self.cases}

    @staticmethod
    def _case_map(nom, gen, dat, acc, ins, loc, voc):
        return dict(zip(
            (
                "nominative", "genitive", "dative", "accusative",
                "instrumental", "locative", "vocative",
            ),
            (nom, gen, dat, acc, ins, loc, voc),
        ))


class RussianNameMorphology(_SlavicNameMorphology):
    id = "ru.personal-names"
    label = "Russian personal names"
    language = "ru"
    cases = (
        ("nominative", "Nominative"),
        ("genitive", "Genitive"),
        ("dative", "Dative"),
        ("accusative", "Accusative"),
        ("instrumental", "Instrumental"),
        ("prepositional", "Prepositional"),
    )

    def _feminine(self, lemma, role):
        lower = lemma.casefold()
        if role == "surname" and lower.endswith(("ская", "цкая")):
            stem = lemma[:-2]
            return self._case_map(
                lemma, stem + "ой", stem + "ой", stem + "ую",
                stem + "ой", stem + "ой",
            )
        if lower.endswith("я"):
            stem = lemma[:-1]
            return self._case_map(
                lemma, stem + "и", stem + "е", stem + "ю",
                stem + "ей", stem + "е",
            )
        if lower.endswith("а"):
            stem = lemma[:-1]
            ending = "и" if stem.casefold().endswith(
                ("г", "к", "х", "ж", "ч", "ш", "щ", "ц")
            ) else "ы"
            return self._case_map(
                lemma, stem + ending, stem + "е", stem + "у",
                stem + "ой", stem + "е",
            )
        return {key: lemma for key, _label in self.cases}

    def _masculine(self, lemma, role):
        lower = lemma.casefold()
        if role == "surname" and lower.endswith(("ский", "цкий")):
            stem = lemma[:-2]
            return self._case_map(
                lemma, stem + "ого", stem + "ому", stem + "ого",
                stem + "им", stem + "ом",
            )
        if role == "surname" and lower.endswith(("ов", "ев", "ин")):
            return self._case_map(
                lemma, lemma + "а", lemma + "у", lemma + "а",
                lemma + "ым", lemma + "е",
            )
        if lower.endswith("й"):
            stem = lemma[:-1]
            return self._case_map(
                lemma, stem + "я", stem + "ю", stem + "я",
                stem + "ем", stem + "е",
            )
        if lower.endswith("ь"):
            stem = lemma[:-1]
            return self._case_map(
                lemma, stem + "я", stem + "ю", stem + "я",
                stem + "ем", stem + "е",
            )
        if lower and lower[-1].isalpha():
            return self._case_map(
                lemma, lemma + "а", lemma + "у", lemma + "а",
                lemma + "ом", lemma + "е",
            )
        return {key: lemma for key, _label in self.cases}

    @staticmethod
    def _case_map(nom, gen, dat, acc, ins, prep):
        return dict(zip(
            (
                "nominative", "genitive", "dative", "accusative",
                "instrumental", "prepositional",
            ),
            (nom, gen, dat, acc, ins, prep),
        ))


def first_party_morphology_providers():
    return MorphologyProviderRegistry((
        UkrainianNameMorphology(),
        RussianNameMorphology(),
    ))
