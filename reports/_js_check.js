
const base = Process.getModuleByName("Weixin.dll").base;
const OUT = "<PROJECT_ROOT>\\reports\\_js_check.txt";
const TEMPLATES = [{"lib_md5": "0fbdd73cc59f210845f4d2457b0167b8", "spec_md5": "9558c0a6b75d4821b7b68c2eecb19eac", "aux_md5": "8cbd585dba8bb6cc4d5c0a7ccfead51d", "url_20401": "http://vweixinf.tc.qq.com/110/20401/stodownload?m=0fbdd73cc59f210845f4d2457b0167b8&filekey=30440201010430302e02016e0402534804203066626464373363633539663231303834356634643234353762303136376238020301be53040d00000004627466730000000132&hy=SH&storeid=26a5d7bc3000c1301e36a4af20000006e01004fb15348025e866150411ac27&ef=1&bizid=1022", "url_20403": "http://vweixinf.tc.qq.com/110/20403/stodownload?m=3e5a0552c232deabe5a0d4e8a6aa0422&filekey=3043020101042f302d02016e0402534804203365356130353532633233326465616265356130643465386136616130343232020226a0040d00000004627466730000000132&hy=SH&storeid=26a5d7bc3000e423ee36a4af20000006e03004fb35348025e866150411ac48&ef=3&bizid=1022", "url_20402": "http://vweixinf.tc.qq.com/110/20402/stodownload?m=1e0ce94dc8da48370f4614709973271c&filekey=30440201010430302e02016e0402534804203165306365393464633864613438333730663436313437303939373332373163020301be60040d00000004627466730000000132&hy=SH&storeid=26a5d7bc3000d205ae36a4af20000006e02004fb25348025e866150411ac37&ef=2&bizid=1022"}, {"lib_md5": "53dcede756bc62e5e7cfb3eca4c3b5c5", "spec_md5": "47a7ee64be7f48bea221fff11c1afcef", "aux_md5": "d85a76430c0abecd1715fc0b723b0e20", "url_20401": "http://vweixinf.tc.qq.com/110/20401/stodownload?m=53dcede756bc62e5e7cfb3eca4c3b5c5&filekey=30440201010430302e02016e0402534804203533646365646537353662633632653565376366623365636134633362356335020302209b040d00000004627466730000000132&hy=SH&storeid=26a5d7a9f000e4eb7e36a4af20000006e01004fb153480fd3b03157b5d6feb&ef=1&bizid=1022", "url_20403": "http://vweixinf.tc.qq.com/110/20403/stodownload?m=f0b6c132c1bf914a6b3988e987f975b2&filekey=3043020101042f302d02016e040253480420663062366331333263316266393134613662333938386539383766393735623202023250040d00000004627466730000000132&hy=SH&storeid=26a5d7aa00000d4a5e36a4af20000006e03004fb353480fd3b03157b5d700a&ef=3&bizid=1022", "url_20402": "http://vweixinf.tc.qq.com/110/20402/stodownload?m=7430d39e838150c21e91969c2b1e0cc7&filekey=30440201010430302e02016e040253480420373433306433396538333831353063323165393139363963326231653063633702030220a0040d00000004627466730000000132&hy=SH&storeid=26a5d7aa000000412e36a4af20000006e02004fb253480fd3b03157b5d6ff8&ef=2&bizid=1022"}, {"lib_md5": "7ed206382321db118c4951f1e448166a", "spec_md5": "49cd60dd1f354795b1334bf655a189a5", "aux_md5": "96d1ce52eeffc92219b7524763fbf5d5", "url_20401": "http://vweixinf.tc.qq.com/110/20401/stodownload?m=7ed206382321db118c4951f1e448166a&filekey=30440201010430302e02016e04025348042037656432303633383233323164623131386334393531663165343438313636610203021390040d00000004627466730000000132&hy=SH&storeid=26a5d7ba3000639e9e36a4af20000006e01004fb1534807e3c03157101db45&ef=1&bizid=1022", "url_20403": "http://vweixinf.tc.qq.com/110/20403/stodownload?m=5f3c31ac7ae8771f51519ce40409ed7a&filekey=3043020101042f302d02016e0402534804203566336333316163376165383737316635313531396365343034303965643761020230d0040d00000004627466730000000132&hy=SH&storeid=26a5d7ba30007b824e36a4af20000006e03004fb3534807e3c03157101db5d&ef=3&bizid=1022", "url_20402": "http://vweixinf.tc.qq.com/110/20402/stodownload?m=455d847059730c65bff4e247110bfd03&filekey=30440201010430302e02016e040253480420343535643834373035393733306336356266663465323437313130626664303302030213a0040d00000004627466730000000132&hy=SH&storeid=26a5d7ba300070b2ce36a4af2000006e02004fb2534807e3c03157101db4e&ef=2&bizid=1022"}, {"lib_md5": "b90ff3bbdb9eb50b8324bb7d6631a3ef", "spec_md5": "957d07571c034bba8d2ecfec7266f181", "aux_md5": "245b5f04c2d19a6ea5cc7a63bb978aae", "url_20401": "http://vweixinf.tc.qq.com/110/20401/stodownload?m=b90ff3bbdb9eb50b8324bb7d6631a3ef&filekey=30440201010430302e02016e0402534804206239306666336262646239656235306238333234626237643636333161336566020301eb95040d00000004627466730000000132&hy=SH&storeid=26a5d7be5000da3bbe36a4af20000006e01004fb1534819ec117156cb3474c&ef=1&bizid=1022", "url_20403": "http://vweixinf.tc.qq.com/110/20403/stodownload?m=8dbf645611ebb473c7c56f417e421d49&filekey=3043020101042f302d02016e040253480420386462663634353631316562623437336337633536663431376534323164343902022600040d00000004627466730000000132&hy=SH&storeid=26a5d7be6000033a6e36a4af20000006e03004fb3534819ec117156cb34781&ef=3&bizid=1022", "url_20402": "http://vweixinf.tc.qq.com/110/20402/stodownload?m=e61d9ddc83e7d47b2fc51014dc9f1475&filekey=30440201010430302e02016e0402534804206536316439646463383365376434376232666335313031346463396631343735020301eba0040d00000004627466730000000132&hy=SH&storeid=26a5d7be5000eb0d2e36a4af20000006e02004fb2534819ec117156cb3476a&ef=2&bizid=1022"}, {"lib_md5": "cbab1418a65ab56a82b228ea2a27c621", "spec_md5": "7901cc692c1442f49374e9f9722e44d8", "aux_md5": "c69a8064b008420fdc9cfbaca518df7a", "url_20401": "http://vweixinf.tc.qq.com/110/20401/stodownload?m=cbab1418a65ab56a82b228ea2a27c621&filekey=30440201010430302e02016e0402534804206362616231343138613635616235366138326232323865613261323763363231020301bd8f040d00000004627466730000000132&hy=SH&storeid=26a5d7bd4000eef3fe36a4af20000006e01004fb153481c6e9661502d4eb91&ef=1&bizid=1022", "url_20403": "http://vweixinf.tc.qq.com/110/20403/stodownload?m=1d6df9a373105c40206f31512982f91c&filekey=3043020101042f302d02016e040253480420316436646639613337333130356334303230366633313531323938326639316302022320040d00000004627466730000000132&hy=SH&storeid=26a5d7bd50001aa6ee36a4af20000006e03004fb353481c6e9661502d4ebb3&ef=3&bizid=1022", "url_20402": "http://vweixinf.tc.qq.com/110/20402/stodownload?m=b4ede003a7df784d24142eb451ef2f66&filekey=30440201010430302e02016e0402534804206234656465303033613764663738346432343134326562343531656632663636020301bd90040d00000004627466730000000132&hy=SH&storeid=26a5d7bd50000bc9ce36a4af2000006e02004fb253481c6e9661502d4eba2&ef=2&bizid=1022"}, {"lib_md5": "ccfabb49a1904b17159ba9f6bb9b3782", "spec_md5": "1402a1e027bd42e885ecc990381318e0", "aux_md5": "203cb0736f7a726941e01062a3d38431", "url_20401": "http://vweixinf.tc.qq.com/110/20401/stodownload?m=ccfabb49a1904b17159ba9f6bb9b3782&filekey=30440201010430302e02016e04025348042063636661626234396131393034623137313539626139663662623962333738320203022bad040d00000004627466730000000132&hy=SH&storeid=26a5d7b92000bd4b5e36a4af20000006e01004fb153482cf3c1f1502cab27d&ef=1&bizid=1022", "url_20403": "http://vweixinf.tc.qq.com/110/20403/stodownload?m=3f2307c65a07d7373125a2c7a56b2a01&filekey=3043020101042f302d02016e040253480420336632333037633635613037643733373331323561326337613536623261303102023260040d00000004627466730000000132&hy=SH&storeid=26a5d7b92000d9589e36a4af20000006e03004fb353482cf3c1f1502cab293&ef=3&bizid=1022", "url_20402": "http://vweixinf.tc.qq.com/110/20402/stodownload?m=d1cc6393f7fb0693c317b7624021e58f&filekey=30440201010430302e02016e04025348042064316363363339336637666230363933633331376237363234303231653538660203022bb0040d00000004627466730000000132&hy=SH&storeid=26a5d7b92000cbdd9e36a4af20000006e02004fb253482cf3c1f1502cab28a&ef=2&bizid=1022"}, {"lib_md5": "d727ccdf2475c436206cbc8ec3fa30b9", "spec_md5": "cd784b225d1948b986dca2d013196923", "aux_md5": "63d09b6fac72997727e5430db24f8f92", "url_20401": "http://vweixinf.tc.qq.com/110/20401/stodownload?m=d727ccdf2475c436206cbc8ec3fa30b9&filekey=30440201010430302e02016e04025348042064373237636364663234373563343336323036636263386563336661333062390203020db6040d00000004627466730000000132&hy=SH&storeid=26a5d7bb2000aa62fe36a4af20000006e01004fb153482ab3f031502cd1c51&ef=1&bizid=1022", "url_20403": "http://vweixinf.tc.qq.com/110/20403/stodownload?m=0fb3fed79b06e10dfcb1cd95355fafcb&filekey=3043020101042f302d02016e040253480420306662336665643739623036653130646663623163643935333535666166636202022fc0040d00000004627466730000000132&hy=SH&storeid=26a5d7bb2000c9d47e36a4af20000006e03004fb353482ab3f031502cd1c70&ef=3&bizid=1022", "url_20402": "http://vweixinf.tc.qq.com/110/20402/stodownload?m=8724a7bc86b8cb42b08834f4168c3399&filekey=30440201010430302e02016e04025348042038373234613762633836623863623432623038383334663431363863333339390203020dc0040d00000004627466730000000132&hy=SH&storeid=26a5d7bb2000b9113e36a4af20000006e02004fb253482ab3f031502cd1c60&ef=2&bizid=1022"}];
const TARGET_IDX = 0;
const LIVE = false;
const MAX_SWAPS = 1;

