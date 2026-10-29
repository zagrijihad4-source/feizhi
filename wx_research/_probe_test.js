var weixin = Process.findModuleByName('Weixin.dll');
console.log('Weixin.dll base = ' + (weixin ? weixin.base : 'NOT FOUND') + ' size=' + (weixin ? weixin.size : 0));
['mmcronet.dll','XNet.dll','ilink2.dll'].forEach(function(m){
  var mod = Process.findModuleByName(m);
  console.log('  ' + m + ' : ' + (mod ? mod.base : 'not loaded'));
});
// ???????
var pats = ['cdnthumburl','cdnbigimgurl','aeskey','filekey'];
pats.forEach(function(pat){
  try {
    var hex = pat.split('').map(function(c){return c.charCodeAt(0).toString(16).padStart(2,'0');}).join(' ');
    var found = Memory.scanSync(weixin.base, Math.min(weixin.size, 0x0C000000), hex);
    console.log('  ? "' + pat + '" ?? ' + found.length + ' ?' + (found.length ? ('  ??: ' + found[0].address) : ''));
  } catch(e) { console.log('  ? "' + pat + '" ????: ' + e); }
});
