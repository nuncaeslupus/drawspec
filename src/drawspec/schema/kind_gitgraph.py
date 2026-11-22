"""The `gitgraph` kind: its checks, refusals and the parse into a `Document`."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

from drawspec.schema._checks import _optional_number
from drawspec.schema._model import Document, GitBranch, GitStep, Violation

#: Why a git graph has no place for a field an author may reach for.
GITGRAPH_REFUSED: Final = {
    "lane": (
        "a branch's lane is its place in `branches`, in the order written; the lane's "
        "position on the page is drawspec's"
    ),
    "column": "a step's place in time is its place in `steps`, in the order written",
    "colour": "a branch's colour is the theme's, never the document's",
    "parent": (
        "a commit's parents are derived: the latest commit on its branch, and for a merge "
        "the latest commit on the branch it merges"
    ),
    "parents": (
        "a commit's parents are derived: the latest commit on its branch, and for a merge "
        "the latest commit on the branch it merges"
    ),
    "branch": (
        "a step names its branch with `on`; a new branch is declared once in `branches`, "
        "with `from` saying where it forks"
    ),
    "checkout": ("there is no current branch to switch: every step says which branch it is `on`"),
    "type": (
        "a commit's kind is derived: `merge` makes a merge commit and `pick` a cherry-pick; "
        "for the commit the figure is about, say `role: emphasis`"
    ),
    "date": (
        "a git graph is an order, not a calendar: steps are evenly spaced in the order "
        "written. For dates on an axis draw a `timeline`"
    ),
    "tags": "a commit takes one `tag`; a second tag on the same commit is a second release name",
}


def _gitgraph_refusal(violation: Violation) -> Violation:
    """A structural refusal in a git graph, told what this kind means by it."""
    name = violation.pointer.split("/")[-1]
    if "is not a known field" in violation.message and name in GITGRAPH_REFUSED:
        return Violation(violation.pointer, f"{name!r}: {GITGRAPH_REFUSED[name]}.")
    return violation


def _gitgraph_violations(document: Mapping[str, Any]) -> list[Violation]:
    """Names and handles that resolve, and a history git could have made.

    The steps are replayed in order, as git would make them: a branch forks at its
    first step from the latest commit on its `from`; a merge takes the latest commit
    of the branch it names; a cherry-pick copies an earlier commit. A step that git
    would refuse, or that would draw nothing new, is refused here, at its pointer.
    """
    found: list[Violation] = []
    raw_branches = document.get("branches")
    raw_steps = document.get("steps")
    if not isinstance(raw_branches, list) or not isinstance(raw_steps, list):
        return found
    branches = [entry if isinstance(entry, dict) else {} for entry in raw_branches]
    steps = [entry if isinstance(entry, dict) else {} for entry in raw_steps]

    names: dict[str, int] = {}
    for index, branch in enumerate(branches):
        name = branch.get("name")
        if not isinstance(name, str):
            continue
        if not name.strip():
            found.append(Violation(f"/branches/{index}/name", "a branch needs a name."))
        elif name in names:
            found.append(
                Violation(
                    f"/branches/{index}/name",
                    f"the branch {name!r} is declared twice (first at /branches/{names[name]}): "
                    f"one lane per branch, so give the second its own name.",
                )
            )
        else:
            names[name] = index

    ids: dict[str, int] = {}
    tags: dict[str, int] = {}
    for index, step in enumerate(steps):
        for field_name in ("text", "tag"):
            value = step.get(field_name)
            if isinstance(value, str) and not value.strip():
                found.append(
                    Violation(
                        f"/steps/{index}/{field_name}",
                        f"an empty {field_name!r} draws nothing: leave the field out.",
                    )
                )
        handle = step.get("id")
        if isinstance(handle, str):
            if not handle.strip():
                found.append(Violation(f"/steps/{index}/id", "an empty 'id' names nothing."))
            elif handle in ids:
                found.append(
                    Violation(
                        f"/steps/{index}/id",
                        f"the id {handle!r} is used twice (first at /steps/{ids[handle]}): a "
                        f"commit's handle names one commit.",
                    )
                )
            elif handle in names:
                found.append(
                    Violation(
                        f"/steps/{index}/id",
                        f"{handle!r} is already a branch's name, and a `from` names either: "
                        f"give the commit another id.",
                    )
                )
            else:
                ids[handle] = index
        tag = step.get("tag")
        if isinstance(tag, str) and tag.strip():
            if tag in tags:
                found.append(
                    Violation(
                        f"/steps/{index}/tag",
                        f"the tag {tag!r} is on two commits (first at /steps/{tags[tag]}): a "
                        f"tag names one commit.",
                    )
                )
            else:
                tags[tag] = index
        if "merge" in step and "pick" in step:
            found.append(
                Violation(
                    f"/steps/{index}/pick",
                    "a step is a merge or a cherry-pick, not both: write them as two steps.",
                )
            )
    if found:
        return found

    known = ", ".join(repr(name) for name in names)
    sources: dict[str, str] = {}
    for index, branch in enumerate(branches):
        name = branch.get("name")
        source = branch.get("from")
        if not isinstance(name, str):
            continue
        if index == 0:
            if source is not None:
                found.append(
                    Violation(
                        "/branches/0/from",
                        "the first branch is the trunk, and forks from nothing: put the "
                        "branch it forks from before it in `branches`.",
                    )
                )
            continue
        if source is None:
            source = next(iter(names))
        if not isinstance(source, str):
            continue
        if source == name:
            found.append(Violation(f"/branches/{index}/from", "a branch cannot fork from itself."))
        elif source not in names and source not in ids:
            found.append(
                Violation(
                    f"/branches/{index}/from",
                    f"{source!r} is neither a branch ({known}) nor a commit's `id`.",
                )
            )
        else:
            sources[name] = source
    if found:
        return found

    # Replay the history, as git would make it.
    tips: dict[str, int] = {}
    ancestors: list[set[int]] = []
    for index, step in enumerate(steps):
        on = step.get("on")
        here = f"/steps/{index}"
        if not isinstance(on, str) or on not in names:
            found.append(Violation(f"{here}/on", f"{on!r} is not one of the branches: {known}."))
            return found
        parents: list[int] = []
        if on in tips:
            parents.append(tips[on])
        elif names[on] != 0:
            source = sources[on]
            if source in names:
                if source not in tips:
                    found.append(
                        Violation(
                            f"{here}/on",
                            f"{on!r} forks from {source!r} at its first commit, and {source!r} "
                            f"has no commit yet: commit on {source!r} first.",
                        )
                    )
                    return found
                parents.append(tips[source])
            else:
                if ids[source] >= index:
                    found.append(
                        Violation(
                            f"/branches/{names[on]}/from",
                            f"{on!r} forks from {source!r}, which is written after the "
                            f"branch's first commit (/steps/{index}): a branch can only fork "
                            f"from a commit that already exists.",
                        )
                    )
                    return found
                parents.append(ids[source])
            if "merge" in step:
                found.append(
                    Violation(
                        f"{here}/merge",
                        f"this is {on!r}'s first commit, so the merge would only fast-forward "
                        f"it: commit on {on!r} first, or merge into the branch it forks from.",
                    )
                )
                return found
        elif "merge" in step:
            found.append(
                Violation(
                    f"{here}/merge",
                    f"a merge needs a commit on {on!r} to merge into: commit on it first.",
                )
            )
            return found
        reach: set[int] = {index}
        for parent in parents:
            reach |= ancestors[parent]
        merged = step.get("merge")
        if isinstance(merged, str):
            if merged not in names:
                found.append(
                    Violation(f"{here}/merge", f"{merged!r} is not one of the branches: {known}.")
                )
                return found
            if merged == on:
                found.append(Violation(f"{here}/merge", f"a branch cannot merge itself ({on!r})."))
                return found
            if merged not in tips:
                found.append(
                    Violation(
                        f"{here}/merge",
                        f"{merged!r} has no commit yet, so there is nothing to merge.",
                    )
                )
                return found
            if tips[merged] in reach:
                found.append(
                    Violation(
                        f"{here}/merge",
                        f"everything on {merged!r} is already in {on!r}: the merge would make "
                        f"no change. Commit on {merged!r} first, or leave the merge out.",
                    )
                )
                return found
            reach |= ancestors[tips[merged]]
        picked = step.get("pick")
        if isinstance(picked, str):
            if picked not in ids:
                found.append(Violation(f"{here}/pick", f"{picked!r} is not any commit's `id`."))
                return found
            source_index = ids[picked]
            if source_index >= index:
                found.append(
                    Violation(
                        f"{here}/pick",
                        f"{picked!r} is written after this step: a cherry-pick copies a commit "
                        f"that already exists.",
                    )
                )
                return found
            if "merge" in steps[source_index]:
                found.append(
                    Violation(
                        f"{here}/pick",
                        f"{picked!r} is a merge commit, which git will not cherry-pick without "
                        f"choosing a side: pick one of the commits it merged.",
                    )
                )
                return found
            if source_index in reach:
                found.append(
                    Violation(
                        f"{here}/pick",
                        f"{picked!r} is already in {on!r}'s history: picking it changes nothing.",
                    )
                )
                return found
        ancestors.append(reach)
        tips[on] = index

    for name, index in names.items():
        if name not in tips:
            found.append(
                Violation(
                    f"/branches/{index}",
                    f"the branch {name!r} has no commit, so it has no lane to draw: commit on "
                    f"it, or leave it out (a name on a commit is a `tag`).",
                )
            )
    return found


def _gitgraph_document(document: Mapping[str, Any]) -> Document:
    """A git graph: its branches and its steps, in the order written."""
    return Document(
        kind=str(document["kind"]),
        title=str(document.get("title", "")),
        description=str(document.get("description", "")),
        caption=str(document.get("caption", "")),
        width=_optional_number(document.get("width")),
        height=_optional_number(document.get("height")),
        height_binding=bool(document.get("height_binding", False)),
        theme=str(document.get("theme", "")),
        git_branches=tuple(
            GitBranch(
                name=str(entry["name"]),
                source=str(entry.get("from", "")),
                role=str(entry.get("role", "step")),
            )
            for entry in document["branches"]
        ),
        git_steps=tuple(
            GitStep(
                on=str(entry["on"]),
                text=str(entry.get("text", "")),
                id=str(entry.get("id", "")),
                merge=str(entry.get("merge", "")),
                pick=str(entry.get("pick", "")),
                tag=str(entry.get("tag", "")),
                role=str(entry.get("role", "step")),
            )
            for entry in document["steps"]
        ),
        git_direction=str(document.get("direction", "right")),
    )
