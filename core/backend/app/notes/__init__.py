# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Notes companion store (see app.notes.service)."""

from .service import delete, get, list_notes, save, search, stats

__all__ = ["save", "get", "list_notes", "search", "delete", "stats"]
