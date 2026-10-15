# Mondo Music Video repository rules

- Keep this independent public application free of private studio source,
  prompts, documentation, credentials, actors, models and production artifacts.
- Never import from a sibling studio checkout or link its Git object store.
- Every delivered batch of program changes needs a new application version.
  The version source is `MGL_APP_VERSION` in `webapp/mondo_web.py`; update
  pyproject.toml, README, version assertions and relevant release documentation
  together. Use a requested version or increment the patch version once per
  delivery. Documentation-only deliveries do not bump versions.
- Freshly import the version handler when verifying a version. Verify live
  `/api/version` too before claiming that a running process has that version.
- Keep one active operation, no production queue, explicit paid consent and
  upstream OAP verification. Do not retry paid submissions automatically.
- Use temporary data and mock services for automated tests. Real paid/GPU/Topaz
  work requires deliberate operator verification, not an automated test run.
- Do not publish or push without user authorization.
