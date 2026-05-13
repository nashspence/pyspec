# Generated Artifacts

`spec/generated/` is durable product evidence, not a disposable cache. The current policy is to check in every generated artifact, including audit PNG renders exactly as produced.

Validation enforces a closed generated tree:

- every expected projection must exist
- no extra generated files may be present
- text projections must match compiler output
- audit SVG files must be valid SVG
- audit PNG files must have a PNG header
- BDD features must be the single canonical generated corpus

Future work can add compression or retention knobs, but the default package API already models that decision through `ArtifactPolicy`.
