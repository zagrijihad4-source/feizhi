#ifndef WX_BRIDGE_SEND_TEXT_H
#define WX_BRIDGE_SEND_TEXT_H

int wxb_send_text(const char *wxid, const char *content);

/* 同构变体：自定义消息类型码（1=文本，47=收藏表情）。
 * 走已验证可用的「消息模型 + 0xDB40 + pack」通道，用于试探以 XML 形式
 * 投递表情/其它结构化消息。 */
int wxb_send_model(const char *wxid, const char *content, int type_code);

/* 图片消息模型发送：以 frida 实测的图片模型布局（vt 0x82CB658，类型码 3，
 * 内容为 UTF-16 文件路径）走已验证的 pack 通道。返回 1 = 已提交。 */
int wxb_send_image_model(const char *wxid, const char *path_utf8);

/* 同上，但类型码（body+0xD8）与 +0xD0 标志可配。
 * 实测：type_code=3 送达但 GIF 只取首帧（静态）；
 *       type_code=47(0x2F) 用于试探"动画表情"处理路径。 */
int wxb_send_image_model_ex(const char *wxid, const char *path_utf8,
                            int type_code, int flag_d0);

#define send_text wxb_send_text

#endif /* WX_BRIDGE_SEND_TEXT_H */
