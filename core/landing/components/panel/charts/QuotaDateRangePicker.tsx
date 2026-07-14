/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Tremor DateRangePicker wrapper. Extracted so
// the /panel/quota page can lazy-load Tremor + Recharts via
// next/dynamic, keeping them out of the panel chrome bundle.
"use client";

import type { Dispatch, SetStateAction } from "react";

import { DateRangePicker, type DateRangePickerValue } from "@tremor/react";

export type { DateRangePickerValue };

export default function QuotaDateRangePicker(props: {
  value: DateRangePickerValue;
  onValueChange: Dispatch<SetStateAction<DateRangePickerValue>>;
  className?: string;
  enableSelect?: boolean;
  ["data-test"]?: string;
}) {
  return (
    <DateRangePicker
      value={props.value}
      onValueChange={props.onValueChange}
      data-test={props["data-test"]}
      enableSelect={props.enableSelect}
      className={props.className}
    />
  );
}
