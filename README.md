# EuroOffice 9.3.5 x2t WASM Builder — v9 (source-independence baseline)

**Status: independent source archiving implemented; independent WebAssembly compilation NOT yet proven.**

This project is a separate build system for `x2t.js` and `x2t.wasm`. **Do not replace your known-working Nurse Memo converter.** It preserves all v8 EuroOffice-first/allowlisted source adaptations, browser-only `doctrenderer` qmake exclusions, the v6 disk optimization and v7 archive verification. The big v9 change is eliminating **live CryptPad source fetching on ordinary builds**.

## What the v9 ZIP contains—and does not

Included:
- Full v8 experimental Docker/Emscripten converter builder.
- One-time bootstrap GitHub Action that obtains the original pinned CryptPad and EuroOffice source commits, then creates two checksummed source archives and publishes them as **Release assets in YOUR GitHub repository**.
- An automatically generated `config/sources.lock.json` that pins the hashes, asset sizes and full commits and is committed to the repository (if branch permissions permit).
- A build GitHub Action that downloads **only your own Release assets** for its source inputs, verifies both SHA-256 hashes, and extracts them securely. It has no live CryptPad checkout step.
- Local no-network source restore and checksum-corruption tests.
- The exact original Kreijstal shell and Bubblewrap reference scripts from the user's archived npm package, documented but **not** run automatically.
- An audit of external downloads still present in the Docker recipe.

Not included:
- Neither the enormous CryptPad and EuroOffice source snapshots nor toolchain binaries. **They must first be archived using the bootstrap workflow.**
- The working ~38 MB third-party WASM binary; preserve the original uploaded npm package separately.
- A fully offline C++ compiler environment. Docker and Emscripten still fetch dependencies from other sites; this is an **independent source baseline**, not a fully hermetic build.
- Proof that final EuroOffice 9.3.5 compiles to a verified converter. v8 has not demonstrated completion.

## First-time setup using only GitHub's website

1. Create or update a **public standalone** repository (for example `eurooffice-wasm-builder`). Upload the **contents** of the full v9 ZIP preserving hidden `.github` folders, or apply the update-only ZIP to the existing v8 repository.
2. Open **Actions → Archive pinned source inputs (one-time bootstrap)** → **Run workflow**. Enter exactly `ARCHIVE` for the confirmation box.
3. This first run **must contact CryptPad and EuroOffice once** to capture their commits while they are available. The workflow checks out pinned revisions, packages their source without `.git`, computes SHA-256 checksums, tests restoration, and creates Release `x2t-source-v9.3.5-baseline-1` in **your own repo**.
4. It attempts to commit `config/sources.lock.json` to the triggering branch. If your GitHub Actions permissions or branch protections prevent pushing, go to that Release, download **`sources.lock.json`**, and upload it yourself at `config/sources.lock.json` using GitHub's web editor. Otherwise, future builds intentionally refuse to continue. (GitHub Actions Settings → General → Workflow permissions may require read/write permissions for a bot push.)
5. Download the three release assets (`cryptpad-source.tar.gz`, `eurooffice-source.tar.gz`, `sources.lock.json`) to an **independent backup** outside GitHub (e.g., external drive). An asset in only one GitHub repository is **not disaster-proof**.
6. Open **Actions → Build EuroOffice 9.3.5 x2t WASM (owned snapshots v9)** → Run `preflight`. Only after preflight succeeds, consider running `build` (free `ubuntu-24.04`, minimum free 8 GiB, cleanup enabled). The full build may still hit C++ or disk limits.

GitHub Release assets, unlike time-limited Actions diagnostic artifacts, are appropriate for preserving these large files, but retain an external backup because GitHub, your account or the release itself could still become unavailable. A release with the tag already present intentionally cannot be silently overwritten by the bootstrap workflow.

### What happens after CryptPad disappears?

