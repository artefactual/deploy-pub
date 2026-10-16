"""Cookie handling shared by the sessions that log in through a web form."""

from __future__ import annotations

from http.cookiejar import Cookie
from typing import Any

from requests.cookies import RequestsCookieJar


class PlainCookieJar(RequestsCookieJar):
    """Stores Secure cookies as plain ones.

    Browsers send Secure cookies to http://localhost, which they treat as a secure
    context; requests only sends them over https, so the flag is dropped on arrival.
    """

    def set_cookie(self, cookie: Cookie, *args: Any, **kwargs: Any) -> None:
        cookie.secure = False
        super().set_cookie(cookie, *args, **kwargs)
