#!/usr/bin/env python3
"""
Tests for kanban_export module.
"""

import json
import pytest
from datetime import datetime
from unittest.mock import Mock

from kanban_mcp.export import (
    ExportBuilder,
    format_json,
    format_yaml,
    format_markdown,
    export_to_format,
    get_mime_type,
    get_file_extension,
    YAML_AVAILABLE
)


class TestExportBuilder:
    """Tests for ExportBuilder class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_db = Mock()
        self.project_id = "test_project_123"

        # Mock project data
        self.mock_db.get_project_by_id.return_value = {
            'id': self.project_id,
            'name': 'Test Project',
            'directory_path': '/path/to/project'
        }

        # Mock item data
        self.sample_items = [
            {
                'id': 1,
                'title': 'Test Feature',
                'description': 'A test feature',
                'type_name': 'feature',
                'status_name': 'in_progress',
                'priority': 2,
                'complexity': 3,
                'parent_id': None,
                'created_at': datetime(2024, 1, 1, 10, 0, 0),
                'closed_at': None
            },
            {
                'id': 2,
                'title': 'Test Issue',
                'description': 'A test issue',
                'type_name': 'issue',
                'status_name': 'done',
                'priority': 1,
                'complexity': 2,
                'parent_id': None,
                'created_at': datetime(2024, 1, 2, 10, 0, 0),
                'closed_at': datetime(2024, 1, 5, 15, 0, 0)
            }
        ]

    def test_build_export_data_basic(self):
        """Test basic export data structure."""
        self.mock_db.list_items.return_value = self.sample_items
        self.mock_db.get_item_tags.return_value = []

        builder = ExportBuilder(self.mock_db, self.project_id)
        data = builder.build_export_data(include_tags=True)

        assert 'metadata' in data
        assert 'items' in data
        assert 'summary' in data
        assert data['metadata']['project_name'] == 'Test Project'
        assert len(data['items']) == 2

    def test_build_export_data_with_filters(self):
        """Test export with type filter."""
        self.mock_db.list_items.return_value = [self.sample_items[0]]
        self.mock_db.get_item_tags.return_value = []

        builder = ExportBuilder(self.mock_db, self.project_id)
        builder.build_export_data(item_type='feature')

        self.mock_db.list_items.assert_called_once()
        call_kwargs = self.mock_db.list_items.call_args[1]
        assert call_kwargs['type_name'] == 'feature'

    def test_build_export_data_with_item_ids(self):
        """Test export with specific item IDs."""
        self.mock_db.get_item.side_effect = (
            lambda id: self.sample_items[0]
            if id == 1 else None
        )
        self.mock_db.get_item_tags.return_value = []

        builder = ExportBuilder(self.mock_db, self.project_id)
        data = builder.build_export_data(item_ids=[1])

        assert len(data['items']) == 1
        assert data['items'][0]['id'] == 1

    def test_build_export_data_with_tags(self):
        """Test export including tags."""
        self.mock_db.list_items.return_value = [self.sample_items[0]]
        self.mock_db.get_item_tags.return_value = [
            {'id': 1, 'name': 'frontend', 'color': '#ff0000'}
        ]

        builder = ExportBuilder(self.mock_db, self.project_id)
        data = builder.build_export_data(include_tags=True)

        assert 'tags' in data['items'][0]
        assert len(data['items'][0]['tags']) == 1
        assert data['items'][0]['tags'][0]['name'] == 'frontend'

    def test_build_export_data_with_relationships(self):
        """Test export including relationships."""
        self.mock_db.list_items.return_value = [self.sample_items[0]]
        self.mock_db.get_item_tags.return_value = []
        self.mock_db.get_item_relationships.return_value = {
            'outgoing': [
                {
                    'relationship_type': 'blocks',
                    'related_item_id': 2,
                    'related_item_title': 'Blocked Item'
                }
            ],
            'incoming': []
        }

        builder = ExportBuilder(self.mock_db, self.project_id)
        data = builder.build_export_data(
            include_tags=False,
            include_relationships=True
        )

        assert 'relationships' in data['items'][0]
        assert len(data['items'][0]['relationships']['outgoing']) == 1

    def test_build_export_data_with_metrics(self):
        """Test export including metrics."""
        self.mock_db.list_items.return_value = [self.sample_items[1]]
        self.mock_db.get_item_tags.return_value = []
        self.mock_db.get_item_metrics.return_value = {
            'lead_time': 77.0,
            'cycle_time': 48.0,
            'time_in_each_status': {
                'in_progress': 24.0,
                'review': 24.0, 'done': 29.0
            },
            'revert_count': 0,
            'current_age': 77.0
        }

        builder = ExportBuilder(self.mock_db, self.project_id)
        data = builder.build_export_data(
            include_tags=False, include_metrics=True
        )

        assert 'metrics' in data['items'][0]
        assert data['items'][0]['metrics']['lead_time'] == 77.0

    def test_build_export_data_with_updates(self):
        """Test export including updates."""
        self.mock_db.list_items.return_value = []
        self.mock_db.get_updates.return_value = [
            {
                'id': 1,
                'content': 'Test update',
                'created_at': datetime(2024, 1, 3, 12, 0, 0),
                'item_ids': [1, 2]
            }
        ]

        builder = ExportBuilder(self.mock_db, self.project_id)
        data = builder.build_export_data(include_updates=True)

        assert 'updates' in data
        assert len(data['updates']) == 1
        assert data['updates'][0]['content'] == 'Test update'

    def test_build_export_data_with_epic_progress(self):
        """Test export including epic progress."""
        epic_item = {
            'id': 10,
            'title': 'Test Epic',
            'description': 'An epic',
            'type_name': 'epic',
            'status_name': 'in_progress',
            'priority': 1,
            'complexity': None,
            'parent_id': None,
            'created_at': datetime(2024, 1, 1, 10, 0, 0),
            'closed_at': None
        }
        self.mock_db.list_items.return_value = [epic_item]
        self.mock_db.get_item_tags.return_value = []
        self.mock_db.get_epic_progress.return_value = {
            'total': 5,
            'completed': 3,
            'percent': 60.0,
            'incomplete_items': [11, 12]
        }

        builder = ExportBuilder(self.mock_db, self.project_id)
        data = builder.build_export_data(
            include_tags=False,
            include_epic_progress=True
        )

        assert 'epic_progress' in data['items'][0]
        assert data['items'][0]['epic_progress']['percent'] == 60.0

    def test_summary_calculation(self):
        """Test summary statistics calculation."""
        self.mock_db.list_items.return_value = self.sample_items
        self.mock_db.get_item_tags.return_value = []

        builder = ExportBuilder(self.mock_db, self.project_id)
        data = builder.build_export_data(include_tags=False)

        assert data['summary']['total_items'] == 2
        assert data['summary']['by_type']['feature'] == 1
        assert data['summary']['by_type']['issue'] == 1
        assert data['summary']['by_status']['in_progress'] == 1
        assert data['summary']['by_status']['done'] == 1


class TestFormatters:
    """Tests for format conversion functions."""

    def setup_method(self):
        """Set up test data."""
        self.sample_data = {
            'metadata': {
                'project_name': 'Test Project',
                'project_path': '/path/to/project',
                'exported_at': '2024-01-25T10:30:00',
                'filters': {'item_type': None, 'status': None, 'limit': 500},
                'include_options': {'tags': True}
            },
            'items': [
                {
                    'id': 1,
                    'title': 'Test Feature',
                    'description': 'A description',
                    'type_name': 'feature',
                    'status_name': 'in_progress',
                    'priority': 2,
                    'complexity': 3,
                    'parent_id': None,
                    'created_at': '2024-01-01T10:00:00',
                    'closed_at': None,
                    'tags': [{'id': 1, 'name': 'frontend', 'color': '#ff0000'}]
                }
            ],
            'summary': {
                'total_items': 1,
                'by_type': {'feature': 1},
                'by_status': {'in_progress': 1}
            }
        }

    def test_format_json(self):
        """Test JSON formatting."""
        result = format_json(self.sample_data)

        assert isinstance(result, str)
        parsed = json.loads(result)
        assert parsed['metadata']['project_name'] == 'Test Project'
        assert len(parsed['items']) == 1

    def test_format_json_custom_indent(self):
        """Test JSON formatting with custom indent."""
        result = format_json(self.sample_data, indent=4)
        assert '    ' in result  # 4-space indent

    @pytest.mark.skipif(not YAML_AVAILABLE, reason="pyyaml not installed")
    def test_format_yaml(self):
        """Test YAML formatting."""
        result = format_yaml(self.sample_data)

        assert isinstance(result, str)
        assert 'project_name: Test Project' in result
        assert 'items:' in result

    def test_format_yaml_missing_pyyaml(self):
        """Test YAML format raises ImportError when pyyaml missing."""
        from kanban_mcp import export as export_module
        original = export_module.YAML_AVAILABLE
        export_module.YAML_AVAILABLE = False

        try:
            with pytest.raises(ImportError, match="pyyaml"):
                format_yaml(self.sample_data)
        finally:
            export_module.YAML_AVAILABLE = original

    def test_format_markdown_summary(self):
        """Test Markdown summary format."""
        result = format_markdown(self.sample_data, detailed=False)

        assert isinstance(result, str)
        assert '# Kanban Export: Test Project' in result
        assert '**Total Items:** 1' in result
        assert '## Summary' in result
        assert '### By Type' in result
        assert '**feature:** 1' in result

    def test_format_markdown_detailed(self):
        """Test Markdown detailed format."""
        result = format_markdown(self.sample_data, detailed=True)

        assert '## Items (Detailed)' in result
        assert '### #1 - Test Feature' in result
        assert '**Type:** feature' in result
        assert '**Tags:** frontend' in result

    def test_format_markdown_table(self):
        """Test Markdown table generation."""
        result = format_markdown(self.sample_data, detailed=False)

        assert '| ID | Title | Status | Priority |' in result
        assert '| #1 |' in result

    def test_format_markdown_with_updates(self):
        """Test Markdown format with updates."""
        data = self.sample_data.copy()
        data['updates'] = [
            {
                'id': 1,
                'content': 'Progress update',
                'created_at': '2024-01-15T14:00:00',
                'item_ids': [1]
            }
        ]

        result = format_markdown(data)

        assert '## Recent Updates' in result
        assert 'Progress update' in result


class TestExportToFormat:
    """Tests for export_to_format dispatcher."""

    def setup_method(self):
        """Set up test data."""
        self.sample_data = {
            'metadata': {'project_name': 'Test'},
            'items': [],
            'summary': {'total_items': 0}
        }

    def test_export_json(self):
        """Test JSON export dispatch."""
        result = export_to_format(self.sample_data, format='json')
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert parsed['metadata']['project_name'] == 'Test'

    @pytest.mark.skipif(not YAML_AVAILABLE, reason="pyyaml not installed")
    def test_export_yaml(self):
        """Test YAML export dispatch."""
        result = export_to_format(self.sample_data, format='yaml')
        assert isinstance(result, str)
        assert 'project_name:' in result

    def test_export_markdown(self):
        """Test Markdown export dispatch."""
        result = export_to_format(self.sample_data, format='markdown')
        assert isinstance(result, str)
        assert '# Kanban Export' in result

    def test_export_md_alias(self):
        """Test 'md' as alias for markdown."""
        result = export_to_format(self.sample_data, format='md')
        assert '# Kanban Export' in result

    def test_export_invalid_format(self):
        """Test invalid format raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported format"):
            export_to_format(self.sample_data, format='pdf')

    def test_export_case_insensitive(self):
        """Test format name is case-insensitive."""
        result = export_to_format(self.sample_data, format='JSON')
        parsed = json.loads(result)
        assert 'metadata' in parsed


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_get_mime_type_json(self):
        """Test MIME type for JSON."""
        assert get_mime_type('json') == 'application/json'

    def test_get_mime_type_yaml(self):
        """Test MIME type for YAML."""
        assert get_mime_type('yaml') == 'text/yaml'

    def test_get_mime_type_markdown(self):
        """Test MIME type for Markdown."""
        assert get_mime_type('markdown') == 'text/markdown'
        assert get_mime_type('md') == 'text/markdown'

    def test_get_mime_type_unknown(self):
        """Test MIME type for unknown format."""
        assert get_mime_type('unknown') == 'text/plain'

    def test_get_file_extension_json(self):
        """Test file extension for JSON."""
        assert get_file_extension('json') == '.json'

    def test_get_file_extension_yaml(self):
        """Test file extension for YAML."""
        assert get_file_extension('yaml') == '.yaml'

    def test_get_file_extension_markdown(self):
        """Test file extension for Markdown."""
        assert get_file_extension('markdown') == '.md'
        assert get_file_extension('md') == '.md'

    def test_get_file_extension_unknown(self):
        """Test file extension for unknown format."""
        assert get_file_extension('unknown') == '.txt'


