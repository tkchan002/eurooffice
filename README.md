# EuroOffice 9.3.5 WebAssembly x2t builder (scoped v2)

**Purpose:** independently compile browser-compatible `x2t.js` and `x2t.wasm` from
**Euro-Office/core v9.3.5**, using CryptPad's modified x2t build recipe.

**Status: experimental, not a confirmed successful binary build.** The source
merge and the GitHub Actions Docker build must be executed on an internet-enabled
runner. The build has not been compiled end-to-end in the environment where this
package was prepared. This project does **not** download an existing x2t binary
or use the third-party `@kreijstal` binary package. It does fetch official
source code, a pinned compiler through CryptPad's Dockerfile, and source deps.

This is a **separate** repository. Do not replace Nurse Memo's known-working
converter until a built pair passes editor-level regression tests.

## Use GitHub.com — no terminal required

1. Create a **new repository**, e.g. `eurooffice-wasm-builder`.
2. Upload **all files** in this ZIP to the new repository, including the hidden
   `.github/workflows/` folder. Commit to the default branch.
3. Open **Actions** > **Build EuroOffice 9.3.5 x2t WASM (experimental)** >
   **Run workflow**.
4. Leave **mode = preflight** for the first run. This fetches source revisions,
   ports only build-scoped CryptPad changes and stops if any conflicts remain within that scope.
5. Download the **eurooffice-9.3.5-x2t-build-diagnostics** artifact. Inspect
   `source-merge.json`. Its `conflicts` array must be empty before compilation. The `excluded` array documents unrelated changes intentionally left as EuroOffice source.
6. If preflight passes, rerun with **mode = build**. This performs a full
   resource-intensive Docker/WebAssembly build, structural WASM validation and
   a real blank DOCX -> internal BIN -> DOCX smoke test.
7. If the entire workflow passes, download
   **eurooffice-9.3.5-x2t-wasm-verified-docx-smoke**. It includes `x2t.js`,
   `x2t.wasm`, `SHA256SUMS`, `validation.json`, `smoke-result.json`, and any
   CryptPad-produced Brotli/ZIP files.

No GitHub Pages deployment, CDN publish, npm dependency on prebuilt x2t or
automatic integration into Nurse Memo is performed.

### Source/version pins

| Component | Pin | Purpose |
| --- | --- | --- |
| EuroOffice core | `v9.3.5` (expected HEAD prefix `5a33ce6`) | The actual source being compiled |
| ONLYOFFICE core | `v9.3.0.140` (expected HEAD prefix `269dd9b`) | Three-way merge ancestor for CryptPad edits |
| CryptPad x2t WASM | `95f775fd3c42fae9e9af66ca072d3da3763e6c76` | WASM changes, Docker recipe, glue files |
| Emscripten | `4.0.11` in pinned CryptPad Dockerfile | First-attempt toolchain; NOT the third-party 6.0.9 build |
| Base Docker OS | Ubuntu 22.04 | CryptPad build system; not runner OS |
| Qt | `qt6-base-dev` from Ubuntu 22.04 | qmake-based compilation |
| Boost | `boost-1.84.0` | CryptPad Docker dependency |
| OpenSSL | `OpenSSL_1_1_1f` | CryptPad Docker dependency |

The workflow captures resolved full Git commit hashes to its diagnostics.
The tag/commit-prefix checks prevent accidental changes to the tagged inputs.
For stronger long-term byte-for-byte pinning, subsequently replace the two
short-prefix checks with full SHAs from your own passing run. Docker sub-dependency
repositories and apt packages are still not locked by digest; this is **not**
a bit-for-bit hermetic/reproducible build.

## Why v1 failed (75 conflicts) and how v2 differs

The previous port attempted to three-way-merge **every** difference in the CryptPad
`core` tree onto EuroOffice 9.3.5. This included independently maintained and
irrelevant third-party tooling such as `Common/3dParty/v8/` and
`Common/3dParty/socketio/`. The error was source selection, not necessarily
75 necessary converter fixes.

