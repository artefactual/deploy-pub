"""Print the ``rt/pipeline/decisions.py`` module from one or more Archivematica workflows.

Usage: python tools/extract_decisions.py path/to/workflow.json [path/to/workflow.json ...] > rt/pipeline/decisions.py

Pass the MCPServer/assets/workflow.json of each supported Archivematica line,
oldest first: 1.17, 1.18 and then qa/1.x; the docstring of the printed module
names those lines. The decision points of the files are merged: a decision
has every link that bears its name in any of the files, and a link offers
every choice it has in any of them, in the order they are first read. When a
choice of a link leads to different targets, the target read first is kept
and a warning is printed to standard error.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import NotRequired, TypedDict


class Chain(TypedDict):
    description: dict[str, str]


class Replacement(TypedDict):
    id: str
    description: dict[str, str]


# The functional syntax allows the "@model" key.
LinkConfig = TypedDict(
    "LinkConfig",
    {"@model": str, "chain_choices": NotRequired[list[str]], "replacements": NotRequired[list[Replacement]]},
)


class Link(TypedDict):
    description: dict[str, str]
    config: LinkConfig


class Workflow(TypedDict):
    chains: dict[str, Chain]
    links: dict[str, Link]


def description(value: object) -> str:
    if isinstance(value, dict):
        return str(value.get("en", ""))
    return str(value)


def decision_points(workflow: Workflow) -> Iterator[tuple[str, str, list[tuple[str, str]]]]:
    """The name, link id and (choice, target id) pairs of each decision point of a workflow."""
    chains = workflow["chains"]
    for link_id, link in workflow["links"].items():
        config = link["config"]
        model = config.get("@model")
        if model == "MicroServiceChainChoice":
            choices = [
                (description(chains[chain_id]["description"]), chain_id)
                for chain_id in config["chain_choices"]
                if chain_id in chains
            ]
        elif model == "MicroServiceChoiceReplacementDic":
            choices = [
                (description(replacement["description"]), replacement["id"])
                for replacement in config["replacements"]
            ]
        else:
            continue
        yield description(link["description"]), link_id, choices


def merge(paths: list[Path]) -> dict[str, dict[str, dict[str, str]]]:
    """The choices of every link of every decision, by decision name and link id, both sorted."""
    names: dict[str, set[str]] = {}
    choices: dict[str, dict[str, str]] = {}
    for path in paths:
        workflow: Workflow = json.loads(path.read_text())
        for name, link_id, pairs in decision_points(workflow):
            names.setdefault(name, set()).add(link_id)
            link_choices = choices.setdefault(link_id, {})
            for choice, target in pairs:
                kept = link_choices.setdefault(choice, target)
                if kept != target:
                    print(
                        f"warning: {path}: choice {choice!r} of {name!r} (link {link_id}) leads to {target};"
                        f" keeping {kept}",
                        file=sys.stderr,
                    )
    return {name: {link_id: choices[link_id] for link_id in sorted(names[name])} for name in sorted(names)}


def main(paths: list[Path]) -> None:
    decisions = merge(paths)
    print('"""Decision points of the Archivematica workflow and the targets of their choices.')
    print()
    print("Generated from the MCPServer/assets/workflow.json of each supported Archivematica")
    print("line, 1.17, 1.18 and qa/1.x, merged by tools/extract_decisions.py; regenerate it")
    print("when one of those workflows changes or the supported lines change.")
    print('"""')
    print()
    print("from __future__ import annotations")
    print()
    print("from dataclasses import dataclass")
    print()
    print()
    print("@dataclass(frozen=True)")
    print("class Decision:")
    print("    link_id: str")
    print("    choices: dict[str, str]")
    print()
    print()
    print("DECISIONS: dict[str, tuple[Decision, ...]] = {")
    for name, links in decisions.items():
        print(f"    {name!r}: (")
        for link_id, choices in links.items():
            print("        Decision(")
            print(f"            {link_id!r},")
            print("            {")
            for choice, target in choices.items():
                print(f"                {choice!r}: {target!r},")
            print("            },")
            print("        ),")
        print("    ),")
    print("}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main([Path(argument) for argument in sys.argv[1:]])
