/**
 * Kanban Board Main Application JavaScript
 * 
 * Dependencies:
 *   - PROJECT_ID: Global variable set in HTML template (e.g., const PROJECT_ID = '...')
 *   - dragdrop.js: Must be loaded after this file for handleDrop function
 * 
 * This module handles:
 *   - Tag management (filtering, autocomplete, CRUD operations)
 *   - Modal dialogs (edit item, create item, create update, delete project)
 *   - Toast notifications
 *   - Update filtering
 *   - Drag-and-drop wrapper for status changes
 */

// --- Tag Management State ---
let projectTags = [];
let activeTagFilters = [];
let tagFilterMode = 'any';
let currentEditItemId = null;

// --- Epic Filter State ---
let activeEpicFilter = null;

// Load project tags on page load
async function loadProjectTags() {
    if (!PROJECT_ID) return;
    try {
        const res = await fetch(`/api/tags?project=${PROJECT_ID}`);
        const data = await res.json();
        projectTags = data.tags || [];
        renderTagPicker();
    } catch (err) {
        console.error('Failed to load tags', err);
    }
}

// Render the tag picker with all project tags
function renderTagPicker() {
    const picker = document.getElementById('tag-picker');
    const section = document.getElementById('tag-filter-section');
    if (!picker || !section) return;

    picker.replaceChildren();

    if (projectTags.length === 0) {
        section.style.display = 'none';
        return;
    }

    section.style.display = 'flex';

    projectTags.forEach(tag => {
        const badge = document.createElement('span');
        badge.className = 'tag-badge tag-picker-item';
        if (activeTagFilters.includes(tag.name)) {
            badge.classList.add('selected');
        }
        badge.dataset.tagName = tag.name;
        badge.style.cssText = `--tag-color: ${tag.color};`;
        badge.textContent = tag.name;
        badge.onclick = () => toggleTagFilter(tag.name);
        picker.appendChild(badge);
    });

    updateFilterBarVisibility();
}

// Toggle a tag in the active filter set
function toggleTagFilter(tagName) {
    const idx = activeTagFilters.indexOf(tagName);
    if (idx >= 0) {
        activeTagFilters.splice(idx, 1);
    } else {
        activeTagFilters.push(tagName);
    }
    applyTagFilters();
}

// Apply tag filters to cards
function applyTagFilters() {
    const cards = document.querySelectorAll('.card');

    // Update tag picker selection state
    document.querySelectorAll('.tag-picker-item').forEach(badge => {
        badge.classList.toggle('selected', activeTagFilters.includes(badge.dataset.tagName));
    });

    // If no tag filters, show all cards (but respect other active filters)
    if (activeTagFilters.length === 0) {
        cards.forEach(card => card.style.display = '');
        // Re-apply other filters if active
        if (activeEpicFilter !== null) applyEpicFilter();
        if (activeRelationshipFilter !== null) applyRelationshipFilter();
        updateFilterBarVisibility();
        return;
    }

    cards.forEach(card => {
        const tagBadges = card.querySelectorAll('.tag-badge:not(.tag-picker-item)');
        const itemTags = Array.from(tagBadges).map(b => b.dataset.tagName);

        let matches = false;
        if (tagFilterMode === 'any') {
            matches = activeTagFilters.some(tag => itemTags.includes(tag));
        } else {
            matches = activeTagFilters.every(tag => itemTags.includes(tag));
        }

        card.style.display = matches ? '' : 'none';
    });

    updateFilterBarVisibility();
}

// Update filter bar visibility based on active filters
function updateFilterBarVisibility() {
    const clearBtn = document.getElementById('clear-all-filters-btn');
    const hasActiveFilters = activeTagFilters.length > 0 || activeEpicFilter !== null || activeRelationshipFilter !== null;

    if (clearBtn) {
        clearBtn.style.display = hasActiveFilters ? '' : 'none';
    }
}

// Set filter mode (any/all)
function setTagFilterMode(mode) {
    tagFilterMode = mode;
    document.querySelectorAll('.tag-filter-mode button').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.mode === mode);
    });
    applyTagFilters();
}

// Clear only tag filters
function clearTagFilters() {
    activeTagFilters = [];
    applyTagFilters();
}

// Clear all filters (tags, epic, relationship)
function clearAllFilters() {
    activeTagFilters = [];
    activeEpicFilter = null;
    activeRelationshipFilter = null;

    // Show all cards
    document.querySelectorAll('.card').forEach(card => card.style.display = '');

    // Update UI
    renderTagPicker();
    updateOtherFiltersUI();
    updateFilterBarVisibility();
}

// --- Epic Filter Functions ---
function filterByEpic(epicId) {
    activeEpicFilter = epicId;
    applyEpicFilter();
}

function applyEpicFilter() {
    const cards = document.querySelectorAll('.card');

    if (activeEpicFilter === null) {
        // If no other filters, show all cards
        if (activeTagFilters.length === 0 && activeRelationshipFilter === null) {
            cards.forEach(card => card.style.display = '');
        }
        updateOtherFiltersUI();
        updateFilterBarVisibility();
        return;
    }

    cards.forEach(card => {
        const parentId = card.dataset.parentId;
        const matches = parentId === String(activeEpicFilter);
        card.style.display = matches ? '' : 'none';
    });

    updateOtherFiltersUI();
    updateFilterBarVisibility();
}

function clearEpicFilter() {
    activeEpicFilter = null;
    applyEpicFilter();
    // Re-apply tag filters if any
    if (activeTagFilters.length > 0) {
        applyTagFilters();
    }
}

// --- Relationship Filter Functions ---
let activeRelationshipFilter = null;

function filterByRelationship(sourceItemId, relatedItemIds, relationshipType) {
    const allItemIds = [sourceItemId, ...relatedItemIds];
    activeRelationshipFilter = {
        sourceId: sourceItemId,
        relatedIds: relatedItemIds,
        type: relationshipType,
        allIds: allItemIds
    };
    applyRelationshipFilter();
}

function applyRelationshipFilter() {
    const cards = document.querySelectorAll('.card');

    if (activeRelationshipFilter === null) {
        if (activeTagFilters.length === 0 && activeEpicFilter === null) {
            cards.forEach(card => card.style.display = '');
        }
        updateOtherFiltersUI();
        updateFilterBarVisibility();
        return;
    }

    cards.forEach(card => {
        const itemId = parseInt(card.dataset.itemId);
        const matches = activeRelationshipFilter.allIds.includes(itemId);
        card.style.display = matches ? '' : 'none';
    });

    updateOtherFiltersUI();
    updateFilterBarVisibility();
}

