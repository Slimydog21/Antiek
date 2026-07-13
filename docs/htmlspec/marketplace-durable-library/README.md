# Marketplace durable library

Start with [index.html](index.html). SPR-01 implements the durable store and
explicit application composition. The nested
[production recovery spec](children/production-recovery/index.html) activates
that store in systemd and closes the nightly backup/restore gap.
