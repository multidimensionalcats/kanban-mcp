/**
 * Comprehensive tests for drag-drop functionality
 */

const {
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
} = require('../static/dragdrop.js');

describe('Drag and Drop Module', () => {
    // Setup DOM before each test
    beforeEach(() => {
        resetDragState();
        resetFetchMock();
        setupTestDOM();
    });

    afterEach(() => {
        resetDragState();
    });

    // ==========================================
    // TYPE_STATUSES Configuration Tests
    // ==========================================
    describe('TYPE_STATUSES configuration', () => {
        test('issue has full workflow', () => {
            expect(TYPE_STATUSES.issue).toEqual([
                'backlog', 'todo', 'in_progress', 'review', 'done', 'closed'
            ]);
        });

        test('feature has full workflow', () => {
            expect(TYPE_STATUSES.feature).toEqual([
                'backlog', 'todo', 'in_progress', 'review', 'done', 'closed'
            ]);
        });

        test('todo has simplified workflow (no review)', () => {
            expect(TYPE_STATUSES.todo).toEqual([
                'backlog', 'todo', 'in_progress', 'done'
            ]);
        });

        test('diary only has done status', () => {
            expect(TYPE_STATUSES.diary).toEqual(['done']);
        });
    });

    // ==========================================
    // isValidStatusForType Tests
    // ==========================================
    describe('isValidStatusForType', () => {
        describe('positive cases', () => {
            test('issue can go to any standard status', () => {
                expect(isValidStatusForType('issue', 'backlog')).toBe(true);
                expect(isValidStatusForType('issue', 'todo')).toBe(true);
                expect(isValidStatusForType('issue', 'in_progress')).toBe(true);
                expect(isValidStatusForType('issue', 'review')).toBe(true);
                expect(isValidStatusForType('issue', 'done')).toBe(true);
                expect(isValidStatusForType('issue', 'closed')).toBe(true);
            });

            test('todo can go to simplified workflow statuses', () => {
                expect(isValidStatusForType('todo', 'backlog')).toBe(true);
                expect(isValidStatusForType('todo', 'todo')).toBe(true);
                expect(isValidStatusForType('todo', 'in_progress')).toBe(true);
                expect(isValidStatusForType('todo', 'done')).toBe(true);
            });

            test('diary can only go to done', () => {
                expect(isValidStatusForType('diary', 'done')).toBe(true);
            });
        });

        describe('negative cases', () => {
            test('todo cannot go to review or closed', () => {
                expect(isValidStatusForType('todo', 'review')).toBe(false);
                expect(isValidStatusForType('todo', 'closed')).toBe(false);
            });

            test('diary cannot go to any status except done', () => {
                expect(isValidStatusForType('diary', 'backlog')).toBe(false);
                expect(isValidStatusForType('diary', 'todo')).toBe(false);
                expect(isValidStatusForType('diary', 'in_progress')).toBe(false);
                expect(isValidStatusForType('diary', 'review')).toBe(false);
                expect(isValidStatusForType('diary', 'closed')).toBe(false);
            });

            test('unknown type returns false for all statuses', () => {
                expect(isValidStatusForType('unknown', 'backlog')).toBe(false);
                expect(isValidStatusForType('unknown', 'done')).toBe(false);
            });

            test('invalid status returns false', () => {
                expect(isValidStatusForType('issue', 'invalid')).toBe(false);
                expect(isValidStatusForType('issue', '')).toBe(false);
            });
        });
    });

    // ==========================================
    // canDrag Tests
    // ==========================================
    describe('canDrag', () => {
        test('returns true for non-blocked card', () => {
            const card = document.querySelector('[data-item-id="1"]');
            expect(canDrag(card)).toBe(true);
        });

        test('returns false for blocked card', () => {
            const card = document.querySelector('[data-item-id="2"]');
            expect(canDrag(card)).toBe(false);
        });

        test('returns true when blocked attribute is missing', () => {
            const card = document.querySelector('[data-item-id="1"]');
            card.removeAttribute('data-blocked');
            expect(canDrag(card)).toBe(true);
        });
    });

    // ==========================================
    // handleDragStart Tests
    // ==========================================
    describe('handleDragStart', () => {
        test('sets draggedCard state for non-blocked card', () => {
            const card = document.querySelector('[data-item-id="1"]');
            const event = createDragEvent('dragstart', card);

            const result = handleDragStart(event);

            expect(result).toBe(true);
            expect(getDraggedCard()).toBe(card);
            expect(card.classList.contains('dragging')).toBe(true);
        });

        test('prevents drag for blocked card', () => {
            const card = document.querySelector('[data-item-id="2"]');
            const event = createDragEvent('dragstart', card);

            const result = handleDragStart(event);

            expect(result).toBe(false);
            expect(getDraggedCard()).toBeNull();
            expect(card.classList.contains('dragging')).toBe(false);
        });

        test('sets dataTransfer data', () => {
            const card = document.querySelector('[data-item-id="1"]');
            const event = createDragEvent('dragstart', card);

            handleDragStart(event);

            expect(event.dataTransfer.effectAllowed).toBe('move');
            expect(event.dataTransfer.getData('text/plain')).toBe('1');
        });
    });

    // ==========================================
    // handleDragEnd Tests
    // ==========================================
    describe('handleDragEnd', () => {
        test('clears dragging class and state', () => {
            const card = document.querySelector('[data-item-id="1"]');
            // First start a drag
            handleDragStart(createDragEvent('dragstart', card));
            expect(card.classList.contains('dragging')).toBe(true);

            // Then end it
            handleDragEnd(createDragEvent('dragend', card));

            expect(card.classList.contains('dragging')).toBe(false);
            expect(getDraggedCard()).toBeNull();
        });

        test('clears all drag-over states from columns', () => {
            const columns = document.querySelectorAll('.column-content');
            columns.forEach(col => col.classList.add('drag-over'));

            const card = document.querySelector('[data-item-id="1"]');
            handleDragEnd(createDragEvent('dragend', card));

            columns.forEach(col => {
                expect(col.classList.contains('drag-over')).toBe(false);
            });
        });
    });

    // ==========================================
    // handleDragOver Tests
    // ==========================================
    describe('handleDragOver', () => {
        test('adds drag-over class for valid drop target', () => {
            const card = document.querySelector('[data-item-id="1"]'); // issue
            handleDragStart(createDragEvent('dragstart', card));

            const todoColumn = document.querySelector('[data-status="todo"]');
            const event = createDragEvent('dragover', todoColumn);
            event.currentTarget = todoColumn;

            handleDragOver(event);

            expect(todoColumn.classList.contains('drag-over')).toBe(true);
            expect(event.dataTransfer.dropEffect).toBe('move');
        });

        test('does not add drag-over class for invalid drop target', () => {
            const card = document.querySelector('[data-item-id="3"]'); // diary
            handleDragStart(createDragEvent('dragstart', card));

            const todoColumn = document.querySelector('[data-status="todo"]');
            const event = createDragEvent('dragover', todoColumn);
            event.currentTarget = todoColumn;

            handleDragOver(event);

            expect(todoColumn.classList.contains('drag-over')).toBe(false);
            expect(event.dataTransfer.dropEffect).toBe('none');
        });

        test('sets dropEffect to none when no card is being dragged', () => {
            const todoColumn = document.querySelector('[data-status="todo"]');
            const event = createDragEvent('dragover', todoColumn);
            event.currentTarget = todoColumn;

            handleDragOver(event);

            expect(event.dataTransfer.dropEffect).toBe('none');
        });
    });

    // ==========================================
    // handleDragLeave Tests
    // ==========================================
    describe('handleDragLeave', () => {
        test('removes drag-over class', () => {
            const column = document.querySelector('[data-status="todo"]');
            column.classList.add('drag-over');

            const event = createDragEvent('dragleave', column);
            event.currentTarget = column;

            handleDragLeave(event);

            expect(column.classList.contains('drag-over')).toBe(false);
        });
    });

    // ==========================================
    // handleDrop Tests - Success Cases
    // ==========================================
    describe('handleDrop - success cases', () => {
        test('successfully moves card to new column', async () => {
            const card = document.querySelector('[data-item-id="1"]');
            const todoColumn = document.querySelector('[data-status="todo"]');

            handleDragStart(createDragEvent('dragstart', card));
            mockFetchSuccess({ success: true });

            const event = createDragEvent('drop', todoColumn);
            event.currentTarget = todoColumn;

            const result = await handleDrop(event, jest.fn(), fetch);

            expect(result.success).toBe(true);
            expect(result.newStatus).toBe('todo');
            expect(todoColumn.contains(card)).toBe(true);
        });

        test('calls API with correct parameters', async () => {
            const card = document.querySelector('[data-item-id="1"]');
            const todoColumn = document.querySelector('[data-status="todo"]');

            handleDragStart(createDragEvent('dragstart', card));
            mockFetchSuccess({ success: true });

            const event = createDragEvent('drop', todoColumn);
            event.currentTarget = todoColumn;

            await handleDrop(event, jest.fn(), fetch);

            expect(fetch).toHaveBeenCalledWith('/api/items/1/status', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ status: 'todo' })
            });
        });

        test('shows success toast on successful drop', async () => {
            const card = document.querySelector('[data-item-id="1"]');
            const todoColumn = document.querySelector('[data-status="todo"]');
            const showToast = jest.fn();

            handleDragStart(createDragEvent('dragstart', card));
            mockFetchSuccess({ success: true });

            const event = createDragEvent('drop', todoColumn);
            event.currentTarget = todoColumn;

            await handleDrop(event, showToast, fetch);

            expect(showToast).toHaveBeenCalledWith('Moved to todo');
        });

        test('returns noChange when dropping on same column', async () => {
            const card = document.querySelector('[data-item-id="1"]');
            const backlogColumn = document.querySelector('[data-status="backlog"]');

            handleDragStart(createDragEvent('dragstart', card));

            const event = createDragEvent('drop', backlogColumn);
            event.currentTarget = backlogColumn;

            const result = await handleDrop(event, jest.fn(), fetch);

            expect(result.success).toBe(true);
            expect(result.noChange).toBe(true);
            expect(fetch).not.toHaveBeenCalled();
        });
    });

    // ==========================================
    // handleDrop Tests - Failure Cases
    // ==========================================
    describe('handleDrop - failure cases', () => {
        test('fails when no card is being dragged', async () => {
            const todoColumn = document.querySelector('[data-status="todo"]');
            const event = createDragEvent('drop', todoColumn);
            event.currentTarget = todoColumn;

            const result = await handleDrop(event, jest.fn(), fetch);

            expect(result.success).toBe(false);
            expect(result.error).toBe('No card being dragged');
        });

        test('fails for invalid status for item type', async () => {
            const card = document.querySelector('[data-item-id="3"]'); // diary
            const todoColumn = document.querySelector('[data-status="todo"]');
            const showToast = jest.fn();

            handleDragStart(createDragEvent('dragstart', card));

            const event = createDragEvent('drop', todoColumn);
            event.currentTarget = todoColumn;

            const result = await handleDrop(event, showToast, fetch);

            expect(result.success).toBe(false);
            expect(result.error).toContain("not valid for diary");
            expect(showToast).toHaveBeenCalledWith(expect.stringContaining("not valid"), 'error');
            expect(fetch).not.toHaveBeenCalled();
        });

        test('fails when server rejects due to blocked relationship', async () => {
            const card = document.querySelector('[data-item-id="1"]');
            const doneColumn = document.querySelector('[data-status="done"]');
            const showToast = jest.fn();

            handleDragStart(createDragEvent('dragstart', card));
            mockFetchSuccess({
                success: false,
                message: 'Cannot set status: blocked by #2',
                blockers: [{ id: 2, title: 'Blocker' }]
            }, 400);

            const event = createDragEvent('drop', doneColumn);
            event.currentTarget = doneColumn;

            const result = await handleDrop(event, showToast, fetch);

            expect(result.success).toBe(false);
            expect(result.blocked).toBe(true);
            expect(result.error).toContain('blocked');
            expect(showToast).toHaveBeenCalledWith(expect.stringContaining('blocked'), 'error');
            // Card should NOT be moved
            expect(doneColumn.contains(card)).toBe(false);
        });

        test('fails on network error', async () => {
            const card = document.querySelector('[data-item-id="1"]');
            const todoColumn = document.querySelector('[data-status="todo"]');
            const showToast = jest.fn();

            handleDragStart(createDragEvent('dragstart', card));
            mockFetchError('Network error');

            const event = createDragEvent('drop', todoColumn);
            event.currentTarget = todoColumn;

            const result = await handleDrop(event, showToast, fetch);

            expect(result.success).toBe(false);
            expect(result.error).toBe('Network error');
            expect(showToast).toHaveBeenCalledWith('Network error', 'error');
            // Card should NOT be moved
            expect(todoColumn.contains(card)).toBe(false);
        });

        test('fails when server returns non-ok status', async () => {
            const card = document.querySelector('[data-item-id="1"]');
            const todoColumn = document.querySelector('[data-status="todo"]');
            const showToast = jest.fn();

            handleDragStart(createDragEvent('dragstart', card));
            global.fetch.mockResolvedValueOnce({
                ok: false,
                status: 500,
                json: () => Promise.resolve({ error: 'Internal server error' })
            });

            const event = createDragEvent('drop', todoColumn);
            event.currentTarget = todoColumn;

            const result = await handleDrop(event, showToast, fetch);

            expect(result.success).toBe(false);
            expect(showToast).toHaveBeenCalledWith(expect.any(String), 'error');
        });
    });

    // ==========================================
    // Edge Cases
    // ==========================================
    describe('edge cases', () => {
        test('diary can only be dropped on done column', async () => {
            const card = document.querySelector('[data-item-id="3"]'); // diary
            const doneColumn = document.querySelector('[data-status="done"]');

            handleDragStart(createDragEvent('dragstart', card));
            mockFetchSuccess({ success: true });

            const event = createDragEvent('drop', doneColumn);
            event.currentTarget = doneColumn;

            const result = await handleDrop(event, jest.fn(), fetch);

            expect(result.success).toBe(true);
            expect(doneColumn.contains(card)).toBe(true);
        });

        test('todo item cannot be dropped on review column', async () => {
            // Add a todo item to the DOM
            addCardToDOM('4', 'todo', 'backlog', false);
            addColumnToDOM('review');

            const card = document.querySelector('[data-item-id="4"]');
            const reviewColumn = document.querySelector('[data-status="review"]');

            handleDragStart(createDragEvent('dragstart', card));

            const event = createDragEvent('drop', reviewColumn);
            event.currentTarget = reviewColumn;

            const result = await handleDrop(event, jest.fn(), fetch);

            expect(result.success).toBe(false);
            expect(result.error).toContain("not valid for todo");
        });
    });
});

