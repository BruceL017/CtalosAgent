"""
GitHub Adapter: 真实 GitHub API 集成
支持 issue、branch、commit、PR、merge、revert
"""
import os
from typing import Any

import httpx


class RealGitHubAdapter:
    def __init__(self, token: str | None = None):
        self.token = token or os.getenv("GITHUB_TOKEN", "")
        self.base_url = "https://api.github.com"
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self.client = httpx.AsyncClient(base_url=self.base_url, headers=self.headers, timeout=60)

    async def create_issue(self, repo: str, title: str, body: str, labels: list[str] | None = None) -> dict[str, Any]:
        try:
            response = await self.client.post(
                f"/repos/{repo}/issues",
                json={"title": title, "body": body, "labels": labels or []},
            )
            response.raise_for_status()
            data = response.json()
            return {"success": True, "issue_number": data["number"], "html_url": data["html_url"], "repo": repo}
        except httpx.HTTPStatusError as e:
            return {"success": False, "error": f"GitHub API error: {e.response.status_code} - {e.response.text}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def create_branch(self, repo: str, branch: str, from_branch: str = "main") -> dict[str, Any]:
        try:
            # Get SHA of from_branch
            ref_resp = await self.client.get(f"/repos/{repo}/git/refs/heads/{from_branch}")
            ref_resp.raise_for_status()
            sha = ref_resp.json()["object"]["sha"]

            response = await self.client.post(
                f"/repos/{repo}/git/refs",
                json={"ref": f"refs/heads/{branch}", "sha": sha},
            )
            response.raise_for_status()
            return {"success": True, "branch": branch, "sha": sha, "repo": repo}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def create_commit(self, repo: str, branch: str, message: str, files: dict[str, str]) -> dict[str, Any]:
        """files: {path: content}"""
        try:
            # Get latest commit SHA on branch
            ref_resp = await self.client.get(f"/repos/{repo}/git/refs/heads/{branch}")
            ref_resp.raise_for_status()
            latest_sha = ref_resp.json()["object"]["sha"]

            # Get base tree
            commit_resp = await self.client.get(f"/repos/{repo}/git/commits/{latest_sha}")
            commit_resp.raise_for_status()
            base_tree_sha = commit_resp.json()["tree"]["sha"]

            # Create blobs and tree
            tree_items = []
            for path, content in files.items():
                blob_resp = await self.client.post(
                    f"/repos/{repo}/git/blobs",
                    json={"content": content, "encoding": "utf-8"},
                )
                blob_resp.raise_for_status()
                tree_items.append({"path": path, "mode": "100644", "type": "blob", "sha": blob_resp.json()["sha"]})

            tree_resp = await self.client.post(
                f"/repos/{repo}/git/trees",
                json={"base_tree": base_tree_sha, "tree": tree_items},
            )
            tree_resp.raise_for_status()

            # Create commit
            new_commit_resp = await self.client.post(
                f"/repos/{repo}/git/commits",
                json={"message": message, "tree": tree_resp.json()["sha"], "parents": [latest_sha]},
            )
            new_commit_resp.raise_for_status()
            new_commit_sha = new_commit_resp.json()["sha"]

            # Update ref
            await self.client.patch(
                f"/repos/{repo}/git/refs/heads/{branch}",
                json={"sha": new_commit_sha},
            )

            return {"success": True, "commit_sha": new_commit_sha, "branch": branch, "repo": repo}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def create_pr(self, repo: str, title: str, head: str, base: str, body: str = "") -> dict[str, Any]:
        try:
            response = await self.client.post(
                f"/repos/{repo}/pulls",
                json={"title": title, "head": head, "base": base, "body": body},
            )
            response.raise_for_status()
            data = response.json()
            return {"success": True, "pr_number": data["number"], "html_url": data["html_url"], "repo": repo}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def merge_pr(self, repo: str, pr_number: int, commit_message: str = "") -> dict[str, Any]:
        try:
            response = await self.client.put(
                f"/repos/{repo}/pulls/{pr_number}/merge",
                json={"merge_method": "squash", "commit_title": commit_message},
            )
            response.raise_for_status()
            data = response.json()
            return {"success": True, "sha": data.get("sha"), "merged": data.get("merged", True), "repo": repo}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def revert_commit(self, repo: str, commit_sha: str, branch: str = "main") -> dict[str, Any]:
        try:
            response = await self.client.post(
                f"/repos/{repo}/reverts",
                json={"sha": commit_sha, "branch": branch},
            )
            response.raise_for_status()
            data = response.json()
            return {"success": True, "revert_sha": data.get("sha"), "repo": repo}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_repo_files(self, repo: str, path: str = "", ref: str = "main") -> list[dict[str, Any]]:
        try:
            response = await self.client.get(f"/repos/{repo}/contents/{path}", params={"ref": ref})
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list):
                return [{"name": item["name"], "path": item["path"], "type": item["type"]} for item in data]
            return [{"name": data["name"], "path": data["path"], "type": data["type"]}]
        except Exception as e:
            return [{"error": str(e)}]
