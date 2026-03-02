/**
 * Tests for timeline.js — Activity panel consolidation (#7540)
 */

// Setup DOM before requiring module
function setupTimelineDOM() {
    // Using DOM manipulation instead of innerHTML for security best practices
    document.body.replaceChildren();

    const drawer = document.createElement('div');
    drawer.id = 'timeline-drawer';
    drawer.className = 'timeline-drawer';

    const header = document.createElement('div');
    header.className = 'drawer-header';
    const title = document.createElement('span');
    title.className = 'drawer-title';
    title.textContent = 'Activity';
    header.appendChild(title);
    drawer.appendChild(header);

    const toggleBar = document.createElement('div');
    toggleBar.className = 'timeline-toggle-bar';
    const projBtn = document.createElement('button');
    projBtn.className = 'timeline-toggle-btn active';
    projBtn.dataset.view = 'project';
    toggleBar.appendChild(projBtn);
    const itemBtn = document.createElement('button');
    itemBtn.className = 'timeline-toggle-btn';
    itemBtn.dataset.view = 'item';
    itemBtn.id = 'timeline-item-btn';
    itemBtn.disabled = true;
    const itemLabel = document.createElement('span');
    itemLabel.id = 'timeline-item-label';
    itemLabel.textContent = 'Item';
    itemBtn.appendChild(itemLabel);
    toggleBar.appendChild(itemBtn);
    drawer.appendChild(toggleBar);

    const filterBar = document.createElement('div');
    filterBar.className = 'timeline-filter-bar';
    ['status_change', 'decision', 'update', 'commit'].forEach(type => {
        const label = document.createElement('label');
        label.className = 'timeline-filter-checkbox';
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.checked = true;
        checkbox.dataset.filter = type;
        label.appendChild(checkbox);
        filterBar.appendChild(label);
    });
    drawer.appendChild(filterBar);

    const newUpdate = document.createElement('div');
    newUpdate.className = 'activity-new-update';
    newUpdate.id = 'activity-new-update';
    newUpdate.style.display = 'none';
    const textarea = document.createElement('textarea');
    textarea.id = 'activity-update-content';
    newUpdate.appendChild(textarea);
    const select = document.createElement('select');
    select.id = 'activity-update-items';
    select.multiple = true;
    newUpdate.appendChild(select);
    const submitBtn = document.createElement('button');
    submitBtn.id = 'activity-update-submit';
    newUpdate.appendChild(submitBtn);
    const cancelBtn = document.createElement('button');
    cancelBtn.id = 'activity-update-cancel';
    newUpdate.appendChild(cancelBtn);
    drawer.appendChild(newUpdate);

    const searchWrapper = document.createElement('div');
    searchWrapper.className = 'search-input-wrapper';
    const searchInput = document.createElement('input');
    searchInput.type = 'text';
    searchInput.id = 'activity-search';
    searchWrapper.appendChild(searchInput);
    drawer.appendChild(searchWrapper);

    const content = document.createElement('div');
    content.className = 'drawer-content';
    content.id = 'timeline-content';
    const loading = document.createElement('div');
    loading.className = 'timeline-loading';
    loading.id = 'timeline-loading';
    loading.style.display = 'none';
    content.appendChild(loading);
    const entries = document.createElement('div');
    entries.className = 'timeline-entries';
    entries.id = 'timeline-entries';
    content.appendChild(entries);
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.id = 'timeline-empty';
    empty.style.display = 'none';
    content.appendChild(empty);
    drawer.appendChild(content);

    document.body.appendChild(drawer);
}

// Mock global PROJECT_ID
global.PROJECT_ID = 'test-project-id';
global.openEditModal = jest.fn();

beforeEach(() => {
    resetFetchMock();
    setupTimelineDOM();
});

// Require the module (will need exports added in Step 5)
const timeline = require('../kanban_mcp/static/timeline.js');

