/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Tremor BarList + scaffolding. Wrapped so the
// /panel page can lazy-load it via next/dynamic, keeping Recharts +
// Tremor base out of the panel chrome bundle.
"use client";

import { useEffect, useRef } from "react";
import {
  BarList,
  Card as TremorCard,
  Flex,
  Subtitle,
  Title,
} from "@tremor/react";

export type CategoryBar = { name: string; value: number };

export default function CategoryBarList({ data }: { data: CategoryBar[] }) {
  // A11y — Tremor's <BarList> root renders an invalid `aria-sort` attribute
  // (only allowed on table/grid headers). Strip it to clear the axe
  // `aria-allowed-attr` critical violation without forking the library.
  const rootRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    rootRef.current
      ?.querySelectorAll("[aria-sort]")
      .forEach((el) => el.removeAttribute("aria-sort"));
  }, [data]);

  return (
    <TremorCard ref={rootRef} className="border-0 bg-transparent p-0 shadow-none">
      <Flex className="mb-2">
        <Title className="text-xs uppercase tracking-wider text-muted-foreground">
          Kategori
        </Title>
        <Subtitle className="text-xs uppercase tracking-wider text-muted-foreground">
          Adet
        </Subtitle>
      </Flex>
      <BarList data={data} color="indigo" />
    </TremorCard>
  );
}
