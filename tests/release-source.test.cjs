const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {execFileSync}=require('node:child_process');
const {exportSource,verifySource,scanText,releaseAmbience}=require('../scripts/release-source.cjs');
const root=path.resolve(__dirname,'..');
const temporary=()=>fs.mkdtempSync(path.join(os.tmpdir(),'ambient-release-'));

test('public export excludes unreviewed files and private arrays, and reproduces its manifest',()=>{
 const base=temporary(),a=path.join(base,'first'),b=path.join(base,'second');
 exportSource(root,a);exportSource(root,b);
 const first=verifySource(a),second=verifySource(b);
 assert.deepEqual(first,second);
 assert.equal(fs.existsSync(path.join(a,'builtin-ambience/thunder.opus')),true);
 assert.equal(fs.existsSync(path.join(a,'docs/environment.json')),false);
 assert.equal(fs.existsSync(path.join(a,'docs/reference-audit.json')),false);
 assert.equal(fs.existsSync(path.join(a,'.pytest_cache')),false);
 assert.equal(fs.existsSync(path.join(a,'builtin-ambience/train.opus')),true);
 execFileSync(process.env.AMBIENT_BUILD_PYTHON||'python',['-c',
  "import zipfile,sys; z=zipfile.ZipFile(sys.argv[1]); assert set(z.namelist())=={'text_labels.npy','text_vectors.npy'}",
  path.join(a,'server/style_reference_v5.npz')]);
 fs.writeFileSync(path.join(a,'ui/unreviewed-private-note.txt'),'private');
 assert.throws(()=>verifySource(a),/Unexpected/);
 const third=path.join(base,'third');exportSource(a,third);
 assert.equal(fs.existsSync(path.join(third,'ui/unreviewed-private-note.txt')),false);
 assert.deepEqual(first,verifySource(third));
});

test('content audit detects modified source and personal paths or credentials',()=>{
 const out=path.join(temporary(),'source');exportSource(root,out);
 fs.appendFileSync(path.join(out,'README.md'),'\nchanged');
 assert.throws(()=>verifySource(out),/hash|size/i);
 assert.throws(()=>scanText('sample.txt','C:'+'/Users/'+'someone/private.wav'),/personal-path/);
 assert.throws(()=>scanText('sample.txt','hf_'+'A'.repeat(34)),/credential/);
});

test('ambience redistribution fails closed on missing or conflicting provenance',()=>{
 const manifest=JSON.parse(fs.readFileSync(path.join(root,'builtin-ambience/manifest.json')));
 const catalog=JSON.parse(fs.readFileSync(path.join(root,'builtin-ambience/provenance.json')));
 const selected=releaseAmbience(manifest,catalog);
 assert.equal(selected.length,13);
 const thunder=manifest.find(x=>x.id==='thunder');
 assert.equal(thunder.sources[0].license,'CC-BY-4.0');
 assert.equal(thunder.sha256,catalog.sources[thunder.sources[0].source_id].acquisition.output_sha256);
 const pending=structuredClone(catalog);pending.sources[thunder.sources[0].source_id].status='MANUAL LEGAL/PROVENANCE VERIFICATION REQUIRED';
 assert(!releaseAmbience(manifest,pending).some(x=>x.id==='thunder'));
 const train=manifest.find(x=>x.id==='train');
 const bad=structuredClone(catalog);bad.sources[train.sources[0].source_id].license_url='';
 assert.throws(()=>releaseAmbience(manifest,bad),/license_url/);
 const missing=structuredClone(manifest);missing.find(x=>x.id==='train').sources[0].source_id='unreviewed';
 assert.throws(()=>releaseAmbience(missing,catalog),/provenance/);
});
