"""Page interactions with the dashboard whose markup depends on the Archivematica release.

From 1.19 the transfer browser of the Transfer tab and the Transfer and Ingest
monitors are Vue applications. Earlier releases render the transfer browser
with AngularJS, its file tree with angular-tree-control, and the monitors with
Backbone, which confirms removals in jQuery UI dialogs and asks for the AtoM
slug of a DIP upload in a Bootstrap modal. :class:`DashboardUI` lists the
interactions the browser steps need, and :func:`dashboard_ui_for` returns the
implementation for the version the pipeline reports.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

from playwright.sync_api import Locator, Page, expect

# The first release whose transfer browser and monitors are Vue applications.
VUE_RELEASE = (1, 19)


class DashboardUI(ABC):
    """The transfer browser of the Transfer tab and the Transfer and Ingest monitors of one release."""

    def __init__(self, page: Page) -> None:
        self.page = page

    # Transfer browser --------------------------------------------------------------

    @abstractmethod
    def select_transfer_type(self, transfer_type: str) -> None:
        """Choose the transfer type by the value of its option, such as ``disk image``."""

    @abstractmethod
    def fill_transfer_name(self, name: str) -> None:
        """Type the name of the transfer."""

    @abstractmethod
    def open_file_browser(self) -> None:
        """Show the tree of the transfer source location."""

    @abstractmethod
    def select_tree_node(self, names: list[str]) -> None:
        """Expand the file browser down the path and leave the last node selected."""

    @abstractmethod
    def add_selected_node(self) -> None:
        """Add the selected node to the transfer as a component."""

    @abstractmethod
    def edit_component(self) -> None:
        """Open the metadata form of the transfer component, which opens in a new page."""

    @abstractmethod
    def open_processing_configurations(self) -> None:
        """Open the menu of processing configurations next to the Start transfer button."""

    @abstractmethod
    def processing_configurations(self) -> list[str]:
        """The entries of the open processing configuration menu, once it shows."""

    @abstractmethod
    def start_with_configuration(self, name: str) -> None:
        """Start the transfer from the open menu with the processing configuration ``name``."""

    # Monitors ----------------------------------------------------------------------

    @abstractmethod
    def remove_all_completed(self) -> None:
        """Ask the monitor to remove all its completed units."""

    @abstractmethod
    def removal_dialog(self) -> Locator:
        """The dialog that asks to confirm the removal of units, with a Confirm button."""

    @abstractmethod
    def dialog_title(self, text: str) -> str:
        """The title of a removal dialog, read from the inner text of :meth:`removal_dialog`."""

    @abstractmethod
    def show_jobs(self, row: Locator) -> None:
        """Show the jobs of the unit of a ``#sip-row-<uuid>`` row of the monitor."""

    @abstractmethod
    def decision_job(self, uuid: str, name: str) -> Locator:
        """The job ``name`` of the unit ``uuid`` that waits for a decision, among the jobs :meth:`show_jobs` shows.

        The job holds the select of the choices, labelled ``- <choice>``.
        """

    @abstractmethod
    def upload_dialog(self) -> Locator:
        """The dialog that asks for the slug of the AtoM description a DIP is uploaded to."""

    @abstractmethod
    def submit_upload_target(self, dialog: Locator, target: str) -> None:
        """Enter the slug of the target description in the upload dialog and submit it."""


class VueDashboardUI(DashboardUI):
    """The Vue transfer browser and monitors of Archivematica 1.19 and later."""

    def select_transfer_type(self, transfer_type: str) -> None:
        self.page.select_option("#transfer-type", transfer_type)

    def fill_transfer_name(self, name: str) -> None:
        self.page.fill("#transfer-name", name)

    def open_file_browser(self) -> None:
        self.page.get_by_text("Browse", exact=True).click()
        expect(self.page.get_by_label("Source location:")).to_be_visible()

    def select_tree_node(self, names: list[str]) -> None:
        for index, name in enumerate(names):
            content = self.page.locator(
                ".tree-node-content",
                has=self.page.locator(".transfer-node-name", has_text=re.compile(rf"^{re.escape(name)}$")),
            ).first
            expect(content).to_be_visible(timeout=30000)
            content.click()
            if index < len(names) - 1:
                node = content.locator("xpath=..")
                if node.get_attribute("aria-expanded") != "true":
                    content.press("ArrowRight")
                expect(node).to_have_attribute("aria-expanded", "true", timeout=30000)

    def add_selected_node(self) -> None:
        self.page.get_by_role("button", name=re.compile(r"^Add .* to transfer$")).click()

    def edit_component(self) -> None:
        self.page.get_by_role("button", name=re.compile(r"^Edit component: ")).click()

    def _menu(self) -> Locator:
        return self.page.locator("ul.dropdown-menu").filter(has=self.page.locator("a[role='menuitem']")).first

    def open_processing_configurations(self) -> None:
        self.page.get_by_role("button", name="Show processing configuration options").click()

    def processing_configurations(self) -> list[str]:
        menu = self._menu()
        expect(menu).to_be_visible()
        return [item.inner_text().strip() for item in menu.locator("a[role='menuitem']").all()]

    def start_with_configuration(self, name: str) -> None:
        self._menu().get_by_role("menuitem", name=f'Start with "{name}" configuration').click()

    def remove_all_completed(self) -> None:
        self.page.locator("a.monitor-remove-all").click()

    def removal_dialog(self) -> Locator:
        return self.page.locator(".modal").filter(has_text="Are you sure you want to remove").first

    def dialog_title(self, text: str) -> str:
        # The close button (x) comes before the title.
        lines = text.strip().splitlines()
        return lines[1] if len(lines) > 1 else text.strip()[:160]

    def show_jobs(self, row: Locator) -> None:
        row.locator(".sip-detail-directory").click()

    def decision_job(self, uuid: str, name: str) -> Locator:
        return self.page.locator(f"#sip-jobs-{uuid} .job", has_text=name).first

    def upload_dialog(self) -> Locator:
        return self.page.locator(".monitor-upload-modal")

    def submit_upload_target(self, dialog: Locator, target: str) -> None:
        dialog.locator("input[type='text']").fill(target)
        dialog.locator("button[type='submit']").click()


