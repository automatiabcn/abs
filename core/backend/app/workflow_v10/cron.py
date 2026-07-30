# Copyright (c) 2026 Automatia BCN. All rights reserved.
# Licensed under the Business Source License 1.1.
# Production use requires a Commercial License - see LICENSE.
# Change Date: 2030-05-07 -> Apache License, Version 2.0

"""A 5-field cron matcher, with no dependency.

The product ships self-hosted and air-gapped, so a scheduler that needs a
package from the internet is a scheduler that does not run for the customers
this tier exists for. The grammar is the common one — ``*``, ``5``, ``1,3``,
``1-5``, ``*/15`` — over minute, hour, day-of-month, month, day-of-week.

Times are UTC. A schedule that means "09:00" to its author and fires at 09:00
UTC is a support ticket, so the caller is told the timezone rather than left to
assume.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List, Set

_FIELD_RANGES = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 6))
_FIELD_NAMES = ("minute", "hour", "day-of-month", "month", "day-of-week")
# One year of minutes: the bound on "when does this next fire". A schedule with
# no occurrence in a year (29 February on a non-leap run) returns None rather
# than spinning.
_MAX_LOOKAHEAD_MINUTES = 366 * 24 * 60


class CronError(ValueError):
    """The expression is not a cron this scheduler can run."""


def _parse_field(raw: str, index: int) -> Set[int]:
    low, high = _FIELD_RANGES[index]
    values: Set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if not part:
            raise CronError(f"empty {_FIELD_NAMES[index]} field")
        step = 1
        if "/" in part:
            part, _, step_raw = part.partition("/")
            try:
                step = int(step_raw)
            except ValueError as exc:
                raise CronError(f"bad step in {_FIELD_NAMES[index]}: {step_raw}") from exc
            if step <= 0:
                raise CronError(f"step must be positive in {_FIELD_NAMES[index]}")
        if part in ("*", ""):
            start, end = low, high
        elif "-" in part:
            a, _, b = part.partition("-")
            try:
                start, end = int(a), int(b)
            except ValueError as exc:
                raise CronError(f"bad range in {_FIELD_NAMES[index]}: {part}") from exc
        else:
            try:
                start = end = int(part)
            except ValueError as exc:
                raise CronError(f"bad value in {_FIELD_NAMES[index]}: {part}") from exc
        if start < low or end > high or start > end:
            raise CronError(
                f"{_FIELD_NAMES[index]} out of range ({low}-{high}): {part}"
            )
        values.update(range(start, end + 1, step))
    if not values:
        raise CronError(f"no values for {_FIELD_NAMES[index]}")
    return values


@dataclass(frozen=True)
class CronSpec:
    minute: Set[int]
    hour: Set[int]
    day: Set[int]
    month: Set[int]
    weekday: Set[int]
    expression: str

    @property
    def day_restricted(self) -> bool:
        return len(self.day) < 31

    @property
    def weekday_restricted(self) -> bool:
        return len(self.weekday) < 7


def parse(expression: str) -> CronSpec:
    """Parse a 5-field expression. Raises CronError with a readable reason."""
    fields: List[str] = (expression or "").split()
    if len(fields) != 5:
        raise CronError(
            f"a cron expression has 5 fields (got {len(fields)}): "
            "minute hour day-of-month month day-of-week"
        )
    parsed = [_parse_field(f, i) for i, f in enumerate(fields)]
    return CronSpec(
        minute=parsed[0],
        hour=parsed[1],
        day=parsed[2],
        month=parsed[3],
        weekday=parsed[4],
        expression=expression.strip(),
    )


def matches(spec: CronSpec, when: datetime) -> bool:
    """Does `when` (UTC, second-precision ignored) fall on this schedule?

    Day-of-month and day-of-week are OR'd when both are restricted — the
    behaviour every cron implementation shares, and the one an author who
    writes ``0 9 1,15 * 1`` expects.
    """
    if when.minute not in spec.minute or when.hour not in spec.hour:
        return False
    if when.month not in spec.month:
        return False
    dom_ok = when.day in spec.day
    # Python: Monday=0..Sunday=6. Cron: Sunday=0..Saturday=6.
    dow_ok = ((when.weekday() + 1) % 7) in spec.weekday
    if spec.day_restricted and spec.weekday_restricted:
        return dom_ok or dow_ok
    return dom_ok and dow_ok


def next_after(spec: CronSpec, after: datetime) -> datetime | None:
    """The first firing strictly after `after` (UTC), or None within a year."""
    cursor = (after + timedelta(minutes=1)).replace(second=0, microsecond=0)
    for _ in range(_MAX_LOOKAHEAD_MINUTES):
        if matches(spec, cursor):
            return cursor
        cursor += timedelta(minutes=1)
    return None


def describe(spec: CronSpec) -> str:
    """A short human reading, so a panel can show more than the raw expression."""
    if spec.expression == "* * * * *":
        return "every minute"
    if len(spec.minute) == 1 and len(spec.hour) == 1:
        minute = next(iter(spec.minute))
        hour = next(iter(spec.hour))
        at = f"{hour:02d}:{minute:02d} UTC"
        if spec.weekday_restricted and not spec.day_restricted:
            days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
            names = ", ".join(days[d] for d in sorted(spec.weekday))
            return f"{names} at {at}"
        if spec.day_restricted:
            return f"day {', '.join(str(d) for d in sorted(spec.day))} at {at}"
        return f"daily at {at}"
    return f"cron {spec.expression} (UTC)"
