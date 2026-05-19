class ConfigError(Exception):
    """Bad config.yaml, missing env var, or invalid repo entry. Exit 2."""


class GitHubAuthError(Exception):
    """GitHub returned 401 — token missing or invalid. Exit 3."""


class GitHubRateLimitError(Exception):
    """GitHub rate limit exhausted. Exit 4. Carries reset_at epoch."""

    def __init__(self, reset_at: int | None = None):
        self.reset_at = reset_at
        super().__init__(f"rate limit exhausted; resets at {reset_at}")


class GitHubRepoError(Exception):
    """Per-repo error (404, 5xx, timeout, generic 403). Logged, run continues."""

    def __init__(self, repo: str, reason: str):
        self.repo = repo
        super().__init__(f"{repo}: {reason}")


class VaultError(Exception):
    """OBSIDIAN_HOME missing or not writable. Exit 5."""
