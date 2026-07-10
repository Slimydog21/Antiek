"""Auth substrate — magic-link sessions + email-provider abstraction.

The auth seam at the API layer
(``interfaces/research/api/app.py`` middleware) reads from here:
- ``email_provider`` for outbound email (magic links, future publisher
  notifications)
- ``magic_link`` for token mint/verify + session-cookie sign/verify

Operator identity resolution itself lives in
``substrate/multi_user/auth.py`` — this module is the transport.
"""

from substrate.auth.email_provider import (
    AgentMailEmailProvider,
    EmailDeliveryFailure,
    EmailProvider,
    EmailRecord,
    MockEmailProvider,
    OutboundEmail,
    ResendEmailProvider,
    get_email_provider,
)
from substrate.auth.magic_link import (
    InvalidSessionCookie,
    InvalidToken,
    SessionClaims,
    TokenExpired,
    mint_magic_link_token,
    mint_session_cookie,
    verify_magic_link_token,
    verify_session_cookie,
)
from substrate.auth.passkeys import (
    PasskeyError,
    authentication_options,
    complete_authentication,
    complete_registration,
    delete_credential,
    list_credentials,
    registration_options,
)

__all__ = [
    "AgentMailEmailProvider",
    "EmailDeliveryFailure",
    "EmailProvider",
    "EmailRecord",
    "InvalidSessionCookie",
    "InvalidToken",
    "MockEmailProvider",
    "OutboundEmail",
    "ResendEmailProvider",
    "SessionClaims",
    "TokenExpired",
    "get_email_provider",
    "mint_magic_link_token",
    "mint_session_cookie",
    "verify_magic_link_token",
    "verify_session_cookie",
    "PasskeyError",
    "authentication_options",
    "complete_authentication",
    "complete_registration",
    "delete_credential",
    "list_credentials",
    "registration_options",
]
