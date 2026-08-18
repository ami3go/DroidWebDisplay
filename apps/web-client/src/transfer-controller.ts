import { BridgeApi } from "./api.js";
import type { AndroidStorageEntryDto, DuplicatePolicy, TransferDto } from "./types.js";

interface TransferElements {
  readonly device: HTMLSelectElement;
  readonly contextUploadFile: HTMLInputElement;
  readonly customDestinationRow: HTMLElement;
  readonly customDestinationPath: HTMLInputElement;
  readonly duplicatePolicy: HTMLSelectElement;
  readonly storageRoot: HTMLSelectElement;
  readonly storagePath: HTMLInputElement;
  readonly storageBreadcrumbs: HTMLElement;
  readonly storageUp: HTMLButtonElement;
  readonly storageRefresh: HTMLButtonElement;
  readonly storageSelectAll: HTMLInputElement;
  readonly storageBody: HTMLElement;
  readonly contextMenu: HTMLElement;
  readonly contextOpen: HTMLButtonElement;
  readonly contextDownload: HTMLButtonElement;
  readonly contextUpload: HTMLButtonElement;
  readonly contextRefresh: HTMLButtonElement;
  readonly destinationProfile: HTMLSelectElement;
  readonly downloadSelected: HTMLButtonElement;
  readonly openPcFolder: HTMLButtonElement;
  readonly transferList: HTMLElement;
  readonly transferStatus: HTMLElement;
  readonly stage: HTMLElement;
  readonly stageDropOverlay: HTMLElement;
}

type StorageSortKey = "name" | "size" | "modified";
type SortDirection = "ascending" | "descending";

const ACTIVE_STATES = new Set(["queued", "preparing", "transferring", "verifying"]);
const EXPLORER_REFRESH_STALE_MS = 3000;
const RETRY_STATES = new Set(["cancelled", "failed", "interrupted"]);
let ANDROID_ROOTS: readonly string[] = ["/sdcard/Download", "/sdcard/Documents", "/sdcard/Pictures", "/sdcard/DCIM", "/sdcard/Movies"];

export class TransferController {
  readonly #api = new BridgeApi();
  #pollTimer: number | null = null;
  #lastTransfers: readonly TransferDto[] = [];
  #currentEntries: readonly AndroidStorageEntryDto[] = [];
  readonly #selectedDownloads = new Set<string>();
  #contextTarget: AndroidStorageEntryDto | null = null;
  #contextUploadDestination = "/sdcard/Download";
  #sortKey: StorageSortKey = "name";
  #sortDirection: SortDirection = "ascending";
  #lastSelectedIndex: number | null = null;
  #lastBrowseAt = 0;
  #browseGeneration = 0;
  #refreshTransfersBusy = false;
  // dragenter/dragleave fire for every child element under the pointer, so the
  // overlay is driven by a depth counter rather than by relatedTarget guesses.
  #stageDragDepth = 0;
  #closed = false;

  public constructor(private readonly elements: TransferElements) {
    this.bindEvents();
  }

