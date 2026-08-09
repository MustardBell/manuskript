from manuskript.plugins.api import (
    ConversionArtifact,
    ExportArtifact,
    ImportResult,
    PageExportDocument,
    RenderedDocument,
    normalize_options,
)
from manuskript.plugins.errors import PluginError

import logging

LOGGER = logging.getLogger(__name__)


class PluginExecutionError(PluginError):
    pass


def run_export(contribution, snapshot, options=None):
    engine = contribution.engine_factory()
    operation = getattr(engine, "export", None)
    if not callable(operation):
        raise PluginExecutionError(
            "Exporter {} has no export(snapshot, options) method."
            .format(contribution.descriptor.id)
        )
    result = operation(
        snapshot,
        normalize_options(contribution.options, options),
    )
    if not isinstance(result, ExportArtifact):
        raise PluginExecutionError(
            "Exporter {} returned {}, expected ExportArtifact."
            .format(
                contribution.descriptor.id,
                type(result).__name__,
            )
        )
    return result


def run_import(contribution, source, options=None):
    engine = contribution.engine_factory()
    operation = getattr(engine, "import_document", None)
    if not callable(operation):
        raise PluginExecutionError(
            "Importer {} has no import_document(source, options) "
            "method.".format(contribution.descriptor.id)
        )
    result = operation(
        source,
        normalize_options(contribution.options, options),
    )
    if not isinstance(result, ImportResult):
        raise PluginExecutionError(
            "Importer {} returned {}, expected ImportResult."
            .format(
                contribution.descriptor.id,
                type(result).__name__,
            )
        )
    return result


class PluginConversionService:
    """Route conversions by declared source/target format capabilities."""

    def __init__(self, registry):
        self.registry = registry

    def available(self, source_format, target_format):
        return tuple(
            contribution
            for contribution in self.registry.converters
            if source_format in contribution.source_formats
            and target_format in contribution.target_formats
        )

    def convert(
        self,
        content,
        source_format,
        target_format,
        options=None,
        converter_id=None,
    ):
        candidates = self.available(source_format, target_format)
        if converter_id is not None:
            candidates = tuple(
                value
                for value in candidates
                if value.descriptor.id == converter_id
            )
        if not candidates:
            raise PluginExecutionError(
                "No plugin converter is available for {} → {}."
                .format(source_format, target_format)
            )
        return run_conversion(
            candidates[0],
            content,
            source_format,
            target_format,
            options,
        )


def run_conversion(
        contribution,
        content,
        source_format,
        target_format,
        options=None):
    engine = contribution.engine_factory()
    operation = getattr(engine, "convert", None)
    if not callable(operation):
        raise PluginExecutionError(
            "Converter {} has no convert(content, source_format, "
            "target_format, options) method.".format(
                contribution.descriptor.id
            )
        )
    result = operation(
        content,
        source_format,
        target_format,
        normalize_options(contribution.options, options),
    )
    if not isinstance(result, ConversionArtifact):
        raise PluginExecutionError(
            "Converter {} returned {}, expected "
            "ConversionArtifact.".format(
                contribution.descriptor.id,
                type(result).__name__,
            )
        )
    return result


def run_page_renderer(contribution, source):
    if contribution.renderer_factory is None:
        raise PluginExecutionError(
            "Page type {} has no renderer.".format(
                contribution.descriptor.id
            )
        )
    model = (
        run_page_parser(contribution, source)
        if contribution.parser_factory is not None
        else source
    )
    renderer = contribution.renderer_factory()
    operation = getattr(renderer, "render", None)
    if not callable(operation):
        raise PluginExecutionError(
            "Page renderer {} has no render(model) method."
            .format(contribution.descriptor.id)
        )
    result = operation(model)
    if not isinstance(result, RenderedDocument):
        raise PluginExecutionError(
            "Page renderer {} returned {}, expected "
            "RenderedDocument.".format(
                contribution.descriptor.id,
                type(result).__name__,
            )
        )
    return result


def run_page_parser(contribution, source):
    if contribution.parser_factory is None:
        raise PluginExecutionError(
            "Page type {} has no parser.".format(
                contribution.descriptor.id
            )
        )
    parser = contribution.parser_factory()
    operation = getattr(parser, "parse", None)
    if not callable(operation):
        raise PluginExecutionError(
            "Page parser {} has no parse(source) method.".format(
                contribution.descriptor.id
            )
        )
    return operation(source)


def run_transform(contribution, content, options=None):
    """One middleware pass over content already in its media type."""
    engine = contribution.engine_factory()
    operation = getattr(engine, "transform", None)
    if not callable(operation):
        raise PluginExecutionError(
            "Transform {} has no transform(content, media_type, options) "
            "method.".format(contribution.descriptor.id)
        )
    result = operation(
        content,
        contribution.media_type,
        normalize_options(contribution.options, options),
    )
    if not isinstance(result, str):
        raise PluginExecutionError(
            "Transform {} returned {}, expected str: a transform takes "
            "and returns {}.".format(
                contribution.descriptor.id,
                type(result).__name__,
                contribution.media_type,
            )
        )
    return result


def run_transforms(contributions, content, option_store=None):
    """Every middleware over one media type, in the order it runs.

    A transform that fails is skipped rather than allowed to lose the
    content: it adds to a result somebody else produced, so the result
    without it is still the document.
    """
    for contribution in contributions:
        options = (
            option_store.load(
                contribution.descriptor.id,
                contribution.options,
            )
            if option_store is not None
            else None
        )
        try:
            content = run_transform(contribution, content, options)
        except Exception:
            LOGGER.exception(
                "Transform %s failed; leaving the content untransformed.",
                contribution.descriptor.id,
            )
    return content


def run_page_format_renderer(
        contribution, model, target_format, options=None):
    renderer = contribution.renderer_factory()
    operation = getattr(renderer, "render", None)
    if not callable(operation):
        raise PluginExecutionError(
            "Page renderer {} has no "
            "render(model, target_format, options) method.".format(
                contribution.descriptor.id
            )
        )
    result = operation(
        model,
        target_format,
        normalize_options(contribution.options, options),
    )
    if not isinstance(result, PageExportDocument):
        raise PluginExecutionError(
            "Page renderer {} returned {}, expected "
            "PageExportDocument.".format(
                contribution.descriptor.id,
                type(result).__name__,
            )
        )
    return result
