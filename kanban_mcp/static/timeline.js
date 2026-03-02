/**
 * Timeline drawer functionality for Kanban MCP Web UI
 *
 * Security Note: All user-generated content is escaped via textContent
 * assignment before being inserted into the DOM to prevent XSS attacks.
 */

// Timeline state
let currentTimelineView = 'project';
let currentTimelineItemId = null;
let timelineData = [];

// Activity type icons
const ACTIVITY_ICONS = {
    'status_change': 'swap_horiz',
    'decision': 'gavel',
    'update': 'comment',
    'commit': 'commit',
    'create': 'add_circle'
};

// Activity type colors
const ACTIVITY_COLORS = {
    'status_change': 'green',
    'decision': 'purple',
    'update': 'blue',
    'commit': 'orange',
    'create': 'teal'
};

/**
 * Open the timeline drawer
 * @param {number|null} itemId - Optional item ID to show item timeline
 */
function openTimelineDrawer(itemId = null) {
    const drawer = document.getElementById('timeline-drawer');
    drawer.classList.add('open');

    // Close updates drawer if open
    document.querySelector('.updates-drawer')?.classList.remove('open');

    // Show/hide item toggle based on whether we have an item context
    const itemBtn = document.getElementById('timeline-item-btn');
    if (itemId) {
        currentTimelineItemId = itemId;
        itemBtn.style.display = '';
        switchTimelineView('item');
    } else {
        currentTimelineItemId = null;
        itemBtn.style.display = 'none';
        switchTimelineView('project');
    }
}

/**
 * Close the timeline drawer
 */
function closeTimelineDrawer() {
    const drawer = document.getElementById('timeline-drawer');
    drawer.classList.remove('open');
}

/**
 * Switch between project and item timeline views
 * @param {string} view - 'project' or 'item'
 */
function switchTimelineView(view) {
    currentTimelineView = view;

    // Update toggle buttons
    document.querySelectorAll('.timeline-toggle-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.view === view);
    });

    // Update item button state
    const itemBtn = document.getElementById('timeline-item-btn');
    const itemLabel = document.getElementById('timeline-item-label');

    if (view === 'item' && currentTimelineItemId) {
        itemBtn.disabled = false;
        itemLabel.textContent = `Item #${currentTimelineItemId}`;
    }

    // Load the appropriate timeline
    if (view === 'project') {
        loadProjectTimeline();
    } else if (view === 'item' && currentTimelineItemId) {
        loadItemTimeline(currentTimelineItemId);
    }
}

/**
 * Load project timeline from API
 */
async function loadProjectTimeline() {
    if (!PROJECT_ID) {
        showTimelineEmpty('Select a project first');
        return;
    }

    showTimelineLoading(true);

    try {
        const response = await fetch(`/api/projects/${PROJECT_ID}/timeline?limit=100`);
        const data = await response.json();

        if (data.success) {
            timelineData = data.entries || [];
            renderTimeline(timelineData);
        } else {
            showTimelineEmpty(data.error || 'Failed to load timeline');
        }
    } catch (error) {
        console.error('Failed to load project timeline:', error);
        showTimelineEmpty('Error loading timeline');
    } finally {
        showTimelineLoading(false);
    }
}

/**
 * Load item timeline from API
 * @param {number} itemId - The item ID
 */
async function loadItemTimeline(itemId) {
    showTimelineLoading(true);

    try {
        const response = await fetch(`/api/items/${itemId}/timeline?limit=100`);
        const data = await response.json();

        if (data.success) {
            timelineData = data.entries || [];
            renderTimeline(timelineData);
        } else {
            showTimelineEmpty(data.error || 'Failed to load timeline');
        }
    } catch (error) {
        console.error('Failed to load item timeline:', error);
        showTimelineEmpty('Error loading timeline');
    } finally {
        showTimelineLoading(false);
    }
}

/**
 * Render timeline entries using DOM manipulation for security
 * @param {Array} entries - Timeline entries
 */
function renderTimeline(entries) {
    const container = document.getElementById('timeline-entries');
    const emptyEl = document.getElementById('timeline-empty');

    // Clear container
    container.replaceChildren();

    if (!entries || entries.length === 0) {
        emptyEl.style.display = 'block';
        return;
    }

    emptyEl.style.display = 'none';

    // Group entries by date
    const groupedByDate = {};
    entries.forEach(entry => {
        const date = entry.timestamp.split('T')[0];
        if (!groupedByDate[date]) {
            groupedByDate[date] = [];
        }
        groupedByDate[date].push(entry);
    });

    // Build DOM elements
    Object.keys(groupedByDate).sort().reverse().forEach(date => {
        const dateLabel = formatDateLabel(date);

        const dateGroup = document.createElement('div');
        dateGroup.className = 'timeline-date-group';

        const dateHeader = document.createElement('div');
        dateHeader.className = 'timeline-date-header';
        dateHeader.textContent = dateLabel;
        dateGroup.appendChild(dateHeader);

        const dateEntries = document.createElement('div');
        dateEntries.className = 'timeline-date-entries';

        groupedByDate[date].forEach(entry => {
            dateEntries.appendChild(createTimelineEntryElement(entry));
        });

        dateGroup.appendChild(dateEntries);
        container.appendChild(dateGroup);
    });

    filterTimelineByType();
}