const VT_ENV = "0x82cb8d8";
const VT_BODY = "0x8755528";

// 槽位 -> 模板字段
const SLOT_MAP = {
    0: "lib_md5",
    2: "spec_md5",
    6: "url_20401",
    7: "url_20403",
    8: "aux_md5",
    9: "url_20402"
};

function w(line) {
    try {
        const f = new File(OUT, "a");
        f.write(line + "\n");
        f.flush();
        f.close();
    } catch (e) {}
}

function rva(p) {
    try { return "0x" + p.sub(base).toString(16); } catch (e) { return "?"; }
}

function slotOff(slot) {
    // 内容对象对象体的第 slot 个字符串：buf @ +0x10+slot*0x20
    return 0x10 + slot * 0x20;
}

function readSlot(obj, slot) {
    const off = slotOff(slot);
    let len = 0, cap = 0, txt = "";
    try {
        len = obj.add(off + 0x10).readInt();
        cap = obj.add(off + 0x18).readInt();
        if (len > 0 && len < 8192) {
            let buf = (cap <= 0xf) ? obj.add(off) : obj.add(off).readPointer();
            if (!buf.isNull()) txt = buf.readUtf8String(len);
        }
    } catch (e) {
        txt = "<ERR " + e + ">";
    }
    return { len: len, cap: cap, txt: txt };
}

