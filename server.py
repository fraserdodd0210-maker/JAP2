import os
import httpx
import jwt

from pydantic import AnyHttpUrl
from jwt import PyJWKClient

from mcp.server import MCPServer
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings


JAP_API_URL = "https://justanotherpanel.com/api/v2"
JAP_API_KEY = os.environ.get("JAP_API_KEY")

AUTH0_DOMAIN = os.environ.get("AUTH0_DOMAIN")
AUTH0_AUDIENCE = os.environ.get("AUTH0_AUDIENCE")

if not AUTH0_DOMAIN:
    raise RuntimeError("AUTH0_DOMAIN is not configured")

if not AUTH0_AUDIENCE:
    raise RuntimeError("AUTH0_AUDIENCE is not configured")

AUTH0_ISSUER = f"https://{AUTH0_DOMAIN}/"
AUTH0_JWKS_URL = f"https://{AUTH0_DOMAIN}/.well-known/jwks.json"

jwks_client = PyJWKClient(AUTH0_JWKS_URL)


class Auth0TokenVerifier(TokenVerifier):
    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            signing_key = jwks_client.get_signing_key_from_jwt(token)

            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=AUTH0_AUDIENCE,
                issuer=AUTH0_ISSUER,
            )

            scopes = payload.get("scope", "").split()

            client_id = (
                payload.get("azp")
                or payload.get("client_id")
                or "auth0-client"
            )

            return AccessToken(
                token=token,
                client_id=client_id,
                scopes=scopes,
                expires_at=payload.get("exp"),
                resource=AUTH0_AUDIENCE,
                subject=payload.get("sub"),
                claims=payload,
            )

        except Exception as exc:
            print(
                f"Token verification failed: {type(exc).__name__}: {exc}",
                flush=True,
            )
            return None


mcp = MCPServer(
    "JAP Connector",
    token_verifier=Auth0TokenVerifier(),
    auth=AuthSettings(
        issuer_url=AnyHttpUrl(AUTH0_ISSUER),
        resource_server_url=AnyHttpUrl(AUTH0_AUDIENCE),
        required_scopes=[],
        validate_token_resource=False,
    ),
)


async def jap_request(action: str, **kwargs):
    if not JAP_API_KEY:
        raise RuntimeError("JAP_API_KEY is not configured")

    payload = {
        "key": JAP_API_KEY,
        "action": action,
        **kwargs,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(JAP_API_URL, data=payload)
        response.raise_for_status()
        return response.json()


@mcp.tool()
async def get_balance():
    """Get the current JAP account balance."""
    return await jap_request("balance")


@mcp.tool()
async def list_services():
    """List the services available on the JAP account."""
    return await jap_request("services")


@mcp.tool()
async def get_order_status(order_id: int):
    """Get the status of an existing JAP order."""
    return await jap_request("status", order=order_id)


app = mcp.streamable_http_app()
