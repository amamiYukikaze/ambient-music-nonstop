const path=require('node:path');
const {exportSource}=require('./release-source.cjs');
const root=path.resolve(__dirname,'..');
const option=process.argv[2];
if(option&&option!=='--out')throw Error('Usage: node scripts/export-github.cjs [--out dist/folder]');
const out=path.resolve(root,process.argv[3]||'dist/github-source-'+require('../package.json').version);
const relative=path.relative(path.join(root,'dist'),out);
if(!relative||relative.startsWith('..')||path.isAbsolute(relative))throw Error('Export must be a new folder inside dist');
console.log(exportSource(root,out));
