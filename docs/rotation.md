# Rotation groups

A group provides camera entries, an interval and an order: `sequential`, `reverse`, `random` or `weighted`. Assign it to one or more rotation slots. Fixed slots retain their own streams, and transitions are cuts.

## Independent slots and controls

The 0.1.0b3 candidate maintains a separate cursor for each rotation slot, even when slots share a group. A rotation entry can select a stream profile; that profile must belong to its camera. Disabled groups do not advance and disabled cameras are excluded from selection.

The remote and API can pause, resume, advance or reverse rotation. Focus suspends layout rotation until **Restore layout** reapplies it. A failed layout/focus operation attempts to retain the previous streams and controller state; successful command handling still needs physical display verification.

Reapply the active layout after editing a group to consistently load its interval, preload and entry configuration. Some entry changes are read during later switches, but saving a group is not a full reload contract.

## Scheduled walls

Schedules use the appliance's local timezone. While a schedule window remains active, the watcher checks approximately every 30 seconds and can reassert its wall after a manual layout change. Fullscreen focus pauses schedule application. When all windows finish, the last displayed wall remains until another schedule or operator changes it; there is no automatic fallback wall.

An overnight window belongs to its starting day: Monday 22:00–06:00 covers Monday evening and Tuesday morning. The end boundary is exclusive, and equal start/end times represent a full-day window.

## Preload and failure behavior

Sequential/reverse order can prepare the next camera during the interval with **Preload: next**. **Off** prepares at switch time, so a ready cut can arrive later than the configured interval. Random/weighted modes prepare at switch time because the next choice is not reliably predictable.

The OMXPlayer backend prepares a player offscreen, then positions and raises it for a cut. GStreamer uses prepared source branches where supported. The actual resource budget depends on backend, number of rotating slots, camera formats and appliance capacity; qualify this on the target hardware.

| Failure setting | When the requested next stream cannot be switched in |
|---|---|
| **Skip** | Keep the currently visible stream and advance toward another entry on the next attempt. |
| **Hold** | Keep the currently visible stream and retry the failed entry on the next attempt. |

A legacy `placeholder` group setting is retained for compatibility and currently behaves as Hold; it is disabled as a new UI selection. There is no implemented group-level placeholder failure policy. Existing GStreamer connecting/stalled-source placeholder graphics are a separate recovery mechanism.

`rotate_together_group` remains stored metadata. It does not implement synchronized switching across tiles. Independent slots may change at different moments, and there is no frame-synchronized multi-display guarantee.

## Health counters and qualification

`switch_count` represents planned changes; `restart_count` represents recovery or manual restarts. Counters reset when the renderer starts. An available process, successful RPC or LIVE label alone does not prove advancing decoded frames on every backend.

Exercise offline cameras, failed preparation, shared groups in two independent slots, both failure settings, focus/restore and long-running recovery on the intended hardware. Earlier Pi/ROCK Pi site evidence applies to the earlier build and does not automatically qualify the candidate. See [performance](performance.md) and the [hardware test plan](hardware-test-plan.md).
