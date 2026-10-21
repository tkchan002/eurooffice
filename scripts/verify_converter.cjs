'use strict';
// Validate binary and JS, without claiming functional round-trip compatibility.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const crypto = require('node:crypto');
const path = require('node:path');
const root = process.argv[2] || 'artifacts/converter';
const records = [];
for (const name of ['x2t.js', 'x2t.wasm']) {
  const file = path.join(root, name);
  const data = fs.readFileSync(file);
  assert(data.length > 4096, `${name} appears too small`);
  records.push({name, sizeBytes: data.byteLength, sha256: crypto.createHash('sha256').update(data).digest('hex')});
}
const wasm = fs.readFileSync(path.join(root, 'x2t.wasm'));
assert.equal(wasm.subarray(0,4).toString('hex'), '0061736d', 'Not a WASM module');
const wasmModule = new WebAssembly.Module(wasm);
const wasmExports = WebAssembly.Module.exports(wasmModule).map(x => x.name);
const imports = WebAssembly.Module.imports(wasmModule).map(x => ({module:x.module,name:x.name,kind:x.kind}));
assert(wasmExports.includes('main1') || wasmExports.includes('_main1'), 'Missing callable main1 export');
const js = fs.readFileSync(path.join(root, 'x2t.js'),'utf8');
assert(/(?:Module|module|wasmBinaryFile|wasm)/.test(js), 'Unexpected Emscripten JS loader');
const output = {status:'STRUCTURALLY_VALID', records, exports:wasmExports.filter(x=>/main|memory|stack/.test(x)).slice(0,40), imports:imports.slice(0,40)};
fs.writeFileSync(path.join(root,'validation.json'),JSON.stringify(output,null,2)+'\n');
fs.writeFileSync(path.join(root,'SHA256SUMS'), records.map(x=>`${x.sha256}  ${x.name}`).join('\n')+'\n');
console.log(JSON.stringify(output,null,2));