function clearRelationshipFilter() {
    activeRelationshipFilter = null;
    applyRelationshipFilter();
    if (activeTagFilters.length > 0) {
        applyTagFilters();
    } else if (activeEpicFilter !== null) {
        applyEpicFilter();
    }
}

// Update the "other filters" section (epic + relationship filters)
function updateOtherFiltersUI() {
    const section = document.getElementById('other-filters');
    const activeDisplay = document.getElementById('active-filters');
    if (!section || !activeDisplay) return;

    activeDisplay.replaceChildren();

    const hasOtherFilters = activeEpicFilter !== null || activeRelationshipFilter !== null;
    section.style.display = hasOtherFilters ? 'flex' : 'none';

    // Epic filter badge
    if (activeEpicFilter !== null) {
        const badge = document.createElement('span');
        badge.className = 'filter-badge epic-filter-badge';
        badge.onclick = () => clearEpicFilter();

        const text = document.createElement('span');
        text.textContent = `Epic #${activeEpicFilter} children`;
        badge.appendChild(text);

        const icon = document.createElement('i');
        icon.className = 'material-icons';
        icon.textContent = 'close';
        badge.appendChild(icon);

        activeDisplay.appendChild(badge);
    }

    // Relationship filter badge
    if (activeRelationshipFilter !== null) {
        const badge = document.createElement('span');
        badge.className = 'filter-badge relationship-filter-badge';
        badge.onclick = () => clearRelationshipFilter();

        const text = document.createElement('span');
        text.textContent = `#${activeRelationshipFilter.sourceId} ${activeRelationshipFilter.type} ${activeRelationshipFilter.relatedIds.map(id => '#' + id).join(', ')}`;
        badge.appendChild(text);

        const icon = document.createElement('i');
        icon.className = 'material-icons';
        icon.textContent = 'close';
        badge.appendChild(icon);

        activeDisplay.appendChild(badge);
    }
}

// --- Tag Manager ---

function openTagManager() {
    openModal('tag-manager-modal');
    renderTagManagerList();
}

function renderTagManagerList() {
    const list = document.getElementById('tag-manager-list');
    const empty = document.getElementById('tag-manager-empty');
    if (!list) return;

    list.replaceChildren();

    if (projectTags.length === 0) {
        empty.style.display = 'block';
        return;
    }
    empty.style.display = 'none';

    projectTags.forEach(tag => {
        const row = document.createElement('div');
        row.className = 'tag-manager-row';
        row.dataset.tagId = tag.id;

        // Color picker
        const colorPicker = document.createElement('input');
        colorPicker.type = 'color';
        colorPicker.className = 'tag-color-picker';
        colorPicker.value = tag.color;
        colorPicker.title = 'Change color';
        colorPicker.onchange = () => updateTagColor(tag.id, colorPicker.value);
        row.appendChild(colorPicker);

        // Tag name
        const name = document.createElement('span');
        name.className = 'tag-manager-name';
        name.textContent = tag.name;
        row.appendChild(name);

        // Usage count
        const count = document.createElement('span');
        count.className = 'tag-manager-count';
        count.textContent = `${tag.count || 0} items`;
        row.appendChild(count);

        // Delete button
        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'tag-manager-delete';
        deleteBtn.title = 'Delete tag';
        deleteBtn.onclick = () => confirmDeleteTag(tag.id, tag.name, tag.count || 0);
        const deleteIcon = document.createElement('i');
        deleteIcon.className = 'material-icons';
        deleteIcon.textContent = 'delete';
        deleteBtn.appendChild(deleteIcon);
        row.appendChild(deleteBtn);

        list.appendChild(row);
    });
}

