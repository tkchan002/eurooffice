# EuroOffice 9.3.5 x2t WebAssembly builder — v6

**Status: experimental; the complete converter has not yet been compiled successfully.** This is a standalone GitHub Actions repository. It attempts to produce `x2t.js` and `x2t.wasm` using source pinned to EuroOffice 9.3.5 and CryptPad's x2t-WASM build system. It does not depend on precompiled converter binaries from third-party contributors.

## Why v6 exists

The uploaded v4 Docker failure was `No space left on device`, including while more than 30 library stages were concurrently copying files from a ~655 MB source context. v5 reduced simultaneous stages to two and provided capacity checks, but it had not yet changed the Dockerfile's repeated `COPY core/...` instructions. v5 also defaulted to **60 GiB minimum free**, preventing a normal free runner from even attempting compilation.

**v6 makes a structural optimization instead of deleting files blindly.** The upstream Dockerfile has many stages that start with `FROM base` and independently execute numerous identical context copies (`COPY core/Common /core/Common`, `COPY core/DesktopEditor /core/DesktopEditor`, etc.). A new `eurooffice-core` stage copies the source tree once; build stages that need source inherit that parent. The redundant copies are removed **only if their input and destination paths match exactly**. The original stage build commands, source content, Emscripten parameters, dependency stage copies and outputs are not removed or changed.

This reuses one parent Docker layer across many stages rather than independently storing the source files in dozens of layers. Docker/BuildKit can share those layers. **This does not guarantee that the C++ compilation will fit on a standard runner**: compiled intermediates and fetched Boost, OpenSSL, HarfBuzz and other sources still consume disk.

## Changes from v5

- New `scripts/optimize_docker_layers.py`: strictly validates pinned Ubuntu base and build stages; creates `eurooffice-core`; converts eligible stage parents; deletes only redundant identical `COPY core/... /core/...` *instructions*. Retains the final `build` and `output` stages and all library compilation steps. Runs **after** the existing Gumbo/Katana repair and recipe audit.
- `config/buildkitd.toml`: reduces independent parallel BuildKit stages from 2 to **1**. This lowers peak concurrent disk usage and memory pressure but can make the job slower.
- Frees redundant **Git checkout metadata** after capturing commit IDs and diff provenance. Git history is not needed inside the Docker build context.
- Keeps v5's cautious pre-build SDK cleanup, no duplicate host source copy, Docker disk telemetry, source allowlist, pinned commits, real DOCX round trip and verified-only artifact upload.
- Changes the default `minimum_free_gib` policy to **8** (with 12, 20, 40, 60 selectable). An 8 GiB check is only an experimental start threshold for a free runner, **not** a prediction of the remaining space needed to compile the source.
- Adds regression tests for the new Docker stage optimizer, including idempotency, modified upstream recipes, unexpected input locations, preservation of `COPY --from` and compiling the original converter target.

**Important:** Deleting a large source tree in a *later* `RUN rm -rf` would not release the original bytes from earlier immutable Docker layers. This is why v6 eliminates repeated layers at their creation point instead. Untracked source trees required for build are not deleted.

## Uploading to GitHub without CLI

If your repository currently contains v4 or v5, use `EuroOffice_WASM_Builder_9.3.5_v6_UPDATE_ONLY.zip`. Extract it on your computer and upload/replace each file into the **same subdirectory** in GitHub. Include the hidden `.github` folder. You can also replace the entire builder repo with `EuroOffice_WASM_Builder_9.3.5_v6_FULL.zip` contents (the full archive is for a clean repository; uploading files never automatically deletes old files).

In **Actions → Build EuroOffice 9.3.5 x2t WASM (shared-layer v6)**:

1. Run `preflight` first (default settings). This fetches sources, ports specific CryptPad adaptations, repairs the Dockerfile, applies the shared-layer optimization and uploads `shared-layers.json`. No Docker compilation is attempted.
2. Check the diagnostic artifact: `shared-layers.json` should show `ok: true`, a nonzero `removed_redundant_source_copy_instructions`, and the `eurooffice-core` stage. The source diff and Dockerfile diff are also included.
3. Run `build`, keeping `runner_label=ubuntu-24.04`, `cleanup_standard_host=true`, `minimum_free_gib=8`. Do not raise the minimum above the runner's actual free capacity if your intention is to test whether v6 fits. If the resource check fails, review `storage-preflight.json` rather than removing more arbitrary source files.
4. On failure, download `eurooffice-9.3.5-x2t-build-diagnostics`. Look at `docker-build.log`, `disk-samples.log`, `docker-build-status.txt` and `shared-layers.json`. Report the **first real compiler/build error**, rather than diagnosing subsequent disk errors as independent code defects.
5. Only if compilation and the DOCX smoke test pass will the workflow upload `eurooffice-9.3.5-x2t-wasm-verified-docx-smoke`. Even then, do not use those binaries in Nurse Memo without additional XLSX/PPTX regression testing as appropriate.

## Limits, security and reproducibility

- GitHub's **standard-hosted compute is free for public repositories**, but an individual **hosted job is limited to 6 hours**. This workflow is configured for 350 minutes. Free public minutes do not increase the runner's SSD capacity.
- Preflight is source and syntax validation, **not** a successful C++ build. The full build may still exceed disk/RAM/time limits or fail due to EuroOffice/CryptPad API incompatibility. No working `x2t.js`/`x2t.wasm` files are included.
- The workflow does **not** prune arbitrary Docker volumes, delete source paths whose consumers are uncertain, or automatically skip supported document formats to save space.
- The builder fetches pinned top-level sources, but transitive dependencies downloaded by upstream scripts are not all independently content-addressed. For true bitwise reproducibility, those still need to be pinned and audited.
- Running untrusted contributors' code within Docker or a workflow can execute arbitrary commands. Keep workflow edits reviewed even though the repository is public. Use no production hospital credentials on a builder.

## Source versions

- EuroOffice `core`: `v9.3.5` (`5a33ce6...`, verified in the build job).
- CryptPad `onlyoffice-x2t-wasm`: `95f775fd3c42fae9e9af66ca072d3da3763e6c76`.
- CryptPad Dockerfile's Emscripten toolchain: `4.0.11`.
- Final target: `output`; runtime smoke test: DOCX conversion.

References: [Docker layer sharing](https://docs.docker.com/engine/storage/drivers/), [GitHub Actions limits](https://docs.github.com/en/actions/reference/limits), [CryptPad pinned Dockerfile](https://github.com/cryptpad/onlyoffice-x2t-wasm/blob/95f775fd3c42fae9e9af66ca072d3da3763e6c76/Dockerfile).