  public async initialize(): Promise<void> {
    const [profiles, roots] = await Promise.all([this.#api.destinationProfiles(), this.#api.androidStorageRoots(this.elements.device.value || undefined)]);
    this.elements.destinationProfile.replaceChildren();
    for (const profile of profiles.profiles) {
      const option = document.createElement("option");
      option.value = profile.id;
      option.textContent = `${profile.id} · ${profile.path}`;
      this.elements.destinationProfile.append(option);
    }
    const custom = document.createElement("option");
    custom.value = "__custom__";
    custom.textContent = "Custom PC folder…";
    this.elements.destinationProfile.append(custom);
    const savedPath = localStorage.getItem("droidwebdisplay-custom-download-path-v1") ?? "";
    const savedDestination = localStorage.getItem("droidwebdisplay-download-destination-v1") ?? "";
    this.elements.customDestinationPath.value = savedPath;
    if ([...this.elements.destinationProfile.options].some((option) => option.value === savedDestination)) this.elements.destinationProfile.value = savedDestination;
    this.updateDestinationUi();
    this.elements.storageRoot.replaceChildren();
    ANDROID_ROOTS = roots.roots.map((root) => root.path);
    for (const root of roots.roots) {
      const rootOption = document.createElement("option");
      rootOption.value = root.path;
      rootOption.textContent = root.label;
      this.elements.storageRoot.append(rootOption);
    }
    this.elements.storageRoot.value = roots.defaultPath;
    await Promise.allSettled([this.browse(roots.defaultPath), this.refreshTransfers()]);
    this.scheduleTransferRefresh();
    document.addEventListener("visibilitychange", () => this.scheduleTransferRefresh(0));
  }

  public close(): void {
    this.#closed = true;
    this.#browseGeneration += 1;
    if (this.#pollTimer !== null) window.clearTimeout(this.#pollTimer);
    this.#pollTimer = null;
  }

  private bindEvents(): void {
    this.elements.device.addEventListener("change", () => void this.runAction(async () => { await this.refreshStorageRoots(); await this.browse(); }));
    this.elements.contextUploadFile.addEventListener("change", () => {
      if (!(this.elements.contextUploadFile.files?.length)) return;
      void this.runAction(() => this.uploadFiles(this.#contextUploadDestination, [...(this.elements.contextUploadFile.files ?? [])]));
    });
    this.elements.storageRefresh.addEventListener("click", () => void this.runAction(() => this.browse()));
    document.querySelector<HTMLButtonElement>('[data-group="files"]')?.addEventListener("click", () => {
      void this.runAction(() => this.refreshExplorerIfStale());
      this.scheduleTransferRefresh(0);
    });
    const explorerSection = document.querySelector<HTMLDetailsElement>('[data-section-key="files-explorer"]');
    explorerSection?.addEventListener("toggle", () => { if (explorerSection.open) void this.runAction(() => this.refreshExplorerIfStale()); });
    this.elements.storageUp.addEventListener("click", () => void this.runAction(() => this.browse(parentAndroidPath(this.elements.storagePath.value))));
    this.elements.storageSelectAll.addEventListener("change", () => {
      const files = this.#currentEntries.filter((entry) => !entry.isDirectory);
      if (this.elements.storageSelectAll.checked) {
        for (const entry of files) this.#selectedDownloads.add(entry.path);
      } else {
        for (const entry of files) this.#selectedDownloads.delete(entry.path);
      }
      this.updateSelectionUi();
    });
    this.elements.downloadSelected.addEventListener("click", () => void this.runAction(() => this.downloadSelected()));
    this.elements.destinationProfile.addEventListener("change", () => {
      localStorage.setItem("droidwebdisplay-download-destination-v1", this.elements.destinationProfile.value);
      this.updateDestinationUi();
    });
    this.elements.customDestinationPath.addEventListener("change", () => {
      localStorage.setItem("droidwebdisplay-custom-download-path-v1", this.elements.customDestinationPath.value.trim());
    });
    this.elements.openPcFolder.addEventListener("click", () => void this.runAction(async () => {
      const destination = this.downloadDestination();
      if (destination.destinationPath) await this.#api.openDestinationPath(destination.destinationPath);
      else await this.#api.openDestinationProfile(destination.destinationProfile);
      this.setStatus("Opened PC destination folder");
    }));
    this.elements.storageRoot.addEventListener("change", () => void this.runAction(() => this.browse(this.elements.storageRoot.value)));
    this.elements.storagePath.addEventListener("keydown", (event) => {
      if (event.key === "Enter") void this.runAction(() => this.browse());
    });
    this.bindStageDropZone();
    this.elements.storageBody.addEventListener("dragover", (event) => {
      if (!event.dataTransfer?.types.includes("Files")) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = "copy";
      this.clearDropTarget();
      const row = (event.target as Element | null)?.closest<HTMLElement>('.explorer-row[data-kind="folder"]');
      (row ?? this.elements.storageBody).classList.add("drop-target");
    });
    this.elements.storageBody.addEventListener("dragleave", (event) => {
      if (!this.elements.storageBody.contains(event.relatedTarget as Node | null)) this.clearDropTarget();
    });
    this.elements.storageBody.addEventListener("drop", (event) => {
      if (!event.dataTransfer?.files.length) return;
      event.preventDefault();
      const row = (event.target as Element | null)?.closest<HTMLElement>('.explorer-row[data-kind="folder"]');
      const destination = row?.dataset.path ?? this.elements.storagePath.value;
      const files = [...event.dataTransfer.files];
      this.clearDropTarget();
      void this.runAction(() => this.uploadFiles(destination, files));
    });
    this.elements.storageBody.addEventListener("click", (event) => {
      const target = event.target as Element | null;
      if (event.target === this.elements.storageBody) {
        this.clearSelection();
        return;
      }
      const row = target?.closest<HTMLElement>(".explorer-row[data-path]") ?? null;
      if (!row) return;
      if (target?.closest(".storage-select")) return;
      const entry = this.entryForRow(row);
      if (!entry) return;
      const menuButton = target?.closest<HTMLButtonElement>(".row-menu-button");
      if (menuButton) {
        event.stopPropagation();
        const rectangle = menuButton.getBoundingClientRect();
        this.prepareContextSelection(entry);
        this.showContextMenu(rectangle.right, rectangle.bottom, entry);
        return;
      }
      const index = Number.parseInt(row.dataset.index ?? "", 10);
      if (Number.isInteger(index)) this.handleRowSelection(entry, index, event);
    });
    this.elements.storageBody.addEventListener("change", (event) => {
      const selector = (event.target as Element | null)?.closest<HTMLInputElement>(".storage-select");
      const row = selector?.closest<HTMLElement>(".explorer-row[data-path]");
      const path = row?.dataset.path;
      if (selector && path) this.setFileSelected(path, selector.checked);
    });
    this.elements.storageBody.addEventListener("dblclick", (event) => {
      const target = event.target as Element | null;
      if (target?.closest(".storage-select, .row-menu-button")) return;
      const row = target?.closest<HTMLElement>(".explorer-row[data-path]") ?? null;
      const entry = this.entryForRow(row);
      if (!entry) return;
      void this.runAction(async () => {
        if (entry.isDirectory) await this.browse(entry.path);
        else await this.download(entry.path);
      });
    });
    this.elements.storageBody.addEventListener("contextmenu", (event) => {
      event.preventDefault();
      const row = (event.target as Element | null)?.closest<HTMLElement>(".explorer-row[data-path]") ?? null;
      const entry = this.entryForRow(row);
      if (entry) this.prepareContextSelection(entry);
      this.showContextMenu(event.clientX, event.clientY, entry);
    });
    this.elements.storageBody.addEventListener("keydown", (event) => {
      const row = (event.target as Element | null)?.closest<HTMLElement>(".explorer-row[data-path]") ?? null;
      if (!row || event.target !== row) return;
      const entry = this.entryForRow(row);
      if (!entry) return;
      if (event.key === "Enter") {
        event.preventDefault();
        void this.runAction(async () => {
          if (entry.isDirectory) await this.browse(entry.path);
          else await this.download(entry.path);
        });
      } else if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) {
        event.preventDefault();
        this.prepareContextSelection(entry);
        const rectangle = row.getBoundingClientRect();
        this.showContextMenu(rectangle.left + 32, rectangle.top + 24, entry);
      }
    });
    for (const button of document.querySelectorAll<HTMLButtonElement>("[data-storage-sort]")) {
      button.addEventListener("click", () => {
        const key = button.dataset.storageSort as StorageSortKey | undefined;
        if (!key) return;
        if (this.#sortKey === key) this.#sortDirection = this.#sortDirection === "ascending" ? "descending" : "ascending";
        else {
          this.#sortKey = key;
          this.#sortDirection = "ascending";
        }
        // The anchor indexes into the rendered order, which is about to
        // change; keeping it would make the next shift-click select rows the
        // user never clicked.
        this.#lastSelectedIndex = null;
        this.renderStorage(this.#currentEntries);
      });
    }
    this.elements.contextOpen.addEventListener("click", () => void this.runAction(async () => {
      const target = this.#contextTarget;
      this.hideContextMenu();
      if (target?.isDirectory) await this.browse(target.path);
    }));
    this.elements.contextDownload.addEventListener("click", () => void this.runAction(async () => {
      this.hideContextMenu();
      await this.downloadSelected();
    }));
    this.elements.contextUpload.addEventListener("click", () => {
      const target = this.#contextTarget;
      const destination = target?.isDirectory ? target.path : this.elements.storagePath.value;
      this.hideContextMenu();
      this.chooseUploadFiles(destination);
    });
    this.elements.contextRefresh.addEventListener("click", () => void this.runAction(async () => {
      this.hideContextMenu();
      await this.browse();
    }));
    document.addEventListener("pointerdown", (event) => {
      if (!this.elements.contextMenu.hidden && !this.elements.contextMenu.contains(event.target as Node)) this.hideContextMenu();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") this.hideContextMenu();
    });
    window.addEventListener("resize", () => this.hideContextMenu());
    window.addEventListener("scroll", () => this.hideContextMenu(), true);
  }

  private async refreshStorageRoots(): Promise<void> {
    const roots = await this.#api.androidStorageRoots(this.elements.device.value || undefined);
    const currentRoot = this.elements.storageRoot.value;
    this.elements.storageRoot.replaceChildren();
    for (const root of roots.roots) {
      const option = document.createElement("option");
      option.value = root.path;
      option.textContent = root.label;
      this.elements.storageRoot.append(option);
    }
    ANDROID_ROOTS = roots.roots.map((root) => root.path);
    this.elements.storageRoot.value = [...this.elements.storageRoot.options].some((item) => item.value === currentRoot) ? currentRoot : roots.defaultPath;
  }

  private async refreshExplorerIfStale(): Promise<void> {
    if (!this.elements.device.value) return;
    if (Date.now() - this.#lastBrowseAt < EXPLORER_REFRESH_STALE_MS) return;
    await this.browse();
  }

  private async browse(path = this.elements.storagePath.value || "/sdcard/Download"): Promise<void> {
    const generation = ++this.#browseGeneration;
    const serial = this.elements.device.value;
    if (!serial) {
      this.elements.storageBody.textContent = "Select an authorized Android device.";
      return;
    }
    this.hideContextMenu();
    this.setStatus("Reading Android storage…");
    const result = await this.#api.androidStorage(serial, path);
    if (generation !== this.#browseGeneration || this.elements.device.value !== serial) return;
    this.elements.storagePath.value = result.path;
    const root = ANDROID_ROOTS.find((candidate) => result.path === candidate || result.path.startsWith(`${candidate}/`));
    if (root && [...this.elements.storageRoot.options].some((option) => option.value === root)) this.elements.storageRoot.value = root;
    this.#currentEntries = result.entries;
    this.#selectedDownloads.clear();
    this.#lastSelectedIndex = null;
    this.renderBreadcrumbs(result.path);
    this.renderStorage(result.entries);
    this.#lastBrowseAt = Date.now();
    this.setStatus(`${result.entries.length} item(s) in ${result.path}`);
  }

  private renderBreadcrumbs(path: string): void {
    this.elements.storageBreadcrumbs.replaceChildren();
    for (const crumb of androidBreadcrumbs(path)) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "breadcrumb-button";
      button.textContent = crumb.label;
      button.title = crumb.path;
      button.addEventListener("click", () => void this.runAction(() => this.browse(crumb.path)));
      this.elements.storageBreadcrumbs.append(button);
      if (crumb.path !== path) {
        const separator = document.createElement("span");
        separator.className = "breadcrumb-separator";
        separator.textContent = "›";
        this.elements.storageBreadcrumbs.append(separator);
      }
    }
  }

  private renderStorage(entries: readonly AndroidStorageEntryDto[]): void {
    this.elements.storageBody.replaceChildren();
    const sorted = sortStorageEntries(entries, this.#sortKey, this.#sortDirection);
    this.updateSortHeaders();
    this.updateSelectionControls();
    if (!sorted.length) {
      const empty = document.createElement("div");
      empty.className = "explorer-empty";
      empty.innerHTML = "<strong>This folder is empty.</strong><span>Right-click here to upload files.</span>";
      this.elements.storageBody.append(empty);
      return;
    }

    sorted.forEach((entry, index) => {
      const row = document.createElement("div");
      row.className = "explorer-row";
      row.dataset.path = entry.path;
      row.dataset.kind = entry.isDirectory ? "folder" : "file";
      row.dataset.index = String(index);
      row.tabIndex = 0;
      row.setAttribute("role", "row");
      row.setAttribute("aria-selected", String(this.#selectedDownloads.has(entry.path)));
      if (this.#selectedDownloads.has(entry.path)) row.classList.add("selected");

      const selectorCell = document.createElement("div");
      selectorCell.className = "explorer-cell select-cell";
      const selector = document.createElement("input");
      selector.type = "checkbox";
      selector.className = "storage-select";
      selector.disabled = entry.isDirectory;
      selector.checked = this.#selectedDownloads.has(entry.path);
      selector.ariaLabel = `Select ${entry.name}`;
      selectorCell.append(selector);

      const nameCell = document.createElement("div");
      nameCell.className = "explorer-cell name-cell";
      const icon = document.createElement("span");
      icon.className = `file-icon ${entry.isDirectory ? "folder-icon" : "document-icon"}`;
      icon.textContent = entry.isDirectory ? "📁" : fileIcon(entry.name);
      const name = document.createElement("span");
      name.className = "file-name";
      name.textContent = entry.name;
      name.title = entry.name;
      nameCell.append(icon, name);

      const sizeCell = document.createElement("div");
      sizeCell.className = "explorer-cell size-cell";
      sizeCell.textContent = entry.isDirectory ? "" : formatBytes(entry.size);

      const modifiedCell = document.createElement("div");
      modifiedCell.className = "explorer-cell modified-cell";
      modifiedCell.textContent = formatDate(entry.modifiedAt);

      const menuCell = document.createElement("div");
      menuCell.className = "explorer-cell menu-cell";
      const menuButton = document.createElement("button");
      menuButton.type = "button";
      menuButton.className = "row-menu-button";
      menuButton.textContent = "⋯";
      menuButton.title = "Actions";
      menuCell.append(menuButton);

      row.append(selectorCell, nameCell, sizeCell, modifiedCell, menuCell);
      this.elements.storageBody.append(row);
    });
  }

  private entryForRow(row: HTMLElement | null): AndroidStorageEntryDto | null {
    const path = row?.dataset.path;
    if (!path) return null;
    return this.#currentEntries.find((entry) => entry.path === path) ?? null;
  }

  private handleRowSelection(entry: AndroidStorageEntryDto, index: number, event: MouseEvent): void {
    if (entry.isDirectory) {
      if (!event.ctrlKey && !event.metaKey) this.clearSelection();
      return;
    }
    if (event.shiftKey && this.#lastSelectedIndex !== null) {
      const sorted = sortStorageEntries(this.#currentEntries, this.#sortKey, this.#sortDirection);
      const start = Math.min(this.#lastSelectedIndex, index);
      const end = Math.max(this.#lastSelectedIndex, index);
      if (!event.ctrlKey && !event.metaKey) this.#selectedDownloads.clear();
      for (const candidate of sorted.slice(start, end + 1)) {
        if (!candidate.isDirectory) this.#selectedDownloads.add(candidate.path);
      }
    } else if (event.ctrlKey || event.metaKey) {
      if (this.#selectedDownloads.has(entry.path)) this.#selectedDownloads.delete(entry.path);
      else this.#selectedDownloads.add(entry.path);
    } else {
      this.#selectedDownloads.clear();
      this.#selectedDownloads.add(entry.path);
    }
    this.#lastSelectedIndex = index;
    this.updateSelectionUi();
  }

  private prepareContextSelection(entry: AndroidStorageEntryDto): void {
    if (!entry.isDirectory && !this.#selectedDownloads.has(entry.path)) {
      this.#selectedDownloads.clear();
      this.#selectedDownloads.add(entry.path);
      this.updateSelectionUi();
    }
  }

  private setFileSelected(path: string, selected: boolean): void {
    if (selected) this.#selectedDownloads.add(path);
    else this.#selectedDownloads.delete(path);
    this.updateSelectionUi();
  }

  private clearSelection(): void {
    if (!this.#selectedDownloads.size) return;
    this.#selectedDownloads.clear();
    this.#lastSelectedIndex = null;
    this.updateSelectionUi();
  }

  private updateSelectionUi(): void {
    for (const row of this.elements.storageBody.querySelectorAll<HTMLElement>(".explorer-row[data-path]")) {
      const path = row.dataset.path ?? "";
      const selected = this.#selectedDownloads.has(path);
      row.classList.toggle("selected", selected);
      row.setAttribute("aria-selected", String(selected));
      const checkbox = row.querySelector<HTMLInputElement>(".storage-select");
      if (checkbox) checkbox.checked = selected;
    }
    this.updateSelectionControls();
  }

  private updateSelectionControls(): void {
    const fileEntries = this.#currentEntries.filter((entry) => !entry.isDirectory);
    const selectedCount = fileEntries.filter((entry) => this.#selectedDownloads.has(entry.path)).length;
    this.elements.storageSelectAll.checked = fileEntries.length > 0 && selectedCount === fileEntries.length;
    this.elements.storageSelectAll.indeterminate = selectedCount > 0 && selectedCount < fileEntries.length;
    this.elements.downloadSelected.disabled = selectedCount === 0;
    this.elements.downloadSelected.textContent = selectedCount > 0 ? `Download (${selectedCount})` : "Download";
  }

  private updateSortHeaders(): void {
    for (const button of document.querySelectorAll<HTMLButtonElement>("[data-storage-sort]")) {
      const active = button.dataset.storageSort === this.#sortKey;
      button.classList.toggle("active", active);
      button.setAttribute("aria-sort", active ? this.#sortDirection : "none");
      const label = button.dataset.label ?? button.textContent?.replace(/[▲▼]/g, "").trim() ?? "";
      button.dataset.label = label;
      this.setSortHeaderLabel(button, active ? `${label} ${this.#sortDirection === "ascending" ? "▲" : "▼"}` : label);
    }
  }

  private setSortHeaderLabel(button: HTMLButtonElement, text: string): void {
    // The label lives in its own span so the column resizer the drawer appends
    // to these buttons is a sibling, not something this write has to preserve.
    const target = button.querySelector<HTMLElement>(".explorer-header-text") ?? button;
    target.textContent = text;
  }

  private showContextMenu(clientX: number, clientY: number, target: AndroidStorageEntryDto | null): void {
    this.#contextTarget = target;
    this.elements.contextOpen.hidden = !target?.isDirectory;
    const selectedCount = this.#selectedDownloads.size;
    this.elements.contextDownload.hidden = target?.isDirectory === true || selectedCount === 0;
    this.elements.contextDownload.textContent = selectedCount > 1 ? `Download ${selectedCount} selected` : "Download";
    this.elements.contextUpload.textContent = target?.isDirectory ? `Upload into “${target.name}”` : "Upload to current folder";
    this.elements.contextMenu.hidden = false;
    this.elements.contextMenu.style.left = "0px";
    this.elements.contextMenu.style.top = "0px";
    const rectangle = this.elements.contextMenu.getBoundingClientRect();
    const left = Math.max(8, Math.min(clientX, window.innerWidth - rectangle.width - 8));
    const top = Math.max(8, Math.min(clientY, window.innerHeight - rectangle.height - 8));
    this.elements.contextMenu.style.left = `${left}px`;
    this.elements.contextMenu.style.top = `${top}px`;
    this.elements.contextMenu.focus();
  }

  private hideContextMenu(): void {
    this.elements.contextMenu.hidden = true;
    this.#contextTarget = null;
  }

  /** Drop files anywhere on the mirrored screen to send them to the Android inbox.

      The Explorer already accepts drops, but only inside the Files drawer, which
      means navigating there first. The stage is where the user is already
      looking, so it doubles as a zero-navigation upload target. */
  private bindStageDropZone(): void {
    const { stage } = this.elements;
    stage.addEventListener("dragenter", (event) => {
      if (!hasFiles(event.dataTransfer)) return;
      event.preventDefault();
      this.#stageDragDepth += 1;
      this.setStageDropActive(true);
    });
    stage.addEventListener("dragover", (event) => {
      if (!hasFiles(event.dataTransfer)) return;
      // Without preventDefault the browser navigates to the dropped file.
      event.preventDefault();
      event.dataTransfer!.dropEffect = "copy";
    });
    stage.addEventListener("dragleave", (event) => {
      if (!hasFiles(event.dataTransfer)) return;
      this.#stageDragDepth = Math.max(0, this.#stageDragDepth - 1);
      if (this.#stageDragDepth === 0) this.setStageDropActive(false);
    });
    stage.addEventListener("drop", (event) => {
      if (!hasFiles(event.dataTransfer)) return;
      event.preventDefault();
      this.#stageDragDepth = 0;
      this.setStageDropActive(false);
      const files = [...(event.dataTransfer?.files ?? [])];
      if (!files.length) return;
      void this.runAction(() => this.uploadToInbox(files));
    });
  }

  private setStageDropActive(active: boolean): void {
    this.elements.stage.classList.toggle("stage-drop-active", active);
    this.elements.stageDropOverlay.hidden = !active;
  }

  /** Upload to the server's configured inbox directory.

      destinationPath is deliberately omitted so the server's
      default_android_upload_directory stays the single source of truth. */
  private async uploadToInbox(files: readonly File[]): Promise<void> {
    await this.uploadFiles(undefined, files);
  }

  private clearDropTarget(): void {
    this.elements.storageBody.classList.remove("drop-target");
    for (const row of this.elements.storageBody.querySelectorAll(".drop-target")) row.classList.remove("drop-target");
  }

  private chooseUploadFiles(destination: string): void {
    this.#contextUploadDestination = destination;
    this.elements.contextUploadFile.value = "";
    this.elements.contextUploadFile.click();
  }

  private async uploadFiles(destinationPath: string | undefined, files: readonly File[]): Promise<void> {
    const serial = this.requireSerial();
    if (!files.length) throw new Error("Choose one or more PC files to upload");
    let queuedTo = destinationPath;
    for (const file of files) {
      const record = await this.#api.uploadFile({
        serial,
        file,
        destinationPath,
        duplicatePolicy: this.duplicatePolicy(),
      });
      // When the server picked the destination, report what it actually chose
      // rather than a path the client guessed.
      queuedTo ??= androidParentPath(record.destinationPath);
    }
    this.elements.contextUploadFile.value = "";
    await this.refreshTransfers();
    this.setStatus(`Queued ${files.length} upload(s) to ${queuedTo ?? "the Android inbox"}`);
  }

  private updateDestinationUi(): void {
    const custom = this.elements.destinationProfile.value === "__custom__";
    this.elements.customDestinationRow.hidden = !custom;
  }

  private downloadDestination(): { destinationProfile: string; destinationPath?: string } {
    if (this.elements.destinationProfile.value !== "__custom__") return { destinationProfile: this.elements.destinationProfile.value };
    const destinationPath = this.elements.customDestinationPath.value.trim();
    if (!destinationPath) throw new Error("Enter an absolute PC destination folder path");
    localStorage.setItem("droidwebdisplay-custom-download-path-v1", destinationPath);
    return { destinationProfile: "default-downloads", destinationPath };
  }

  private async download(sourcePath: string): Promise<void> {
    const serial = this.requireSerial();
    const destination = this.downloadDestination();
    await this.#api.downloadFile({
      serial,
      sourcePath,
      ...destination,
      duplicatePolicy: this.duplicatePolicy(),
    });
    await this.refreshTransfers();
    this.setStatus(`Queued download: ${sourcePath.split("/").at(-1) ?? sourcePath}`);
  }

  private async downloadSelected(): Promise<void> {
    if (!this.#selectedDownloads.size) throw new Error("Select one or more Android files");
    const selected = [...this.#selectedDownloads];
    for (const path of selected) await this.download(path);
    this.#selectedDownloads.clear();
    this.#lastSelectedIndex = null;
    this.updateSelectionUi();
    this.setStatus(`Queued ${selected.length} download(s)`);
  }

  private filesDrawerVisible(): boolean {
    return document.visibilityState === "visible"
      && document.querySelector('.gb-drawer')?.classList.contains("gb-open") === true
      && document.querySelector('.gb-drawer-slot[data-slot="files"]')?.classList.contains("gb-active") === true;
  }

  private transferRefreshDelay(): number {
    if (document.visibilityState !== "visible") return 10_000;
    if (this.#lastTransfers.some((transfer) => ACTIVE_STATES.has(transfer.state))) return 750;
    return this.filesDrawerVisible() ? 2500 : 8000;
  }

  private scheduleTransferRefresh(delay = this.transferRefreshDelay()): void {
    if (this.#closed) return;
    if (this.#pollTimer !== null) window.clearTimeout(this.#pollTimer);
    this.#pollTimer = window.setTimeout(() => {
      this.#pollTimer = null;
      void this.refreshTransfers().finally(() => this.scheduleTransferRefresh());
    }, Math.max(0, delay));
  }

  private async refreshTransfers(): Promise<void> {
    if (this.#refreshTransfersBusy) return;
    this.#refreshTransfersBusy = true;
    try {
      const response = await this.#api.transfers();
      this.#lastTransfers = response.transfers;
      this.renderTransfers(response.transfers);
    } catch (error) {
      this.setStatus(errorMessage(error), true);
    } finally {
      this.#refreshTransfersBusy = false;
    }
  }

  private renderTransfers(transfers: readonly TransferDto[]): void {
    this.elements.transferList.replaceChildren();
    if (!transfers.length) {
      const empty = document.createElement("p");
      empty.className = "empty-state";
      empty.textContent = "No transfers yet.";
      this.elements.transferList.append(empty);
      return;
    }
    for (const transfer of transfers.slice(0, 30)) {
      const card = document.createElement("div");
      card.className = `transfer-row state-${transfer.state}`;
      const header = document.createElement("div");
      header.className = "transfer-header";
      const title = document.createElement("strong");
      title.textContent = `${transfer.direction === "upload" ? "↑" : "↓"} ${transfer.filename}`;
      const state = document.createElement("span");
      state.className = "transfer-state";
      state.textContent = transfer.state;
      header.append(title, state);
      const progress = document.createElement("progress");
      progress.max = 1;
      progress.value = transfer.progress ?? (transfer.state === "completed" ? 1 : 0);
      const detail = document.createElement("small");
      detail.textContent = transferDetail(transfer);
      card.append(header, progress, detail);
      if (transfer.error) {
        const error = document.createElement("small");
        error.className = "transfer-error";
        error.textContent = transfer.error;
        card.append(error);
      }
      if (ACTIVE_STATES.has(transfer.state)) {
        const cancel = document.createElement("button");
        cancel.className = "danger compact";
        cancel.textContent = "Cancel";
        cancel.addEventListener("click", () => void this.runAction(async () => {
          await this.#api.cancelTransfer(transfer.transferId);
          await this.refreshTransfers();
        }));
        card.append(cancel);
      } else if (RETRY_STATES.has(transfer.state)) {
        const retry = document.createElement("button");
        retry.className = "secondary compact";
        retry.textContent = "Retry";
        retry.addEventListener("click", () => void this.runAction(async () => {
          await this.#api.retryTransfer(transfer.transferId);
          await this.refreshTransfers();
        }));
        card.append(retry);
      }
      this.elements.transferList.append(card);
    }
  }

  private duplicatePolicy(): DuplicatePolicy {
    return this.elements.duplicatePolicy.value as DuplicatePolicy;
  }

  private requireSerial(): string {
    const serial = this.elements.device.value;
    if (!serial) throw new Error("Select an authorized Android device");
    return serial;
  }

  private async runAction(action: () => Promise<void>): Promise<void> {
    try {
      await action();
    } catch (error) {
      this.setStatus(errorMessage(error), true);
    }
  }

  private setStatus(message: string, error = false): void {
    this.elements.transferStatus.textContent = message;
    this.elements.transferStatus.classList.toggle("error-text", error);
  }
}

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KiB", "MiB", "GiB", "TiB"];
  let value = bytes / 1024;
  let unit = units[0]!;
  for (let index = 1; index < units.length && value >= 1024; index += 1) {
    value /= 1024;
    unit = units[index]!;
  }
  return `${value.toFixed(value >= 10 ? 1 : 2)} ${unit}`;
}

/** True when a drag actually carries files, not text or a page selection. */
function hasFiles(data: DataTransfer | null): boolean {
  return Boolean(data?.types.includes("Files"));
}

/** Plain containing directory of an Android path.

    Unlike parentAndroidPath this does not clamp to a known shared root, because
    it is used to report where the server put an upload, which may sit outside
    the roots the Explorer offers. */
function androidParentPath(path: string): string {
  const parent = path.replace(/\/+$/, "").split("/").slice(0, -1).join("/");
  return parent || "/";
}

export function parentAndroidPath(path: string): string {
  const root = androidRootForPath(path);
  if (!root || path === root) return root ?? "/sdcard/Download";
  const parent = path.replace(/\/+$/, "").split("/").slice(0, -1).join("/") || root;
  return parent.length < root.length ? root : parent;
}

export function androidBreadcrumbs(path: string): readonly { label: string; path: string }[] {
  const root = androidRootForPath(path) ?? "/sdcard/Download";
  const crumbs: { label: string; path: string }[] = [{ label: root.split("/").at(-1) ?? root, path: root }];
  const relative = path.slice(root.length).split("/").filter(Boolean);
  let current = root;
  for (const part of relative) {
    current = `${current}/${part}`;
    crumbs.push({ label: part, path: current });
  }
  return crumbs;
}

export function sortStorageEntries(
  entries: readonly AndroidStorageEntryDto[],
  key: StorageSortKey,
  direction: SortDirection,
): readonly AndroidStorageEntryDto[] {
  const multiplier = direction === "ascending" ? 1 : -1;
  return [...entries].sort((left, right) => {
    if (left.isDirectory !== right.isDirectory) return left.isDirectory ? -1 : 1;
    let comparison: number;
    if (key === "size") comparison = left.size - right.size;
    else if (key === "modified") comparison = left.modifiedAt - right.modifiedAt;
    else comparison = left.name.localeCompare(right.name, undefined, { numeric: true, sensitivity: "base" });
    if (comparison === 0) comparison = left.name.localeCompare(right.name, undefined, { numeric: true, sensitivity: "base" });
    return comparison * multiplier;
  });
}

function androidRootForPath(path: string): string | null {
  const normalized = path.replace(/\/+$/, "") || path;
  return ANDROID_ROOTS.find((root) => normalized === root || normalized.startsWith(`${root}/`)) ?? null;
}

function fileIcon(name: string): string {
  const extension = name.split(".").at(-1)?.toLowerCase() ?? "";
  if (["jpg", "jpeg", "png", "gif", "webp", "heic"].includes(extension)) return "🖼️";
  if (["mp4", "mkv", "webm", "mov"].includes(extension)) return "🎬";
  if (["pdf"].includes(extension)) return "📕";
  if (["zip", "7z", "rar", "tar", "gz"].includes(extension)) return "🗜️";
  if (["txt", "md", "log", "csv", "json", "xml"].includes(extension)) return "📝";
  return "📄";
}

function transferDetail(transfer: TransferDto): string {
  const total = transfer.size === null ? "unknown" : formatBytes(transfer.size);
  const completed = formatBytes(transfer.bytesTransferred);
  const speed = transfer.speedBytesPerSecond > 0 ? ` · ${formatBytes(transfer.speedBytesPerSecond)}/s` : "";
  return `${completed} / ${total}${speed}${transfer.verification ? ` · ${transfer.verification}` : ""}`;
}

function formatDate(timestamp: number): string {
  if (!timestamp) return "—";
  return new Date(timestamp * 1000).toLocaleString([], { dateStyle: "short", timeStyle: "short" });
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function downloadJson(filename: string, payload: unknown): void {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const anchor = document.createElement("a");
  anchor.href = URL.createObjectURL(blob);
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(anchor.href);
}
