/**
 * Drag and Drop module for Kanban board
 * Extracted for testability
 */

// Valid statuses per item type (matching kanban_mcp.py workflows)
const TYPE_STATUSES = {
    'issue': ['backlog', 'todo', 'in_progress', 'review', 'done', 'closed'],
    'feature': ['backlog', 'todo', 'in_progress', 'review', 'done', 'closed'],
    'todo': ['backlog', 'todo', 'in_progress', 'done'],
    'diary': ['done']
};

// State
let draggedCard = null;

/**
 * Check if a status is valid for an item type
 */
function isValidStatusForType(itemType, status) {
    const validStatuses = TYPE_STATUSES[itemType] || [];
    return validStatuses.includes(status);
}

/**
 * Check if an item can be dragged (not blocked)
 */
function canDrag(cardElement) {
    return cardElement.dataset.blocked !== 'true';
}

/**
 * Handle drag start event
 */
function handleDragStart(e) {
    const card = e.target.closest('.card');
    if (!card || !canDrag(card)) {
        e.preventDefault();
        return false;
    }

    draggedCard = card;
    card.classList.add('dragging');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', card.dataset.itemId);
    return true;
}

/**
 * Handle drag end event
 */
function handleDragEnd(e) {
    const card = e.target.closest('.card');
    if (card) {
        card.classList.remove('dragging');
    }
    // Clear all drag-over states
    document.querySelectorAll('.column-content.drag-over').forEach(col => {
        col.classList.remove('drag-over');
    });
    draggedCard = null;
}

/**
 * Handle drag over event
 */
function handleDragOver(e) {
    e.preventDefault();

    if (!draggedCard) {
        e.dataTransfer.dropEffect = 'none';
        return;
    }

    const dropTarget = e.currentTarget;
    const itemType = draggedCard.dataset.itemType;
    const targetStatus = dropTarget.dataset.status;

    if (isValidStatusForType(itemType, targetStatus)) {
        e.dataTransfer.dropEffect = 'move';
        dropTarget.classList.add('drag-over');
    } else {
        e.dataTransfer.dropEffect = 'none';
    }
}

/**
 * Handle drag leave event
 */
function handleDragLeave(e) {
    e.currentTarget.classList.remove('drag-over');
}

/**
 * Handle drop event
 * @param {DragEvent} e - The drop event
 * @param {Function} showToast - Toast notification function
 * @param {Function} fetchFn - Fetch function (for testing injection)
 * @returns {Promise<{success: boolean, error?: string}>}
 */
async function handleDrop(e, showToast, fetchFn = fetch) {
    e.preventDefault();

    // Capture target synchronously before any async operations
    const dropTarget = e.currentTarget;
    dropTarget.classList.remove('drag-over');

    if (!draggedCard) {
        return { success: false, error: 'No card being dragged' };
    }

    const card = draggedCard;
    const itemId = card.dataset.itemId;
    const itemType = card.dataset.itemType;
    const currentStatus = card.closest('.column-content')?.dataset.status;
    const newStatus = dropTarget.dataset.status;

    // Don't do anything if dropping on same column
    if (currentStatus === newStatus) {
        return { success: true, noChange: true };
    }

    // Validate status is allowed for item type
    if (!isValidStatusForType(itemType, newStatus)) {
        const error = `Status '${newStatus}' not valid for ${itemType}`;
        if (showToast) showToast(error, 'error');
        return { success: false, error };
    }

    try {
        const res = await fetchFn(`/api/items/${itemId}/status`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ status: newStatus })
        });
        const result = await res.json();

        if (!res.ok || !result.success) {
            const error = result.message || result.error || 'Failed to update status';
            if (showToast) showToast(error, 'error');
            return { success: false, error, blocked: !!result.blockers };
        }

        // Move card visually
        dropTarget.appendChild(card);
        if (showToast) showToast(`Moved to ${newStatus.replace('_', ' ')}`);

        return { success: true, newStatus };
    } catch (err) {
        const error = err.message || 'Network error';
        if (showToast) showToast(error, 'error');
        return { success: false, error };
    }
}

/**
 * Get the currently dragged card (for testing)
 */
function getDraggedCard() {
    return draggedCard;
}

/**
 * Reset drag state (for testing)
 */
function resetDragState() {
    draggedCard = null;
}

// Export for testing (CommonJS for Jest compatibility)
if (typeof module !== 'undefined' && module.exports) {
    module.exports = {
        TYPE_STATUSES,
        isValidStatusForType,
        canDrag,
        handleDragStart,
        handleDragEnd,
        handleDragOver,
        handleDragLeave,
        handleDrop,
        getDraggedCard,
        resetDragState
    };
}
