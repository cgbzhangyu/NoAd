# Changelog

All notable changes are recorded here. Versions follow Semantic Versioning.

## [Unreleased]

### Changed

- Repository scope is now limited to app-specific HTTPS rewrite and response-script rules.
- Generated modules are published only under `dist/apps/`.
- General advertising is documented as direct upstream `Advertising.list` and `Advertising_Domain.list` references.
- Bilibili splash blocking uses the repository-owned response filter that clears ad and cache-retention lists without logging request data.
- Device verification passed for Bilibili, Taobao and JD; the SMZDM rule remains available with a failed status for further diagnosis.
- SMZDM now clears the `/util/loading` splash response with a repository-owned minimal filter so cached startup ads can expire.

### Removed

- Stable, canary and experimental release channels, aggregate modules, allowlist promotion, reports and checksums.
- The duplicated general Bilibili domain rule; general domain blocking now belongs to the upstream rule sets.