async function updateTagColor(tagId, newColor) {
    try {
        const res = await fetch(`/api/tags/${tagId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ color: newColor })
        });
        if (res.ok) {
            // Update local state
            const tag = projectTags.find(t => t.id === tagId);
            if (tag) tag.color = newColor;
            renderTagPicker();
            showToast('Tag color updated', 'success');
        } else {
            showToast('Failed to update tag color', 'error');
        }
    } catch (err) {
        console.error('Failed to update tag color:', err);
        showToast('Failed to update tag color', 'error');
    }
}

function confirmDeleteTag(tagId, tagName, itemCount) {
    const message = itemCount > 0
        ? `Delete tag "${tagName}"? It will be removed from ${itemCount} item${itemCount > 1 ? 's' : ''}.`
        : `Delete tag "${tagName}"?`;

    if (confirm(message)) {
        deleteTag(tagId);
    }
}

async function deleteTag(tagId) {
    try {
        // Find tag name before deleting from local state
        const deletedTag = projectTags.find(t => t.id === tagId);
        const deletedTagName = deletedTag ? deletedTag.name : null;

        const res = await fetch(`/api/tags/${tagId}`, { method: 'DELETE' });
        if (res.ok) {
            // Remove from local state
            projectTags = projectTags.filter(t => t.id !== tagId);
            activeTagFilters = activeTagFilters.filter(name => name !== deletedTagName);

            // Remove tag badges from all cards
            if (deletedTagName) {
                document.querySelectorAll(`.card .tag-badge[data-tag-name="${deletedTagName}"]`).forEach(badge => {
                    badge.remove();
                });
            }

            renderTagManagerList();
            renderTagPicker();
            applyTagFilters();
            showToast('Tag deleted', 'success');
        } else {
            showToast('Failed to delete tag', 'error');
        }
    } catch (err) {
        console.error('Failed to delete tag:', err);
        showToast('Failed to delete tag', 'error');
    }
}

// --- Tag Input Autocomplete ---
function setupTagInput(inputId, suggestionsId) {
    const input = document.getElementById(inputId);
    const suggestions = document.getElementById(suggestionsId);
    if (!input || !suggestions) return;

    input.addEventListener('input', () => {
        const value = input.value.toLowerCase().trim();
        if (!value) {
            suggestions.classList.remove('show');
            return;
        }

        const matches = projectTags.filter(t =>
            t.name.includes(value) && !isTagOnItem(t.name)
        );

        suggestions.textContent = '';
        if (matches.length === 0) {
            const item = document.createElement('div');
            item.className = 'tag-suggestion-item';
            item.onclick = () => addTagToCurrentItem(value);
            const span = document.createElement('span');
            span.style.color = 'var(--text-medium-emphasis)';
            span.textContent = 'Create new tag: ';
            const strong = document.createElement('strong');
            strong.textContent = value;
            item.appendChild(span);
            item.appendChild(strong);
            suggestions.appendChild(item);
        } else {
            matches.forEach(tag => {
                const item = document.createElement('div');
                item.className = 'tag-suggestion-item';
                item.onclick = () => addTagToCurrentItem(tag.name);
                const preview = document.createElement('div');
                preview.className = 'tag-color-preview';
                preview.style.background = tag.color;
                const name = document.createElement('span');
                name.textContent = tag.name;
                item.appendChild(preview);
                item.appendChild(name);
                suggestions.appendChild(item);
            });
        }
        suggestions.classList.add('show');
    });

    input.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' && input.value.trim()) {
            e.preventDefault();
            addTagToCurrentItem(input.value.trim());
        }
    });

    // Close suggestions when clicking outside
    document.addEventListener('click', (e) => {
        if (!input.contains(e.target) && !suggestions.contains(e.target)) {
            suggestions.classList.remove('show');
        }
    });
}

// Check if tag is already on the current item being edited
function isTagOnItem(tagName) {
    const container = document.getElementById('edit-current-tags');
    if (!container) return false;
    const badges = container.querySelectorAll('.tag-badge');
    return Array.from(badges).some(b => b.dataset.tagName === tagName);
}

// Add tag to current item being edited
async function addTagToCurrentItem(tagName) {
    if (!currentEditItemId || !tagName.trim()) return;

    try {
        const res = await fetch(`/api/items/${currentEditItemId}/tags`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ tags: [tagName.trim()] })
        });
        const result = await res.json();

        if (!res.ok || !result.success) {
            showToast(result.error || 'Failed to add tag', 'error');
            return;
        }

        // Refresh project tags and item tags display
        await loadProjectTags();
        await loadItemTags(currentEditItemId);

        // Clear input
        const input = document.getElementById('edit-tags-input');
        if (input) input.value = '';
        document.getElementById('edit-tags-suggestions')?.classList.remove('show');

        showToast('Tag added');
    } catch (err) {
        showToast('Failed to add tag', 'error');
    }
}

// Remove tag from current item being edited
async function removeTagFromCurrentItem(tagId) {
    if (!currentEditItemId) return;

    try {
        const res = await fetch(`/api/items/${currentEditItemId}/tags/${tagId}`, {
            method: 'DELETE'
        });
        const result = await res.json();

        if (!res.ok || !result.success) {
            showToast('Failed to remove tag', 'error');
            return;
        }

        await loadItemTags(currentEditItemId);
        showToast('Tag removed');
    } catch (err) {
        showToast('Failed to remove tag', 'error');
    }
}

// Load and display tags for an item in the edit modal
async function loadItemTags(itemId) {
    const container = document.getElementById('edit-current-tags');
    if (!container) return;

    try {
        const res = await fetch(`/api/items/${itemId}/tags`);
        const data = await res.json();
        const tags = data.tags || [];

        container.textContent = '';
        if (tags.length === 0) {
            const span = document.createElement('span');
            span.style.cssText = 'color: var(--text-disabled); font-size: 12px;';
            span.textContent = 'No tags';
            container.appendChild(span);
        } else {
            tags.forEach(tag => {
                const badge = document.createElement('span');
                badge.className = 'tag-badge';
                badge.dataset.tagName = tag.name;
                badge.style.cssText = `background: ${tag.color}20; color: ${tag.color}; border: 1px solid ${tag.color}40;`;
                badge.textContent = tag.name + ' ';
                const icon = document.createElement('i');
                icon.className = 'material-icons';
                icon.style.cssText = 'font-size:12px; cursor:pointer; margin-left:4px;';
                icon.textContent = 'close';
                icon.onclick = () => removeTagFromCurrentItem(tag.id);
                badge.appendChild(icon);
                container.appendChild(badge);
            });
        }
    } catch (err) {
        container.textContent = '';
        const span = document.createElement('span');
        span.style.color = 'var(--text-disabled)';
        span.textContent = 'Error loading tags';
        container.appendChild(span);
    }
}

// Load and display children for an item in the edit modal
async function loadItemChildren(itemId) {
    const section = document.getElementById('edit-children-section');
    const container = document.getElementById('edit-children-list');
    if (!section || !container) return;

    try {
        const res = await fetch(`/api/items/${itemId}/children`);
        const data = await res.json();
        const children = data.children || [];

        if (children.length === 0) {
            section.style.display = 'none';
            return;
        }

        section.style.display = 'block';
        container.textContent = '';

        children.forEach(child => {
            const row = document.createElement('div');
            row.className = 'child-item';
            row.onclick = () => {
                closeModal('edit-modal');
                setTimeout(() => openEditModal(child.id), 100);
            };

            // Item ID
            const idSpan = document.createElement('span');
            idSpan.className = 'child-item-id';
            idSpan.textContent = '#' + child.id;
            row.appendChild(idSpan);

            // Title
            const titleSpan = document.createElement('span');
            titleSpan.className = 'child-item-title';
            titleSpan.textContent = child.title;
            row.appendChild(titleSpan);

            // Type badge
            const typeBadge = document.createElement('span');
            typeBadge.className = 'child-item-type type-' + child.type_name;
            typeBadge.textContent = child.type_name;
            row.appendChild(typeBadge);

            // Status badge
            const statusBadge = document.createElement('span');
            statusBadge.className = 'child-item-status status-' + child.status_name;
            statusBadge.textContent = child.status_name;
            row.appendChild(statusBadge);

            container.appendChild(row);
        });
    } catch (err) {
        section.style.display = 'none';
        console.error('Failed to load children', err);
    }
}

// --- File Linking Functions ---

// Load and display linked files for an item
async function loadItemFiles(itemId) {
    const container = document.getElementById('edit-linked-files');
    if (!container) return;

    try {
        const res = await fetch(`/api/items/${itemId}/files`);
        const data = await res.json();
        const files = data.files || [];

        container.textContent = '';

        if (files.length === 0) {
            const emptySpan = document.createElement('span');
            emptySpan.style.color = 'var(--text-disabled)';
            emptySpan.textContent = 'No files linked';
            container.appendChild(emptySpan);
            return;
        }

        files.forEach(file => {
            const row = document.createElement('div');
            row.className = 'linked-file-item';

            // File icon
            const icon = document.createElement('i');
            icon.className = 'material-icons';
            icon.style.fontSize = '16px';
            icon.style.color = 'var(--text-secondary)';
            icon.textContent = 'insert_drive_file';
            row.appendChild(icon);

            // File path display
            const fullPath = formatFullPath(file.file_path);

            // Format display text with line numbers
            let displayText = file.file_path;
            let lineNum = null;
            if (file.line_start !== null) {
                lineNum = file.line_start;
                if (file.line_end !== null) {
                    displayText += `:${file.line_start}-${file.line_end}`;
                } else {
                    displayText += `:${file.line_start}`;
                }
            }

            // VS Code link (works from web pages)
            const vscodeLink = document.createElement('a');
            vscodeLink.className = 'file-vscode-btn';
            vscodeLink.href = formatVSCodeLink(fullPath, lineNum);
            vscodeLink.title = 'Open in VS Code';
            const vscodeIcon = document.createElement('i');
            vscodeIcon.className = 'material-icons';
            vscodeIcon.style.fontSize = '14px';
            vscodeIcon.textContent = 'open_in_new';
            vscodeLink.appendChild(vscodeIcon);
            row.appendChild(vscodeLink);

            // Path text (copyable)
            const pathSpan = document.createElement('span');
            pathSpan.className = 'file-path-text';
            pathSpan.textContent = displayText;
            pathSpan.title = fullPath;
            row.appendChild(pathSpan);

            // Copy button
            const copyBtn = document.createElement('button');
            copyBtn.className = 'file-copy-btn';
            copyBtn.title = 'Copy full path';
            copyBtn.onclick = (e) => {
                e.stopPropagation();
                const copyPath = lineNum ? `${fullPath}:${lineNum}` : fullPath;
                navigator.clipboard.writeText(copyPath).then(() => {
                    showToast('Path copied');
                });
            };
            const copyIcon = document.createElement('i');
            copyIcon.className = 'material-icons';
            copyIcon.style.fontSize = '14px';
            copyIcon.textContent = 'content_copy';
            copyBtn.appendChild(copyIcon);
            row.appendChild(copyBtn);

            // Remove button
            const removeBtn = document.createElement('button');
            removeBtn.className = 'file-remove-btn';
            removeBtn.title = 'Remove link';
            removeBtn.onclick = (e) => {
                e.stopPropagation();
                removeFileLink(itemId, file.file_path, file.line_start, file.line_end);
            };
            const removeIcon = document.createElement('i');
            removeIcon.className = 'material-icons';
            removeIcon.style.fontSize = '16px';
            removeIcon.textContent = 'close';
            removeBtn.appendChild(removeIcon);
            row.appendChild(removeBtn);

            container.appendChild(row);
        });
    } catch (err) {
        container.textContent = '';
        const span = document.createElement('span');
        span.style.color = 'var(--md-sys-color-error)';
        span.textContent = 'Error loading files';
        container.appendChild(span);
    }
}

// Format file path to full absolute path
function formatFullPath(filePath) {
    // Check if it's already an absolute path
    if (filePath.startsWith('/')) {
        return filePath;
    }
    // For relative paths, prepend the project directory
    if (typeof PROJECT_DIR !== 'undefined' && PROJECT_DIR) {
        return PROJECT_DIR + '/' + filePath;
    }
    return filePath;
}

// Format VS Code URL (vscode://file/path:line)
function formatVSCodeLink(fullPath, lineNum) {
    let url = 'vscode://file' + fullPath;
    if (lineNum) {
        url += ':' + lineNum;
    }
    return url;
}

// Add a file link
async function addFileLink() {
    if (!currentEditItemId) return;

    const pathInput = document.getElementById('add-file-path');
    const startInput = document.getElementById('add-file-start');
    const endInput = document.getElementById('add-file-end');

    const filePath = pathInput.value.trim();
    if (!filePath) {
        showToast('File path is required', 'error');
        return;
    }

    const data = {
        file_path: filePath,
        line_start: startInput.value ? parseInt(startInput.value) : null,
        line_end: endInput.value ? parseInt(endInput.value) : null
    };

    try {
        const res = await fetch(`/api/items/${currentEditItemId}/files`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
        const result = await res.json();

        if (!res.ok || !result.success) {
            throw new Error(result.error || 'Failed to link file');
        }

        // Clear inputs
        pathInput.value = '';
        startInput.value = '';
        endInput.value = '';

        // Reload file list
        await loadItemFiles(currentEditItemId);
        showToast('File linked');
    } catch (err) {
        showToast(err.message, 'error');
    }
}

// Remove a file link
async function removeFileLink(itemId, filePath, lineStart, lineEnd) {
    const data = {
        file_path: filePath,
        line_start: lineStart,
        line_end: lineEnd
    };

    try {
        const res = await fetch(`/api/items/${itemId}/files`, {
            method: 'DELETE',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
        const result = await res.json();

        if (!res.ok || !result.success) {
            throw new Error(result.error || 'Failed to unlink file');
        }

        // Reload file list
        await loadItemFiles(itemId);
        showToast('File unlinked');
    } catch (err) {
        showToast(err.message, 'error');
    }
}

// --- Decision History Functions ---

// Load and display decisions for an item
async function loadItemDecisions(itemId) {
    const container = document.getElementById('edit-decisions-list');
    if (!container) return;

    try {
        const res = await fetch(`/api/items/${itemId}/decisions`);
        const data = await res.json();
        const decisions = data.decisions || [];

        container.textContent = '';

        if (decisions.length === 0) {
            const emptySpan = document.createElement('span');
            emptySpan.style.color = 'var(--text-disabled)';
            emptySpan.textContent = 'No decisions recorded';
            container.appendChild(emptySpan);
            return;
        }

        decisions.forEach(decision => {
            const row = document.createElement('div');
            row.className = 'decision-item';

            // Decision content
            const content = document.createElement('div');
            content.className = 'decision-content';

            // Choice (required)
            const choiceDiv = document.createElement('div');
            choiceDiv.className = 'decision-choice';
            const choiceLabel = document.createElement('strong');
            choiceLabel.textContent = 'Chose: ';
            choiceDiv.appendChild(choiceLabel);
            choiceDiv.appendChild(document.createTextNode(decision.choice));
            content.appendChild(choiceDiv);

            // Rejected alternatives (optional)
            if (decision.rejected_alternatives) {
                const rejectedDiv = document.createElement('div');
                rejectedDiv.className = 'decision-rejected';
                const rejectedLabel = document.createElement('span');
                rejectedLabel.textContent = 'Rejected: ';
                rejectedLabel.style.color = 'var(--md-sys-color-error)';
                rejectedDiv.appendChild(rejectedLabel);
                rejectedDiv.appendChild(document.createTextNode(decision.rejected_alternatives));
                content.appendChild(rejectedDiv);
            }

            // Rationale (optional)
            if (decision.rationale) {
                const rationaleDiv = document.createElement('div');
                rationaleDiv.className = 'decision-rationale';
                const rationaleLabel = document.createElement('span');
                rationaleLabel.textContent = 'Why: ';
                rationaleLabel.style.color = 'var(--text-medium-emphasis)';
                rationaleDiv.appendChild(rationaleLabel);
                rationaleDiv.appendChild(document.createTextNode(decision.rationale));
                content.appendChild(rationaleDiv);
            }

            // Timestamp
            const timestamp = document.createElement('div');
            timestamp.className = 'decision-timestamp';
            timestamp.textContent = new Date(decision.created_at).toLocaleString();
            content.appendChild(timestamp);

            row.appendChild(content);

            // Remove button
            const removeBtn = document.createElement('button');
            removeBtn.className = 'decision-remove-btn';
            removeBtn.title = 'Delete decision';
            removeBtn.onclick = (e) => {
                e.stopPropagation();
                removeDecision(decision.id);
            };
            const removeIcon = document.createElement('i');
            removeIcon.className = 'material-icons';
            removeIcon.style.fontSize = '16px';
            removeIcon.textContent = 'close';
            removeBtn.appendChild(removeIcon);
            row.appendChild(removeBtn);

            container.appendChild(row);
        });
    } catch (err) {
        container.textContent = '';
        const span = document.createElement('span');
        span.style.color = 'var(--md-sys-color-error)';
        span.textContent = 'Error loading decisions';
        container.appendChild(span);
    }
}

// Add a decision to current item
async function addDecision() {
    if (!currentEditItemId) return;

    const choiceInput = document.getElementById('add-decision-choice');
    const rejectedInput = document.getElementById('add-decision-rejected');
    const rationaleInput = document.getElementById('add-decision-rationale');

    const choice = choiceInput.value.trim();
    if (!choice) {
        showToast('Choice is required', 'error');
        return;
    }

    const data = {
        choice: choice,
        rejected_alternatives: rejectedInput.value.trim() || null,
        rationale: rationaleInput.value.trim() || null
    };

    try {
        const res = await fetch(`/api/items/${currentEditItemId}/decisions`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
        const result = await res.json();

        if (!res.ok || !result.success) {
            throw new Error(result.error || 'Failed to add decision');
        }

        // Clear inputs
        choiceInput.value = '';
        rejectedInput.value = '';
        rationaleInput.value = '';

        // Reload decisions list
        await loadItemDecisions(currentEditItemId);
        showToast('Decision recorded');
    } catch (err) {
        showToast(err.message, 'error');
    }
}

// Remove a decision
async function removeDecision(decisionId) {
    try {
        const res = await fetch(`/api/decisions/${decisionId}`, {
            method: 'DELETE'
        });
        const result = await res.json();

        if (!res.ok || !result.success) {
            throw new Error(result.error || 'Failed to delete decision');
        }

        // Reload decisions list
        if (currentEditItemId) {
            await loadItemDecisions(currentEditItemId);
        }
        showToast('Decision deleted');
    } catch (err) {
        showToast(err.message, 'error');
    }
}

// Initialize on page load
if (typeof PROJECT_ID !== 'undefined' && PROJECT_ID) {
    loadProjectTags();
}

// --- Utility: HTML escape for XSS prevention ---
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// --- Modal Functions ---
function openModal(id) {
    document.getElementById(id).classList.add('open');
}

function closeModal(id) {
    document.getElementById(id).classList.remove('open');
}

// Close modal on overlay click
document.querySelectorAll('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', e => {
        if (e.target === overlay) closeModal(overlay.id);
    });
});

// Close modal on Escape key
document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
        document.querySelectorAll('.modal-overlay.open').forEach(m => closeModal(m.id));
    }
});

// --- Toast Notifications ---
function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    const icon = document.createElement('i');
    icon.className = 'material-icons';
    icon.textContent = type === 'error' ? 'error' : 'check_circle';
    toast.appendChild(icon);
    const text = document.createTextNode(' ' + message);
    toast.appendChild(text);
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 4000);
}

// --- Edit Item ---
async function openEditModal(itemId) {
    currentEditItemId = itemId;
    try {
        const res = await fetch(`/api/items/${itemId}`);
        if (!res.ok) throw new Error('Failed to load item');
        const item = await res.json();

        document.getElementById('edit-id').value = item.id;
        document.getElementById('edit-item-id').textContent = '#' + item.id;
        document.getElementById('edit-title').value = item.title;
        document.getElementById('edit-description').value = item.description || '';
        document.getElementById('edit-priority').value = item.priority;
        document.getElementById('edit-complexity').value = item.complexity || '';
        document.getElementById('edit-status').value = item.status;
        document.getElementById('edit-type').value = item.type;

        // Load parent dropdown (exclude current item to prevent circular reference)
        await loadEpicsForDropdown('edit-parent', item.parent_id, itemId);

        // Load tags for this item
        await loadItemTags(itemId);
        setupTagInput('edit-tags-input', 'edit-tags-suggestions');

        // Load children for epics
        if (item.type === 'epic') {
            await loadItemChildren(itemId);
        } else {
            document.getElementById('edit-children-section').style.display = 'none';
        }

        // Load linked files
        await loadItemFiles(itemId);

        // Load decision history
        await loadItemDecisions(itemId);

        openModal('edit-modal');
    } catch (err) {
        showToast(err.message, 'error');
    }
}

async function saveItem() {
    const itemId = document.getElementById('edit-id').value;
    const complexityVal = document.getElementById('edit-complexity').value;
    const parentVal = document.getElementById('edit-parent').value;
    const data = {
        title: document.getElementById('edit-title').value,
        description: document.getElementById('edit-description').value,
        priority: parseInt(document.getElementById('edit-priority').value),
        complexity: complexityVal ? parseInt(complexityVal) : null,
        status: document.getElementById('edit-status').value,
        parent_id: parentVal ? parseInt(parentVal) : null
    };

    try {
        const res = await fetch(`/api/items/${itemId}`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
        const result = await res.json();

        if (!res.ok || !result.success) {
            throw new Error(result.message || result.error || 'Failed to save');
        }

        closeModal('edit-modal');
        showToast('Item updated');
        setTimeout(() => location.reload(), 500);
    } catch (err) {
        showToast(err.message, 'error');
    }
}

// --- Delete Item ---

function confirmDeleteItem() {
    const itemId = document.getElementById('edit-id').value;
    const title = document.getElementById('edit-title').value;
    if (confirm(`Delete item #${itemId} "${title}"? This cannot be undone.`)) {
        deleteItem(itemId);
    }
}

async function deleteItem(itemId) {
    try {
        const res = await fetch(`/api/items/${itemId}`, { method: 'DELETE' });
        const result = await res.json();
        if (!res.ok || !result.success) {
            throw new Error(result.error || 'Failed to delete item');
        }
        closeModal('edit-modal');
        showToast('Item deleted');
        // Remove the card from the board
        const card = document.querySelector(`.card[data-item-id="${itemId}"]`);
        if (card) card.remove();
    } catch (err) {
        showToast(err.message, 'error');
    }
}

// --- Create Update ---
async function openUpdateModal(preselectedItemId = null) {
    // Load items for dropdown using safe DOM methods
    try {
        const res = await fetch(`/api/items?project=${PROJECT_ID}`);
        const data = await res.json();
        const select = document.getElementById('update-items');
        select.replaceChildren(); // Clear existing options
        data.items.forEach(item => {
            const option = document.createElement('option');
            option.value = item.id;
            option.textContent = `#${item.id} ${item.title}`;
            if (item.id == preselectedItemId) option.selected = true;
            select.appendChild(option);
        });
    } catch (err) {
        console.error('Failed to load items', err);
    }

    document.getElementById('update-content').value = '';
    openModal('update-modal');
}

async function createUpdate() {
    const content = document.getElementById('update-content').value.trim();
    if (!content) {
        showToast('Content is required', 'error');
        return;
    }

    const select = document.getElementById('update-items');
    const itemIds = Array.from(select.selectedOptions).map(o => parseInt(o.value));

    try {
        const res = await fetch('/api/updates', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                project_id: PROJECT_ID,
                content: content,
                item_ids: itemIds
            })
        });
        const result = await res.json();

        if (!res.ok || !result.success) {
            throw new Error(result.error || 'Failed to create update');
        }

        closeModal('update-modal');
        showToast('Update created');
        setTimeout(() => location.reload(), 500);
    } catch (err) {
        showToast(err.message, 'error');
    }
}

