# EuroOffice 9.3.5 x2t WebAssembly builder — v3 (source-preparation correction)

**Status: experimental. This repository has NOT yet independently compiled or validated an EuroOffice 9.3.5 converter.** It is a deliberately separate GitHub Actions builder; it does not modify Nurse Memo and never downloads the third-party prebuilt x2t package. The workflow's preflight is useful, but passing preflight alone is *not* evidence that `x2t.js` or `x2t.wasm` can be generated.

## Why v2 failed: analysis of the actual diagnostic ZIP

The user's `eurooffice-9.3.5-x2t-build-diagnostics.zip` contains `source-merge.json`: **8,079 modified and 69 newly added files in the broad scoped comparison, 8,071 already identical to the EuroOffice tree, 39 auto-merged, 16 copied and 22 unresolved conflicts**. This was not a normal 22-file branch merge: the comparison used an older ONLYOFFICE baseline, so it treated ordinary historical source changes, translation changes and even removed copyright notice lines as CryptPad-specific WASM changes.

The 22 failing files have explicit v3 decisions:

| Conflict class | Paths | Decision |
| --- | ---: | --- |
| qmake/Emscripten include adjustments | 5 | Apply an exact reviewed include replacement in the EuroOffice source, leaving all other content unchanged. |
| EuroOffice CMake and unrelated web JS | 13 | Retain EuroOffice 9.3.5. The pinned CryptPad Docker recipe uses qmake, not these CMake definitions. |
| EuroOffice TLS verification | 1 | Keep EuroOffice's `CURLOPT_SSL_VERIFYPEER=1` and `CURLOPT_SSL_VERIFYHOST=2` logic; never restore CryptPad's older TLS bypass. |
| EuroOffice `BinaryReader` implementation | 2 | Keep EuroOffice's consistent constructor/destructor. |
| EuroOffice PDF SHA/OpenSSL handling | 1 | Keep EuroOffice's `openssl/sha.h` integration instead of inlining older OpenSSL C sources. |

Additional reviewed non-conflicting porting edits: one renderer include-path correction and two Emscripten process-limit guards in `X2tConverter/src/main.cpp`. The project also edits one x2t qmake dependency declaration to link the libraries in the selected Docker recipe, and adds `libFb2File.a` to that recipe rather than adopting CryptPad's silently disabled FB2 conversion functions.

All 22 previous conflicts are covered by an explicit allowlist entry. Unlike v2, there is **no three-way merge** and no source-wide copying. Most EuroOffice C++ files remain byte-for-byte identical to the pinned release. Changes are recorded in `artifacts/provenance/eurooffice-diff.patch` for human review.

## GitHub website installation (no command line needed)

**For an existing v2 builder repository:** unzip `EuroOffice_WASM_Builder_9.3.5_v3_UPDATE_ONLY.zip`; upload its files to the corresponding paths using GitHub's Add file > Upload files interface. Preserve the `.github/workflows/` folder. Commit the update. The following obsolete v2 files should be deleted through GitHub's website: `config/port-scope.json`, `scripts/port_wasm_changes.py`, and `tests/test_port_wasm_changes.py`. They are not referenced by the v3 workflow if left on disk, but removal keeps the repository clean.

**For a new repository:** upload the contents of the `FULL` ZIP (not the containing folder).

1. Go to **Actions > Build EuroOffice 9.3.5 x2t WASM (allowlisted v3)**.
2. Select **Run workflow**, choose `preflight`, and run it.
3. The preflight produces `artifacts/provenance/source-preparation.json`, `eurooffice-diff.patch`, `docker-diff.patch`, exact source commit IDs and `docker-recipe-audit.json`.
4. Review the `source-preparation.json` file: it must have no errors, and should show copied qmake/build files plus exactly reviewed code edits.
5. **Before running `build`, inspect the recipe audit and the unresolved build-recipe caveat below.** The actual C++ compilation remains unverified.

