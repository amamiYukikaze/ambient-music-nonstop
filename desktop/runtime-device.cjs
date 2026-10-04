exports.deviceSupport=({platform,arch,ram,vram})=>{
 const allowed=platform==='win32'&&arch==='x64'&&Number.isFinite(ram)&&Number.isFinite(vram)&&ram>=15.5&&vram>=3.8;
 return {allowed,sa3:allowed&&ram>=23.5&&vram>=5.8,ram,vram};
};
