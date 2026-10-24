"""Entra ID token exchange for Azure Database for PostgreSQL Flexible Server.

The Container Apps Job runs with a user-assigned managed identity. Instead of a
stored password we request a short-lived access token for the OSS RDBMS
resource and pass it as the libpq password. Tokens live ~60-90 minutes, longer
than any pipeline run in this project.
"""

from __future__ import annotations

POSTGRES_SCOPE = "https://ossrdbms-aad.database.windows.net/.default"


def postgres_access_token() -> str:
    from azure.identity import DefaultAzureCredential

    # DefaultAzureCredential honours AZURE_CLIENT_ID to pick the user-assigned identity.
    credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
    return credential.get_token(POSTGRES_SCOPE).token
