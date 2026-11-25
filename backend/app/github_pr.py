from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .config import ROOT_DIR, Settings
from .models import CleanupPRResult


def _run_cmd(args: list[str], cwd: Path) -> tuple[int, str, str]:
    proc = subprocess.run(
        args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def check_gh_status() -> dict[str, str | bool]:
    if not shutil.which("gh"):
        return {"installed": False, "authenticated": False, "account": ""}
    code, out, err = _run_cmd(["gh", "auth", "status"], ROOT_DIR)
    combined = f"{out}\n{err}"
    account = ""
    for line in combined.splitlines():
        if "Logged in to github.com account" in line:
            parts = line.split("account")
            if len(parts) > 1:
                account = parts[1].strip().split()[0]
                break
    return {
        "installed": True,
        "authenticated": code == 0,
        "account": account,
    }


class GitHubPRManager:
    """Applies approved patches and creates real GitHub cleanup PRs via git + gh CLI."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def _find_git_root(self, start_dir: Path) -> Path | None:
        cur = start_dir.resolve()
        for parent in [cur, *cur.parents]:
            if (parent / ".git").exists():
                return parent
        return None

    def resolve_target_file(self, rel_path: str) -> Path:
        repo_dir = self.settings.resolved_target_repo()
        candidate = (repo_dir / rel_path).resolve()
        if not str(candidate).startswith(str(ROOT_DIR.resolve())):
            raise ValueError("Target file escapes workspace boundary")
        return candidate

    def apply_file_change(self, rel_path: str, new_content: str) -> Path:
        target = self.resolve_target_file(rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(new_content, encoding="utf-8")
        return target

    def open_cleanup_pr(
        self,
        flag_name: str,
        winning_variant: str,
        target_file: str,
        cleaned_content: str,
        cleanup_diff: str,
        verdict_brief: str,
    ) -> CleanupPRResult:
        applied_path = self.apply_file_change(target_file, cleaned_content)
        git_root = self._find_git_root(applied_path.parent)
        branch_name = f"flagpilot/cleanup-{flag_name}".replace("_", "-")[:60]

        if git_root is None:
            return CleanupPRResult(
                winning_variant=winning_variant,
                target_file=target_file,
                cleanup_diff=cleanup_diff,
                cleaned_file_content=cleaned_content,
                branch_name=branch_name,
                pr_status="preview_only",
                message=(
                    f"Updated {target_file} locally with winning variant '{winning_variant}'. "
                    "Initialize git + GitHub origin remote to push a real PR automatically."
                ),
            )

        # Check current branch & origin remote
        _, orig_branch, _ = _run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], git_root)
        code_remote, remote_url, _ = _run_cmd(["git", "remote", "get-url", "origin"], git_root)
        has_remote = code_remote == 0 and bool(remote_url)

        # Create/switch branch, commit only target file
        _run_cmd(["git", "checkout", "-B", branch_name], git_root)
        rel_to_git = applied_path.relative_to(git_root)
        _run_cmd(["git", "add", str(rel_to_git)], git_root)
        commit_code, commit_out, commit_err = _run_cmd(
            ["git", "commit", "-m", f"chore(flags): promote {winning_variant} & remove {flag_name}"],
            git_root,
        )

        if commit_code != 0 and "nothing to commit" not in f"{commit_out}{commit_err}".lower():
            if orig_branch:
                _run_cmd(["git", "checkout", orig_branch], git_root)
            return CleanupPRResult(
                winning_variant=winning_variant,
                target_file=target_file,
                cleanup_diff=cleanup_diff,
                cleaned_file_content=cleaned_content,
                branch_name=branch_name,
                pr_status="preview_only",
                message=f"File updated locally; git commit skipped: {commit_err or commit_out}",
            )

        pr_url = ""
        pr_status = "local_branch_committed"
        msg = f"Committed cleanup branch '{branch_name}' locally."

        if has_remote and shutil.which("gh"):
            push_code, _, push_err = _run_cmd(["git", "push", "-u", "origin", branch_name, "--force"], git_root)
            if push_code == 0:
                pr_body = (
                    f"## FlagPilot Automated Cleanup PR\n\n"
                    f"- **Flag Removed:** `{flag_name}`\n"
                    f"- **Winning Variant Promoted:** `{winning_variant}`\n"
                    f"- **Bayesian Verdict:** {verdict_brief}\n\n"
                    f"Approved via FlagPilot Human Gate #2."
                )
                pr_args = [
                    "gh",
                    "pr",
                    "create",
                    "--title",
                    f"chore(flags): remove '{flag_name}' and keep '{winning_variant}'",
                    "--body",
                    pr_body,
                    "--head",
                    branch_name,
                ]
                if self.settings.github_repo.strip():
                    pr_args.extend(["--repo", self.settings.github_repo.strip()])
                pr_code, pr_out, pr_err = _run_cmd(pr_args, git_root)
                if pr_code == 0 and pr_out.startswith("http"):
                    pr_url = pr_out.splitlines()[-1].strip()
                    pr_status = "opened_github_pr"
                    msg = f"Opened real GitHub Pull Request: {pr_url}"
                else:
                    msg = f"Pushed branch '{branch_name}' to origin; gh pr create note: {pr_err or pr_out}"
            else:
                msg = f"Committed locally on '{branch_name}' (push failed: {push_err})"

        # Return to original branch while leaving the branch/PR intact
        if orig_branch and orig_branch != "HEAD":
            _run_cmd(["git", "checkout", orig_branch], git_root)

        return CleanupPRResult(
            winning_variant=winning_variant,
            target_file=target_file,
            cleanup_diff=cleanup_diff,
            cleaned_file_content=cleaned_content,
            branch_name=branch_name,
            pr_url=pr_url,
            pr_status=pr_status,  # type: ignore[arg-type]
            message=msg,
        )
