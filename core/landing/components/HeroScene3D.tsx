/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// The hero scene: six providers on a ring, the vault in the middle, traffic
// falling inward through the cascade.
//
// What it replaces was a generic AI orb with 600 particles streaming into it —
// the same visual every model wrapper on the market ships, saying nothing about
// what this product is. It was painted in #1e57ac (the retired Automatia blue)
// under a #3b82f6 lamp, colours that exist nowhere else in the product any more,
// and it was mounted `absolute inset-0` across the whole hero: measured in the
// browser, 600 × 300 pixels of orb sat directly on top of the headline.
//
// This scene is the mark, in motion: the vault holding the core, with the thing
// the product actually does happening around it. One accent — the brand token.
"use client";

import { Canvas, useFrame } from "@react-three/fiber";
import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";

// Read from the token so the scene follows the theme instead of hardcoding a
// second source of truth for the brand colour. Falls back to the light-theme
// value when the CSS has not landed (SSR is off here, so this is belt-and-braces).
function brandColor(): THREE.Color {
  if (typeof window === "undefined") return new THREE.Color("#0b7c74");
  const raw = getComputedStyle(document.documentElement)
    .getPropertyValue("--abs-brand-rgb")
    .trim();
  const parts = raw.split(/\s+/).map(Number);
  if (parts.length === 3 && parts.every((n) => Number.isFinite(n))) {
    return new THREE.Color(parts[0] / 255, parts[1] / 255, parts[2] / 255);
  }
  return new THREE.Color("#0b7c74");
}

const PROVIDER_COUNT = 6;
// The frame is ~2.7 units half-width at this camera, so a 3.1 ring put two of
// the six providers outside it — a cascade with two of its sources cropped off.
const RING_RADIUS = 2.35;

// ─── The vault: the logo's hexagon, holding the core ──────────────────────
//
// A wireframe icosahedron was the first thing I reached for and it was wrong —
// it reads as a faceted ball, not as the mark. The vault is a hexagon, so the
// shell is drawn as hexagons: one facing the viewer, two more rotated about the
// vertical, which gives volume as the group turns without inventing a shape the
// logo does not have.
function hexagonGeometry(radius: number): THREE.BufferGeometry {
  const points = Array.from({ length: 7 }, (_, i) => {
    const a = (i / 6) * Math.PI * 2 - Math.PI / 2;
    return new THREE.Vector3(Math.cos(a) * radius, Math.sin(a) * radius, 0);
  });
  return new THREE.BufferGeometry().setFromPoints(points);
}

function Vault({ color }: { color: THREE.Color }) {
  const shellRef = useRef<THREE.Group>(null);
  const innerRef = useRef<THREE.Group>(null);
  const coreRef = useRef<THREE.Mesh>(null);

  const shell = useMemo(() => hexagonGeometry(1.25), []);
  const inner = useMemo(() => hexagonGeometry(0.82), []);

  useFrame((state) => {
    const t = state.clock.elapsedTime;
    if (shellRef.current) {
      shellRef.current.rotation.y = t * 0.22;
      shellRef.current.rotation.x = Math.sin(t * 0.3) * 0.1;
    }
    // Counter-rotation reads as depth without needing a second colour.
    if (innerRef.current) innerRef.current.rotation.y = -t * 0.36;
    if (coreRef.current) {
      coreRef.current.scale.setScalar(1 + Math.sin(t * 1.5) * 0.07);
    }
  });

  return (
    <group>
      <group ref={shellRef}>
        {[0, Math.PI / 3, (2 * Math.PI) / 3].map((yaw, i) => (
          // The rotation rides on a <group>: `rotation` on a bare <line> is
          // typed as SVG's <line>, which has no such prop.
          // eslint-disable-next-line react/no-unknown-property
          <group key={`shell-${i}`} rotation={[0, yaw, 0]}>
            {/* eslint-disable-next-line react/no-unknown-property */}
            <line>
              <primitive object={shell.clone()} attach="geometry" />
              <lineBasicMaterial color={color} transparent opacity={0.5} />
            </line>
          </group>
        ))}
      </group>
      <group ref={innerRef}>
        {[0, Math.PI / 3].map((yaw, i) => (
          // eslint-disable-next-line react/no-unknown-property
          <group key={`inner-${i}`} rotation={[0, yaw, 0]}>
            {/* eslint-disable-next-line react/no-unknown-property */}
            <line>
              <primitive object={inner.clone()} attach="geometry" />
              <lineBasicMaterial color={color} transparent opacity={0.2} />
            </line>
          </group>
        ))}
      </group>
      <mesh ref={coreRef}>
        <sphereGeometry args={[0.32, 32, 32]} />
        <meshStandardMaterial
          color={color}
          emissive={color}
          emissiveIntensity={0.9}
          roughness={0.3}
        />
      </mesh>
    </group>
  );
}

