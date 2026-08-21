# Herdr bridge on the Mac mini

This bridge is the outbound-only adapter between Antiek's authenticated agent-work API and one explicitly selected local Herdr pane. It never scrapes terminal output. The prompted agent writes a correlated structured result into a private local directory; the bridge delivers it to Antiek.

## Safety boundary

- Do not put the credential in Git, the plist, an environment variable, or a command argument.
- Both config and credential files must be owned by the current user, regular single-link files, and mode `0600`.
- The Antiek origin must use HTTPS. No inbound port is opened on the Mac mini.
- Set `preferred_pane_id`. A selector matching zero or multiple panes fails closed.
- Complete the dry checks below before loading the LaunchAgent. Loading it can lease work and prompt the selected agent.

## Install without starting

From an isolated, reviewed checkout:

```bash
python3 -m venv .venv-herdr-bridge
.venv-herdr-bridge/bin/pip install --no-deps -e .
mkdir -p "$HOME/.local/bin" "$HOME/.config/antiek-herdr-bridge" "$HOME/.local/state/antiek-herdr-bridge"
ln -sfn "$PWD/.venv-herdr-bridge/bin/herdr-bridge" "$HOME/.local/bin/herdr-bridge"
chmod 700 "$HOME/.config/antiek-herdr-bridge" "$HOME/.local/state/antiek-herdr-bridge"
```

Copy `config.example.json` to `~/.config/antiek-herdr-bridge/config.json`, replace every placeholder, and create `credential.secret` from the separately issued bridge credential. Then:

```bash
chmod 600 "$HOME/.config/antiek-herdr-bridge/config.json" "$HOME/.config/antiek-herdr-bridge/credential.secret"
herdr agent list
plutil -lint infrastructure/connectors/herdr_bridge/com.antiek.herdr-bridge.plist.example
```

Do not continue if the configured worker selector is not unique in `herdr agent list`.

## Canary

Create one harmless feedback thread whose comment clearly identifies it as the bridge canary. Run the bridge in the foreground:

```bash
"$HOME/.local/bin/herdr-bridge" --config "$HOME/.config/antiek-herdr-bridge/config.json" run
```

Verify all of the following before stopping it with Ctrl-C:

1. Exactly one Herdr pane receives exactly one prompt.
2. Antiek records submitted, acknowledged, and working transitions.
3. The agent's private result file is mode `0600` and is accepted by `submit-result`.
4. The thread gains one typed reply and remains bound to the same immutable artifact version and anchor hashes.
5. Restarting the foreground bridge does not prompt the pane a second time.

## Enable at login

Render the plist by replacing `OPERATOR` with the macOS account name, copy it to `~/Library/LaunchAgents/com.antiek.herdr-bridge.plist`, and validate it. Then use the modern per-user launchd interface:

```bash
plutil -lint "$HOME/Library/LaunchAgents/com.antiek.herdr-bridge.plist"
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.antiek.herdr-bridge.plist"
launchctl kickstart -k "gui/$(id -u)/com.antiek.herdr-bridge"
launchctl print "gui/$(id -u)/com.antiek.herdr-bridge"
```

Logs are written to `~/Library/Logs/antiek-herdr-bridge.{out,err}.log`. The SQLite journal and result inbox remain under `~/.local/state/antiek-herdr-bridge/` with private permissions.

## Stop or remove

```bash
launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/com.antiek.herdr-bridge.plist"
```

Bootout is reversible and does not delete the journal. Preserve the journal while any attempt may still be active; it is what prevents a restart from issuing a duplicate prompt.

## Failure behavior

- HTTP 5xx or transport failure: the process exits nonzero; launchd restarts it and the journal replays safely.
- HTTP 410: the expired local attempt is closed and is not retried.
- Missing Herdr agent: Antiek receives a retryable `herdr_unavailable` result.
- Ambiguous Herdr selector: Antiek receives terminal `herdr_target_ambiguous`; fix the selector before retrying.
- Restart after a prompt receipt: progress and renewal are replayed, but Herdr is not prompted again.
