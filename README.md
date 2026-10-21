# EuroOffice 9.3.5 x2t WebAssembly Builder — v4 (Gumbo/Katana Docker repair)

**Status: experimental.** This repository is intended to independently compile `x2t.js` and `x2t.wasm` from EuroOffice/core `v9.3.5`, without consuming another developer's precompiled converter. The full C++ compilation has **not** yet been completed or verified. Keep the existing working Nurse Memo converter unchanged until the build and document round-trip tests succeed.

## v4: what the uploaded GitHub Actions diagnostics revealed

The supplied `eurooffice-9.3.5-x2t-build-diagnostics(1).zip` proves that v3 source preparation completed and that Docker failed **before compiler execution**, while resolving the undeclared `gumbo` stage:

```
[internal] load metadata for docker.io/library/gumbo:latest
ERROR: pull access denied, repository does not exist or may require authorization
Dockerfile:490 COPY --from=gumbo /gumbo-parser /gumbo-parser
```

The recipe audit correctly identified **two undefined Docker stage names**, `gumbo` and `katana`, but v3 only warned rather than blocking the expensive Docker command. These names were not intended to be Docker Hub images. This is not an authentication problem, so Docker login will not fix it.

### Verified parser source relationships

- The pinned CryptPad recipe already defines `FROM base AS html` and calls `python fetch.py` in `core/Common/3dParty/html`.
- EuroOffice 9.3.5 `Common/3dParty/html/fetch.py` clones `google/gumbo-parser` at `aa91b27b02c0c80c482e24348a457ed7c3c088e0` and `jasenhuang/katana-parser` at `be6df458d4540eee375c513958dcb862a391cdd1`, applying several source compatibility edits.
- EuroOffice `Common/3dParty/html/gumbo.pri` directly includes the Gumbo C sources and `htmltoxhtml.cpp` in qmake `SOURCES`. The corresponding `katana.pri` likewise includes the Katana C sources. There is no requirement for an additional independently compiled `libgumbo.a` / `libkatana.a` just to use these `.pri` projects.
- The old `libgumbo.a` / `libkatana.a` COPYs appear only in the **optional `log-symbols` stage**, not in the final `output` stage's dependency graph. They can be removed without inventing replacement images or builds.

### Exact source-recipe changes

v4's `scripts/tune_docker_recipe.py` modifies the **pinned** CryptPad Dockerfile in `.work/cryptpad/Dockerfile`:

1. In `fb2file`, replace `COPY --from=gumbo /gumbo-parser /gumbo-parser` with `COPY --from=html /core/Common/3dParty/html /core/Common/3dParty/html`. That supplies the fetched parser tree **where EuroOffice's `.pri` files expect it**.
2. In optional `log-symbols`, remove the two invalid `COPY --from=gumbo ...libgumbo.a` and `COPY --from=katana ...libkatana.a` lines. These are not inputs to the actual converter build. The C source is compiled via the existing qmake source lists.
3. Retain the v3 correction that copies `libFb2File.a` into the **final `build` stage**, so we do not disable EuroOffice's FB2 conversion logic.
4. Fail rather than guess if the pinned Dockerfile's structure changes.

`check_docker_recipe.py` now **exits with failure** if any undefined `COPY --from` stage remains, the `html` stage is missing its fetch command, the `fb2file` stage lacks the parser source, or the final build stage lacks `libFb2File.a`. It writes details to `artifacts/provenance/docker-recipe-audit.json` before Docker starts.

## Install via GitHub website (no terminal)

**If your v3 repository is already uploaded:**

1. Download and extract `EuroOffice_WASM_Builder_9.3.5_v4_UPDATE_ONLY.zip`.
2. Upload its **six files** to their identical paths in your GitHub repository, replacing the current versions. Upload the *contents* of the ZIP, not the ZIP itself. Preserve the `.github` directory.
3. Open **Actions → Build EuroOffice 9.3.5 x2t WASM (parser sources v4)**.
4. Run `preflight`. Download `eurooffice-9.3.5-x2t-build-diagnostics` and check `docker-recipe-audit.json`: the `ok` field must be `true` and `undefined_copy_sources` must be empty.
5. Then run `build`. If it fails, attach that run's diagnostics ZIP and the compiler's **first actual error**. Do not downgrade security fixes or replace a needed library with arbitrary host binaries.

**If starting over:** extract `EuroOffice_WASM_Builder_9.3.5_v4_FULL.zip` and upload the extracted files to a new GitHub repository. This is standalone; it does not alter Nurse Memo.

For a historical v2 repository, delete the obsolete files `config/port-scope.json`, `scripts/port_wasm_changes.py`, and `tests/test_port_wasm_changes.py`. They are not used by the v4 workflow.

## Validation and scope

| Check | Status |
| --- | --- |
| Original v3 undefined-stage failure reproduced in a pinned-layout fixture | Verified |
| Repair eliminates the undefined `gumbo` / `katana` references | Verified on fixture |
| `fb2file` gets fetched HTML parser source; final link keeps FB2 | Verified on fixture |
| Repair is idempotent, rejects changed Dockerfile structure | Verified |
| All existing EuroOffice source conflict preservation tests | Passed |
| Repository source and workflow syntax | Checked locally |
| Full pinned Dockerfile processed by GitHub | **Awaiting next preflight** |
| EuroOffice 9.3.5 C++ compilation and emitted converter | **Not yet verified** |
| Browser/document conversion compatibility | **Not yet verified** |

**22 Python tests pass** as of packaging. They test source preparation and Docker recipe transformations; they do not compile EuroOffice. The actual build may reveal further issues, particularly toolchain/ABI mismatches, external dependency fetches, and OpenSSL linkage. The workflow will preserve the first failing compile log for diagnosis.

### Reproducibility notes

- EuroOffice source is pinned to the `v9.3.5` tag (expected Git hash prefix `5a33ce6`).
- CryptPad build recipe is pinned to commit `95f775fd3c42fae9e9af66ca072d3da3763e6c76` and Emscripten `4.0.11`.
- Gumbo and Katana source revisions are specified by EuroOffice's `fetch.py`.
- Some transitive dependencies are still retrieved from moving repositories/package registries; this pipeline is *version-pinned at the main source level* but is not proven bit-for-bit reproducible or fully hermetic.
- The v3 allowlisted source adaptations remain unchanged. No wholesale merge with older ONLYOFFICE code is performed. EuroOffice TLS validation and modern PDF/OpenSSL source remain protected by tests/assertions.
- The successful `build` mode (if achieved) verifies its generated WebAssembly and runs a DOCX smoke conversion before uploading a separate verified-converter artifact. Passing preflight never indicates successful compilation.

## Technical references

- [Pinned CryptPad Dockerfile](https://raw.githubusercontent.com/cryptpad/onlyoffice-x2t-wasm/95f775fd3c42fae9e9af66ca072d3da3763e6c76/Dockerfile)
- [EuroOffice 9.3.5 HTML parser fetch.py](https://raw.githubusercontent.com/Euro-Office/core/v9.3.5/Common/3dParty/html/fetch.py)
- [EuroOffice 9.3.5 Gumbo qmake project](https://raw.githubusercontent.com/Euro-Office/core/v9.3.5/Common/3dParty/html/gumbo.pri)
- [EuroOffice 9.3.5 Katana qmake project](https://raw.githubusercontent.com/Euro-Office/core/v9.3.5/Common/3dParty/html/katana.pri)

Keep all upstream license notices. Before releasing generated converter binaries for hospital use, review the complete dependency licenses and perform broader DOCX/XLSX/PPTX regression and security testing.