// ─── The providers, and the traffic falling into the vault ────────────────
function Cascade({ color }: { color: THREE.Color }) {
  const groupRef = useRef<THREE.Group>(null);
  const packetsRef = useRef<THREE.Points>(null);

  // A flat ring, tilted a little. The first version pushed each node out along
  // three axes at once and the six of them read as scatter rather than as a
  // cascade with an order to it.
  const nodes = useMemo(() => {
    return Array.from({ length: PROVIDER_COUNT }, (_, i) => {
      const a = (i / PROVIDER_COUNT) * Math.PI * 2 - Math.PI / 2;
      return new THREE.Vector3(
        Math.cos(a) * RING_RADIUS,
        Math.sin(a) * RING_RADIUS,
        0,
      );
    });
  }, []);

  // 96 packets, against the 600 particles the old scene ran every frame.
  const PACKETS = 96;
  const { positions, origin, progress, speed } = useMemo(() => {
    const pos = new Float32Array(PACKETS * 3);
    const org = new Int32Array(PACKETS);
    const prg = new Float32Array(PACKETS);
    const spd = new Float32Array(PACKETS);
    for (let i = 0; i < PACKETS; i++) {
      org[i] = i % PROVIDER_COUNT;
      prg[i] = Math.random();
      spd[i] = 0.15 + Math.random() * 0.28;
    }
    return { positions: pos, origin: org, progress: prg, speed: spd };
  }, []);

  useFrame((state, delta) => {
    if (groupRef.current) {
      // A slow tilt rather than a full spin: the ring stays legible as a ring.
      groupRef.current.rotation.y = Math.sin(state.clock.elapsedTime * 0.12) * 0.25;
      groupRef.current.rotation.x = -0.18;
    }
    const points = packetsRef.current;
    if (!points) return;
    const arr = points.geometry.attributes.position.array as Float32Array;
    for (let i = 0; i < PACKETS; i++) {
      progress[i] += speed[i] * delta;
      if (progress[i] > 1) {
        progress[i] = 0;
        origin[i] = Math.floor(Math.random() * PROVIDER_COUNT);
      }
      const from = nodes[origin[i]];
      // Squared easing: the packet accelerates as the vault pulls it in.
      const e = progress[i] * progress[i];
      arr[i * 3] = from.x * (1 - e);
      arr[i * 3 + 1] = from.y * (1 - e);
      arr[i * 3 + 2] = from.z * (1 - e);
    }
    points.geometry.attributes.position.needsUpdate = true;
  });

  return (
    <group ref={groupRef}>
      {nodes.map((p, i) => (
        <mesh key={i} position={p}>
          <sphereGeometry args={[0.09, 16, 16]} />
          <meshBasicMaterial color={color} />
        </mesh>
      ))}
      {nodes.map((p, i) => {
        const geometry = new THREE.BufferGeometry().setFromPoints([
          p,
          new THREE.Vector3(0, 0, 0),
        ]);
        return (
          // eslint-disable-next-line react/no-unknown-property
          <line key={`spoke-${i}`}>
            <primitive object={geometry} attach="geometry" />
            <lineBasicMaterial color={color} transparent opacity={0.16} />
          </line>
        );
      })}
      <points ref={packetsRef}>
        <bufferGeometry>
          <bufferAttribute
            attach="attributes-position"
            args={[positions, 3]}
            count={PACKETS}
            itemSize={3}
          />
        </bufferGeometry>
        <pointsMaterial
          color={color}
          size={0.075}
          sizeAttenuation
          transparent
          opacity={0.8}
        />
      </points>
    </group>
  );
}

// Stops rendering once the hero is off screen. The previous scene animated 600
// particles for as long as the tab was open — scrolled past, tabbed away, still
// drawing.
function useOnScreen(ref: React.RefObject<HTMLElement | null>): boolean {
  const [onScreen, setOnScreen] = useState(true);
  useEffect(() => {
    const node = ref.current;
    if (!node || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(
      ([entry]) => setOnScreen(entry.isIntersecting),
      { threshold: 0.05 },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [ref]);
  return onScreen;
}

export default function HeroScene3D() {
  const color = useMemo(() => brandColor(), []);
  const boxRef = useRef<HTMLDivElement>(null);
  const onScreen = useOnScreen(boxRef);

  return (
    <div
      ref={boxRef}
      data-testid="hero-3d"
      // Its own box inside the hero's second column. The scene can no longer
      // reach the type: the previous one was `absolute inset-0`, which is how it
      // came to be sitting on the headline.
      className="relative aspect-square w-full max-w-[520px]"
      aria-hidden="true"
    >
      <Canvas
        camera={{ position: [0, 0.6, 7], fov: 42 }}
        dpr={[1, 1.5]}
        frameloop={onScreen ? "always" : "never"}
        gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
      >
        <ambientLight intensity={0.7} />
        <pointLight position={[5, 5, 5]} intensity={0.8} color={color} />
        <Vault color={color} />
        <Cascade color={color} />
      </Canvas>
    </div>
  );
}