// --- Load Epics for Parent Dropdown ---
async function loadEpicsForDropdown(selectId, currentParentId = null, excludeItemId = null) {
    if (!PROJECT_ID) return;
    try {
        const res = await fetch(`/api/epics?project=${PROJECT_ID}`);
        const data = await res.json();
        const select = document.getElementById(selectId);
        // Clear existing options except first
        while (select.options.length > 1) {
            select.remove(1);
        }
        // Add epic options
        (data.epics || []).forEach(epic => {
            if (excludeItemId && epic.id == excludeItemId) return; // Don't allow item to be its own parent
            const option = document.createElement('option');
            option.value = epic.id;
            option.textContent = `#${epic.id} ${epic.title} (${epic.status})`;
            if (currentParentId && epic.id == currentParentId) option.selected = true;
            select.appendChild(option);
        });
    } catch (err) {
        console.error('Failed to load epics', err);
    }
}

// --- Create Item ---
async function openNewItemModal() {
    document.getElementById('newitem-title').value = '';
    document.getElementById('newitem-description').value = '';
    document.getElementById('newitem-type').value = 'issue';
    document.getElementById('newitem-priority').value = '3';
    document.getElementById('newitem-complexity').value = '';
    document.getElementById('newitem-parent').value = '';
    await loadEpicsForDropdown('newitem-parent');
    openModal('newitem-modal');
}

