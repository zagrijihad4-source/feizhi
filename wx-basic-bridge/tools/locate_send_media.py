"""用于定位微信「发送图片 / 发送自定义表情」内部函数的 Frida 探针。

背景：
  - 当前 hook 桥只支持 type=1 文本（outbox.c 里写死 only type 1 supported）
  - 微信 4.1.9.23 符号被剥离干净，字符串里搜不到 sendImagesMsg / SendCustomEmotion
    （那些是第三方框架自定义的 HTTP 路由名，不是微信内部符号）
  - 微信本地表情是加密文件（Persist\<md5>，统一魔数 D0 B1 68 C5），不能直接塞 jpg
  => 只能走微信内部的「发图片 / 发自定义表情」函数，需要动态定位

思路：
  1. 挂上微信进程，对若干通用 API 做轻量埋点（文件读取、消息投递）
  2. 在微信界面上手工发一次表情/图片（仅这一次，用于产生调用；属调试采样，
     不是产品功能上的 UI 自动化）
  3. 脚本会打印命中时的调用栈，据此定位真正的发送函数
  4. 定位到之后，把偏移填进 wx_bridge_offsets.h，按 send_text.c 的模式写 send_emotion.c

用法：
  frida -p <Weixin主进程PID> -l locate_send_media.js
  # 然后在微信里手动发一个表情，观察输出
"""
import frida
import sys
import time

JS = r"""
'use strict';

function ts() { return new Date().toISOString().substr(11, 12); }
function log(s) { console.log('[' + ts() + '] ' + s); }

log('=== 媒体发送定位探针已挂载 ===');

// 1) 文件读取类：发图片/表情前必然会读本地文件
var fileApis = [
    ['kernel32.dll', 'CreateFileW'],
    ['kernel32.dll', 'ReadFile'],
];

fileApis.forEach(function (pair) {
    var mod = Process.findModuleByName(pair[0]);
    if (!mod) { log('模块不存在: ' + pair[0]); return; }
    var addr = mod.findExportByName(pair[1]);
    if (!addr) { log('导出不存在: ' + pair[1]); return; }
    try {
        Interceptor.attach(addr, {
            onEnter: function (args) {
                if (pair[1] === 'CreateFileW') {
                    var p = args[0].readUtf16String();
                    if (!p) return;
                    // 只看与表情/图片相关的路径
                    if (/emoticon|Emoticon|\.jpg|\.png|\.gif|\.webp|image|Image/i.test(p)) {
                        log('CreateFileW -> ' + p);
                        var bt = Thread.backtrace(this.context, Backtracer.ACCURATE)
                            .map(DebugSymbol.fromAddress).slice(0, 8);
                        bt.forEach(function (f) { log('    ' + f); });
                    }
                }
            }
        });
        log('已挂钩 ' + pair[0] + '!' + pair[1]);
    } catch (e) {
        log('挂钩失败 ' + pair[1] + ': ' + e);
    }
});

// 2) 网络层：发图片会走 CDN 上传（4.x 用 cronet / mmcronet）
['mmcronet.dll', 'XNet.dll', 'ilink2.dll'].forEach(function (m) {
    var mod = Process.findModuleByName(m);
    log('网络模块 ' + m + ' : ' + (mod ? mod.base : '未加载'));
});

// 3) 扫描 Weixin.dll 中可能的图片消息构造点
//    微信消息里图片走 XML，<img> 标签是可靠特征
var weixin = Process.findModuleByName('Weixin.dll');
if (weixin) {
    log('Weixin.dll base = ' + weixin.base);
    // 找 "<img" 字符串的引用，可能指向图片消息构造/解析
    var patterns = ['<img ', '<img>', 'cdnthumburl', 'cdnbigimgurl', 'aeskey', 'filekey'];
    patterns.forEach(function (pat) {
        var found = [];
        try {
            found = Memory.scanSync(weixin.base, Math.min(weixin.size, 0x0C000000),
                pat.split('').map(function (c) {
                    return c.charCodeAt(0).toString(16).padStart(2, '0');
                }).join(' '));
        } catch (e) { }
        if (found.length) {
            log('特征串 "' + pat + '" 命中 ' + found.length + ' 处，前 3 个：');
            found.slice(0, 3).forEach(function (f) { log('    ' + f.address); });
        }
    });
}

log('=== 现在请在微信里手工发一次表情或图片，观察上方输出 ===');
"""


def main():
    if len(sys.argv) > 1:
        pid = int(sys.argv[1])
    else:
        # 自动找加载了 Weixin.dll 的进程
        import subprocess
        ps = ("Get-Process Weixin -ErrorAction SilentlyContinue | "
              "Where-Object { $_.MainWindowHandle -ne 0 } | "
              "ForEach-Object { $_.Id }")
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                             capture_output=True, text=True, timeout=30).stdout.strip()
        if not out:
            print("未找到微信主进程，请手动传 PID")
            return 2
        pid = int(out.splitlines()[0].split()[-1])

    print(f"attach 到进程 {pid} ...")
    session = frida.attach(pid)
    script = session.create_script(JS)

    def on_message(message, data):
        if message.get("type") == "send":
            print(message["payload"])
        else:
            print("[err]", message)

    script.on("message", on_message)
    script.load()
    print("探针已运行。在微信里手工发一次表情/图片，然后回来看输出。Ctrl+C 结束。")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("结束")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
