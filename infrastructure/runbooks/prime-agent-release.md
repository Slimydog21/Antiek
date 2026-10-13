# Prime in an atomic release

The atomic deployment playbook installs the checksum-pinned Prime 0.9.8 Linux
x86_64/glibc bundle into each new unpublished release. It does not execute the
publisher's install script or enable Prime model calls or RLM workflows.

`tools/deploy/prime_agent_release.json` records the publisher URL, compressed
and expanded sizes, archive SHA256 and every directory and regular member.
The data-only installer refuses links, special files, duplicate or unexpected
paths, changed bodies and unsupported platforms. Installed executable files
and directories are 0555; other files are 0444. The deployment runs as root.
The candidate directory and its ancestors must remain under the existing
root-controlled deployment workflow.

Ansible uses ordinary curl with a replacement environment, curlrc disabled,
HTTPS only, no proxy, no redirect following and no retry. The download has a
120-second total timeout and an exact compressed-size limit. Curl must be at
least 8.4.0 to enforce that limit while receiving an unknown-length body.
This requirement is checked before downloading. See the
[curl size-limit contract](https://curl.se/docs/manpage.html#--max-filesize).

After complete extraction and verification, the installer publishes
`.prime-agent/` and `.prime-agent.env` sequentially inside the unpublished
candidate. A failure between those operations leaves an incomplete candidate.
It creates no release receipt and does not change the public pointer. The
existing playbook removes and rebuilds candidates without a receipt. The
installer refuses partial state rather than repairing it.

The release receipt includes the archive and committed manifest digests.
After the existing release freeze, verification checks the whole bundle,
exact environment file, receipt and readonly modes before the live phase.
This check also runs when a preexisting receipt skips the build block. It
never repairs a receipted release. A stale receipt, changed native leaf or
incomplete freeze therefore fails before service quiescence or cutover.

The generated environment contains only:

```text
ANTIEK_PRIME_AGENT_BIN=/opt/antiek/.prime-agent/prime-agent
```

The API unit reads that optional file after the existing secrets file.
Later EnvironmentFile entries override earlier entries, so a historical
Prime path in secrets cannot select another binary for a new release.
The file follows the same `/opt/antiek` pointer as the API and frontend.
Rollback therefore restores the previous bundle and environment together.
A release predating this change has no file; the optional include lets its
previous startup behavior continue. See the
[systemd environment-file contract](https://github.com/systemd/systemd/blob/main/man/systemd.exec.xml).

To diagnose an already-frozen release, run the verifier as root with the exact
retained SHA. This performs data reads and hashing, with no vendor execution:

```bash
/usr/bin/env -i PATH=/usr/bin:/bin LANG=C /usr/bin/python3 -I -S \
  /opt/antiek-releases/<exact-40-hex-sha>/tools/deploy/install_prime_agent.py \
  verify --release /opt/antiek-releases/<exact-40-hex-sha> --public /opt/antiek
```

Do not alter a retained receipted release to repair a failed check. Use a new
gated source commit and the existing atomic deployment and rollback process.
OS upgrades remain a setup concern. A release before this installer existed
is not eligible for its verification command.

Artifact updates require a separately reviewed URL, archive digest and full
member manifest. Version text alone is insufficient. The embedded
`PRIME_AGENT_INTERACTIVE_SELF_UPDATE` variable is a restart-protocol marker,
not a verified update-disable setting, so this deployment does not set it.
Readonly release ownership and existing service restrictions limit writes;
they do not prove every updater or native behavior is disabled.

Successful bundle verification establishes exact installed data only.
Loaded native compatibility, BYOT account routing, usage settlement and
each RLM workflow still require their own execution evidence.
