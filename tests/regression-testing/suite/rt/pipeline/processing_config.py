"""Processing configurations rendered per scenario from one of the pipeline's own files."""

from __future__ import annotations

from lxml import etree

from rt.pipeline.decisions import DECISIONS, Decision

VIRUS_SCANNING_DECISIONS = (
    "Do you want to scan for viruses in attachments?",
    "Do you want to scan for viruses in directories?",
    "Do you want to scan for viruses in extracted files?",
    "Do you want to scan for viruses in metadata?",
    "Do you want to scan for viruses in submission documentation?",
)


class UnknownDecision(KeyError):
    pass


class UnknownChoice(KeyError):
    pass


def config_name(item_id: str) -> str:
    """The processing configuration name of a checklist item (``\\w{1,16}`` in the dashboard URL)."""
    return "rt" + item_id.replace(".", "_")


class ProcessingConfig:
    def __init__(self, xml: str | bytes) -> None:
        data = xml.encode("utf-8") if isinstance(xml, str) else xml
        self._root = etree.fromstring(data)
        choices = self._root.find("preconfiguredChoices")
        if choices is None:
            choices = etree.SubElement(self._root, "preconfiguredChoices")
        self._choices = choices

    def targets(self) -> dict[str, str]:
        """The ``appliesTo`` to ``goToChain`` pairs currently in the file."""
        pairs: dict[str, str] = {}
        for choice in self._choices.findall("preconfiguredChoice"):
            applies_to = choice.findtext("appliesTo") or ""
            pairs[applies_to.strip()] = (choice.findtext("goToChain") or "").strip()
        return pairs

    def set_target(self, applies_to: str, go_to: str, comment: str | None = None) -> None:
        for choice in self._choices.findall("preconfiguredChoice"):
            if (choice.findtext("appliesTo") or "").strip() == applies_to:
                target = choice.find("goToChain")
                if target is None:
                    target = etree.SubElement(choice, "goToChain")
                target.text = go_to
                return
        if comment:
            self._choices.append(etree.Comment(f" {comment} "))
        choice = etree.SubElement(self._choices, "preconfiguredChoice")
        etree.SubElement(choice, "appliesTo").text = applies_to
        etree.SubElement(choice, "goToChain").text = go_to

    def remove(self, decision: str) -> None:
        link_ids = {entry.link_id for entry in self._decision(decision)}
        for choice in list(self._choices.findall("preconfiguredChoice")):
            if (choice.findtext("appliesTo") or "").strip() in link_ids:
                self._choices.remove(choice)

    def set(self, decision: str, choice: str) -> None:
        """Preconfigure a choice on every decision point of that name that offers it.

        Some decisions, such as Normalize, appear at several points of the workflow
        with different sets of choices; the points without the choice are left alone.
        """
        entries = self._decision(decision)
        offering = [entry for entry in entries if choice in entry.choices]
        if not offering:
            choices = sorted({name for entry in entries for name in entry.choices})
            raise UnknownChoice(f"{decision!r} has no choice {choice!r}; choices: {choices}")
        for entry in offering:
            self.set_target(entry.link_id, entry.choices[choice], comment=f"{decision}: {choice}")

    def set_virus_scanning(self, enabled: bool) -> None:
        for decision in VIRUS_SCANNING_DECISIONS:
            self.set(decision, "Yes" if enabled else "No")

    def to_xml(self) -> str:
        etree.indent(self._root, space="  ")
        return etree.tostring(self._root, encoding="unicode") + "\n"

    @staticmethod
    def _decision(decision: str) -> tuple[Decision, ...]:
        try:
            return DECISIONS[decision]
        except KeyError:
            raise UnknownDecision(f"unknown decision {decision!r}; known: {sorted(DECISIONS)}") from None
