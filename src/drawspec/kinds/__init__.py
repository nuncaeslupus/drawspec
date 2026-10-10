"""Document to `Scene`, one module per rendering family.

`scene_for` is the dispatch: it picks the family from the document's kind, which
is the only place in drawspec that knows which families exist. Everything
downstream of it sees a `Scene` and nothing else.
"""

from __future__ import annotations

from drawspec.charts import chart_scene
from drawspec.errors import DrawspecError
from drawspec.kinds.barmodel import barmodel_scene
from drawspec.kinds.board import board_scene
from drawspec.kinds.common import box_primitives, captioned, outline, text_runs
from drawspec.kinds.cycle import cycle_scene
from drawspec.kinds.entities import entities_scene
from drawspec.kinds.files import files_scene
from drawspec.kinds.fishbone import fishbone_scene
from drawspec.kinds.gantt import gantt_scene
from drawspec.kinds.graph import DRAWN_KINDS, graph_scene
from drawspec.kinds.grid import grid_scene
from drawspec.kinds.journey import journey_scene
from drawspec.kinds.numberline import numberline_scene
from drawspec.kinds.sankey import sankey_scene
from drawspec.kinds.sequence import sequence_scene
from drawspec.kinds.shape import shape_scene
from drawspec.kinds.treemap import treemap_scene
from drawspec.kinds.venn import venn_scene
from drawspec.kinds.waterfall import waterfall_scene
from drawspec.scene import Scene
from drawspec.schema import (
    BARMODEL_KINDS,
    BOARD_KINDS,
    CHART_KINDS,
    ENTITIES_KINDS,
    FILES_KINDS,
    FISHBONE_KINDS,
    GANTT_KINDS,
    GRID_KINDS,
    JOURNEY_KINDS,
    NUMBERLINE_KINDS,
    SANKEY_KINDS,
    SEQUENCE_KINDS,
    SHAPE_KINDS,
    TREEMAP_KINDS,
    VENN_KINDS,
    WATERFALL_KINDS,
    Document,
)
from drawspec.text.measure import TextMeasurer
from drawspec.theme import Theme

#: Kinds that have a renderer. The document schema accepts all nine; the ones
#: absent here are the tasks still to come, and asking for one says so rather
#: than failing obscurely.
IMPLEMENTED: tuple[str, ...] = (
    *GRID_KINDS,
    *SHAPE_KINDS,
    *CHART_KINDS,
    *FILES_KINDS,
    *DRAWN_KINDS,
    *SEQUENCE_KINDS,
    *ENTITIES_KINDS,
    *GANTT_KINDS,
    *BOARD_KINDS,
    *FISHBONE_KINDS,
    *VENN_KINDS,
    *JOURNEY_KINDS,
    *TREEMAP_KINDS,
    *SANKEY_KINDS,
    *NUMBERLINE_KINDS,
    *BARMODEL_KINDS,
    *WATERFALL_KINDS,
    "cycle",
)


def scene_for(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Render `document` to a `Scene` with the family its kind selects.

    The document's `caption` is added here rather than in each family, for the
    same reason `centred` lives in one place: it belongs to the whole diagram, so
    a family that forgot it would be wrong in a way only a reader with two
    documents open could see. It happens inside the fit, so a caption too wide
    for the canvas shrinks the diagram like anything else that will not fit.

    Raises:
        DrawspecError: the kind is valid but has no renderer yet.
        FitError: the content cannot fit at this type scale.
    """
    return captioned(_drawn(document, theme, measurer), document.caption, theme, measurer)


def _drawn(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    if document.kind in GRID_KINDS:
        return grid_scene(document, theme, measurer)
    if document.kind in SHAPE_KINDS:
        return shape_scene(document, theme, measurer)
    if document.kind in CHART_KINDS:
        return chart_scene(document, theme, measurer)
    if document.kind in FILES_KINDS:
        return files_scene(document, theme, measurer)
    if document.kind in SEQUENCE_KINDS:
        return sequence_scene(document, theme, measurer)
    if document.kind in ENTITIES_KINDS:
        return entities_scene(document, theme, measurer)
    if document.kind in GANTT_KINDS:
        return gantt_scene(document, theme, measurer)
    if document.kind in BOARD_KINDS:
        return board_scene(document, theme, measurer)
    if document.kind in FISHBONE_KINDS:
        return fishbone_scene(document, theme, measurer)
    if document.kind in VENN_KINDS:
        return venn_scene(document, theme, measurer)
    if document.kind in JOURNEY_KINDS:
        return journey_scene(document, theme, measurer)
    if document.kind in TREEMAP_KINDS:
        return treemap_scene(document, theme, measurer)
    if document.kind in SANKEY_KINDS:
        return sankey_scene(document, theme, measurer)
    if document.kind in NUMBERLINE_KINDS:
        return numberline_scene(document, theme, measurer)
    if document.kind in BARMODEL_KINDS:
        return barmodel_scene(document, theme, measurer)
    if document.kind in WATERFALL_KINDS:
        return waterfall_scene(document, theme, measurer)
    if document.kind == "cycle":
        # A cycle is a parametric template, not a graph layout — see D-1.
        return cycle_scene(document, theme, measurer)
    if document.kind in DRAWN_KINDS:
        return graph_scene(document, theme, measurer)
    raise DrawspecError(
        f"kind {document.kind!r} is valid but drawspec cannot render it yet; "
        f"implemented so far: {', '.join(sorted(IMPLEMENTED))}"
    )


__all__ = [
    "IMPLEMENTED",
    "barmodel_scene",
    "board_scene",
    "box_primitives",
    "captioned",
    "cycle_scene",
    "entities_scene",
    "files_scene",
    "fishbone_scene",
    "gantt_scene",
    "graph_scene",
    "journey_scene",
    "numberline_scene",
    "outline",
    "sankey_scene",
    "scene_for",
    "sequence_scene",
    "shape_scene",
    "text_runs",
    "treemap_scene",
    "venn_scene",
    "waterfall_scene",
]
