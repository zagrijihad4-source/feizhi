#ifndef WX_BRIDGE_SEND_IMAGE_H
#define WX_BRIDGE_SEND_IMAGE_H

#include "wx_bridge_platform.h"

/* 发送本地图片文件。
 *
 * 实现来源：aixed/WeChat-Hook 的开源实现（已在其支持的 4.1.x 上长期验证），
 * 本机 4.1.9.23 的 offset 已逐项核对有效。
 *
 * 关键点：不需要我们自己上传 CDN —— 只填本地路径与文件大小，
 *        上传与消息投递由微信内部完成。
 *
 * file_type: 3 = 普通图片(png/jpg/gif)，47 = 动画表情
 * 返回 1 表示提交成功（异步发送，不代表已送达）。
 */
int wxb_send_image_ex(const char *wxid, const char *img_path, int file_type);

/* 等价于 file_type = 3 */
int wxb_send_image(const char *wxid, const char *img_path);

#endif /* WX_BRIDGE_SEND_IMAGE_H */
