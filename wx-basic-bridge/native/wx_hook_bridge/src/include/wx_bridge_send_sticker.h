#ifndef WX_BRIDGE_SEND_STICKER_H
#define WX_BRIDGE_SEND_STICKER_H

#include "wx_bridge_platform.h"

/* 收藏表情的引用信息。
 *
 * 这六个值来自微信内部状态（本地表情库 Persist\ 下只有加密文件，没有 CDN 链接），
 * 所以只能从"用户实际发过的表情"里采集。实测同一表情重复发送时逐字节相同，
 * 说明可以复用。
 */
typedef struct {
    const char *md5;        /* 内容对象 +0x020 */
    const char *md5b;       /* +0x060 */
    const char *url20401;   /* +0x0e0 */
    const char *url20403;   /* +0x100 */
    const char *md5c;       /* +0x120 */
    const char *url20402;   /* +0x140 */
} WxbStickerSpec;

/* 按 id 取一个内置的表情规格（用于测试通路）。id 从 0 开始。
 * 返回 NULL 表示没有该 id。 */
const WxbStickerSpec *wxb_sticker_preset(int id);
int wxb_sticker_preset_count(void);

/* 发送收藏表情。
 * 返回 1 表示提交成功（异步，不代表已送达）。 */
int wxb_send_sticker(const char *wxid, const WxbStickerSpec *spec);

#endif /* WX_BRIDGE_SEND_STICKER_H */
