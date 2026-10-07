# ADR 002: SQLite with revisioned JSON layout snapshots

- Status: Accepted
- Date: 2026-10-02

## Context

Users need persistent reusable cameras, credentials, layouts, schedules, revisions, import/export, and transactional upgrade behavior without editing files manually.

## Decision

Use SQLite in WAL mode through SQLAlchemy, with Alembic migrations. Store normalized slot snapshots as validated JSON in immutable `LayoutRevision` rows while relational tables own reusable objects.

## Consequences

SQLite provides a single local backup unit and robust transactions for an appliance. JSON revisions make rollback simple while validation prevents malformed state. Multi-appliance clustering is not a v0.1 goal.
