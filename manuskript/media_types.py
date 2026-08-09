"""The vocabulary export routing speaks.

Three separate acts, deliberately not fused:

**Declaring** says a name exists and the declarer has an interest in it. It is
not a promise to do anything with the format. Declaration is global and
non-exclusive, so core, a plugin and the user may all declare one type; that is
agreement rather than collision. Whoever names a type first supplies its
attributes, and later declarers need only the identifier.

**Promising** says how a party participates in producing a format:

``produces``
    Converts the raw manuscript into this format itself, from scratch.
``consumes``
    Grabs an existing producer of this format rather than implementing it.
``transforms``
    Middleware: grabs an existing producer and adds things on the way out.

Only ``produces`` stands alone. The other two need a producer to exist, and
when none does the answer is *unassigned* rather than an error.

**Resolving** is the user's: a fallback for a type nothing produces, and an
override for a type somebody declared wrongly.

Nothing here imports Qt, so the vocabulary can be read without a GUI.
"""

from dataclasses import dataclass


#: Origin used for everything Manuskript itself declares.
CORE = "core"

#: Origin used for declarations made by the person using Manuskript.
USER = "user"

#: The three promises. See the module docstring for what each one means.
PRODUCES = "produces"
CONSUMES = "consumes"
TRANSFORMS = "transforms"

PROMISES = (PRODUCES, CONSUMES, TRANSFORMS)


class MediaTypeError(ValueError):
    """Something is wrong with a media type declaration or assignment."""


class MediaTypeCycleError(MediaTypeError):
    """A fallback or override chain would loop back on itself."""


@dataclass(frozen=True)
class MediaType:
    """One format, as named by whoever named it first.

    ``base`` seeds the default fallback: Reddit-flavoured Markdown based on
    ``text/markdown`` is served by an ordinary Markdown producer until
    somebody registers a Reddit-specific one. ``textual`` says whether content
    in this format can be embedded in an assembled document; ePub and DocX
    cannot, which is why they are destinations reached *via* a textual
    representation rather than representations themselves.
    """

    id: str
    label: str = ""
    base: str = ""
    textual: bool = True

    def __post_init__(self):
        identifier = str(self.id).strip()
        if not identifier:
            raise MediaTypeError("A media type needs an identifier.")
        object.__setattr__(self, "id", identifier)
        object.__setattr__(self, "label", str(self.label).strip())
        object.__setattr__(self, "base", str(self.base).strip())
        if self.base == identifier:
            raise MediaTypeCycleError(
                "Media type {} cannot be based on itself.".format(identifier)
            )

    @property
    def named(self):
        """Whether anyone has supplied this type's attributes yet.

        A plugin may declare interest in a type nobody has introduced. That
        is legal: the identifier is on record and the attributes arrive when
        whoever owns the format does.
        """
        return bool(self.label)


PLAIN = "text/plain"
MARKDOWN = "text/markdown"
HTML = "text/html"
#: BBCode has no registered IANA type, and calling it text/plain -- as the
#: BBCode exporter did -- collides with actual plain text once media types
#: become the routing key. This is the one identifier Manuskript mints.
BBCODE = "text/x-bbcode"
LATEX = "application/x-latex"
RST = "text/x-rst"
OPML = "text/x-opml+xml"
EPUB = "application/epub+zip"
ODT = "application/vnd.oasis.opendocument.text"
DOCX = (
    "application/vnd.openxmlformats-officedocument"
    ".wordprocessingml.document"
)
PDF = "application/pdf"


#: Every format Manuskript itself knows how to name.
CORE_MEDIA_TYPES = (
    MediaType(PLAIN, "Plain text"),
    MediaType(MARKDOWN, "Markdown"),
    MediaType(HTML, "HTML"),
    MediaType(BBCODE, "BBCode"),
    MediaType(LATEX, "LaTeX"),
    MediaType(RST, "reStructuredText"),
    # Destinations. Reached through a textual representation, never embedded
    # in one, which is what textual=False records.
    MediaType(OPML, "OPML", textual=False),
    MediaType(EPUB, "ePub", textual=False),
    MediaType(ODT, "OpenDocument", textual=False),
    MediaType(DOCX, "DocX", textual=False),
    MediaType(PDF, "PDF", textual=False),
)