The build workflow never executes `scripts/fetch_sources.sh`. It calls `scripts/fetch_archived_sources.sh`, which obtains **your own** release archives and verifies them using SHA-256 hashes committed in `config/sources.lock.json`. It does not need the live CryptPad repository. The archived CryptPad-derived recipe still contains third-party *non-CryptPad* dependency downloads, so those dependencies may remain externally required until mirrored separately.

An entirely local restoration also works without GitHub if you possess the archives and the lockfile:

```bash
# From a clean checkout of this builder, with both .tar.gz files already
# present under .work/source-archives/:
SOURCE_OFFLINE=true bash scripts/fetch_archived_sources.sh
```

This only checks the **source-restoration phase**, not a network-isolated full compilation. Back up the build repository, release archives, reference binary package, licenses, and toolchain details together.

## Technical architecture

| Responsibility | Process | Dependency |
|---|---|---|
| One-time bootstrap | `scripts/bootstrap_upstream.sh` + original pinned fetcher | Original CryptPad + EuroOffice, once |
| Own source archive | `scripts/source_snapshot.py create` | Local pinned checkouts |
| SHA256 lock | `config/sources.lock.json` | Committed to own repo |
| Normal builds | `scripts/fetch_archived_sources.sh` + `source_snapshot.py restore` | Own release or offline copies |
| WebAssembly preparation | `prepare_eurooffice.py`, `port_renderer_qmake.py`, recipe adaptations | Restored source snapshots |
| Remaining remote inputs | `audit_external_inputs.py` | Non-hermetic and **not archived** |
| Converter build | Existing Docker BuildKit pipeline | Emscripten 4.0.11 pinned by recipe, external dependencies |
| Verification | Existing DOCX smoke test | Does not replace XLSX/PPTX regression tests |

### Important source provenance nuance

Kreijstal's original `build-x2t-eurooffice.sh` was found inside your uploaded `eurooffice-sdkjs-common-9.3.5-rc.1.build.1.tgz`. It uses CryptPad's recipe and a host Emscripten 6.0.9-git toolchain. The script does **not** itself pin the source checkout, despite its README identifying the CryptPad commit. Our v9 baseline instead preserves the separately pinned CryptPad-derived WASM recipe (`95f775fd…`) and final EuroOffice v9.3.5 source as **distinct archives**, then applies the reviewed v8 adaptations. Do not represent these as identical to the original RC binary's source provenance.

In `reference/kreijstal/` the historical scripts are preserved for traceability. They are not a drop-in reproducible Ubuntu build. For eventual independence from all external projects, freeze/mirror the exact Emscripten SDK and native dependency source tarballs, pin container base-image digests, and run a **network-disabled full build** on clean hardware. That is not implemented in v9.

## Verification and failure modes

- Unit tests: `python3 -m unittest discover -s tests -p 'test_*.py'`.
- Test local extraction: `python3 scripts/source_snapshot.py restore --lock config/sources.lock.json --archives-dir .work/source-archives --work-root .work/verify-restored`. Run this only when the lock and archive assets exist.
- A broken SHA-256, asset length, source revision, unsafe archive member or missing `.lock.json` fails closed.
- The first archiving job may need GitHub write permissions and enough **temporary** disk to package both full source trees. It is not guaranteed to fit the free 14 GB runner (unlike the much larger compilation, it does not build dependencies).
- Source archive ZIP does not include the compiler; you can lose the ability to compile if other repositories disappear. The diagnostics `remaining-network-dependencies.json` highlight this risk.
- Reference known-good converter hashes: `x2t.js`: `66c2fe0e6de280d81643ffc7ba31cd9a5205c004b72227c08e78a0821ba0e520`; `x2t.wasm`: `841ff9b648f0a03a6e610e6f1d0e822a526dd3142eb43a64101653963f4fc35e`.

## Maintenance policy

Keep the source archives and lockfile immutable. A future EuroOffice upgrade must use a new release tag, independently reviewed port policy, and tested converter artifacts. Never silently replace the pinned archive at an existing tag. Maintain third-party copyright and AGPL licenses and check any distribution obligations with your hospital IT/legal team.
