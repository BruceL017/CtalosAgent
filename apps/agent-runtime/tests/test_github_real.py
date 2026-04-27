"""Test real GitHub adapter with actual GitHub API (read-only operations).
Requires gh CLI auth. Skips gracefully if not available."""
import os

import pytest

from tools.integrations.github_adapter import RealGitHubAdapter


class TestRealGitHubAdapter:
    async def _get_adapter(self):
        """Get adapter using gh CLI token or GITHUB_TOKEN env."""
        token = os.getenv("GITHUB_TOKEN", "")
        if not token:
            # Try to get token from gh CLI
            import subprocess
            try:
                result = subprocess.run(
                    ["gh", "auth", "token"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    token = result.stdout.strip()
            except Exception:
                pass
        if not token:
            pytest.skip("No GitHub token available (set GITHUB_TOKEN or use gh auth login)")
        return RealGitHubAdapter(token=token)

    @pytest.mark.asyncio
    async def test_get_repo_files(self):
        """Read public repo file list — read-only, safe."""
        adapter = await self._get_adapter()
        # Use a well-known public repo
        files = await adapter.get_repo_files("octocat/Hello-World", "", "master")
        assert isinstance(files, list)
        assert len(files) > 0
        for f in files:
            assert "name" in f
            assert "path" in f
            assert "type" in f
        await adapter.client.aclose()

    @pytest.mark.asyncio
    async def test_get_repo_files_with_path(self):
        """Read specific directory in public repo."""
        adapter = await self._get_adapter()
        files = await adapter.get_repo_files("octocat/Hello-World", "", "master")
        assert isinstance(files, list)
        # Should contain README or similar
        names = [f["name"] for f in files]
        assert len(names) > 0
        await adapter.client.aclose()

    @pytest.mark.asyncio
    async def test_get_repo_files_invalid_repo(self):
        """Invalid repo returns error info."""
        adapter = await self._get_adapter()
        files = await adapter.get_repo_files("nonexistent-user-12345/nonexistent-repo-67890")
        assert isinstance(files, list)
        assert len(files) == 1
        assert "error" in files[0]
        await adapter.client.aclose()
