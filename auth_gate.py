"""
Inbound login for the MCP endpoint: GitHub OAuth, restricted to an allowlist.

Claude's connector registers itself and signs in through GitHub. Every request
then re-checks the caller's GitHub token against the allowlist, so removing
someone from MCP_ALLOWED_GITHUB_USERS takes effect on their next call.
"""

import logging
from typing import Optional

from fastmcp.server.auth import AccessToken
from fastmcp.server.auth.oauth_proxy import OAuthProxy
from fastmcp.server.auth.providers.github import GitHubTokenVerifier

logger = logging.getLogger(__name__)

GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"


def parse_allowlist(raw: str) -> frozenset[str]:
    """Split a comma-separated list of GitHub logins or numeric user IDs."""
    return frozenset(entry.strip().lower() for entry in raw.split(",") if entry.strip())


class AllowlistGitHubVerifier(GitHubTokenVerifier):
    """GitHub token verifier that only accepts listed accounts (login or numeric ID)."""

    def __init__(self, allowed: frozenset[str], **kwargs):
        super().__init__(**kwargs)
        if not allowed:
            raise ValueError(
                "Allowlist is empty: refusing to start with no permitted users."
            )
        self.allowed = allowed

    async def verify_token(self, token: str) -> Optional[AccessToken]:
        result = await super().verify_token(token)
        if result is None:
            return None
        login = str(result.claims.get("login") or "").lower()
        user_id = str(result.claims.get("sub") or "")
        if login in self.allowed or user_id in self.allowed:
            return result
        logger.warning(
            "Rejected GitHub user %s (id %s): not in allowlist", login, user_id
        )
        return None


def build_github_gate(
    client_id: str, client_secret: str, base_url: str, allowed: frozenset[str]
) -> OAuthProxy:
    """The GitHub OAuth App's callback must be {base_url}/auth/callback."""
    return OAuthProxy(
        upstream_authorization_endpoint=GITHUB_AUTHORIZE_URL,
        upstream_token_endpoint=GITHUB_TOKEN_URL,
        upstream_client_id=client_id,
        upstream_client_secret=client_secret,
        # read:user is enough to identify the caller; FastMCP's default ("user")
        # can write the profile
        token_verifier=AllowlistGitHubVerifier(
            allowed=allowed, required_scopes=["read:user"]
        ),
        base_url=base_url,
        issuer_url=base_url,
    )
