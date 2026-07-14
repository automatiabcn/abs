/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// React Three Fiber hero scene.
// Network nodes + particle flow + central ABS orb. Brand #1e57ac + electric cyan.
// Lazy-mounted only on desktop AND when prefers-reduced-motion is "no-preference".
"use client";

import { Canvas, useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

const BRAND_BLUE = new THREE.Color("#1e57ac");
const ELECTRIC_CYAN = new THREE.Color("#22d3ee");

// ─── Central ABS orb ─────────────────────────────────────────────────────
function CenterOrb() {
  const meshRef = useRef<THREE.Mesh>(null);
  const haloRef = useRef<THREE.Mesh>(null);

  useFrame((state) => {
    const t = state.clock.elapsedTime;
    if (meshRef.current) {
      meshRef.current.rotation.y = t * 0.25;
      meshRef.current.rotation.x = Math.sin(t * 0.4) * 0.15;
      const pulse = 1 + Math.sin(t * 1.6) * 0.04;
      meshRef.current.scale.setScalar(pulse);
    }
    if (haloRef.current) {
      const haloPulse = 1.4 + Math.sin(t * 1.2 + Math.PI / 2) * 0.06;
      haloRef.current.scale.setScalar(haloPulse);
    }
  });

  return (
    <group>
      <mesh ref={meshRef}>
        <icosahedronGeometry args={[1.0, 1]} />
        <meshStandardMaterial
          color={BRAND_BLUE}
          emissive={BRAND_BLUE}
          emissiveIntensity={0.45}
          roughness={0.25}
          metalness={0.6}
          flatShading
        />
      </mesh>
      <mesh ref={haloRef}>
        <sphereGeometry args={[1.05, 32, 32]} />
        <meshBasicMaterial
          color={ELECTRIC_CYAN}
          transparent
          opacity={0.08}
          side={THREE.BackSide}
        />
      </mesh>
    </group>
  );
}

// ─── Network nodes with edges ────────────────────────────────────────────
function NetworkNodes({ count = 24 }: { count?: number }) {
  const groupRef = useRef<THREE.Group>(null);

  const positions = useMemo(() => {
    const arr: THREE.Vector3[] = [];
    const radius = 3.2;
    for (let i = 0; i < count; i++) {
      // Fibonacci sphere for even distribution.
      const golden = Math.PI * (3 - Math.sqrt(5));
      const y = 1 - (i / (count - 1)) * 2;
      const r = Math.sqrt(1 - y * y);
      const theta = golden * i;
      arr.push(
        new THREE.Vector3(
          Math.cos(theta) * r * radius,
          y * radius,
          Math.sin(theta) * r * radius,
        ),
      );
    }
    return arr;
  }, [count]);

  // Edges between nearby nodes only (avoids visual clutter).
  const edges = useMemo(() => {
    const lines: [THREE.Vector3, THREE.Vector3][] = [];
    for (let i = 0; i < positions.length; i++) {
      for (let j = i + 1; j < positions.length; j++) {
        if (positions[i].distanceTo(positions[j]) < 2.4) {
          lines.push([positions[i], positions[j]]);
        }
      }
    }
    return lines;
  }, [positions]);

  useFrame((state) => {
    if (groupRef.current) {
      groupRef.current.rotation.y = state.clock.elapsedTime * 0.05;
    }
  });

  return (
    <group ref={groupRef}>
      {positions.map((p, i) => (
        <mesh key={i} position={p}>
          <sphereGeometry args={[0.05, 16, 16]} />
          <meshBasicMaterial color={ELECTRIC_CYAN} />
        </mesh>
      ))}
      {edges.map(([a, b], i) => {
        const geom = new THREE.BufferGeometry().setFromPoints([a, b]);
        return (
          // eslint-disable-next-line react/no-unknown-property
          <line key={`edge-${i}`}>
            <primitive object={geom} attach="geometry" />
            <lineBasicMaterial color={BRAND_BLUE} transparent opacity={0.35} />
          </line>
        );
      })}
    </group>
  );
}

// ─── Particle flow ───────────────────────────────────────────────────────
function ParticleFlow({ count = 600 }: { count?: number }) {
  const pointsRef = useRef<THREE.Points>(null);

  const { positions, speeds } = useMemo(() => {
    const pos = new Float32Array(count * 3);
    const sp = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      const r = 1.6 + Math.random() * 2.6;
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(2 * Math.random() - 1);
      pos[i * 3] = r * Math.sin(phi) * Math.cos(theta);
      pos[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
      pos[i * 3 + 2] = r * Math.cos(phi);
      sp[i] = 0.0006 + Math.random() * 0.0018;
    }
    return { positions: pos, speeds: sp };
  }, [count]);

  useFrame(() => {
    if (!pointsRef.current) return;
    const pos = pointsRef.current.geometry.attributes.position
      .array as Float32Array;
    for (let i = 0; i < count; i++) {
      const dx = -pos[i * 3] * speeds[i];
      const dy = -pos[i * 3 + 1] * speeds[i];
      const dz = -pos[i * 3 + 2] * speeds[i];
      pos[i * 3] += dx;
      pos[i * 3 + 1] += dy;
      pos[i * 3 + 2] += dz;
      const r = Math.sqrt(
        pos[i * 3] ** 2 + pos[i * 3 + 1] ** 2 + pos[i * 3 + 2] ** 2,
      );
      if (r < 1.1) {
        const newR = 1.6 + Math.random() * 2.6;
        const theta = Math.random() * Math.PI * 2;
        const phi = Math.acos(2 * Math.random() - 1);
        pos[i * 3] = newR * Math.sin(phi) * Math.cos(theta);
        pos[i * 3 + 1] = newR * Math.sin(phi) * Math.sin(theta);
        pos[i * 3 + 2] = newR * Math.cos(phi);
      }
    }
    pointsRef.current.geometry.attributes.position.needsUpdate = true;
  });

  return (
    <points ref={pointsRef}>
      <bufferGeometry>
        <bufferAttribute
          attach="attributes-position"
          args={[positions, 3]}
          count={count}
          itemSize={3}
        />
      </bufferGeometry>
      <pointsMaterial
        color={ELECTRIC_CYAN}
        size={0.04}
        sizeAttenuation
        transparent
        opacity={0.65}
      />
    </points>
  );
}

// ─── Top-level scene ─────────────────────────────────────────────────────
export default function HeroScene3D() {
  return (
    <div
      data-testid="hero-3d"
      className="absolute inset-0 -z-10"
      aria-hidden="true"
    >
      <Canvas
        camera={{ position: [0, 0, 6], fov: 45 }}
        dpr={[1, 1.5]}
        gl={{ antialias: true, alpha: true, powerPreference: "high-performance" }}
      >
        <ambientLight intensity={0.55} />
        <pointLight position={[6, 6, 6]} intensity={1.1} color="#3b82f6" />
        <pointLight position={[-6, -3, -4]} intensity={0.4} color="#22d3ee" />
        <CenterOrb />
        <NetworkNodes />
        <ParticleFlow />
      </Canvas>
    </div>
  );
}
