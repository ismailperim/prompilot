# Host health check

A quick read on whether the demo host is healthy: saturation of CPU, memory and disk, and whether every scrape target is up.

1. Add a stat panel "Targets up" with `up` per job, colour mode background, red below 1.
2. Add a stat panel "CPU busy" showing the machine-wide busy fraction (average over cores) as `percentunit`, with thresholds orange at 0.7 and red at 0.9.
3. Add a stat panel "Memory used" as a fraction of total, same thresholds.
4. Add a table "Filesystem usage" of usage ratio per device (exclude tmpfs/overlay), sorted by value.
5. Finish with a two-sentence summary: is anything saturated or down right now, and what would you look at next.
