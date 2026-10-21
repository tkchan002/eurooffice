# EuroOffice 9.3.5 WebAssembly x2t builder

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
   reports CryptPad-vs-EuroOffice changes and stops if there are conflicts.
5. Download the **eurooffice-9.3.5-x2t-build-diagnostics** artifact. Inspect
   `source-merge.json`. Its `conflicts` array must be empty before compilation.
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

## Exactly what CryptPad changes

The **cryptpad/onlyoffice-x2t-wasm** repository maintains a modified copy of
ONLYOFFICE/core in `/core` (its README documents comparing against
`ONLYOFFICE/core v9.3.0.140`). It also supplies:

- `Dockerfile`: separate stages compile numerous core libraries with Emscripten;
  the final stage builds `X2tConverter/build/Qt/X2tConverter.pro`;
- `embuild.sh`: overrides qmake to use `emcc` / `em++` / `emmake`, ICU,
  size-optimized compilation, WASM memory growth, and exported runtime methods;
- `wrap-main.cpp`: exposes `main1(char* xmlPath)` to call the ordinary x2t `main`;
- `pre-js.js`: disables automatic main execution/exit and locates the WASM
  companion file relative to the loader;
- `DesktopEditor/doctrenderer/*_empty.cpp`: modified-source compatibility
  files referenced by Dockerfile's `doctrenderer` stage. These are **not**
  present under the same paths in stock EuroOffice v9.3.5;
- final linker flags including `--pre-js`, `-sEXPORTED_RUNTIME_METHODS=ccall,FS`,
  `-sEXPORTED_FUNCTIONS=_main1`, `-sALLOW_MEMORY_GROWTH`.

It **isn't safe** to copy the old ONLYOFFICE `/core` tree wholesale and call it
EuroOffice 9.3.5. This builder starts with authentic EuroOffice 9.3.5 and ports
only the modifications made between stock ONLYOFFICE 9.3.0 and CryptPad's tree.
For each changed file, it chooses a copy if the base is unchanged, otherwise
attempts a three-way text merge. Mismatched binary files, ambiguous dual
additions and text conflicts are **fatal**. It logs missing/deleted files but
never silently deletes newer EuroOffice source.

`source-merge.json` lists **every modified or added source pathname** and
records whether it was merged/copied/left alone/conflicted. That list is your
starting point for creating a curated version-specific patch once preflight
is stable. `cryptpad-source-changes.diff` contains the actual modified text
for code review (it is informational, not intended to apply directly). A three-way text merge does **not** prove binary compatibility.

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
code 1). This builder brings CryptPad-added files into the EuroOffice source
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