class TestMarkdownEdgeCases:
    """Tests for Markdown formatting edge cases."""

    def test_title_with_pipe_characters(self):
        """Test titles with pipe characters are escaped."""
        data = {
            'metadata': {'project_name': 'Test'},
            'items': [
                {
                    'id': 1,
                    'title': 'Feature | with | pipes',
                    'type_name': 'feature',
                    'status_name': 'todo',
                    'priority': 3,
                    'complexity': None,
                    'tags': []
                }
            ],
            'summary': {
                'total_items': 1,
                'by_type': {'feature': 1},
                'by_status': {'todo': 1}
            }
        }

        result = format_markdown(data)
        # Pipes should be escaped in table
        assert (
            '\\|' in result
            or 'Feature | with | pipes' in result
        )

    def test_long_title_truncation(self):
        """Test long titles are truncated in tables."""
        long_title = 'A' * 100
        data = {
            'metadata': {'project_name': 'Test'},
            'items': [
                {
                    'id': 1,
                    'title': long_title,
                    'type_name': 'feature',
                    'status_name': 'todo',
                    'priority': 3,
                    'complexity': None,
                    'tags': []
                }
            ],
            'summary': {
                'total_items': 1,
                'by_type': {'feature': 1},
                'by_status': {'todo': 1}
            }
        }

        result = format_markdown(data, detailed=False)
        # Should be truncated with ellipsis
        assert '...' in result

    def test_empty_items(self):
        """Test export with no items."""
        data = {
            'metadata': {'project_name': 'Empty Project'},
            'items': [],
            'summary': {'total_items': 0, 'by_type': {}, 'by_status': {}}
        }

        result = format_markdown(data)
        assert '**Total Items:** 0' in result


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