describe('Timeline Module — Activity Panel Consolidation', () => {

    // ==========================================
    // Removed Truncation Tests
    // ==========================================
    describe('Update entry content display', () => {
        test('shows full content for long updates (no truncation)', () => {
            const longContent = 'A'.repeat(500);
            const entry = {
                activity_type: 'update',
                timestamp: '2026-03-01T10:00:00',
                title: 'Test update',
                details: { content: longContent }
            };
            const el = timeline.createTimelineEntryElement(entry);
            // Full content should appear, no ellipsis
            expect(el.textContent).toContain(longContent);
            expect(el.textContent).not.toContain('...');
        });

        test('short content unchanged', () => {
            const shortContent = 'Quick fix applied';
            const entry = {
                activity_type: 'update',
                timestamp: '2026-03-01T10:00:00',
                title: 'Short update',
                details: { content: shortContent }
            };
            const el = timeline.createTimelineEntryElement(entry);
            expect(el.textContent).toContain(shortContent);
        });

        test('empty content handled without crash', () => {
            const entry = {
                activity_type: 'update',
                timestamp: '2026-03-01T10:00:00',
                title: 'Empty update',
                details: { content: '' }
            };
            expect(() => {
                timeline.createTimelineEntryElement(entry);
            }).not.toThrow();
        });
    });

    // ==========================================
    // Text Search Tests
    // ==========================================
    describe('filterActivityEntries', () => {
        function renderTestEntries() {
            const entries = [
                {
                    activity_type: 'status_change',
                    timestamp: '2026-03-01T10:00:00',
                    title: 'Moved to deploy',
                    details: {}
                },
                {
                    activity_type: 'update',
                    timestamp: '2026-03-01T11:00:00',
                    title: 'Added note',
                    details: { content: 'Fixed the login bug' }
                },
                {
                    activity_type: 'commit',
                    timestamp: '2026-03-01T12:00:00',
                    title: 'Refactored auth module',
                    details: { sha_short: 'abc1234', author: 'dev' }
                }
            ];
            timeline.renderTimeline(entries);
        }

        test('matches title text', () => {
            renderTestEntries();
            timeline.filterActivityEntries('deploy');
            const visible = document.querySelectorAll('.timeline-entry:not([style*="display: none"])');
            const hidden = document.querySelectorAll('.timeline-entry[style*="display: none"]');
            expect(visible.length).toBe(1);
            expect(hidden.length).toBe(2);
        });

        test('matches update content text', () => {
            renderTestEntries();
            timeline.filterActivityEntries('login bug');
            const visible = document.querySelectorAll('.timeline-entry:not([style*="display: none"])');
            expect(visible.length).toBe(1);
        });

        test('case insensitive search', () => {
            renderTestEntries();
            timeline.filterActivityEntries('DEPLOY');
            const visible = document.querySelectorAll('.timeline-entry:not([style*="display: none"])');
            expect(visible.length).toBe(1);
        });

        test('empty query shows all entries', () => {
            renderTestEntries();
            timeline.filterActivityEntries('');
            const visible = document.querySelectorAll('.timeline-entry:not([style*="display: none"])');
            expect(visible.length).toBe(3);
        });

        test('no matches hides all entries', () => {
            renderTestEntries();
            timeline.filterActivityEntries('zzzznonexistent');
            const hidden = document.querySelectorAll('.timeline-entry[style*="display: none"]');
            expect(hidden.length).toBe(3);
        });
    });

    // ==========================================
    // Inline Update Form Tests
    // ==========================================
    describe('toggleActivityNewUpdate', () => {
        test('shows form when toggled', () => {
            // Mock the fetch for items list
            mockFetchSuccess({ items: [{ id: 1, title: 'Test Item' }] });
            timeline.toggleActivityNewUpdate();
            const form = document.getElementById('activity-new-update');
            expect(form.style.display).not.toBe('none');
        });

        test('hides form when toggled twice', () => {
            mockFetchSuccess({ items: [{ id: 1, title: 'Test Item' }] });
            timeline.toggleActivityNewUpdate();
            timeline.toggleActivityNewUpdate();
            const form = document.getElementById('activity-new-update');
            expect(form.style.display).toBe('none');
        });

        test('populates item selector via fetch', async () => {
            mockFetchSuccess({ items: [
                { id: 1, title: 'Item One' },
                { id: 2, title: 'Item Two' }
            ]});
            timeline.toggleActivityNewUpdate();
            // Wait for async fetch
            await new Promise(r => setTimeout(r, 10));
            const select = document.getElementById('activity-update-items');
            expect(select.options.length).toBeGreaterThanOrEqual(2);
        });
    });

    describe('createActivityUpdate', () => {
        test('posts to API with correct body', async () => {
            mockFetchSuccess({ success: true, update_id: 1 });
            // Also mock the timeline reload
            mockFetchSuccess({ success: true, entries: [] });

            const textarea = document.getElementById('activity-update-content');
            textarea.value = 'New update from activity panel';

            await timeline.createActivityUpdate();

            expect(fetch).toHaveBeenCalledWith('/api/updates', expect.objectContaining({
                method: 'POST',
                body: expect.any(String)
            }));
            const callBody = JSON.parse(fetch.mock.calls[0][1].body);
            expect(callBody.content).toBe('New update from activity panel');
            expect(callBody.project_id).toBe('test-project-id');
        });

        test('reloads timeline after successful post', async () => {
            mockFetchSuccess({ success: true, update_id: 1 });
            mockFetchSuccess({ success: true, entries: [] });

            const textarea = document.getElementById('activity-update-content');
            textarea.value = 'Update content';

            await timeline.createActivityUpdate();

            // Second fetch call should be the timeline reload
            expect(fetch.mock.calls.length).toBeGreaterThanOrEqual(2);
        });

        test('empty content rejected without fetch', async () => {
            const textarea = document.getElementById('activity-update-content');
            textarea.value = '';

            await timeline.createActivityUpdate();

            expect(fetch).not.toHaveBeenCalled();
        });

        test('no page reload after update', async () => {
            const reloadMock = jest.fn();
            Object.defineProperty(window, 'location', {
                value: { ...window.location, reload: reloadMock },
                writable: true,
                configurable: true
            });

            mockFetchSuccess({ success: true, update_id: 1 });
            mockFetchSuccess({ success: true, entries: [] });

            const textarea = document.getElementById('activity-update-content');
            textarea.value = 'No reload test';

            await timeline.createActivityUpdate();

            expect(reloadMock).not.toHaveBeenCalled();
        });
    });

    // ==========================================
    // Search + Type Filter Combination
    // ==========================================
    describe('Search and type filter combination', () => {
        test('search and type filter combine correctly', () => {
            const entries = [
                {
                    activity_type: 'commit',
                    timestamp: '2026-03-01T10:00:00',
                    title: 'Deploy fix',
                    details: { sha_short: 'abc1234', author: 'dev' }
                },
                {
                    activity_type: 'status_change',
                    timestamp: '2026-03-01T11:00:00',
                    title: 'Deploy status change',
                    details: {}
                },
                {
                    activity_type: 'update',
                    timestamp: '2026-03-01T12:00:00',
                    title: 'Other update',
                    details: { content: 'Unrelated' }
                }
            ];
            timeline.renderTimeline(entries);

            // Uncheck commits
            const commitCheckbox = document.querySelector('[data-filter="commit"]');
            commitCheckbox.checked = false;
            timeline.filterTimelineByType();

            // Now search for "deploy"
            timeline.filterActivityEntries('deploy');

            // Only the status_change entry matching "deploy" should be visible
            // The commit is hidden by type filter, the update doesn't match search
            const allEntries = document.querySelectorAll('.timeline-entry');
            let visibleCount = 0;
            allEntries.forEach(e => {
                if (e.style.display !== 'none') visibleCount++;
            });
            expect(visibleCount).toBe(1);
        });
    });
});
