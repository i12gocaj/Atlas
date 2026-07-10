# Security policy

## Supported scope

Atlas is a hackathon prototype built around a synthetic dataset. It is intended
for local evaluation and portfolio demonstration, not for processing production
telemetry without additional controls.

## Safe local use

- Keep `ATLAS_OLLAMA_HOST` on `localhost` when prompts may contain sensitive
  information.
- Pipe text to `atlas scan` instead of putting sensitive text in shell arguments.
- Do not replace the included synthetic snapshot with real telemetry before
  publishing or sharing the dashboard.
- Treat generated `data/` files as potentially sensitive. They are ignored by
  Git and should remain local.
- The bundled server listens only on `127.0.0.1`.

Atlas is detective and read-only. It does not block prompt submission, replace a
DLP, or provide a production data-retention model.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting for this repository instead
of opening a public issue with exploit details or sensitive data.