async function createItem() {
    const title = document.getElementById('newitem-title').value.trim();
    if (!title) {
        showToast('Title is required', 'error');
        return;
    }

    const complexityVal = document.getElementById('newitem-complexity').value;
    const parentVal = document.getElementById('newitem-parent').value;
    const data = {
        project_id: PROJECT_ID,
        type: document.getElementById('newitem-type').value,
        title: title,
        description: document.getElementById('newitem-description').value,
        priority: parseInt(document.getElementById('newitem-priority').value),
        complexity: complexityVal ? parseInt(complexityVal) : null,
        parent_id: parentVal ? parseInt(parentVal) : null
    };

    try {
        const res = await fetch('/api/items', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(data)
        });
        const result = await res.json();

        if (!res.ok || !result.success) {
            throw new Error(result.error || 'Failed to create item');
        }

        closeModal('newitem-modal');
        showToast('Item created');
        setTimeout(() => location.reload(), 500);
    } catch (err) {
        showToast(err.message, 'error');
    }
}

// --- Delete Project ---
function confirmDeleteProject(projectId, projectName) {
    document.getElementById('delete-project-id').value = projectId;
    document.getElementById('delete-project-name').textContent = projectName;
    openModal('delete-modal');
}

async function deleteProject() {
    const projectId = document.getElementById('delete-project-id').value;

    try {
        const res = await fetch(`/api/projects/${projectId}`, {method: 'DELETE'});
        const result = await res.json();

        if (!res.ok || !result.success) {
            throw new Error(result.error || 'Failed to delete project');
        }

        closeModal('delete-modal');
        showToast('Project deleted');
        setTimeout(() => window.location.href = '/', 500);
    } catch (err) {
        showToast(err.message, 'error');
    }
}

