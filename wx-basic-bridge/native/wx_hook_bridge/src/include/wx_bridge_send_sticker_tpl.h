#ifndef WX_BRIDGE_SEND_STICKER_TPL_H
#define WX_BRIDGE_SEND_STICKER_TPL_H

/* 用预采集的模板发送收藏表情。
 *   tpl_index : 模板序号（0 .. WXB_STK_TPL_COUNT-1），见 wx_sticker_templates.h
 *   to_wxid   : 接收者 wxid（UTF-8）
 * 返回：4 = 已提交发送；1..3 = 卡在该阶段；负数 = 该阶段失败。
 *       -1 参数非法，-2 内容对象构造失败，-3 信封构造失败，-4 填字段失败。
 */
int wxb_send_sticker_tpl(int tpl_index, const char *to_wxid);

/* pack 路线（frida 实证）：内容对象 → 信封 → 放进 pack 的 vector → 0x160EBE0。
 * 与文本发送同构，绕开 0x16A60D0 / TaskContext。返回 1 = 已提交 pack。 */
int wxb_send_sticker_pack(int tpl_index, const char *to_wxid);

/* 表情包（表情商店添加）表情：与收藏表情共用发送链路，仅内容对象布局不同 */
int wxb_send_sticker_pack_ex(int tpl_index, const char *to_wxid, int is_pack);
int wxb_send_pack_sticker(int tpl_index, const char *to_wxid);
int wxb_pack_tpl_count(void);

/* pack 入口常驻 hook：自动捕获任务上下文（TASK_LOG §31）。
 * 安装失败不影响其它功能，只是退化为「需要人工触发一次上下文」。 */
int wxb_install_pack_hook(void);
void wxb_uninstall_pack_hook(void);
int wxb_pack_hook_installed(void);

/* 只构造内容对象并 dump 为十六进制（control\content_built.hex），不做任何发送。
 * 用于离线核验手工构造结果与原生样本的逐字段差异。返回 1 成功，负数失败。 */
int wxb_dump_content_tpl(int tpl_index);

/* 构造「内容对象 → 信封 → TaskContext」全链并 dump（control\task_built.hex），
 * 不发送。用于在调用真入口前零风险验证 TaskContext 构造。返回 1 成功，负数失败。 */
int wxb_dump_task_tpl(int tpl_index);

#endif /* WX_BRIDGE_SEND_STICKER_TPL_H */
