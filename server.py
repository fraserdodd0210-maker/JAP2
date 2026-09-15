import os
import httpx
import jwt

from pydantic import AnyHttpUrl
from jwt import PyJWKClient

from mcp.server import MCPServer
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.transport_security import TransportSecuritySettings


# --------------------------------------------------
# JAP SETTINGS
# --------------------------------------------------

JAP_API_URL = "https://justanotherpanel.com/api/v2"
JAP_API_KEY = os.environ.get("JAP_API_KEY")


# --------------------------------------------------
# AUTH0 SETTINGS
# --------------------------------------------------

AUTH0_DOMAIN = os.environ.get("AUTH0_DOMAIN")
AUTH0_AUDIENCE = os.environ.get("AUTH0_AUDIENCE")

if not AUTH0_DOMAIN:
    raise RuntimeError("AUTH0_DOMAIN is not configured")

if not AUTH0_AUDIENCE:
    raise RuntimeError("AUTH0_AUDIENCE is not configured")

AUTH0_ISSUER = f"https://{AUTH0_DOMAIN}/"
AUTH0_JWKS_URL = f"https://{AUTH0_DOMAIN}/.well-known/jwks.json"

jwks_client = PyJWKClient(AUTH0_JWKS_URL)


# --------------------------------------------------
# AUTH0 TOKEN VERIFIER
# --------------------------------------------------

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


# --------------------------------------------------
# MCP SERVER
# --------------------------------------------------

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


# --------------------------------------------------
# JAP API REQUEST
# --------------------------------------------------

async def jap_request(action: str, **kwargs):

    if not JAP_API_KEY:
        raise RuntimeError("JAP_API_KEY is not configured")

    payload = {
        "key": JAP_API_KEY,
        "action": action,
        **kwargs,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            JAP_API_URL,
            data=payload,
        )

        response.raise_for_status()

        return response.json()


# --------------------------------------------------
# MCP TOOLS
# --------------------------------------------------

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

    return await jap_request(
        "status",
        order=order_id,
    )


@mcp.tool()
async def place_order(
    service: int,
    link: str,
    quantity: int | None = None,
    runs: int | None = None,
    interval: int | None = None,
    comments: str | None = None,
    usernames: str | None = None,
    hashtags: str | None = None,
    hashtag: str | None = None,
    username: str | None = None,
    min_quantity: int | None = None,
    max_quantity: int | None = None,
    posts: int | None = None,
    delay: int | None = None,
    expiry: str | None = None,
    old_posts: int | None = None,
):
    """Place a new order on JAP.

    Required for almost all services (likes, comments, follows, views, etc.):
        service  -- the JAP service ID (see list_services)
        link     -- the URL of the post/profile/page to target
        quantity -- how many units to order

    Optional, only needed for specific service categories:
        runs, interval             -- drip-feed delivery (spread the order over time)
        comments                   -- newline-separated custom comments
                                       (for "custom comments" services; quantity can
                                       be omitted when comments is provided)
        usernames                  -- newline-separated usernames (for "mentions" services)
        hashtags, hashtag          -- for hashtag-targeted services
        username                   -- for services that target by username instead of link
        min_quantity, max_quantity -- for auto/subscription-style services (sent as
                                       JAP's "min"/"max" fields)
        posts                      -- for subscription services: number of posts to cover
        delay                      -- for subscription services: delay between posts (minutes)
        expiry                     -- for subscription services: expiry date (mm/dd/yyyy)
        old_posts                  -- for subscription services: include existing posts

    Returns JAP's raw response: typically {"order": <id>} on success, or
    {"error": "<message>"} if JAP rejects the order (e.g. bad service ID,
    quantity out of range, or insufficient balance).
    """

    if quantity is None and comments is None:
        raise ValueError("place_order needs either 'quantity' or 'comments'.")

    params = {
        "service": service,
        "link": link,
    }

    optional = {
        "quantity": quantity,
        "runs": runs,
        "interval": interval,
        "comments": comments,
        "usernames": usernames,
        "hashtags": hashtags,
        "hashtag": hashtag,
        "username": username,
        "min": min_quantity,
        "max": max_quantity,
        "posts": posts,
        "delay": delay,
        "expiry": expiry,
        "old_posts": old_posts,
    }
    params.update({k: v for k, v in optional.items() if v is not None})

    return await jap_request("add", **params)


# --------------------------------------------------
# TRANSPORT SECURITY
# --------------------------------------------------

security = TransportSecuritySettings(
    allowed_hosts=[
        "jap2.onrender.com",
        "jap2.onrender.com:*",
    ],
)


# --------------------------------------------------
# ASGI APPLICATION
# --------------------------------------------------

app = mcp.streamable_http_app(
    transport_security=security,
)