class MediaTypeRegistry:
    """Who knows about which formats, and what they promise to do with them.

    The registry never looks up a plugin. Everything is keyed by media type,
    which is what lets a second plugin providing the same format become
    assignable the moment it is installed.
    """

    def __init__(self, default_fallback=""):
        self._types = {}         # id -> MediaType, first namer wins
        self._declaredBy = {}    # id -> [origin], insertion-ordered
        self._promises = {}      # id -> {promise: [origin]}
        self._fallbacks = {}     # id -> id, assigned by the user
        self._overrides = {}     # id -> id, assigned by the user
        # What stands in for a textual format that declared no base and
        # whose owner assigned nothing. A default rather than a policy: it
        # is one value, visible, and the user's assignment outranks it.
        self._defaultFallback = str(default_fallback).strip()

    @property
    def default_fallback(self):
        """The format that stands in when nothing more specific does."""
        return self._defaultFallback

    # ------------------------------------------------------------ declaring

    def declare(self, media_type, origin):
        """Record that ``origin`` knows about a format, and maybe name it.

        ``media_type`` is a :class:`MediaType` to introduce a format, or a
        bare identifier to declare interest in one somebody else names.
        Declaring twice is agreement: both origins go on record, and the
        first set of attributes stands.
        """
        if isinstance(media_type, str):
            media_type = MediaType(media_type)
        if not isinstance(media_type, MediaType):
            raise MediaTypeError(
                "Declare a MediaType or an identifier, not {}.".format(
                    type(media_type).__name__
                )
            )
        origin = str(origin).strip()
        if not origin:
            raise MediaTypeError("A declaration needs an origin.")

        known = self._types.get(media_type.id)
        if known is None or (not known.named and media_type.named):
            # Either nobody has named it, or somebody declared bare interest
            # first and the attributes have only now arrived.
            self._guard_base(media_type)
            self._types[media_type.id] = media_type
        origins = self._declaredBy.setdefault(media_type.id, [])
        if origin not in origins:
            origins.append(origin)
        return self._types[media_type.id]

    def declared_by(self, media_id):
        """Every origin with an interest in this format, in declared order."""
        return tuple(self._declaredBy.get(str(media_id).strip(), ()))

    def known(self):
        """Every declared format, sorted by identifier."""
        return tuple(
            self._types[media_id]
            for media_id in sorted(self._types)
        )

    def is_known(self, media_id):
        return str(media_id).strip() in self._types

    def get(self, media_id):
        return self._types.get(str(media_id).strip())

    def label(self, media_id):
        """A displayable name, falling back to the identifier itself."""
        media_id = str(media_id).strip()
        media_type = self._types.get(media_id)
        if media_type is not None and media_type.named:
            return media_type.label
        return media_id

    # ------------------------------------------------------------ promising

    def promise(self, media_id, kind, origin):
        """Record that ``origin`` produces, consumes or transforms a format.

        The format must be declared first. A promise about a format nobody
        has declared is the manifest inconsistency that refuses a plugin, so
        it is refused here rather than quietly accepted.
        """
        media_id = str(media_id).strip()
        if kind not in PROMISES:
            raise MediaTypeError(
                "Unknown promise {!r}; expected one of {}.".format(
                    kind,
                    ", ".join(PROMISES),
                )
            )
        if media_id not in self._types:
            raise MediaTypeError(
                "Cannot promise to {} {}, which nothing has declared."
                .format(kind, media_id)
            )
        origin = str(origin).strip()
        if not origin:
            raise MediaTypeError("A promise needs an origin.")
        by_kind = self._promises.setdefault(media_id, {})
        origins = by_kind.setdefault(kind, [])
        if origin not in origins:
            origins.append(origin)

    def promises(self, media_id):
        """What each party promised about this format, by promise kind."""
        by_kind = self._promises.get(str(media_id).strip(), {})
        return {
            kind: tuple(by_kind.get(kind, ()))
            for kind in PROMISES
        }

    def promised_by(self, origin, kind=None):
        """Every format one origin promised something about."""
        origin = str(origin).strip()
        kinds = PROMISES if kind is None else (kind,)
        return tuple(sorted(
            media_id
            for media_id, by_kind in self._promises.items()
            if any(origin in by_kind.get(name, ()) for name in kinds)
        ))

    # ------------------------------------------------------------- resolving

    def resolve(self, media_id):
        """The format an identifier really means, after user overrides."""
        media_id = str(media_id).strip()
        seen = []
        while media_id in self._overrides:
            if media_id in seen:
                raise MediaTypeCycleError(
                    "Media type overrides loop back to {}.".format(media_id)
                )
            seen.append(media_id)
            media_id = self._overrides[media_id]
        return media_id

    def fallback_chain(self, media_id):
        """This format, then everything that may stand in for it.

        The first entry is always the resolved format itself. Each step after
        it is the user's assigned fallback if there is one, otherwise the
        declared ``base``.
        """
        media_id = self.resolve(media_id)
        chain = []
        while media_id:
            if media_id in chain:
                raise MediaTypeCycleError(
                    "Media type fallbacks loop back to {}.".format(media_id)
                )
            chain.append(media_id)
            media_id = self._next_fallback(media_id)
        return tuple(chain)

    def fallback(self, media_id):
        """The user's assigned fallback, or '' when they chose none."""
        return self._fallbacks.get(self.resolve(media_id), "")

    def assign_fallback(self, media_id, target):
        """Choose what stands in for a format nothing produces.

        Passing an empty target leaves the format unassigned, which is a
        legal, inert state rather than an error.
        """
        media_id = self.resolve(media_id)
        target = str(target or "").strip()
        if not target:
            self._fallbacks.pop(media_id, None)
            return
        if not self.is_known(target):
            raise MediaTypeError(
                "Cannot fall back to {}, which nothing has declared."
                .format(target)
            )
        self._guard_chain(media_id, target, "fallbacks")
        self._fallbacks[media_id] = target

    def override(self, media_id):
        """The user's remapping of this identifier, or '' when there is none."""
        return self._overrides.get(str(media_id).strip(), "")

    def assign_override(self, media_id, target):
        """Remap an identifier a declarer got wrong.

        This asserts a fact about the bytes somebody else emits, so it is a
        developer-level act. Getting it wrong produces well-formed content
        under the wrong name.
        """
        media_id = str(media_id).strip()
        target = str(target or "").strip()
        if not target or target == media_id:
            self._overrides.pop(media_id, None)
            return
        if not self.is_known(target):
            raise MediaTypeError(
                "Cannot override {} to {}, which nothing has declared."
                .format(media_id, target)
            )
        self._guard_chain(media_id, target, "overrides")
        self._overrides[media_id] = target

    def affected_by(self, media_id):
        """Origins that declared an interest in a format, for warnings.

        Reassigning or overriding a type is safe to offer precisely because
        every interested party is on record.
        """
        return self.declared_by(self.resolve(media_id))

    # ---------------------------------------------------------------- guards

    def _next_fallback(self, media_id):
        """One step along the chain, most specific answer first.

        The user's assignment beats the type's declared base, because a base
        states what a format is a kind of and an assignment states what the
        user wants instead. Both beat the registry default, which knows
        nothing about the format beyond it being textual.

        A format declared but not yet named gets no stand-in at all. Nobody
        has said what it is, so assuming text would put Markdown into a file
        that may not be text.
        """
        assigned = self._fallbacks.get(media_id)
        if assigned:
            return assigned
        media_type = self._types.get(media_id)
        if media_type is None:
            return ""
        if media_type.base:
            return media_type.base
        if (
            media_type.named
            and media_type.textual
            and media_id != self._defaultFallback
        ):
            return self._defaultFallback
        return ""

    def _guard_base(self, media_type):
        if not media_type.base:
            return
        walker = media_type.base
        seen = {media_type.id}
        while walker:
            if walker in seen:
                raise MediaTypeCycleError(
                    "Basing {} on {} would loop back to {}.".format(
                        media_type.id,
                        media_type.base,
                        walker,
                    )
                )
            seen.add(walker)
            walker = self._next_fallback(walker)

    def _guard_chain(self, media_id, target, what):
        """Refuse an edge that would close a loop, naming where it closes."""
        walker = target
        seen = {media_id}
        while walker:
            if walker in seen:
                raise MediaTypeCycleError(
                    "Pointing {} at {} would make media type {} loop back "
                    "to {}.".format(media_id, target, what, walker)
                )
            seen.add(walker)
            walker = (
                self._overrides.get(walker, "")
                if what == "overrides"
                else self._next_fallback(walker)
            )


