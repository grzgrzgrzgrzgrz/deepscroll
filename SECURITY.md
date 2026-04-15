# Security Policy

## Supported Versions

Security fixes are applied to:

- the latest commit on `main`
- the most recent published release, once releases exist

Older snapshots may not receive fixes.

## Reporting a Vulnerability

Please do not open public GitHub issues for suspected security problems.

Report vulnerabilities privately to:

- `grzegorzolszowka@gmail.com`

Include:

- a clear description of the issue
- impact and exploitation assumptions
- reproduction steps or a proof of concept
- any suggested mitigations

I will acknowledge receipt as quickly as possible and work toward a coordinated fix.

## Threat Model Notes

`deepscroll` executes model-generated Python using RestrictedPython. That is a
best-effort language-level restriction, not a full operating-system sandbox.

If you process untrusted content or run untrusted prompts:

- prefer an isolated container or VM
- avoid giving the process access to sensitive local files
- treat API keys and model outputs as sensitive operational data