// ==========================================
// Helper Functions
// ==========================================

function setupTestDOM() {
    const boardContainer = document.createElement('div');
    boardContainer.className = 'board-container';

    // Backlog column with cards
    const backlogColumn = createColumn('backlog');
    backlogColumn.querySelector('.column-content').appendChild(
        createCard('1', 'issue', false)
    );
    backlogColumn.querySelector('.column-content').appendChild(
        createCard('2', 'feature', true) // blocked
    );
    backlogColumn.querySelector('.column-content').appendChild(
        createCard('3', 'diary', false)
    );
    boardContainer.appendChild(backlogColumn);

    // Other columns
    boardContainer.appendChild(createColumn('todo'));
    boardContainer.appendChild(createColumn('in_progress'));
    boardContainer.appendChild(createColumn('done'));

    document.body.replaceChildren(boardContainer);
}

function createColumn(status) {
    const column = document.createElement('div');
    column.className = 'column';

    const content = document.createElement('div');
    content.className = 'column-content';
    content.dataset.status = status;

    column.appendChild(content);
    return column;
}

function createCard(itemId, itemType, blocked) {
    const card = document.createElement('div');
    card.className = `card ${itemType}${blocked ? ' blocked' : ''}`;
    card.dataset.itemId = itemId;
    card.dataset.itemType = itemType;
    card.dataset.blocked = blocked ? 'true' : 'false';
    card.draggable = !blocked;

    const title = document.createElement('span');
    title.className = 'card-title';
    title.textContent = `Test ${itemType} ${itemId}`;
    card.appendChild(title);

    return card;
}

function addCardToDOM(itemId, itemType, status, blocked) {
    const column = document.querySelector(`[data-status="${status}"]`);
    if (column) {
        column.appendChild(createCard(itemId, itemType, blocked));
    }
}

function addColumnToDOM(status) {
    const boardContainer = document.querySelector('.board-container');
    if (boardContainer) {
        boardContainer.appendChild(createColumn(status));
    }
}

function createDragEvent(type, target) {
    const event = {
        type,
        target,
        currentTarget: target,
        preventDefault: jest.fn(),
        dataTransfer: {
            effectAllowed: '',
            dropEffect: '',
            data: {},
            setData(key, value) {
                this.data[key] = value;
            },
            getData(key) {
                return this.data[key] || '';
            }
        }
    };
    return event;
}
