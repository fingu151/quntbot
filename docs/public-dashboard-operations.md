# Public Dashboard Operations

This dashboard is read-only. It refreshes local JSON artifacts and never submits
orders.

## Normal Start

Use this for the regular dashboard plus a 30-minute refresh loop:

```powershell
.\scripts\start_public_dashboard_with_refresh.ps1 -Port 8520 -HostAddress 0.0.0.0 -BrowserAddress localhost -RefreshIntervalMinutes 30 -RunTimeoutMinutes 10
```

Open on this PC:

```text
http://localhost:8520/
```

Open from another device on the same network:

```text
http://<PC_LOCAL_IP>:8520/
```

Do not open `http://0.0.0.0:8520/` in a browser. `0.0.0.0` is only the
listen address.

## Check What To Do Next

Run this whenever you are unsure whether the dashboard is fresh:

```powershell
.\venv\Scripts\python.exe -m scripts.public_dashboard_ops --max-age-minutes 35
```

Read these fields:

- `overall_status=ok`: no immediate manual work.
- `overall_status=needs_attention`: run the `recommended_command`.
- `recommended_action`: plain-language next step.
- `recommended_command`: exact command to run next.

For machine-readable checks:

```powershell
.\venv\Scripts\python.exe -m scripts.public_dashboard_ops --max-age-minutes 35 --json
```

## Refresh Once

Use this when the dashboard looks stale:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\refresh_public_portfolio_snapshot.ps1 -RunOnce -RunTimeoutMinutes 10
```

Use this when Ticker Briefs still show actionable `Needs review` after a normal
refresh. It tries public supplemental source discovery before manual work:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\refresh_public_portfolio_snapshot.ps1 -RunOnce -RunTimeoutMinutes 10 -IncludeSupplementalDiscovery
```

Use this for a local-only refresh that avoids supplemental source URL ingestion:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\refresh_public_portfolio_snapshot.ps1 -RunOnce -RunTimeoutMinutes 10 -SkipSupplementalSources
```

## Start After Reboot

Preferred current-user startup shortcut:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\install_public_dashboard_startup_shortcut.ps1
```

Preview the shortcut command without creating it:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\install_public_dashboard_startup_shortcut.ps1 -WhatIf
```

Alternative Windows logon scheduled task:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\install_public_dashboard_startup_task.ps1
```

Preview the task command without creating it:

```powershell
powershell.exe -ExecutionPolicy Bypass -File .\scripts\install_public_dashboard_startup_task.ps1 -WhatIf
```

For a local-only startup refresh loop, add `-SkipSupplementalSources` to either
installer command.

## Research Brief Workflow

1. Check Ticker Briefs in the dashboard.
2. If `Operator Next Action` says `Automated quality pass`, run the command shown
   in that card.
3. If only `Latest not found` remains, no manual work is required immediately.
   Those tickers are monitored separately until another broad source refresh.
4. If portfolio tickers are still missing after supplemental discovery, fill the
   supplement template or add known public report URLs, then refresh again.

## Logs

Logs are written under `.tmp`:

- `.tmp\public_portfolio_snapshot_refresh.log`
- `.tmp\public_dashboard_streamlit.log`

If the site does not respond, inspect the Streamlit log first. If the timestamp
or Ticker Briefs are stale, inspect the refresh log and then run
`scripts.public_dashboard_ops`.
