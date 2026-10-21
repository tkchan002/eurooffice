# Historical build scripts (reference only)

These two files were copied verbatim from the user-supplied archive
`@kreijstal/eurooffice-sdkjs-common@9.3.5-rc.1.build.1`.
They are **not** run automatically by v9. `build-x2t-eurooffice.sh`
clones the live CryptPad repository; running it unchanged would violate
v9's CryptPad-disappearance goal. It requires an Arch-specific Emscripten
6.0.9-git environment that is not shipped here.

The uploaded package records these known converter checksums:

```
66c2fe0e6de280d81643ffc7ba31cd9a5205c004b72227c08e78a0821ba0e520  x2t.js
841ff9b648f0a03a6e610e6f1d0e822a526dd3142eb43a64101653963f4fc35e  x2t.wasm
```

The author's README states that the recipe uses CryptPad commit
`95f775fd3c42fae9e9af66ca072d3da3763e6c76` but the historical script
itself does not check that commit out. It also describes the source as
EuroOffice, though the script does not independently establish the provenance
of the CryptPad `core` tree. Treat the binary as a functional reference,
not independent proof of the corresponding C++ revision.
