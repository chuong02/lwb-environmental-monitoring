# Verification record - 2026-10-22

## Executed in the authoring environment

- 15 standard-library Python tests: PASS.
  Status thresholds, clock skew, null/sentinel conversion, parameter validation,
  backup/apply/rollback, refusal of invalid project root, original file integrity.
- Python AST parsing for delivered Python sources: PASS.
- Bash syntax check of start_mobile_api.sh: PASS.
- Lexical delimiter check of 15 Dart files (12 implementation + 3 tests): PASS.
  This checks balanced brackets/strings ONLY, not Dart types or Flutter API compatibility.
- Package integrity and relative imports checked before ZIP creation.

## Prepared, NOT executed in this environment

- 13 Django/DRF endpoint tests, including a 252-node pagination fixture and
  a two-query assertion for a list page. Run by backend/run_selftest.py using
  the user's existing Django environment and an in-memory SQLite database.
- 10 Dart/Flutter tests (models, HTTP service, polling lifecycle/no overlap).
- flutter analyze; flutter test; Android APK build; Android UI rendering.
- Real PostgreSQL load test, simultaneous mobile users, real RF Node counts,
  end-to-end MQTT-to-Mobile correctness, long running reliability.
- PowerShell installer/restore execution on Windows.

The authoring container has no Flutter SDK, Django or DRF. Network installation
of those dependencies was unavailable. No claim is made that a compiled APK or
end-to-end deployment has already passed. The installers run applicable tests on
the target machine before normal startup, and stop if those tests fail.

## Compatibility basis

Read live from chuong02/lwb-environmental-monitoring (folder backend/) through the GitHub connector:
- telemetry/models.py, blob 39a8d719678c5aeaa0f1855390276f4ecf654d61
- telemetry/views.py, blob 734c5ea7bcdf85720cec5452fcf4586e3147bcb6
- telemetry/urls.py, blob 6d2ebcfec591a80aeff777191c36ecd90c6a109a

The local WSL checkout may differ. The installer checks required model fields,
adds separate files and preserves all existing code/configuration/DB records.

## Release boundary

This package is a local read-only monitoring implementation, not a completed
enterprise deployment. No mobile authentication UI, per-gateway authorization,
public HTTPS hosting, command downlink, push notification, or 24/7 service setup
is included. Normal (non-local) API mode denies access except authenticated staff.
The local configuration must never be exposed by a public tunnel/reverse proxy.
