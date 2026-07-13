/**
 * Copyright (c) 2026 Automatia BCN. All rights reserved.
 * Licensed under the Business Source License 1.1.
 * Production use requires a Commercial License - see LICENSE.
 * Change Date: 2030-05-07 -> Apache License, Version 2.0
 */

// Q12-L18 — IndexedDB-backed draft persistence for the
// /panel/chat textarea. The R36 service-worker caches *responses*;
// this helper persists *user input* across reloads, navigations,
// and browser-tab closures.
//
// Contract:
//   loadDraft()        → "" if no draft, otherwise the saved text
//   saveDraft("")      → deletes the record
//   saveDraft("xyz…")  → upserts the record
//
// Bails silently on:
//   - SSR (no window/indexedDB)
//   - Private-mode browsers where IndexedDB is disabled
//   - Quota errors
//
// Single record key: `current`. Multiple sessions/users share one
// browser profile → one draft. If we ever want per-session drafts
// we'd switch to a keyed-by-session_id store.
"use client";

const DB_NAME = "abs-chat-drafts";
const STORE_NAME = "drafts";
const KEY = "current";
const VERSION = 1;

const isClient =
  typeof window !== "undefined" && "indexedDB" in window;

function openDB(): Promise<IDBDatabase | null> {
  if (!isClient) return Promise.resolve(null);
  return new Promise((resolve) => {
    const req = indexedDB.open(DB_NAME, VERSION);
    req.onerror = () => resolve(null);
    req.onupgradeneeded = (e: IDBVersionChangeEvent) => {
      const db = (e.target as IDBOpenDBRequest).result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        db.createObjectStore(STORE_NAME);
      }
    };
    req.onsuccess = (e: Event) =>
      resolve((e.target as IDBOpenDBRequest).result);
  });
}

export async function loadDraft(): Promise<string> {
  try {
    const db = await openDB();
    if (!db) return "";
    return await new Promise<string>((resolve) => {
      const tx = db.transaction(STORE_NAME, "readonly");
      const req = tx.objectStore(STORE_NAME).get(KEY);
      req.onerror = () => resolve("");
      req.onsuccess = (e: Event) => {
        const val = (e.target as IDBRequest<unknown>).result;
        resolve(typeof val === "string" ? val : "");
      };
    });
  } catch {
    return "";
  }
}

export async function saveDraft(text: string): Promise<void> {
  try {
    const db = await openDB();
    if (!db) return;
    const tx = db.transaction(STORE_NAME, "readwrite");
    const store = tx.objectStore(STORE_NAME);
    if (text === "") {
      store.delete(KEY);
    } else {
      store.put(text, KEY);
    }
    await new Promise<void>((resolve) => {
      tx.oncomplete = () => resolve();
      tx.onerror = () => resolve();
      tx.onabort = () => resolve();
    });
  } catch {
    // best-effort; private mode / quota → degrade silently
  }
}