**v2 uses an explicit version-controlled port scope**, defined in
`config/port-scope.json`. It includes the source roots compiled by CryptPad's
x2t Docker recipe, while restricting `Common/3dParty` modifications to
listed actually used components. It excludes V8, Socket.IO, and `nc-build` /
`gclient_paths.patch` tooling. Those files remain as authentic EuroOffice
9.3.5 source rather than being overwritten. This is **not** an instruction to
remove them from the EuroOffice source tree; the filter only governs what
CryptPad changes may be transplanted.

The importer records all skipped differences as `excluded`, including the
exact file and exclusion reason, in `source-merge.json`. An excluded file is
never copied or merged. A conflict in an included build-scoped source still
stops preflight: the builder never silently resolves C++ conflicts by picking
EuroOffice or CryptPad. It checks that all three CryptPad renderer stubs
(`doctrenderer_empty.cpp`, `docbuilder_empty.cpp`, `docbuilder_p_empty.cpp`)
are present after the port.

**Scope is an engineering hypothesis** based on CryptPad's Dockerfile and can
be revised if compiler diagnostics demonstrate missing adaptations. A passing
preflight is not proof that all required build-time changes have been carried
over, and a passing compilation is not proof of round-trip fidelity. Keep the
existing Nurse Memo converter unchanged until full testing.

### CryptPad's specific WebAssembly approach

- Docker stages compile the converter and dependent static libraries with
  Emscripten 4.0.11 (Qt/qmake via `embuild.sh`).
- `wrap-main.cpp` exposes `main1(char *xmlPath)` to the JS runtime;
  `pre-js.js` prepares its browser/WASM loader.
- The x2t link uses `--pre-js`, exports the converter entry point and
  `ccall`/`FS`, and enables WebAssembly memory growth.
- The renderer stage substitutes three CryptPad-supplied `*_empty.cpp` stubs
  before compiling the renderer library.

None of this requires merging Chromium V8 or Socket.IO source-control scripts.
The untouched CryptPad Docker recipe still contains a few upstream toolchain
assumptions and may need explicit EuroOffice 9.3.5-specific fixes once the
full build is attempted; these will be diagnosed at the compile stage.

### Reading the preflight diagnostics

- `source-merge.json` > `excluded`: CryptPad changes NOT applied, with reasons.
- `source-merge.json` > `copied` / `merged`: CryptPad changes applied to EuroOffice.
- `source-merge.json` > `conflicts`: build-scoped changes that still need manual
  source reconciliation. The report is intentionally fatal on these.
- `source-merge.json` > `mandatory`: verifies renderer compatibility stubs.
- `cryptpad-source-changes.diff`: review diff of only selected changes.
- `eurooffice-diff.patch`: exact modifications made to pinned EuroOffice in preflight.
- `port-scope.json`: the policy used by the run, archived for traceability.

## Why the former workflow failed

CryptPad's Dockerfile contains three instructions similar to:

```dockerfile
COPY core/DesktopEditor/ /core/DesktopEditor/
RUN cp /core/DesktopEditor/doctrenderer/doctrenderer_empty.cpp /core/DesktopEditor/doctrenderer/doctrenderer.cpp
RUN cp /core/DesktopEditor/doctrenderer/docbuilder_empty.cpp /core/DesktopEditor/doctrenderer/docbuilder.cpp
RUN cp /core/DesktopEditor/doctrenderer/docbuilder_p_empty.cpp /core/DesktopEditor/doctrenderer/docbuilder_p.cpp
```

Those `*_empty.cpp` files are part of CryptPad's modified source. If the
Dockerfile is fed an unmodified EuroOffice source tree, the `cp` fails (exit
code 1). This builder brings *selected* CryptPad-added files into the EuroOffice source
**before** invoking Docker. If any subsequent compile conflicts arise, address
them individually: do not skip compiler errors or copy an old binary library.

## Toolchain and compatibility boundaries

