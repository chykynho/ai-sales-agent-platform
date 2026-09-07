# Upgrade v0.7.1 -> v0.8.0

1. Extract the v0.8 upgrade over the existing project.
2. Do not delete `.env` or Docker volumes.
3. Run `PowerShell -ExecutionPolicy Bypass -File .\scripts\upgrade_v08.ps1`.
4. Validate migration `0005_tenant_saas_config -> 0006_whatsapp_channel`.
5. Run `PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v08.ps1`.

The upgrade appends local-only webhook secret defaults when the variables are absent. Replace them before exposing a real public endpoint.
