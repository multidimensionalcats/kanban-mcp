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

// Load project tags on page load
async function loadProjectTags() {
    if (!PROJECT_ID) return;
    try {
        const res = await fetch(`/api/tags?project=${PROJECT_ID}`);
        const data = await res.json();
        projectTags = data.tags || [];
        // Show filter bar if there are tags
        const filterBar = document.getElementById('tag-filter-bar');
        if (filterBar && projectTags.length > 0) {
            filterBar.style.display = 'flex';
        }
    } catch (err) {
        console.error('Failed to load tags', err);
    }
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
    const filterBar = document.getElementById('tag-filter-bar');

    if (activeTagFilters.length === 0) {
        cards.forEach(card => card.style.display = '');
        if (filterBar) filterBar.style.display = projectTags.length > 0 ? 'flex' : 'none';
        updateFilterUI();
        return;
    }

    // Show filter bar when filtering
    if (filterBar) filterBar.style.display = 'flex';

    cards.forEach(card => {
        const tagBadges = card.querySelectorAll('.tag-badge');
        const itemTags = Array.from(tagBadges).map(b => b.dataset.tagName);

        let matches = false;
        if (tagFilterMode === 'any') {
            matches = activeTagFilters.some(tag => itemTags.includes(tag));
        } else {
            matches = activeTagFilters.every(tag => itemTags.includes(tag));
        }

        card.style.display = matches ? '' : 'none';
    });

    updateFilterUI();
}

// Update the filter bar UI - uses escapeHtml for user content
function updateFilterUI() {
    const activeDisplay = document.getElementById('active-filters');
    if (!activeDisplay) return;

    if (activeTagFilters.length === 0) {
        activeDisplay.textContent = '';
        const span = document.createElement('span');
        span.style.color = 'var(--text-disabled)';
        span.textContent = 'Click tags on cards to filter';
        activeDisplay.appendChild(span);
    } else {
        activeDisplay.textContent = '';
        activeTagFilters.forEach(tag => {
            const tagInfo = projectTags.find(t => t.name === tag);
            const color = tagInfo ? tagInfo.color : '#666';
            const badge = document.createElement('span');
            badge.className = 'tag-badge';
            badge.style.cssText = `background: ${color}20; color: ${color}; border: 1px solid ${color}40;`;
            badge.onclick = () => toggleTagFilter(tag);
            badge.textContent = tag + ' ';
            const icon = document.createElement('i');
            icon.className = 'material-icons';
            icon.style.fontSize = '12px';
            icon.textContent = 'close';
            badge.appendChild(icon);
            activeDisplay.appendChild(badge);
        });
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

// Clear all tag filters
function clearTagFilters() {
    activeTagFilters = [];
    applyTagFilters();
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

        // Load tags for this item
        await loadItemTags(itemId);
        setupTagInput('edit-tags-input', 'edit-tags-suggestions');

        openModal('edit-modal');
    } catch (err) {
        showToast(err.message, 'error');
    }
}

async function saveItem() {
    const itemId = document.getElementById('edit-id').value;
    const complexityVal = document.getElementById('edit-complexity').value;
    const data = {
        title: document.getElementById('edit-title').value,
        description: document.getElementById('edit-description').value,
        priority: parseInt(document.getElementById('edit-priority').value),
        complexity: complexityVal ? parseInt(complexityVal) : null,
        status: document.getElementById('edit-status').value
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

// --- Create Item ---
function openNewItemModal() {
    document.getElementById('newitem-title').value = '';
    document.getElementById('newitem-description').value = '';
    document.getElementById('newitem-type').value = 'issue';
    document.getElementById('newitem-priority').value = '3';
    document.getElementById('newitem-complexity').value = '';
    openModal('newitem-modal');
}

async function createItem() {
    const title = document.getElementById('newitem-title').value.trim();
    if (!title) {
        showToast('Title is required', 'error');
        return;
    }

    const complexityVal = document.getElementById('newitem-complexity').value;
    const data = {
        project_id: PROJECT_ID,
        type: document.getElementById('newitem-type').value,
        title: title,
        description: document.getElementById('newitem-description').value,
        priority: parseInt(document.getElementById('newitem-priority').value),
        complexity: complexityVal ? parseInt(complexityVal) : null
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
        handleDropWrapper
    };
}
