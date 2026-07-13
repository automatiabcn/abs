# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""GET /v1/email/unsubscribe?token=...

Verifies the JWT (license_jti) and marks every kind of queued email as
unsubscribed. Answers with a plain HTML page, since this is opened straight
from a mail client.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse

from app.email.scheduler import unsubscribe

router = APIRouter(prefix="/v1/email", tags=["email"])
logger = logging.getLogger(__name__)


_HTML_OK = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>Unsubscribed</title></head>
<body style="font-family:system-ui,Arial,sans-serif;max-width:560px;margin:80px auto;padding:24px;color:#1f2937;">
<h1 style="color:#1e57ac;">You have been unsubscribed</h1>
<p>You are off the onboarding email series and will receive no further automated onboarding email from ABS.</p>
<p>Transactional email, such as license and refund notices, will still be delivered.</p>
<p>If you think this is a mistake: <a href="mailto:support@automatiabcn.com">support@automatiabcn.com</a></p>
</body></html>
"""

_HTML_FAIL = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><title>Error</title></head>
<body style="font-family:system-ui,Arial,sans-serif;max-width:560px;margin:80px auto;padding:24px;color:#991b1b;">
<h1>Could not unsubscribe you</h1>
<p>{reason}</p>
<p>If the problem persists, contact <a href="mailto:support@automatiabcn.com">support@automatiabcn.com</a>.</p>
</body></html>
"""


@router.get("/unsubscribe", response_class=HTMLResponse)
async def unsubscribe_endpoint(token: str = Query(..., min_length=10)) -> HTMLResponse:
    ok, info = unsubscribe(token)
    if ok:
        return HTMLResponse(content=_HTML_OK, status_code=200)
    return HTMLResponse(
        content=_HTML_FAIL.format(reason=info or "Invalid token"),
        status_code=400,
    )
