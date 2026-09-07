# Upgrade v0.6.1 → v0.7.0

1. Preserve `.env` and Docker volumes.
2. Overlay the upgrade ZIP on the existing project.
3. Run `PowerShell -ExecutionPolicy Bypass -File .\scripts\upgrade_v07.ps1`.
4. Run `PowerShell -ExecutionPolicy Bypass -File .\scripts\test_v07.ps1`.

Migration `0005_tenant_saas_config` creates `tenant_configs` and `tenant_products`. Bootstrap seeds defaults idempotently for existing tenants.