The known third-party `@kreijstal/eurooffice-sdkjs-common@9.3.5-rc.1.build.1`
converter used Arch Linux's **Emscripten 6.0.9-git**, LLVM 24, Binaryen 132,
and a bubblewrap runner for CryptPad's Dockerfile stages, according to its
published build notes. This project deliberately starts with **CryptPad's
pinned Emscripten 4.0.11 Docker recipe**, because that is the open recipe we
can audit. Do **not** expect the same SHA256 hashes or identical imports and
memory behavior as the third-party converter. Migrating the entire build to
6.0.9 is separate engineering work, not a single version-string substitution.

`verify_converter.cjs` checks the WASM module and main export and records
hashes. `smoke_docx.cjs` executes a real conversion using the same XML API
pattern as CryptPad's test.js, but it only exercises a simple blank DOCX.
It does not validate spreadsheet, presentation, complicated DOCX, or PDF fidelity.
Before use in Nurse Memo, test the new pair inside the actual Ranuts/EuroOffice
loader with opening, saving, reopening, and multiple document classes. If
imports differ, adapt the browser loader only after auditing the generated
module's `validation.json`.

## Diagnostics and first-failure guide

- **Pin mismatch:** a tag moved or a source reference no longer resolves;
  verify the cited upstream release and replace with a reviewed full commit SHA.
- **Port conflict in `source-merge.json`:** an upstream file changed on both
  branches; inspect the paths in `.work/merge-conflicts` from the diagnostics
  artifact and write a reviewed 9.3.5-specific patch. Never ignore it.
- **Missing renderer stubs:** compare adapted files listed under `added` and
  ensure `doctrenderer_empty.cpp`, `docbuilder_empty.cpp`, and
  `docbuilder_p_empty.cpp` are present in the assembled context.
- **`emcc`/Qt/qmake failure:** inspect `docker-build.log`, note the named build
  stage, and check whether a CryptPad recipe expectation is incompatible with
  the final EuroOffice source layout. Do not apply broad text substitutions.
- **Link errors:** check the Emscripten flag set, source ABI changes, missing
  static libraries, and whether a native library was accidentally introduced.
- **WASM validation fails:** the expected `main1` export is absent or the file
  is not a valid WASM module; do not publish it.
- **DOCX smoke test fails:** a structurally valid WASM binary is not yet a
  compatible converter. The workflow does **not** upload it as a passing result.
- **Out of disk/memory:** CryptPad's multi-stage build and three upstream
  source trees can exceed standard GitHub-hosted runner resources. Use a
  larger runner (if your GitHub plan allows) or a self-hosted Linux runner with
  ample RAM and free storage. Do not treat resource failure as source failure.

The GitHub diagnostics artifact is retained even if the build fails. Build
results are not automatically tagged or released; intentional promotion is a
separate, manually reviewed step.

## Local, source-only unit tests

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m py_compile scripts/port_wasm_changes.py
bash -n scripts/fetch_sources.sh
node --check scripts/verify_converter.cjs
node --check scripts/smoke_docx.cjs
```

All of the above require only Python, git, bash and Node; no compiler.
The full GitHub Actions build additionally requires Docker Buildx, rsync,
network access, and substantial CPU/RAM/disk resources.

## References and licensing

- CryptPad source: https://github.com/cryptpad/onlyoffice-x2t-wasm
- CryptPad pinned recipe: https://github.com/cryptpad/onlyoffice-x2t-wasm/tree/95f775fd3c42fae9e9af66ca072d3da3763e6c76
- EuroOffice core source: https://github.com/Euro-Office/core/releases/tag/v9.3.5
- ONLYOFFICE comparison source: https://github.com/ONLYOFFICE/core/releases/tag/v9.3.0.140
- Third-party build description: https://socket.dev/npm/package/@kreijstal/eurooffice-fonts-1

EuroOffice and CryptPad-derived C++ source remain subject to upstream AGPL and
other associated license requirements. See their original repositories for
complete notices and ensure source/offers/notices are preserved in any
redistributed converter. The bundled `LICENSES/euro-office-LICENSE.txt` is a
convenience copy, not a substitute for legal review.
