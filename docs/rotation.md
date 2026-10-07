# Rotation groups

A rotation group belongs to one or more rotation slots; fixed cameras remain in place. Each group has camera entries, an interval, and an order (`sequential`, `reverse`, `random`, or `weighted`). Transitions are cuts.

On OMXPlayer, Mosaivue can prepare the next sequential or reverse camera offscreen while the current one remains visible. It moves the prepared surface into position and raises its layer only when playback is ready. At most one extra decoder is kept. If preparation or positioning fails, the current camera remains visible and the group retries on its next interval. `Preload: off` prepares at switch time, so a successful cut can still arrive late; `next` prepares during the interval. Random and weighted order cannot reliably predict the next stream, so those modes prepare at switch time.

The renderer reports planned changes as `switch_count`. `restart_count` records recovery or manual restarts. Both counters reset when the renderer service starts.

The web remote and API can pause, resume, advance, or reverse rotation. A manual fullscreen focus suspends layout rotation until `Restore layout` rebuilds it.
