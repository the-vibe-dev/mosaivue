# ADR 004: Separate AES-GCM credential records

- Status: Accepted
- Date: 2026-10-02

## Context

RTSP URLs commonly contain passwords that would leak through logs, API responses, browser storage, process arguments, exports, and support bundles if stored as complete URLs.

## Decision

Strip URL userinfo at ingestion. Store username and an AES-256-GCM encrypted password in a separate credential row. Keep the random master key in a root-owned mode-0640 file restricted to the dedicated `mosaivue` group outside SQLite. Authenticate the credential row ID as GCM associated data.

## Consequences

The renderer resolves a full URL only in memory. A database copy alone does not reveal passwords, while backup with credentials requires both decryption and a new passphrase-encrypted archive. Root compromise remains outside the protection boundary.
