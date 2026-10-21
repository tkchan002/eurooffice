'use strict';
// Adapted from CryptPad's public test.js. Runs an actual DOCX -> .bin -> DOCX
// conversion. Only called after successful binary compilation.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(process.argv[2] || 'artifacts/converter');
const sample = path.resolve('tests/fixtures/blank.docx');
const current = process.cwd();
const x2t = require(path.join(root,'x2t.js'));

function makeDir(p) { try { x2t.FS.mkdir(p); } catch(e) { if (!x2t.FS.analyzePath(p).exists) throw e; } }
function convert(src,dst) {
  const s='/working/'+path.basename(src), d='/working/'+path.basename(dst);
  x2t.FS.writeFile(s,fs.readFileSync(src));
  const xml='<?xml version="1.0" encoding="utf-8"?>' +
    '<TaskQueueDataConvert xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">' +
    '<m_sFontDir>/working/fonts/</m_sFontDir>' +
    '<m_sThemeDir>/working/themes/</m_sThemeDir>' +
    '<m_sFileFrom>'+s+'</m_sFileFrom><m_sFileTo>'+d+'</m_sFileTo>' +
    '<m_bIsNoBase64>false</m_bIsNoBase64><m_nCsvTxtEncoding>46</m_nCsvTxtEncoding><m_nCsvDelimiter>4</m_nCsvDelimiter>' +
    '</TaskQueueDataConvert>';
  x2t.FS.writeFile('/working/params.xml',xml);
  const code=x2t.ccall('main1','number',['string'],['/working/params.xml']);
  assert.equal(code,0,`${src} -> ${dst}: converter exit code ${code}`);
  fs.writeFileSync(dst,x2t.FS.readFile(d));
}

x2t.onRuntimeInitialized=()=>{
  try {
    makeDir('/working'); makeDir('/working/media'); makeDir('/working/fonts'); makeDir('/working/themes');
    const intermediate=path.join(root,'blank.bin');
    const result=path.join(root,'blank-roundtrip.docx');
    convert(sample,intermediate);
    convert(intermediate,result);
    assert.equal(fs.readFileSync(result).subarray(0,2).toString('ascii'),'PK','DOCX output not a ZIP');
    const bytes=fs.statSync(result).size;
    assert(bytes > 500,'Round-trip DOCX suspiciously short');
    fs.writeFileSync(path.join(root,'smoke-result.json'),JSON.stringify({status:'PASS',test:'blank DOCX -> .bin -> DOCX',bytes},null,2));
    console.log('PASS: functional DOCX conversion', bytes);
  } catch (error) { console.error('FAIL: functional conversion',error); process.exitCode=1; }
};