function writeSlot(obj, slot, text) {
    const off = slotOff(slot);
    let cap = 0;
    try { cap = obj.add(off + 0x18).readInt(); } catch (e) { return "CAP_ERR"; }
    // 硬安全阀：只在原容量内就地覆写，绝不重新分配
    if (text.length > cap) return "NO_ROOM(len=" + text.length + " cap=" + cap + ")";
    let buf = null;
    try {
        buf = (cap <= 0xf) ? obj.add(off) : obj.add(off).readPointer();
    } catch (e) { return "BUF_ERR"; }
    if (buf === null || buf.isNull()) return "NULL_BUF";
    try {
        buf.writeUtf8String(text);
        buf.add(text.length).writeU8(0);          // std::string 要求 buf[len] = 0
        obj.add(off + 0x10).writeInt(text.length);
    } catch (e) { return "WRITE_ERR " + e; }
    return "OK";
}

w("== sticker swap loaded base=" + base.toString() + " live=" + LIVE +
  " target=" + TARGET_IDX + " ==");

let swaps = 0;

Interceptor.attach(base.add(0x160EBE0), {
    onEnter(args) {
        const tid = Process.getCurrentThreadId();
        try {
            const b = args[0].add(8).readPointer();
            const e = args[0].add(0x10).readPointer();
            const n = e.sub(b).toInt32() / 16;
            if (n <= 0 || n > 32) return;              // 不是我们关心的提交
            let s = "PACK tid=" + tid + " models=" + n + "\n";
            for (let i = 0; i < Math.min(n, 4); i++) {
                let m = null, vt = "?";
                try {
                    m = b.add(i * 16).readPointer();
                    vt = rva(m.readPointer());
                } catch (e1) { s += "  model" + i + " read ERR\n"; continue; }
                s += "  model" + i + " vt=" + vt + "\n";
                if (vt !== VT_ENV) continue;           // 只处理收藏表情信封

                let cb = null, cvt = "?";
                try {
                    cb = m.add(0x660).readPointer();
                    if (cb.isNull()) { s += "    +0x660 NULL\n"; continue; }
                    cvt = rva(cb.readPointer());
                } catch (e2) { s += "    content read ERR\n"; continue; }
                s += "    content=" + cb + " vt=" + cvt + "\n";
                if (cvt !== VT_BODY) continue;         // 布局不符则不碰

                const before = {};
                Object.keys(SLOT_MAP).forEach(function (k) {
                    before[k] = readSlot(cb, parseInt(k, 10));
                    s += "      before slot" + k + " " + SLOT_MAP[k] +
                         " len=" + before[k].len + " cap=" + before[k].cap +
                         " : " + before[k].txt + "\n";
                });

                // 载体 == 目标时自动换一个，保证一次点击就能看出差异
                let ti = TARGET_IDX;
                if (ti < 0 || ti >= TEMPLATES.length) ti = 0;
                if (before[0].txt === TEMPLATES[ti].lib_md5) {
                    ti = (ti + 1) % TEMPLATES.length;
                }
                s += "      carrier=" + before[0].txt +
                     "  ->  target[" + ti + "]=" + TEMPLATES[ti].lib_md5 + "\n";

                if (!LIVE) {
                    s += "      DRY-RUN：只观察，未写入\n";
                    w(s);
                    continue;
                }
                if (swaps >= MAX_SWAPS) {
                    s += "      已达写入上限 " + MAX_SWAPS + "，跳过\n";
                    w(s);
                    continue;
                }

                let allOk = true;
                Object.keys(SLOT_MAP).forEach(function (k) {
                    const r = writeSlot(cb, parseInt(k, 10), TEMPLATES[ti][SLOT_MAP[k]]);
                    s += "      write slot" + k + " " + SLOT_MAP[k] + " -> " + r + "\n";
                    if (r !== "OK") allOk = false;
                });
                Object.keys(SLOT_MAP).forEach(function (k) {
                    const a = readSlot(cb, parseInt(k, 10));
                    s += "      after  slot" + k + " len=" + a.len + " : " +
                         a.txt.substring(0, 72) +
                         (a.txt.length > 72 ? "…" : "") + "\n";
                });
                if (allOk) { swaps++; s += "      SWAP#" + swaps + " 完成\n"; }
                w(s);
            }
            if (n > 0 && s.indexOf("model0 vt=" + VT_ENV) < 0) w(s);
        } catch (err) {
            w("PACK ERR " + err);
        }
    }
});

w("attached pack 0x160EBE0");
