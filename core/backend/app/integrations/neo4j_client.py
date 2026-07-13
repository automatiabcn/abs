# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""Q7 Phase A — Neo4j async client (Bolt protocol)."""

from __future__ import annotations

import logging
from typing import Optional

from neo4j import AsyncGraphDatabase

from app.config import settings

logger = logging.getLogger(__name__)

_driver = None


def _get_driver():
    global _driver
    if _driver is None:
        _driver = AsyncGraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
    return _driver


class Neo4jClient:
    def __init__(self) -> None:
        self.driver = _get_driver()

    async def close(self) -> None:
        if self.driver is not None:
            await self.driver.close()

    async def query(self, cypher: str, params: Optional[dict] = None) -> list[dict]:
        async with self.driver.session() as s:
            result = await s.run(cypher, params or {})
            return [r.data() async for r in result]

    async def upsert_entity(
        self, label: str, props: dict, key: str = "id"
    ) -> list[dict]:
        if not props.get(key):
            raise ValueError(f"missing key {key} in props")
        cypher = f"MERGE (n:{label} {{{key}: ${key}_val}}) SET n += $props RETURN n"
        return await self.query(cypher, {f"{key}_val": props[key], "props": props})

    async def upsert_relation(
        self, src_id: str, rel_type: str, dst_id: str, props: Optional[dict] = None
    ) -> list[dict]:
        cypher = (
            "MATCH (a {id: $src_id}), (b {id: $dst_id}) "
            f"MERGE (a)-[r:{rel_type}]->(b) "
            "SET r += $props RETURN r"
        )
        return await self.query(
            cypher, {"src_id": src_id, "dst_id": dst_id, "props": props or {}}
        )

    async def health(self) -> bool:
        try:
            r = await self.query("RETURN 1 AS ok")
            return bool(r and r[0].get("ok") == 1)
        except Exception as exc:
            logger.warning("neo4j health failed: %s", exc)
            return False
