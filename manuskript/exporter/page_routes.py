from dataclasses import dataclass


@dataclass(frozen=True)
class PageRendererRoute:
    """An available Compile target that consumes rendered page fragments."""

    id: str
    label: str
    output_format: str
    representation_format: str
    exporter_name: str = ""


def page_renderer_route_id(output_format, representation_format):
    return "{}:{}".format(output_format, representation_format)


def page_renderer_routes(exporters):
    """Discover page-aware routes from the live exporter graph."""
    discovered = []
    seen = set()
    for exporter in exporters:
        if not exporter.isValid():
            continue
        for output in exporter.exportTo:
            if not output.implemented or not output.isValid():
                continue
            render_target = getattr(output, "pageRenderTarget", None)
            output_format = getattr(output, "pageOutputFormat", None)
            if not callable(render_target) or not callable(output_format):
                continue
            representation = str(render_target() or "")
            destination = str(output_format() or "")
            if not representation or not destination:
                continue
            route_id = page_renderer_route_id(
                destination,
                representation,
            )
            if route_id in seen:
                continue
            seen.add(route_id)
            discovered.append(PageRendererRoute(
                id=route_id,
                label=output.name,
                output_format=destination,
                representation_format=representation,
                exporter_name=exporter.name,
            ))
    return tuple(discovered)