// --- Filter Updates ---
function filterUpdates(query) {
    const q = query.toLowerCase().trim();
    const groups = document.querySelectorAll('.update-group');

    groups.forEach(group => {
        const itemId = group.dataset.itemId || '';
        const itemTitle = (group.dataset.itemTitle || '').toLowerCase();
        const updates = group.querySelectorAll('.update-item');
        let hasVisibleUpdate = false;

        updates.forEach(update => {
            const content = update.dataset.content || '';
            const matches = q === '' ||
                itemId.includes(q) ||
                ('#' + itemId).includes(q) ||
                itemTitle.includes(q) ||
                content.includes(q);

            update.classList.toggle('hidden', !matches);
            if (matches) hasVisibleUpdate = true;
        });

        group.classList.toggle('hidden', !hasVisibleUpdate);
    });
}

// --- Drag and Drop (wrapper for tested module) ---
// The drag-drop logic is in /static/dragdrop.js - we wrap it here to provide showToast
async function handleDropWrapper(e) {
    const result = await handleDrop(e, showToast, fetch);
    if (result.success && !result.noChange) {
        // Reload after brief delay to sync fully
        setTimeout(() => location.reload(), 800);
    }
}

// --- Export Functions ---
function openExportModal() {
    // Reset form to defaults
    document.getElementById('export-format').value = 'json';
    document.getElementById('export-type').value = '';
    document.getElementById('export-status').value = '';
    document.getElementById('export-tags').checked = true;
    document.getElementById('export-relationships').checked = false;
    document.getElementById('export-metrics').checked = false;
    document.getElementById('export-updates').checked = false;
    document.getElementById('export-epic-progress').checked = false;
    document.getElementById('export-detailed').checked = false;
    document.getElementById('export-limit').value = '500';
    openModal('export-modal');
}

