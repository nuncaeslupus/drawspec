"""Document to `Scene`, one module per rendering family.

`scene_for` is the dispatch: it picks the family from the document's kind, which
is the only place in drawspec that knows which families exist. Everything
downstream of it sees a `Scene` and nothing else.
"""

from __future__ import annotations

from drawspec.errors import DrawspecError
from drawspec.kinds.common import box_primitives, outline, text_runs
from drawspec.kinds.grid import grid_scene
from drawspec.scene import Scene
from drawspec.schema import GRID_KINDS, Document
from drawspec.text.measure import TextMeasurer
from drawspec.theme import Theme

#: Kinds that have a renderer. The document schema accepts all nine; the ones
#: absent here are the tasks still to come, and asking for one says so rather
#: than failing obscurely.
IMPLEMENTED: tuple[str, ...] = GRID_KINDS


def scene_for(document: Document, theme: Theme, measurer: TextMeasurer) -> Scene:
    """Render `document` to a `Scene` with the family its kind selects.

    Raises:
        DrawspecError: the kind is valid but has no renderer yet.
        FitError: the content cannot fit at this type scale.
    """
    if document.kind in GRID_KINDS:
        return grid_scene(document, theme, measurer)
    raise DrawspecError(
        f"kind {document.kind!r} is valid but drawspec cannot render it yet; "
        f"implemented so far: {', '.join(sorted(IMPLEMENTED))}"
    )


__all__ = ["IMPLEMENTED", "box_primitives", "outline", "scene_for", "text_runs"]