class AngularDashboardUI(DashboardUI):
    """The AngularJS transfer browser and the Backbone monitors of Archivematica 1.18 and earlier."""

    def _form(self) -> Locator:
        return self.page.locator("#transfer-browser-form")

    def select_transfer_type(self, transfer_type: str) -> None:
        self._form().locator("select[ng-model='vm.transfer.type']").select_option(transfer_type)

    def fill_transfer_name(self, name: str) -> None:
        self._form().locator("input[ng-model='vm.transfer.name']").fill(name)

    def open_file_browser(self) -> None:
        self.page.get_by_text("Browse", exact=True).click()
        expect(self.page.locator("#transfer_browse_tree")).to_be_visible()

    def select_tree_node(self, names: list[str]) -> None:
        # A node is an li classed tree-collapsed or tree-expanded, holding the
        # branch icon, the label and, once expanded, the children it fetches.
        # The label reads the name, followed by the number of objects in a
        # directory.
        tree = self.page.locator("#transfer_browse_tree")
        for index, name in enumerate(names):
            label = (
                tree.locator("div.tree-label")
                .filter(has_text=re.compile(rf"^\s*{re.escape(name)}\s*(\(.*\))?\s*$"))
                .first
            )
            expect(label).to_be_visible(timeout=30000)
            if index < len(names) - 1:
                node = label.locator("xpath=..")
                if "tree-collapsed" in (node.get_attribute("class") or "").split():
                    node.locator(":scope > i.tree-branch-head").click()
                expect(node).to_have_class(re.compile(r"(^|\s)tree-expanded(\s|$)"), timeout=30000)
                expect(node.locator(":scope > treeitem li").first).to_be_visible(timeout=30000)
            else:
                label.click()
                expect(label).to_have_class(re.compile(r"(^|\s)tree-selected(\s|$)"), timeout=30000)

    def add_selected_node(self) -> None:
        self.page.locator("#transfer_browse_tree button.btn-primary").click()

    def edit_component(self) -> None:
        # The editor is an unnamed icon next to the path of the component.
        self.page.locator("#path_container .transfer_path_edit_icon").click()

    def _menu(self) -> Locator:
        return self._form().locator("ul.dropdown-menu")

    def open_processing_configurations(self) -> None:
        # The only text of the toggle is its screen reader label, "Toggle Dropdown".
        self._form().locator("button.dropdown-toggle").click()

    def processing_configurations(self) -> list[str]:
        menu = self._menu()
        expect(menu).to_be_visible()
        return [item.inner_text().strip() for item in menu.locator("li.processing-config-choice a").all()]

    def start_with_configuration(self, name: str) -> None:
        entry = re.compile(rf'^\s*Start with "{re.escape(name)}" configuration\s*$')
        self._menu().locator("li.processing-config-choice a").filter(has_text=entry).click()

    def remove_all_completed(self) -> None:
        self.page.locator("#sip-header-actions a.btn_remove_all_sips").click()

    def removal_dialog(self) -> Locator:
        # jQuery UI appends every dialog to the page and keeps it, hidden, once closed.
        return self.page.locator("div.ui-dialog").filter(has_text="Are you sure you want to remove").last

    def dialog_title(self, text: str) -> str:
        # The title comes before the label of the close button.
        lines = text.strip().splitlines()
        return lines[0] if lines else ""

    def show_jobs(self, row: Locator) -> None:
        # Units render with their jobs shown, and a click on the directory hides them.
        unit = row.locator("xpath=..")
        if "sip-selected" not in (unit.get_attribute("class") or "").split():
            row.locator(".sip-detail-directory").click()

    def decision_job(self, uuid: str, name: str) -> Locator:
        # The jobs follow the row; only a job that waits for a decision has a select.
        jobs = self.page.locator(f"#sip-row-{uuid} + .sip-detail-job-container .job", has_text=name)
        return jobs.filter(has=self.page.locator("select")).first

    def upload_dialog(self) -> Locator:
        return self.page.locator("#upload-dip-modal")

    def submit_upload_target(self, dialog: Locator, target: str) -> None:
        dialog.locator("input[type='text']").fill(target)
        dialog.locator("a.btn-primary").click()


def _major_minor(version: str) -> tuple[int, int]:
    match = re.match(r"(\d+)\.(\d+)", version.strip())
    if match is None:
        raise ValueError(f"not an Archivematica version: {version!r}")
    return int(match.group(1)), int(match.group(2))


def dashboard_ui_for(page: Page, version: str) -> DashboardUI:
    """The interactions with the dashboard of the Archivematica ``version``, such as ``1.18.0``."""
    if _major_minor(version) >= VUE_RELEASE:
        return VueDashboardUI(page)
    return AngularDashboardUI(page)