class MediaTypeView:
    """Read-only access to the vocabulary, for plugins that ask.

    A plugin declares formats in its manifest, where the declaration is
    visible and versioned with the plugin. It does not declare them at
    runtime, and it does not choose fallbacks or overrides for anyone --
    those are the user's. So what a plugin gets is a reader.
    """

    def __init__(self, registry):
        self._registry = registry

    def known(self):
        return self._registry.known()

    def is_known(self, media_id):
        return self._registry.is_known(media_id)

    def get(self, media_id):
        return self._registry.get(media_id)

    def label(self, media_id):
        return self._registry.label(media_id)

    def declared_by(self, media_id):
        return self._registry.declared_by(media_id)

    def promises(self, media_id):
        return self._registry.promises(media_id)

    def fallback_chain(self, media_id):
        return self._registry.fallback_chain(media_id)

    def resolve(self, media_id):
        return self._registry.resolve(media_id)


def core_registry():
    """A registry holding everything Manuskript itself declares.

    Markdown is the default stand-in because every pipeline accepts it: it
    is what the manuscript is written in and what every exporter can take.
    That used to be spelled as a literal inside the renderer search, where
    nobody could see or change it.
    """
    registry = MediaTypeRegistry(default_fallback=MARKDOWN)
    for media_type in CORE_MEDIA_TYPES:
        registry.declare(media_type, CORE)
    return registry