async function doExport() {
    if (!PROJECT_ID) {
        showToast('No project selected', 'error');
        return;
    }

    // Build query parameters
    const params = new URLSearchParams();
    params.set('project', PROJECT_ID);
    params.set('format', document.getElementById('export-format').value);
    params.set('download', 'true');

    // Add filters
    const itemType = document.getElementById('export-type').value;
    if (itemType) params.set('type', itemType);

    const status = document.getElementById('export-status').value;
    if (status) params.set('status', status);

    // Add include options
    params.set('tags', document.getElementById('export-tags').checked);
    params.set('relationships', document.getElementById('export-relationships').checked);
    params.set('metrics', document.getElementById('export-metrics').checked);
    params.set('updates', document.getElementById('export-updates').checked);
    params.set('epic_progress', document.getElementById('export-epic-progress').checked);
    params.set('detailed', document.getElementById('export-detailed').checked);

    // Add limit
    const limit = parseInt(document.getElementById('export-limit').value) || 500;
    params.set('limit', Math.max(1, Math.min(limit, 10000)));

    try {
        // Trigger download
        const url = `/api/export?${params.toString()}`;
        const response = await fetch(url);

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Export failed');
        }

        // Get filename from Content-Disposition header
        const disposition = response.headers.get('Content-Disposition');
        let filename = 'export';
        if (disposition) {
            const match = disposition.match(/filename="?([^"]+)"?/);
            if (match) filename = match[1];
        }

        // Download the file
        const blob = await response.blob();
        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(downloadUrl);

        closeModal('export-modal');
        showToast('Export downloaded');
    } catch (err) {
        showToast(err.message, 'error');
    }
}

// --- Search Functions ---
function openSearchModal() {
    document.getElementById('search-query').value = '';
    document.getElementById('search-results').textContent = '';
    openModal('search-modal');
    // Focus the search input
    setTimeout(() => document.getElementById('search-query').focus(), 100);
}

async function doSearch() {
    const query = document.getElementById('search-query').value.trim();
    const resultsDiv = document.getElementById('search-results');
    const useSemanticSearch = document.getElementById('semantic-search-toggle')?.checked || false;

    if (!query) {
        resultsDiv.textContent = '';
        return;
    }

    if (!PROJECT_ID) {
        showToast('No project selected', 'error');
        return;
    }

    try {
        let res, data;

        if (useSemanticSearch) {
            // Use semantic search API
            res = await fetch(`/api/semantic-search?project=${PROJECT_ID}&q=${encodeURIComponent(query)}&limit=20`);
            data = await res.json();

            if (!res.ok) {
                throw new Error(data.error || 'Semantic search failed');
            }

            renderSemanticSearchResults(data, resultsDiv);
        } else {
            // Use regular full-text search
            res = await fetch(`/api/search?project=${PROJECT_ID}&q=${encodeURIComponent(query)}`);
            data = await res.json();

            if (!res.ok) {
                throw new Error(data.error || 'Search failed');
            }

            renderSearchResults(data, resultsDiv);
        }
    } catch (err) {
        showToast(err.message, 'error');
    }
}

function renderSearchResults(data, container) {
    container.textContent = '';

    if (data.total_count === 0) {
        const empty = document.createElement('div');
        empty.className = 'empty-state';
        empty.textContent = 'No results found';
        container.appendChild(empty);
        return;
    }

    // Items section
    if (data.items && data.items.length > 0) {
        const section = document.createElement('div');
        section.className = 'search-section';

        const header = document.createElement('div');
        header.className = 'search-section-header';
        header.textContent = `Items (${data.items.length})`;
        section.appendChild(header);

        data.items.forEach(item => {
            const row = document.createElement('div');
            row.className = 'search-result-item';
            row.onclick = () => {
                closeModal('search-modal');
                openEditModal(item.id);
            };

            const idSpan = document.createElement('span');
            idSpan.className = 'search-result-id';
            idSpan.textContent = '#' + item.id;
            row.appendChild(idSpan);

            const titleSpan = document.createElement('span');
            titleSpan.className = 'search-result-title';
            titleSpan.textContent = item.title;
            row.appendChild(titleSpan);

            const typeBadge = document.createElement('span');
            typeBadge.className = 'search-result-type type-' + item.type_name;
            typeBadge.textContent = item.type_name;
            row.appendChild(typeBadge);

            const statusBadge = document.createElement('span');
            statusBadge.className = 'search-result-status status-' + item.status_name;
            statusBadge.textContent = item.status_name;
            row.appendChild(statusBadge);

            if (item.snippet) {
                const snippet = document.createElement('div');
                snippet.className = 'search-result-snippet';
                snippet.textContent = item.snippet;
                row.appendChild(snippet);
            }

            section.appendChild(row);
        });

        container.appendChild(section);
    }

    // Updates section
    if (data.updates && data.updates.length > 0) {
        const section = document.createElement('div');
        section.className = 'search-section';

        const header = document.createElement('div');
        header.className = 'search-section-header';
        header.textContent = `Updates (${data.updates.length})`;
        section.appendChild(header);

        data.updates.forEach(update => {
            const row = document.createElement('div');
            row.className = 'search-result-update';

            const meta = document.createElement('div');
            meta.className = 'search-result-meta';
            meta.textContent = update.created_at ? new Date(update.created_at).toLocaleString() : '';
            row.appendChild(meta);

            const snippet = document.createElement('div');
            snippet.className = 'search-result-snippet';
            snippet.textContent = update.snippet || '';
            row.appendChild(snippet);

            section.appendChild(row);
        });

        container.appendChild(section);
    }
}

