# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""External MCP federation — ABS as an MCP *client*.

A tenant registers a third-party MCP server (GitHub / Slack / their own) from
the panel; this package connects out to it, discovers its tools and (Slice 2)
federates them into ABS's own catalog + agents.
"""