## Known upstream Docker recipe problem — NOT resolved by the 22-file port

The pinned CryptPad Dockerfile's `COPY --from=gumbo` and `COPY --from=katana` statements refer to stage names not defined by a `FROM ... AS gumbo` or `FROM ... AS katana` in that same Dockerfile. In ordinary Docker syntax, the builder may try to resolve these as external images instead. This is a separate, likely **build-stage blocker**, unrelated to EuroOffice merge conflicts.

The v3 workflow explicitly audits and reports such undefined names. It does not fabricate unverified Gumbo/Katana build recipes or silently pull images. To finish the independent build, these third-party parser libraries must be compiled for the same Emscripten target and supplied to the stages that expect `/usr/local/lib/libgumbo.a`, `/usr/local/lib/libkatana.a` and source directories. The pinned `html` stage fetches parser source, but does not visibly compile these two static libraries. Even if preflight is successful, **a full build may still fail at this stage**. Additional compiler or ABI incompatibilities may appear afterward.

The CryptPad Dockerfile also builds OpenSSL `OpenSSL_1_1_1f`, while EuroOffice's newer PDF source was updated for a different OpenSSL linkage strategy. This is an additional possible compatibility concern to review at link time; do not downgrade EuroOffice's security patches to force compilation.

## Dependencies and reproducibility

- EuroOffice/core `v9.3.5` (checked tag hash prefix `5a33ce6`).
- CryptPad/onlyoffice-x2t-wasm commit `95f775fd3c42fae9e9af66ca072d3da3763e6c76`.
- CryptPad's recipe pins Emscripten `4.0.11`, Ubuntu `22.04`, and builds multiple dependent native libraries as WASM-compatible `.a` archives.
- Source archive plus patches and SHA hashes are recorded in the CI artifacts; no built converter is considered verified unless the WASM validation and actual DOCX smoke test pass.
- Several transitive packages/apt dependencies are not locked by immutable digest. The build is **source-pinned but not bit-for-bit reproducible/hermetic**.

The third-party EuroOffice RC converter used a different compiler toolchain; equality with its `x2t.js`/`x2t.wasm` hashes is neither assumed nor required.

## What the repo does and does not guarantee

| Check | v3 status |
| --- | --- |
| All 22 reported conflicts have an explicit reviewed policy | Implemented / unit-tested |
| No broad two-fork source merge | Implemented / unit-tested |
| Previous TLS and PDF security changes preserved | Guarded by assertions |
| Previously removed license-header text not copied wholesale | Implemented |
| CryptPad qmake support and three renderer stubs available | Included when absent, guarded |
| Real C++ compile with EuroOffice 9.3.5 | **Not executed** |
| Gumbo/Katana static parser libraries defined in recipe | **Outstanding** |
| `x2t.js` and `x2t.wasm` generated | **Not demonstrated** |
| DOCX conversion fidelity and hospital security | **Not established** |

## Source-preparation tests

The repository includes 13 automated Python unit tests for allowlist behavior, preservation of EuroOffice files, rejected unexpected changes, renderer-stub conflicts, idempotence, dangerous path rejection, all 22 prior conflict decisions, and Docker link/audit utilities. CI runs those and Python, bash, and JavaScript syntax checks before retrieving upstream source.

## Technical references

- CryptPad pinned Docker build recipe: https://raw.githubusercontent.com/cryptpad/onlyoffice-x2t-wasm/95f775fd3c42fae9e9af66ca072d3da3763e6c76/Dockerfile
- CryptPad qmake/Emscripten wrapper: https://raw.githubusercontent.com/cryptpad/onlyoffice-x2t-wasm/95f775fd3c42fae9e9af66ca072d3da3763e6c76/embuild.sh
- EuroOffice core: https://github.com/Euro-Office/core/releases/tag/v9.3.5
- Existing license records: `LICENSES/euro-office-LICENSE.txt` and upstream license files must be preserved and reviewed before redistribution.