/**
 * Create a DOM element for a timeline entry
 * @param {Object} entry - Timeline entry
 * @returns {HTMLElement} Timeline entry element
 */
function createTimelineEntryElement(entry) {
    const icon = entry.icon || ACTIVITY_ICONS[entry.activity_type] || 'radio_button_unchecked';
    const color = entry.color || ACTIVITY_COLORS[entry.activity_type] || 'grey';
    const time = formatTime(entry.timestamp);

    const entryEl = document.createElement('div');
    entryEl.className = 'timeline-entry';
    entryEl.dataset.activityType = entry.activity_type;

    // Icon
    const iconContainer = document.createElement('div');
    iconContainer.className = `timeline-entry-icon ${color}`;
    const iconEl = document.createElement('i');
    iconEl.className = 'material-icons';
    iconEl.textContent = icon;
    iconContainer.appendChild(iconEl);
    entryEl.appendChild(iconContainer);

    // Content
    const contentEl = document.createElement('div');
    contentEl.className = 'timeline-entry-content';

    // Header with time and item link
    const headerEl = document.createElement('div');
    headerEl.className = 'timeline-entry-header';

    const timeEl = document.createElement('span');
    timeEl.className = 'timeline-entry-time';
    timeEl.textContent = time;
    headerEl.appendChild(timeEl);

    if (entry.item_id) {
        const itemLink = document.createElement('span');
        itemLink.className = 'timeline-item-link';
        itemLink.textContent = `#${entry.item_id}`;
        itemLink.onclick = (e) => {
            e.stopPropagation();
            openEditModal(entry.item_id);
        };
        headerEl.appendChild(itemLink);
    }
    contentEl.appendChild(headerEl);

    // Title
    const titleEl = document.createElement('div');
    titleEl.className = 'timeline-entry-title';
    titleEl.textContent = entry.title;
    contentEl.appendChild(titleEl);

    // Details based on activity type
    if (entry.details) {
        const detailsEl = document.createElement('div');
        detailsEl.className = 'timeline-entry-details';

        if (entry.activity_type === 'commit') {
            const sha = entry.details.sha_short || entry.details.sha?.substring(0, 7) || '';
            const author = entry.details.author || '';

            const shaSpan = document.createElement('span');
            shaSpan.className = 'commit-sha';
            shaSpan.textContent = sha;
            detailsEl.appendChild(shaSpan);

            const authorSpan = document.createElement('span');
            authorSpan.className = 'commit-author';
            authorSpan.textContent = author;
            detailsEl.appendChild(authorSpan);

            contentEl.appendChild(detailsEl);
        } else if (entry.activity_type === 'decision' && entry.details.rationale) {
            const rationaleEl = document.createElement('em');
            rationaleEl.textContent = entry.details.rationale;
            detailsEl.appendChild(rationaleEl);
            contentEl.appendChild(detailsEl);
        } else if (entry.activity_type === 'update' && entry.details.content) {
            const content = entry.details.content;
            detailsEl.textContent = content.length > 100 ? content.substring(0, 100) + '...' : content;
            contentEl.appendChild(detailsEl);
        }
    }

    entryEl.appendChild(contentEl);
    return entryEl;
}

/**
 * Filter timeline by activity type based on checkboxes
 */
function filterTimelineByType() {
    const checkboxes = document.querySelectorAll('.timeline-filter-checkbox input');
    const activeTypes = [];

    checkboxes.forEach(checkbox => {
        if (checkbox.checked) {
            activeTypes.push(checkbox.dataset.filter);
        }
    });

    const entries = document.querySelectorAll('.timeline-entry');
    entries.forEach(entry => {
        const type = entry.dataset.activityType;
        entry.style.display = activeTypes.includes(type) ? '' : 'none';
    });
}

/**
 * Show/hide loading indicator
 * @param {boolean} show
 */
function showTimelineLoading(show) {
    const loading = document.getElementById('timeline-loading');
    const entries = document.getElementById('timeline-entries');
    const empty = document.getElementById('timeline-empty');

    loading.style.display = show ? 'flex' : 'none';
    if (show) {
        entries.replaceChildren();
        empty.style.display = 'none';
    }
}

/**
 * Show empty state with message
 * @param {string} message
 */
function showTimelineEmpty(message) {
    const empty = document.getElementById('timeline-empty');
    const entries = document.getElementById('timeline-entries');

    entries.replaceChildren();
    empty.textContent = message;
    empty.style.display = 'block';
}

/**
 * Format date for display
 * @param {string} dateStr - ISO date string
 * @returns {string} Formatted date
 */
function formatDateLabel(dateStr) {
    const date = new Date(dateStr);
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(yesterday.getDate() - 1);

    if (dateStr === today.toISOString().split('T')[0]) {
        return 'Today';
    } else if (dateStr === yesterday.toISOString().split('T')[0]) {
        return 'Yesterday';
    } else {
        return date.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
    }
}

/**
 * Format time for display
 * @param {string} timestamp - ISO timestamp
 * @returns {string} Formatted time
 */
function formatTime(timestamp) {
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
}

/**
 * Open timeline for a specific item (called from item modal)
 * @param {number} itemId
 */
function openItemTimeline(itemId) {
    currentTimelineItemId = itemId;
    openTimelineDrawer(itemId);
}
