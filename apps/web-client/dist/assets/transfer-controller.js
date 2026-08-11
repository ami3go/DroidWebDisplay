import { BridgeApi } from "./api.js";
const ACTIVE_STATES = new Set(["queued", "preparing", "transferring", "verifying"]);
const RETRY_STATES = new Set(["cancelled", "failed", "interrupted"]);
let ANDROID_ROOTS = ["/sdcard/Download", "/sdcard/Documents", "/sdcard/Pictures", "/sdcard/DCIM", "/sdcard/Movies"];
export class TransferController {
    elements;
    #api = new BridgeApi();
    #pollTimer = null;
    #lastTransfers = [];
    #currentEntries = [];
    #selectedDownloads = new Set();
    #contextTarget = null;
    #contextUploadDestination = "/sdcard/Download";
    #sortKey = "name";
    #sortDirection = "ascending";
    #lastSelectedIndex = null;
    constructor(elements) {
        this.elements = elements;
        this.bindEvents();
    }
    async initialize() {
        const [profiles, roots] = await Promise.all([this.#api.destinationProfiles(), this.#api.androidStorageRoots(this.elements.device.value || undefined)]);
        this.elements.destinationProfile.replaceChildren();
        for (const profile of profiles.profiles) {
            const option = document.createElement("option");
            option.value = profile.id;
            option.textContent = `${profile.id} · ${profile.path}`;
            this.elements.destinationProfile.append(option);
        }
        this.elements.storageRoot.replaceChildren();
        ANDROID_ROOTS = roots.roots.map((root) => root.path);
        const currentUpload = this.elements.uploadDirectory.value;
        this.elements.uploadDirectory.replaceChildren();
        const inbox = document.createElement("option");
        inbox.value = "/sdcard/Download/GptBridgeInbox";
        inbox.textContent = "Internal storage · Download · GptBridgeInbox";
        this.elements.uploadDirectory.append(inbox);
        for (const root of roots.roots) {
            const rootOption = document.createElement("option");
            rootOption.value = root.path;
            rootOption.textContent = root.label;
            this.elements.storageRoot.append(rootOption);
            const uploadOption = document.createElement("option");
            uploadOption.value = root.path;
            uploadOption.textContent = root.label;
            this.elements.uploadDirectory.append(uploadOption);
        }
        if ([...this.elements.uploadDirectory.options].some((option) => option.value === currentUpload))
            this.elements.uploadDirectory.value = currentUpload;
        this.elements.storageRoot.value = roots.defaultPath;
        await Promise.allSettled([this.browse(roots.defaultPath), this.refreshTransfers()]);
        this.#pollTimer = window.setInterval(() => void this.refreshTransfers(), 750);
    }
    bindEvents() {
        this.elements.device.addEventListener("change", () => void this.runAction(async () => { await this.refreshStorageRoots(); await this.browse(); }));
        this.elements.upload.addEventListener("click", () => void this.runAction(() => this.uploadFiles(this.elements.uploadDirectory.value, this.elements.file)));
        this.elements.contextUploadFile.addEventListener("change", () => {
            if (!(this.elements.contextUploadFile.files?.length))
                return;
            void this.runAction(() => this.uploadFiles(this.#contextUploadDestination, this.elements.contextUploadFile));
        });
        this.elements.openUploadFolder.addEventListener("click", () => void this.runAction(() => this.browse(this.elements.uploadDirectory.value)));
        this.elements.storageRefresh.addEventListener("click", () => void this.runAction(() => this.browse()));
        this.elements.storageUp.addEventListener("click", () => void this.runAction(() => this.browse(parentAndroidPath(this.elements.storagePath.value))));
        this.elements.storageSelectAll.addEventListener("change", () => {
            const files = this.#currentEntries.filter((entry) => !entry.isDirectory);
            if (this.elements.storageSelectAll.checked) {
                for (const entry of files)
                    this.#selectedDownloads.add(entry.path);
            }
            else {
                for (const entry of files)
                    this.#selectedDownloads.delete(entry.path);
            }
            this.renderStorage(this.#currentEntries);
        });
        this.elements.downloadSelected.addEventListener("click", () => void this.runAction(() => this.downloadSelected()));
        this.elements.openPcFolder.addEventListener("click", () => void this.runAction(async () => {
            await this.#api.openDestinationProfile(this.elements.destinationProfile.value);
            this.setStatus("Opened PC destination folder");
        }));
        this.elements.storageRoot.addEventListener("change", () => void this.runAction(() => this.browse(this.elements.storageRoot.value)));
        this.elements.storagePath.addEventListener("keydown", (event) => {
            if (event.key === "Enter")
                void this.runAction(() => this.browse());
        });
        this.elements.storageBody.addEventListener("click", (event) => {
            if (event.target === this.elements.storageBody)
                this.clearSelection();
        });
        this.elements.storageBody.addEventListener("contextmenu", (event) => {
            if (event.target !== this.elements.storageBody)
                return;
            event.preventDefault();
            this.showContextMenu(event.clientX, event.clientY, null);
        });
        for (const button of document.querySelectorAll("[data-storage-sort]")) {
            button.addEventListener("click", () => {
                const key = button.dataset.storageSort;
                if (!key)
                    return;
                if (this.#sortKey === key)
                    this.#sortDirection = this.#sortDirection === "ascending" ? "descending" : "ascending";
                else {
                    this.#sortKey = key;
                    this.#sortDirection = "ascending";
                }
                this.renderStorage(this.#currentEntries);
            });
        }
        this.elements.contextOpen.addEventListener("click", () => void this.runAction(async () => {
            const target = this.#contextTarget;
            this.hideContextMenu();
            if (target?.isDirectory)
                await this.browse(target.path);
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
            if (!this.elements.contextMenu.hidden && !this.elements.contextMenu.contains(event.target))
                this.hideContextMenu();
        });
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape")
                this.hideContextMenu();
        });
        window.addEventListener("resize", () => this.hideContextMenu());
        window.addEventListener("scroll", () => this.hideContextMenu(), true);
    }
    async refreshStorageRoots() {
        const roots = await this.#api.androidStorageRoots(this.elements.device.value || undefined);
        const currentRoot = this.elements.storageRoot.value;
        this.elements.storageRoot.replaceChildren();
        const currentUpload = this.elements.uploadDirectory.value;
        this.elements.uploadDirectory.replaceChildren();
        const inbox = document.createElement("option");
        inbox.value = "/sdcard/Download/GptBridgeInbox";
        inbox.textContent = "Internal storage · Download · GptBridgeInbox";
        this.elements.uploadDirectory.append(inbox);
        for (const root of roots.roots) {
            const option = document.createElement("option");
            option.value = root.path;
            option.textContent = root.label;
            this.elements.storageRoot.append(option);
            const upload = document.createElement("option");
            upload.value = root.path;
            upload.textContent = root.label;
            this.elements.uploadDirectory.append(upload);
        }
        ANDROID_ROOTS = roots.roots.map((root) => root.path);
        this.elements.storageRoot.value = [...this.elements.storageRoot.options].some((item) => item.value === currentRoot) ? currentRoot : roots.defaultPath;
        this.elements.uploadDirectory.value = [...this.elements.uploadDirectory.options].some((item) => item.value === currentUpload) ? currentUpload : inbox.value;
    }
    async browse(path = this.elements.storagePath.value || "/sdcard/Download") {
        const serial = this.elements.device.value;
        if (!serial) {
            this.elements.storageBody.textContent = "Select an authorized Android device.";
            return;
        }
        this.hideContextMenu();
        this.setStatus("Reading Android storage…");
        const result = await this.#api.androidStorage(serial, path);
        this.elements.storagePath.value = result.path;
        const root = ANDROID_ROOTS.find((candidate) => result.path === candidate || result.path.startsWith(`${candidate}/`));
        if (root && [...this.elements.storageRoot.options].some((option) => option.value === root))
            this.elements.storageRoot.value = root;
        this.#currentEntries = result.entries;
        this.#selectedDownloads.clear();
        this.#lastSelectedIndex = null;
        this.renderBreadcrumbs(result.path);
        this.renderStorage(result.entries);
        this.setStatus(`${result.entries.length} item(s) in ${result.path}`);
    }
    renderBreadcrumbs(path) {
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
    renderStorage(entries) {
        this.elements.storageBody.replaceChildren();
        const sorted = sortStorageEntries(entries, this.#sortKey, this.#sortDirection);
        this.updateSortHeaders();
        this.updateSelectionControls();
        if (!sorted.length) {
            const empty = document.createElement("div");
            empty.className = "explorer-empty";
            empty.innerHTML = "<strong>This folder is empty.</strong><span>Right-click here to upload files.</span>";
            empty.addEventListener("contextmenu", (event) => {
                event.preventDefault();
                this.showContextMenu(event.clientX, event.clientY, null);
            });
            this.elements.storageBody.append(empty);
            return;
        }
        sorted.forEach((entry, index) => {
            const row = document.createElement("div");
            row.className = "explorer-row";
            row.dataset.path = entry.path;
            row.dataset.kind = entry.isDirectory ? "folder" : "file";
            row.tabIndex = 0;
            row.setAttribute("role", "row");
            row.setAttribute("aria-selected", String(this.#selectedDownloads.has(entry.path)));
            if (this.#selectedDownloads.has(entry.path))
                row.classList.add("selected");
            const selectorCell = document.createElement("div");
            selectorCell.className = "explorer-cell select-cell";
            const selector = document.createElement("input");
            selector.type = "checkbox";
            selector.className = "storage-select";
            selector.disabled = entry.isDirectory;
            selector.checked = this.#selectedDownloads.has(entry.path);
            selector.ariaLabel = `Select ${entry.name}`;
            selector.addEventListener("click", (event) => event.stopPropagation());
            selector.addEventListener("change", () => this.setFileSelected(entry.path, selector.checked));
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
            menuButton.addEventListener("click", (event) => {
                event.stopPropagation();
                const rectangle = menuButton.getBoundingClientRect();
                this.prepareContextSelection(entry);
                this.showContextMenu(rectangle.right, rectangle.bottom, entry);
            });
            menuCell.append(menuButton);
            row.append(selectorCell, nameCell, sizeCell, modifiedCell, menuCell);
            row.addEventListener("click", (event) => this.handleRowSelection(entry, index, event));
            row.addEventListener("dblclick", () => void this.runAction(async () => {
                if (entry.isDirectory)
                    await this.browse(entry.path);
                else
                    await this.download(entry.path);
            }));
            row.addEventListener("contextmenu", (event) => {
                event.preventDefault();
                this.prepareContextSelection(entry);
                this.showContextMenu(event.clientX, event.clientY, entry);
            });
            row.addEventListener("keydown", (event) => {
                if (event.key === "Enter") {
                    event.preventDefault();
                    void this.runAction(async () => {
                        if (entry.isDirectory)
                            await this.browse(entry.path);
                        else
                            await this.download(entry.path);
                    });
                }
                else if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) {
                    event.preventDefault();
                    this.prepareContextSelection(entry);
                    const rectangle = row.getBoundingClientRect();
                    this.showContextMenu(rectangle.left + 32, rectangle.top + 24, entry);
                }
            });
            this.elements.storageBody.append(row);
        });
    }
    handleRowSelection(entry, index, event) {
        if (entry.isDirectory) {
            if (!event.ctrlKey && !event.metaKey)
                this.clearSelection();
            return;
        }
        if (event.shiftKey && this.#lastSelectedIndex !== null) {
            const sorted = sortStorageEntries(this.#currentEntries, this.#sortKey, this.#sortDirection);
            const start = Math.min(this.#lastSelectedIndex, index);
            const end = Math.max(this.#lastSelectedIndex, index);
            if (!event.ctrlKey && !event.metaKey)
                this.#selectedDownloads.clear();
            for (const candidate of sorted.slice(start, end + 1)) {
                if (!candidate.isDirectory)
                    this.#selectedDownloads.add(candidate.path);
            }
        }
        else if (event.ctrlKey || event.metaKey) {
            if (this.#selectedDownloads.has(entry.path))
                this.#selectedDownloads.delete(entry.path);
            else
                this.#selectedDownloads.add(entry.path);
        }
        else {
            this.#selectedDownloads.clear();
            this.#selectedDownloads.add(entry.path);
        }
        this.#lastSelectedIndex = index;
        this.renderStorage(this.#currentEntries);
    }
    prepareContextSelection(entry) {
        if (!entry.isDirectory && !this.#selectedDownloads.has(entry.path)) {
            this.#selectedDownloads.clear();
            this.#selectedDownloads.add(entry.path);
            this.renderStorage(this.#currentEntries);
        }
    }
    setFileSelected(path, selected) {
        if (selected)
            this.#selectedDownloads.add(path);
        else
            this.#selectedDownloads.delete(path);
        this.renderStorage(this.#currentEntries);
    }
    clearSelection() {
        if (!this.#selectedDownloads.size)
            return;
        this.#selectedDownloads.clear();
        this.#lastSelectedIndex = null;
        this.renderStorage(this.#currentEntries);
    }
    updateSelectionControls() {
        const fileEntries = this.#currentEntries.filter((entry) => !entry.isDirectory);
        const selectedCount = fileEntries.filter((entry) => this.#selectedDownloads.has(entry.path)).length;
        this.elements.storageSelectAll.checked = fileEntries.length > 0 && selectedCount === fileEntries.length;
        this.elements.storageSelectAll.indeterminate = selectedCount > 0 && selectedCount < fileEntries.length;
        this.elements.downloadSelected.disabled = selectedCount === 0;
        this.elements.downloadSelected.textContent = selectedCount > 0 ? `Download (${selectedCount})` : "Download";
    }
    updateSortHeaders() {
        for (const button of document.querySelectorAll("[data-storage-sort]")) {
            const active = button.dataset.storageSort === this.#sortKey;
            button.classList.toggle("active", active);
            button.setAttribute("aria-sort", active ? this.#sortDirection : "none");
            const label = button.dataset.label ?? button.textContent?.replace(/[▲▼]/g, "").trim() ?? "";
            button.dataset.label = label;
            button.textContent = active ? `${label} ${this.#sortDirection === "ascending" ? "▲" : "▼"}` : label;
        }
    }
    showContextMenu(clientX, clientY, target) {
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
    hideContextMenu() {
        this.elements.contextMenu.hidden = true;
        this.#contextTarget = null;
    }
    chooseUploadFiles(destination) {
        this.#contextUploadDestination = destination;
        this.elements.contextUploadFile.value = "";
        this.elements.contextUploadFile.click();
    }
    async uploadFiles(destinationPath, sourceInput) {
        const serial = this.requireSerial();
        const files = [...(sourceInput.files ?? [])];
        if (!files.length)
            throw new Error("Choose one or more PC files to upload");
        this.elements.upload.disabled = true;
        try {
            for (const file of files) {
                await this.#api.uploadFile({
                    serial,
                    file,
                    destinationPath,
                    duplicatePolicy: this.duplicatePolicy(),
                });
            }
            sourceInput.value = "";
            await this.refreshTransfers();
            this.setStatus(`Queued ${files.length} upload(s) to ${destinationPath}`);
        }
        finally {
            this.elements.upload.disabled = false;
        }
    }
    async download(sourcePath) {
        const serial = this.requireSerial();
        await this.#api.downloadFile({
            serial,
            sourcePath,
            destinationProfile: this.elements.destinationProfile.value,
            duplicatePolicy: this.duplicatePolicy(),
        });
        await this.refreshTransfers();
        this.setStatus(`Queued download: ${sourcePath.split("/").at(-1) ?? sourcePath}`);
    }
    async downloadSelected() {
        if (!this.#selectedDownloads.size)
            throw new Error("Select one or more Android files");
        const selected = [...this.#selectedDownloads];
        for (const path of selected)
            await this.download(path);
        this.#selectedDownloads.clear();
        this.renderStorage(this.#currentEntries);
        this.setStatus(`Queued ${selected.length} download(s)`);
    }
    async refreshTransfers() {
        try {
            const response = await this.#api.transfers();
            this.#lastTransfers = response.transfers;
            this.renderTransfers(response.transfers);
        }
        catch (error) {
            this.setStatus(errorMessage(error), true);
        }
    }
    renderTransfers(transfers) {
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
            }
            else if (RETRY_STATES.has(transfer.state)) {
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
    duplicatePolicy() {
        return this.elements.duplicatePolicy.value;
    }
    requireSerial() {
        const serial = this.elements.device.value;
        if (!serial)
            throw new Error("Select an authorized Android device");
        return serial;
    }
    async runAction(action) {
        try {
            await action();
        }
        catch (error) {
            this.setStatus(errorMessage(error), true);
        }
    }
    setStatus(message, error = false) {
        this.elements.transferStatus.textContent = message;
        this.elements.transferStatus.classList.toggle("error-text", error);
    }
}
export function formatBytes(bytes) {
    if (!Number.isFinite(bytes) || bytes < 0)
        return "—";
    if (bytes < 1024)
        return `${bytes} B`;
    const units = ["KiB", "MiB", "GiB", "TiB"];
    let value = bytes / 1024;
    let unit = units[0];
    for (let index = 1; index < units.length && value >= 1024; index += 1) {
        value /= 1024;
        unit = units[index];
    }
    return `${value.toFixed(value >= 10 ? 1 : 2)} ${unit}`;
}
export function parentAndroidPath(path) {
    const root = androidRootForPath(path);
    if (!root || path === root)
        return root ?? "/sdcard/Download";
    const parent = path.replace(/\/+$/, "").split("/").slice(0, -1).join("/") || root;
    return parent.length < root.length ? root : parent;
}
export function androidBreadcrumbs(path) {
    const root = androidRootForPath(path) ?? "/sdcard/Download";
    const crumbs = [{ label: root.split("/").at(-1) ?? root, path: root }];
    const relative = path.slice(root.length).split("/").filter(Boolean);
    let current = root;
    for (const part of relative) {
        current = `${current}/${part}`;
        crumbs.push({ label: part, path: current });
    }
    return crumbs;
}
export function sortStorageEntries(entries, key, direction) {
    const multiplier = direction === "ascending" ? 1 : -1;
    return [...entries].sort((left, right) => {
        if (left.isDirectory !== right.isDirectory)
            return left.isDirectory ? -1 : 1;
        let comparison;
        if (key === "size")
            comparison = left.size - right.size;
        else if (key === "modified")
            comparison = left.modifiedAt - right.modifiedAt;
        else
            comparison = left.name.localeCompare(right.name, undefined, { numeric: true, sensitivity: "base" });
        if (comparison === 0)
            comparison = left.name.localeCompare(right.name, undefined, { numeric: true, sensitivity: "base" });
        return comparison * multiplier;
    });
}
function androidRootForPath(path) {
    const normalized = path.replace(/\/+$/, "") || path;
    return ANDROID_ROOTS.find((root) => normalized === root || normalized.startsWith(`${root}/`)) ?? null;
}
function fileIcon(name) {
    const extension = name.split(".").at(-1)?.toLowerCase() ?? "";
    if (["jpg", "jpeg", "png", "gif", "webp", "heic"].includes(extension))
        return "🖼️";
    if (["mp4", "mkv", "webm", "mov"].includes(extension))
        return "🎬";
    if (["pdf"].includes(extension))
        return "📕";
    if (["zip", "7z", "rar", "tar", "gz"].includes(extension))
        return "🗜️";
    if (["txt", "md", "log", "csv", "json", "xml"].includes(extension))
        return "📝";
    return "📄";
}
function transferDetail(transfer) {
    const total = transfer.size === null ? "unknown" : formatBytes(transfer.size);
    const completed = formatBytes(transfer.bytesTransferred);
    const speed = transfer.speedBytesPerSecond > 0 ? ` · ${formatBytes(transfer.speedBytesPerSecond)}/s` : "";
    return `${completed} / ${total}${speed}${transfer.verification ? ` · ${transfer.verification}` : ""}`;
}
function formatDate(timestamp) {
    if (!timestamp)
        return "—";
    return new Date(timestamp * 1000).toLocaleString([], { dateStyle: "short", timeStyle: "short" });
}
function errorMessage(error) {
    return error instanceof Error ? error.message : String(error);
}
function downloadJson(filename, payload) {
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const anchor = document.createElement("a");
    anchor.href = URL.createObjectURL(blob);
    anchor.download = filename;
    anchor.click();
    URL.revokeObjectURL(anchor.href);
}
//# sourceMappingURL=transfer-controller.js.map