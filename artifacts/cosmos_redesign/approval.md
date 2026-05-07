# Cosmos 3D Redesign — Founder Approval

**Approved variant:** `mockup_2` — Force-directed graph
**Approved by:** founder
**Date:** 2026-05-07
**Reference:** `MOCKUP_GATE.md` · branch `feat/sprint-q12-deep-quality`

## What ships

- d3-force layout (free-floating nodes, no symmetric orbit) — react-three-fiber render.
- Single brand palette: `#0a0e1a` bg, `#1e57ac` primary, `#3a9dff` highlight, `#78bdff` accent. **No rainbow per provider.**
- Glass morphism via `MeshPhysicalMaterial { transmission: 0.6, thickness: 0.5, roughness: 0.1 }`.
- Edge particles: small luminous dots flowing along active edges (cascade hop visualisation).
- Active node pulse halo on the current cascade hop.
- Entrance: scattered nodes snap into relational geometry (chaos → order, "Automate the Chaos").
- `prefers-reduced-motion` fallback: static iso layout per Variant 3 reference; no WebGL physics.
- Bundle delta budget ≤180 KB gz; 60 fps M4 / 30 fps Hetzner CX22.
- Keyboard nav (Tab cycles nodes, Enter opens detail), 2 px `#78bdff` focus rings, ARIA `role="button" aria-label="…"`.

## What we are NOT shipping

- Variant 1 (Cosmos-orbital) — orbits read as fixed hierarchy.
- Variant 3 (Iso-axonometric) — too static for cascade telemetry; reused only as the reduced-motion fallback layout.
- Rainbow per provider · constant rotation · CSS-gradient fake 3D · vendor 3D models.

## Rounds executing under this approval

R3 implementation → R4 a11y → R5 tests (pytest + Playwright) → R6 atomic commit + image rebuild.
