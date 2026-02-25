#!/usr/bin/env python3
"""Git timeline provider for kanban-mcp.

Provides git commit history for timeline integration.
"""

import re
import time
import logging
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class GitTimelineProvider:
    """Provides git commit data for timeline integration.

    Features:
    - Get all commits on current branch
    - Parse item IDs from commit messages (e.g., #123, fixes #456)
    - Get commits for files linked to items
    - LRU caching with 5-minute TTL
    """

    # Pattern to match item references in commit messages: #123, fixes #456, etc.
    ITEM_REF_PATTERN = re.compile(r'#(\d+)')

    # Cache TTL in seconds
    CACHE_TTL = 300  # 5 minutes

    def __init__(self, repo_path: str = None):
        """Initialize git provider.

        Args:
            repo_path: Path to git repository. If None, will be set later via set_repo_path.
        """
        self._repo = None
        self._repo_path = repo_path
        self._cache_timestamp: Dict[str, float] = {}

        if repo_path:
            self._init_repo()

    def _init_repo(self) -> bool:
        """Initialize the git repository object.

        Returns:
            True if repo initialized successfully, False otherwise.
        """
        if not self._repo_path:
            return False

        try:
            import git
            self._repo = git.Repo(self._repo_path)
            return True
        except Exception as e:
            logger.warning(f"Failed to initialize git repo at {self._repo_path}: {e}")
            self._repo = None
            return False

    def set_repo_path(self, repo_path: str) -> bool:
        """Set or update the repository path.

        Args:
            repo_path: Path to git repository

        Returns:
            True if valid git repo, False otherwise
        """
        self._repo_path = repo_path
        self._clear_cache()
        return self._init_repo()

    def is_valid(self) -> bool:
        """Check if this is a valid git repository."""
        return self._repo is not None

    def _clear_cache(self):
        """Clear all cached data."""
        self._cache_timestamp.clear()
        # Clear the lru_cache functions
        self._get_commits_cached.cache_clear()

    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cache entry is still valid."""
        if cache_key not in self._cache_timestamp:
            return False
        age = time.time() - self._cache_timestamp[cache_key]
        return age < self.CACHE_TTL

    @lru_cache(maxsize=32)
    def _get_commits_cached(self, branch: str, since_timestamp: float, limit: int) -> tuple:
        """Cached commit fetching (returns tuple for hashability)."""
        if not self._repo:
            return tuple()

        try:
            commits = []
            for commit in self._repo.iter_commits(branch, max_count=limit):
                # Filter by since timestamp if provided
                if since_timestamp and commit.authored_date < since_timestamp:
                    continue

                commits.append({
                    'sha': commit.hexsha,
                    'sha_short': commit.hexsha[:7],
                    'message': commit.message.strip(),
                    'summary': commit.summary,
                    'author': commit.author.name,
                    'author_email': commit.author.email,
                    'timestamp': datetime.fromtimestamp(commit.authored_date),
                    'files': list(commit.stats.files.keys()) if hasattr(commit.stats, 'files') else []
                })
            return tuple(commits)
        except Exception as e:
            logger.warning(f"Failed to get commits: {e}")
            return tuple()

    def get_project_commits(self, since: datetime = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Get commits from the current branch.

        Args:
            since: Only include commits after this date
            limit: Maximum number of commits to return

        Returns:
            List of commit dicts with sha, message, author, timestamp, files
        """
        if not self._repo:
            return []

        try:
            branch = self._repo.active_branch.name
        except Exception:
            branch = 'HEAD'

        since_ts = since.timestamp() if since else 0
        cache_key = f"project:{branch}:{since_ts}:{limit}"

        # Check if we need to refresh cache
        if not self._is_cache_valid(cache_key):
            self._get_commits_cached.cache_clear()
            self._cache_timestamp[cache_key] = time.time()

        commits = self._get_commits_cached(branch, since_ts, limit)
        return list(commits)

    def get_item_commits(self, item_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Get commits that reference a specific item ID.

        Searches commit messages for patterns like #123, fixes #123, etc.

        Args:
            item_id: The item ID to search for
            limit: Maximum number of commits to search through

        Returns:
            List of matching commit dicts
        """
        if not self._repo:
            return []

        all_commits = self.get_project_commits(limit=limit * 2)  # Get more to filter
        matching = []

        for commit in all_commits:
            # Search for item references in commit message
            refs = self.ITEM_REF_PATTERN.findall(commit['message'])
            if str(item_id) in refs:
                commit_copy = dict(commit)
                commit_copy['matched_ref'] = f'#{item_id}'
                matching.append(commit_copy)

                if len(matching) >= limit:
                    break

        return matching

    def get_file_commits(self, file_path: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Get commits that touched a specific file.

        Args:
            file_path: Relative path to the file
            limit: Maximum number of commits to return

        Returns:
            List of commit dicts that modified the file
        """
        if not self._repo:
            return []

        try:
            commits = []
            for commit in self._repo.iter_commits(paths=file_path, max_count=limit):
                commits.append({
                    'sha': commit.hexsha,
                    'sha_short': commit.hexsha[:7],
                    'message': commit.message.strip(),
                    'summary': commit.summary,
                    'author': commit.author.name,
                    'author_email': commit.author.email,
                    'timestamp': datetime.fromtimestamp(commit.authored_date),
                    'file_path': file_path
                })
            return commits
        except Exception as e:
            logger.warning(f"Failed to get commits for file {file_path}: {e}")
            return []

    def get_commits_for_linked_files(self, file_paths: List[str], limit: int = 20) -> List[Dict[str, Any]]:
        """Get commits for multiple linked files, merged and sorted by date.

        Args:
            file_paths: List of relative file paths
            limit: Maximum total commits to return

        Returns:
            List of commit dicts, sorted by timestamp descending
        """
        if not file_paths:
            return []

        all_commits = []
        seen_shas = set()

        for file_path in file_paths:
            commits = self.get_file_commits(file_path, limit=limit // len(file_paths) + 1)
            for commit in commits:
                if commit['sha'] not in seen_shas:
                    seen_shas.add(commit['sha'])
                    all_commits.append(commit)

        # Sort by timestamp descending
        all_commits.sort(key=lambda c: c['timestamp'], reverse=True)
        return all_commits[:limit]

    def parse_item_refs_from_message(self, message: str) -> List[int]:
        """Extract item IDs referenced in a commit message.

        Args:
            message: The commit message to parse

        Returns:
            List of unique item IDs found in the message
        """
        refs = self.ITEM_REF_PATTERN.findall(message)
        return sorted(set(int(ref) for ref in refs))
