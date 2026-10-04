# v1.0 release gate

The historical development directory is not the public repository. Existing staged files are not sanitized by `.gitignore`. Publish only the explicitly exported tree after its manifest, actual Git index, and package contents have been checked.

## Source and tests

1. Run the complete Python tests, `npm run test:release`, `npm run test:mix`, JavaScript syntax checks, `npm audit`, and both environments' `uv pip check`.
2. Export with `npm run export:github`. The new directory is `dist/github-source-1.0.1`; an existing export is never overwritten. Each file is listed with SHA-256 in `public-source-manifest.json`.
3. Run `node scripts/verify-source.cjs dist/github-source-1.0.1`. Reject extra, missing or changed files, personal user paths, credentials, non-public embedding arrays, and unverified ambience sources.
4. Initialize Git only in that export, add the files, then run `node scripts/verify-public-index.cjs .` there to compare every staged filename and blob hash with the export and manifest. Preserve `.gitattributes` so line-ending conversion does not silently change the public files. Never add the historical working tree as the public source.
5. In the exported source, install Node dependencies and run its tests too. Development dependencies and test caches are not release assets.

## Build from the export

From the public source directory, with Node.js, npm and a build Python available:

```powershell
npm ci
npm run package
$build = Get-Content .\release\build-source.json -Raw | ConvertFrom-Json
node scripts/verify-package.cjs $build.directories[0] $build.source
python scripts/release-artifacts.py --source . --package $build.directories[0] --output release-artifacts-1.0.1
```

The package builder makes another verified allowlisted staging tree, then creates the Windows x64 Electron package from it. `build-source.json` records the exact staging tree. The package auditor compares all ASAR product files, backend resources, runtime specification and notices with that tree; it rejects development/cache/user-data paths. The ZIP tool verifies every archived file against its uncompressed content and writes `release-content-manifest.json` and `SHA256SUMS.txt`. Use a new output directory for each artifact set.

Keep the app AGPL license, Electron and Chromium notices, original D-DIN licenses, `THIRD_PARTY_NOTICES.md`, `AMBIENCE_ATTRIBUTION.md`, and machine-readable recording provenance. Runtime tools and model weights are downloaded separately; their own licenses apply. Do not claim that HF login alone grants SA3 model permission.

## Runtime and acceptance

- Test the exact noninteractive PowerShell install and repair invocation with Python/uv/FFmpeg absent from PATH, including an interrupted install and a damaged dependency/source file. Verify the resulting runtime receipt and CUDA device 0 operation.
- Exercise fresh, malformed and incomplete configuration; safe first-generation retry; QC-gated completion and refill; interrupted migration; missing/corrupt builtins; audio playback, output fallback and bounded ambience buffers.
- Perform the [clean Windows acceptance matrix](CLEAN_WINDOWS_ACCEPTANCE.md). Keep standard-user, real Chinese username, no D: drive, physical audio devices, clean GPU drivers and code-signing checks PENDING until actually tested.
- Include [release notes](RELEASE_NOTES_1.0.md) and [backup/recovery instructions](RECOVERY_AND_UPGRADE.md). A source/test pass alone is not a clean-machine or listening acceptance pass.

Creating these local artifacts does not publish a remote repository or release. Authentication, remote creation and public upload are separate owner actions.
