"""Converting one markup into another, with whatever plugins have added.

A plugin that needs Markdown as HTML asks for it here and is given it. It
does not call a Markdown library, does not know which library that is, and
does not know that some other plugin taught the conversion about lists
written ``1)``. That is the whole point: an addition to a conversion has to
reach every rendering of it, and it cannot do that if each caller performs
the conversion itself.

No format is named in this module's interface. A route is two media types
supplied by the caller, so asking for Markdown as BBCode is the same call as
asking for Markdown as HTML, and a route core cannot perform says so rather
than pretending.
"""

import logging
from importlib.util import find_spec

from manuskript.plugins.api import ConversionRequest
from manuskript.plugins.conversion_augmentations import augmentations_for


LOGGER = logging.getLogger(__name__)


class UnknownRoute(LookupError):
    """Nothing here converts between those two formats."""


class ConversionService:
    """Perform a conversion between two media types.

    Holds the registry rather than a snapshot of what it contained. A plugin
    enabled after this was built contributes to conversions performed after
    that, which is what somebody enabling a plugin expects.
    """

    def __init__(self, engines, registry=None, report_error=None):
        #: (source, target) -> callable(text, additions) -> text.
        self._engines = dict(engines)
        self._registry = registry
        self._report_error = report_error

    def routes(self):
        """Every conversion this service can perform."""
        return tuple(sorted(self._engines))

    def can_convert(self, source_format, target_format):
        return (source_format, target_format) in self._engines

    def convert(self, text, source_format, target_format, page_type=None):
        """Convert ``text``, applying what plugins have added to this route.

        ``page_type`` narrows which additions apply, for an addition that was
        declared only for certain pages. Absent means an ordinary document.
        """
        engine = self._engines.get((source_format, target_format))
        if engine is None:
            raise UnknownRoute(
                "Nothing converts {} into {}.".format(
                    source_format, target_format,
                )
            )
        if not isinstance(text, str) or not text:
            return text
        additions = augmentations_for(
            self._registry,
            ConversionRequest(
                source_format=source_format,
                target_format=target_format,
                page_type=page_type,
            ),
            report_error=self._report_error,
        )
        return engine(text, additions)


def _markdown_to_html(text, additions):
    """python-markdown, which takes its additions as extensions."""
    import markdown as MD

    return MD.markdown(text, extensions=list(additions))


def _markdown_to_bbcode(text, additions):
    """Manuskript's own rules, extended by whatever was added.

    The converter takes rules rather than extensions, so an addition for this
    route is a rule. What an addition must be belongs to the route, which is
    why this service takes engines rather than assuming one shape.
    """
    from manuskript.converters.markdownToBBCode import markdown_to_bbcode

    return markdown_to_bbcode(text, additions)


def _installed(name):
    """Whether ``name`` could be imported, without importing it."""
    try:
        return find_spec(name) is not None
    except (ImportError, ValueError):
        # A parent package that will not import, or an entry deliberately
        # blocked in sys.modules. Either way the import would fail.
        return False


def core_engines():
    """The conversions Manuskript itself performs.

    Kept here rather than discovered, because these are core's own and their
    absence would be a broken installation rather than a missing plugin.

    Markdown to HTML is offered only where python-markdown is installed. It
    is a listed requirement, but an installation can be without it -- core
    guards for exactly that in its own HTML exporter -- and a caller told the
    route exists and then handed an ImportError has nothing left to do,
    while one told the route does not exist can show the text plainly
    instead. Only a route that can be performed is offered.
    """
    from manuskript.media_types import BBCODE, HTML, MARKDOWN

    engines = {(MARKDOWN, BBCODE): _markdown_to_bbcode}
    if _installed("markdown"):
        engines[(MARKDOWN, HTML)] = _markdown_to_html
    return engines


def conversion_service(registry=None, report_error=None):
    return ConversionService(
        core_engines(), registry=registry, report_error=report_error,
    )
