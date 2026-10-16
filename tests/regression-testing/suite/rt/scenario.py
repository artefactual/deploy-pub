"""Per-scenario state shared between the Given and When steps."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ScenarioConfig:
    """The processing configuration a scenario writes before starting its transfer."""

    name: str
    base: str = "automated"
    choices: list[tuple[str, str]] = field(default_factory=list)
    # Decisions left without a preconfigured choice, so the unit waits for the user.
    removals: list[str] = field(default_factory=list)
    # Choices given as the decision point's link and the value it takes, for the
    # decisions whose choices are not chains, such as a storage location URI.
    targets: dict[str, str] = field(default_factory=dict)
