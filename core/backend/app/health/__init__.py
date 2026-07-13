# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Provider health monitoring paketi.

NOT: Singleton `monitor` instance'ini dogrudan submodule'den import edin:
    from app.health.monitor import monitor
__init__'te re-export edersek `app.health.monitor` attribute'u submodule'u
maskeler ve `import app.health.monitor as mod` testlerde calismaz.
"""

from .monitor import HealthMonitor, ProviderHealth

__all__ = ["HealthMonitor", "ProviderHealth"]
