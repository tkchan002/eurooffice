# EuroOffice 9.3.5 x2t WebAssembly Builder — v7

**Experimental. No verified converter binary is included.** This repository builds from the pinned EuroOffice 9.3.5 source and the pinned CryptPad x2t-WASM recipe using GitHub Actions. It is separate from Nurse Memo; do **not** overwrite the working `x2t.js` / `x2t.wasm` until real conversion tests pass.

## v7: fix confirmed UnicodeConverter Docker failure

The v6 GitHub run successfully compiled the `UnicodeConverter` project. Its compiler output shows:

```
... -o UnicodeConverter/core_build/linux_64/release/obj/UnicodeConverter.o ...
rm -f build/lib/linux_64/libUnicodeConverter.a
ar cqs build/lib/linux_64/libUnicodeConverter.a UnicodeConverter/core_build/linux_64/release/obj/UnicodeConverter.o
```

The pinned CryptPad Dockerfile nevertheless executes:

```
RUN mv /core/UnicodeConverter.o /core/build/lib/linux_64/libUnicodeConverter.a
```

That `mv` assumes an object file at a different location and incorrectly treats an object as a static-library archive. The archive already exists. v7 removes **only this stale `mv`** and substitutes an explicit check:

```dockerfile
RUN test -s /core/build/lib/linux_64/libUnicodeConverter.a && \
    ar t /core/build/lib/linux_64/libUnicodeConverter.a | grep -Fxq UnicodeConverter.o
```

This verifies that the archive is nonempty and includes the actual compiled object. It does not copy, rename, fake, or skip the library. It preserves all compilation commands and dependent `COPY --from=unicodeconverter` instructions.

The change is applied by `scripts/tune_docker_recipe.py` **before** v6's shared-layer optimization. `scripts/check_docker_recipe.py` refuses to proceed if the obsolete move remains or the archive-verification instruction is missing. The adapter is idempotent and rejects unrecognized upstream recipe changes.

## Files to update from v6

If your repository is already on **v6**, use `EuroOffice_WASM_Builder_9.3.5_v7_UPDATE_ONLY.zip`. Replace the following five files using the GitHub website, preserving their paths:

- `.github/workflows/build-eurooffice-x2t.yml`
- `scripts/tune_docker_recipe.py`
- `scripts/check_docker_recipe.py`
- `tests/test_docker_recipe.py`
- `README.md`

For a new builder repository, use `EuroOffice_WASM_Builder_9.3.5_v7_FULL.zip` instead. Do not add this builder directly to the Nurse Memo web app; maintain it as a separate build repository.

## Run the workflow

1. In GitHub, open **Actions → Build EuroOffice 9.3.5 x2t WASM (qmake-archive v7)**.
2. First choose `preflight`, `runner_label=ubuntu-24.04`. Check that `docker-recipe-audit.json` has `"ok": true` and `"unicodeconverter_archive_verified": true`.
3. Run `build` with `runner_label=ubuntu-24.04`, `cleanup_standard_host=true`, `minimum_free_gib=8` (experimental setting, **not** a disk capacity guarantee).
4. If the next step fails, download `eurooffice-9.3.5-x2t-build-diagnostics` and inspect `docker-build.log` for the **first** substantive compiler or linking error. Upload that ZIP for further diagnosis.
5. Only when compilation and the DOCX smoke test pass does the workflow publish a converter artifact. Additional format tests and actual Nurse Memo integration tests remain necessary.

## What stays unchanged from v6

- Pinned EuroOffice 9.3.5 / CryptPad sources; reviewed source allowlist (no whole-fork merge).
- Gumbo/Katana source handling; shared immutable EuroOffice Docker source layer.
- Serialized BuildKit stages and disk monitoring for free/public GitHub Actions runners.
- No arbitrary deletion of C++ source dependencies or compiler outputs.
- Dedicated converter verification and DOCX round-trip smoke test.

## Local validation and limitations

The v7 regression suite tests the old failing instruction, the new archive check, incorrect/missing archives, idempotency and the unchanged downstream dependency wiring. It also runs the existing source, Docker and GitHub workflow tests. Local syntax/unit testing is **not** a full Emscripten compilation. The pinned recipe may expose more EuroOffice-specific differences once additional libraries compile. GitHub-hosted public-repository jobs still have individual runtime and storage limits, irrespective of billing.

No proprietary credentials or patient data are required for this build. The workflow fetches third-party sources; review their licensing and security posture before using binaries in a hospital deployment.

Source: [pinned CryptPad Dockerfile](https://github.com/cryptpad/onlyoffice-x2t-wasm/blob/95f775fd3c42fae9e9af66ca072d3da3763e6c76/Dockerfile).