function renderSemanticSearchResults(data, container) {
    container.textContent = '';

    if (!data.results || data.results.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'empty-state';
        empty.textContent = 'No semantic matches found';
        container.appendChild(empty);
        return;
    }

    // Group results by type
    const items = data.results.filter(r => r.source_type === 'item');
    const decisions = data.results.filter(r => r.source_type === 'decision');
    const updates = data.results.filter(r => r.source_type === 'update');

    // Render items
    if (items.length > 0) {
        const section = document.createElement('div');
        section.className = 'search-section';

        const header = document.createElement('div');
        header.className = 'search-section-header';
        header.textContent = `Items (${items.length})`;
        section.appendChild(header);

        items.forEach(item => {
            const row = document.createElement('div');
            row.className = 'search-result-item';
            row.onclick = () => {
                closeModal('search-modal');
                openEditModal(item.source_id);
            };

            const idSpan = document.createElement('span');
            idSpan.className = 'search-result-id';
            idSpan.textContent = '#' + item.source_id;
            row.appendChild(idSpan);

            const titleSpan = document.createElement('span');
            titleSpan.className = 'search-result-title';
            titleSpan.textContent = item.title || '';
            row.appendChild(titleSpan);

            // Similarity score badge
            const simBadge = document.createElement('span');
            simBadge.className = 'search-result-similarity';
            simBadge.textContent = Math.round(item.similarity * 100) + '%';
            simBadge.title = 'Semantic similarity';
            row.appendChild(simBadge);

            if (item.type_name) {
                const typeBadge = document.createElement('span');
                typeBadge.className = 'search-result-type type-' + item.type_name;
                typeBadge.textContent = item.type_name;
                row.appendChild(typeBadge);
            }

            if (item.status_name) {
                const statusBadge = document.createElement('span');
                statusBadge.className = 'search-result-status status-' + item.status_name;
                statusBadge.textContent = item.status_name;
                row.appendChild(statusBadge);
            }

            if (item.snippet) {
                const snippet = document.createElement('div');
                snippet.className = 'search-result-snippet';
                snippet.textContent = item.snippet;
                row.appendChild(snippet);
            }

            section.appendChild(row);
        });

        container.appendChild(section);
    }

    // Render decisions
    if (decisions.length > 0) {
        const section = document.createElement('div');
        section.className = 'search-section';

        const header = document.createElement('div');
        header.className = 'search-section-header';
        header.textContent = `Decisions (${decisions.length})`;
        section.appendChild(header);

        decisions.forEach(decision => {
            const row = document.createElement('div');
            row.className = 'search-result-item';
            if (decision.item_id) {
                row.onclick = () => {
                    closeModal('search-modal');
                    openEditModal(decision.item_id);
                };
            }

            const idSpan = document.createElement('span');
            idSpan.className = 'search-result-id';
            idSpan.textContent = 'D#' + decision.source_id;
            row.appendChild(idSpan);

            const titleSpan = document.createElement('span');
            titleSpan.className = 'search-result-title';
            titleSpan.textContent = decision.title || '';
            row.appendChild(titleSpan);

            const simBadge = document.createElement('span');
            simBadge.className = 'search-result-similarity';
            simBadge.textContent = Math.round(decision.similarity * 100) + '%';
            row.appendChild(simBadge);

            section.appendChild(row);
        });

        container.appendChild(section);
    }

    // Render updates
    if (updates.length > 0) {
        const section = document.createElement('div');
        section.className = 'search-section';

        const header = document.createElement('div');
        header.className = 'search-section-header';
        header.textContent = `Updates (${updates.length})`;
        section.appendChild(header);

        updates.forEach(update => {
            const row = document.createElement('div');
            row.className = 'search-result-update';

            const meta = document.createElement('div');
            meta.className = 'search-result-meta';
            const simText = Math.round(update.similarity * 100) + '% match';
            const dateText = update.created_at ? new Date(update.created_at).toLocaleString() : '';
            meta.textContent = dateText ? `${simText} • ${dateText}` : simText;
            row.appendChild(meta);

            const snippet = document.createElement('div');
            snippet.className = 'search-result-snippet';
            snippet.textContent = update.snippet || '';
            row.appendChild(snippet);

            section.appendChild(row);
        });

        container.appendChild(section);
    }
}

// Export for testing (CommonJS for Jest compatibility)
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        // State
        getProjectTags: () => projectTags,
        setProjectTags: (tags) => { projectTags = tags; },
        getActiveTagFilters: () => activeTagFilters,
        setActiveTagFilters: (filters) => { activeTagFilters = filters; },
        getTagFilterMode: () => tagFilterMode,
        setTagFilterMode,
        getCurrentEditItemId: () => currentEditItemId,
        setCurrentEditItemId: (id) => { currentEditItemId = id; },
        getActiveEpicFilter: () => activeEpicFilter,
        setActiveEpicFilter: (filter) => { activeEpicFilter = filter; },

        // Tag management
        loadProjectTags,
        toggleTagFilter,
        applyTagFilters,
        updateFilterUI,
        clearTagFilters,
        setupTagInput,
        isTagOnItem,
        addTagToCurrentItem,
        removeTagFromCurrentItem,
        loadItemTags,

        // Epic/hierarchy
        loadEpicsForDropdown,
        loadItemChildren,
        filterByEpic,
        applyEpicFilter,
        updateEpicFilterUI,
        clearEpicFilter,

        // Relationship filter
        getActiveRelationshipFilter: () => activeRelationshipFilter,
        setActiveRelationshipFilter: (filter) => { activeRelationshipFilter = filter; },
        filterByRelationship,
        applyRelationshipFilter,
        updateRelationshipFilterUI,
        clearRelationshipFilter,

        // Utilities
        escapeHtml,

        // Modal functions
        openModal,
        closeModal,

        // Toast
        showToast,

        // Item operations
        openEditModal,
        saveItem,
        openUpdateModal,
        createUpdate,
        openNewItemModal,
        createItem,

        // Project operations
        confirmDeleteProject,
        deleteProject,

        // Filter
        filterUpdates,

        // Drag and drop
        handleDropWrapper,

        // Export
        openExportModal,
        doExport,

        // Search
        openSearchModal,
        doSearch,
        renderSearchResults,

        // Decision history
        loadItemDecisions,
        addDecision,
        removeDecision
    };
}
