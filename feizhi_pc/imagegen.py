"""生图 —— 让绯栀偶尔能发一张「自己拍的照片」。

网关
----
主用**三宝**（sanbaobeauty.com），协议：
    POST {base}/openapi/v1/images          -> 2xx + { data: { id, status, progress } }
    GET  {base}/openapi/v1/images/{id}     -> { data: { status, progress, image_url | images[] } }
    status: queued / processing / succeeded / failed
    body: { model, prompt, quality: high|medium|low, aspect_ratio: 1:1|3:4|16:9, concurrency }

备用 **AIStarsLab**（api.video.aistarslab.com），协议是另一套
（/generation/create/image + channel + quality=1K/2K/4K）。2026-10-14 起该账号积分不足。

耗时提醒
--------
出图是**慢操作**（实测约 80 秒）。调用方必须放在后台线程里，绝不能进收消息的主循环。
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path

import requests

LOG = logging.getLogger("feizhi_pc.imagegen")

CONFIG_PATH = Path(r"<PROJECT_ROOT>\feizhi_pc\image_config.json")
IMAGE_DIR = Path(r"<PROJECT_ROOT>\feizhi_pc\images")

DEFAULT_ASPECT = "16:9"     # 实测三宝只有 16:9 稳定；竖构图靠生成后裁切（见 crop_to_portrait）
DEFAULT_TIMEOUT = 300.0

# 外貌锚点：固定人物特征，保证多次出图看起来是同一个人。
# LLM 只负责给「场景」（[draw:场景]），人物描述在这里统一拼接。
# 注意保持简短 —— prompt 过长会被网关拒（实测 150 字报「参数不符」，40 字正常）。
# ★ prompt 写法是硬约束（2026-10-14 实测隔离变量）：
#     逗号连写的短句                       -> 成功（44s）
#     带句号的多句 + 「浅色墙背景」这类布局词 -> 400 上游拒绝
#   上游会把带句号的描述当成「编辑/多段指令」，所以这里一律用逗号连写，不用句号。
#
# ★ 外貌锚点里**不写发型**：发型/发长由参考图（personaRefUrl）决定，
#   写进提示词反而会覆盖参考图 —— 实测基准照是短发时，出图却成了长发。
PERSONA_ANCHOR = (
    "19岁中国女孩，杭州人，美院大二，皮肤白，"
    "五官清秀自然，素颜或淡妆，简单针织衫"
)
STYLE_SUFFIX = "手机随手拍的生活照，自然光，真实感，主体居中，无文字"

# 人物基准照：将来若能上传成公网 URL，可作为参考图锁脸。
PERSONA_REF = IMAGE_DIR / "_persona_ref.jpg"

# 失败熔断：网关出问题时不反复撞墙
_FAIL_STREAK = 0
_FAIL_UNTIL = 0.0
FAIL_THRESHOLD = 3
FAIL_COOLDOWN = 1800.0
QUOTA_COOLDOWN = 6 * 3600.0


def load_config() -> dict:
    cfg: dict = {}
    if CONFIG_PATH.exists():
        try:
            cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            LOG.warning("读生图配置失败 %s: %s", CONFIG_PATH, exc)
    return cfg


def build_prompt(scene: str) -> str:
    """把「场景」拼成完整提示词：外貌锚点 + 场景 + 拍摄风格。

    一律用逗号连写、不用句号 —— 实测带句号的描述会被上游当成编辑指令而拒。
    """
    scene = (scene or "").strip().rstrip("。.")
    if not scene:
        return ""
    if "19岁" in scene or PERSONA_ANCHOR[:6] in scene:
        return f"{scene}，{STYLE_SUFFIX}"
    return f"{PERSONA_ANCHOR}，{scene}，{STYLE_SUFFIX}"


def cooling_down() -> bool:
    return time.time() < _FAIL_UNTIL


def _note_fail() -> None:
    global _FAIL_STREAK, _FAIL_UNTIL
    _FAIL_STREAK += 1
    if _FAIL_STREAK >= FAIL_THRESHOLD:
        _FAIL_UNTIL = time.time() + FAIL_COOLDOWN
        LOG.warning("生图连续失败 %d 次，暂停 %.0f 分钟", _FAIL_STREAK, FAIL_COOLDOWN / 60)


def _note_quota_exhausted(msg: str) -> None:
    global _FAIL_STREAK, _FAIL_UNTIL
    _FAIL_STREAK = 0
    _FAIL_UNTIL = time.time() + QUOTA_COOLDOWN
    LOG.warning("生图额度不足（%s），暂停 %.0f 小时；充值后重启即恢复",
                msg[:60], QUOTA_COOLDOWN / 3600)


def _note_ok() -> None:
    global _FAIL_STREAK, _FAIL_UNTIL
    _FAIL_STREAK = 0
    _FAIL_UNTIL = 0.0


def _download(url: str, dst: Path, timeout: float = 300.0,
              attempts: int = 3) -> bool:
    """下载生成图。**CDN 慢的时候要重试，不能白扔一次生成额度。**

    ★ 2026-10-28：默认超时 180s、单次尝试，网络一抖就整张图丢掉 ——
      而图其实已经在服务端生成好了，只是没拉下来。现在放宽到 300s 并重试 3 次。
    """
    for i in range(max(1, attempts)):
        try:
            r = requests.get(url, timeout=timeout, stream=True)
            if r.status_code != 200:
                LOG.warning("下载生成图失败 HTTP %s（第 %d 次）", r.status_code, i + 1)
            else:
                dst.parent.mkdir(parents=True, exist_ok=True)
                with dst.open("wb") as fh:
                    for chunk in r.iter_content(65536):
                        fh.write(chunk)
                if dst.stat().st_size > 1024:
                    return True
                LOG.warning("下载到的图太小（第 %d 次）：%s 字节",
                            i + 1, dst.stat().st_size)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("下载生成图异常（第 %d/%d 次）: %s", i + 1, attempts, exc)
        if i + 1 < attempts:
            time.sleep(3.0)
    return False


def _crop_portrait(src: Path, ratio: float = 3 / 4) -> Path | None:
    """把横图裁成竖构图（保中间）。

    为什么要裁：三宝只有 16:9 稳定（竖比例会走另一档线路、频繁失败），
    而发到微信里的自拍应当是竖的。裁切前会要求模型把主体放中间，减少损失。
    """
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        dst = src.with_name(src.stem + "_p.jpg")
        with Image.open(src) as im:
            im = im.convert("RGB")
            w, h = im.size
            cur = w / h
            if abs(cur - ratio) < 0.02:
                return None                      # 已经是目标比例
            if cur > ratio:                      # 太宽 → 裁两侧，保中间
                new_w = int(h * ratio)
                left = (w - new_w) // 2
                im = im.crop((left, 0, left + new_w, h))
            else:                                # 太高 → 裁上下
                new_h = int(w / ratio)
                top = (h - new_h) // 3           # 略偏上，保留人脸
                im = im.crop((0, top, w, top + new_h))
            im.thumbnail((1440, 1920))
            im.save(dst, "JPEG", quality=88, optimize=True)
        if dst.stat().st_size > 1024:
            return dst
    except Exception as exc:  # noqa: BLE001
        LOG.warning("裁切竖构图失败（保留原图）: %s", exc)
    return None


def _to_jpeg(src: Path, max_side: int = 1440, quality: int = 88) -> Path | None:
    """转成压缩 JPEG：手机随手拍通常是 1~3MB 的 JPEG，原图 PNG 动辄 3~7MB。"""
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        dst = src.with_suffix(".jpg")
        with Image.open(src) as im:
            im = im.convert("RGB")
            im.thumbnail((max_side, max_side * 2))
            im.save(dst, "JPEG", quality=quality, optimize=True)
        if dst.stat().st_size > 1024:
            try:
                src.unlink()
            except OSError:
                pass
            return dst
    except Exception as exc:  # noqa: BLE001
        LOG.warning("转 JPEG 失败（保留原图）: %s", exc)
    return None


# ---------------------------------------------------------------- 三宝

def _sanbao_generate(prompt: str, cfg: dict, aspect: str, quality: str,
                     timeout: float, cache: Path, use_ref: bool = True,
                     crop_portrait: bool = False) -> Path | None:
    sc = cfg.get("sanbao") or {}
    base = str(sc.get("baseURL") or "https://sanbaobeauty.com").rstrip("/")
    key = str(sc.get("apiKey") or "")
    model = str(sc.get("model") or "gpt-image-2")
    ref_url = str(sc.get("personaRefUrl") or "")
    if not key:
        LOG.warning("三宝未配置 apiKey")
        return None

    h = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    body = {"model": model, "prompt": prompt, "quality": quality,
            "aspect_ratio": aspect, "concurrency": 1}
    # ★ 参考图锁脸：字段名是 images（URL 数组），不是 aistarslab 那套 inputImages。
    # 这张基准照先经 /api/uploads/raw 上传成公网 URL 才能用（data URL 会被拒）。
    if use_ref and ref_url:
        body["images"] = [ref_url]
        LOG.info("已附带人物基准照（参考图锁脸）")

    try:
        r = requests.post(f"{base}/openapi/v1/images", headers=h, json=body, timeout=90)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("三宝创建请求异常: %s", exc)
        _note_fail()
        return None

    # 注意：三宝创建成功返回 201，不是 200
    if not (200 <= r.status_code < 300):
        detail = (r.text or "")[:180]
        LOG.warning("三宝创建失败 HTTP %s: %s", r.status_code, detail)
        if r.status_code in (401, 403) or "积分" in detail or "额度" in detail:
            _note_quota_exhausted(detail)
        else:
            _note_fail()
        return None

    data = (r.json() or {}).get("data") or {}
    tid = data.get("id") or data.get("taskId") or data.get("task_id")
    if not tid:
        LOG.warning("三宝未返回 taskId: %s", str(data)[:160])
        _note_fail()
        return None
    LOG.info("三宝任务已创建 id=%s model=%s", tid, model)

    deadline = time.time() + timeout
    polls = 0
    while time.time() < deadline:
        time.sleep(4.0)
        polls += 1
        try:
            q = requests.get(f"{base}/openapi/v1/images/{tid}", headers=h, timeout=45)
            d = (q.json() or {}).get("data") or {}
        except Exception as exc:  # noqa: BLE001
            LOG.debug("三宝轮询异常(继续): %s", exc)
            continue

        st = str(d.get("status") or "")
        if st == "succeeded":
            url = d.get("image_url")
            if not url and isinstance(d.get("images"), list) and d["images"]:
                url = d["images"][0]
            if not url:
                LOG.warning("三宝成功但没有图片地址")
                _note_fail()
                return None
            if _download(str(url), cache):
                jpg = _to_jpeg(cache)
                final = jpg or cache
                # 16:9 横图 → 裁成 3:4 竖构图（更像手机自拍）
                if crop_portrait:
                    cropped = _crop_portrait(final)
                    if cropped:
                        final = cropped
                _note_ok()
                LOG.info("三宝出图完成 %s（%.1fMB，轮询 %d 次）",
                         final.name, final.stat().st_size / 1048576, polls)
                return final
            _note_fail()
            return None
        if st == "failed":
            LOG.warning("三宝任务失败: %s", str(d.get("error"))[:180])
            _note_fail()
            return None

    LOG.warning("三宝轮询超时（%.0fs，%d 次）", timeout, polls)
    _note_fail()
    return None


# ------------------------------------------------------------ AIStarsLab

# 备用线路（synapse-ai.uk，OpenAI 兼容形状）：比例 -> size
_ASPECT_TO_SIZE = {
    "1:1": "1024x1024",
    "3:4": "1024x1536",
    "4:3": "1536x1024",
    "9:16": "1024x1536",
    "16:9": "1536x1024",
}


def _synapse_generate(prompt: str, cfg: dict, aspect: str,
                      timeout: float, cache: Path,
                      affect_breaker: bool = True) -> Path | None:
    """备用线路：synapse-ai.uk，OpenAI 兼容 POST {base}/images/generations。"""
    sc = cfg.get("synapse") or {}
    base = str(sc.get("baseURL") or "https://synapse-ai.uk/v1").rstrip("/")
    key = str(sc.get("apiKey") or "")
    model = str(sc.get("model") or "gpt-image-2")
    if not key:
        return None

    def breaker(fn, *a):
        if affect_breaker:
            fn(*a)

    h = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    body = {"model": model, "prompt": prompt, "n": 1,
            "size": str(sc.get("size") or _ASPECT_TO_SIZE.get(aspect, "1024x1536"))}
    try:
        r = requests.post(f"{base}/images/generations", headers=h, json=body,
                          timeout=min(timeout, 240))
    except Exception as exc:  # noqa: BLE001
        LOG.warning("synapse 请求异常: %s", exc)
        breaker(_note_fail)
        return None

    if r.status_code != 200:
        detail = (r.text or "")[:180]
        LOG.warning("synapse HTTP %s: %s", r.status_code, detail)
        if r.status_code in (401, 402, 403) or "quota" in detail.lower():
            breaker(_note_quota_exhausted, detail)
        else:
            breaker(_note_fail)
        return None

    try:
        item = (r.json().get("data") or [{}])[0]
    except Exception as exc:  # noqa: BLE001
        LOG.warning("synapse 响应解析失败: %s", exc)
        breaker(_note_fail)
        return None

    url = item.get("url")
    b64 = item.get("b64_json")
    try:
        if url:
            if not _download(str(url), cache):
                breaker(_note_fail)
                return None
        elif b64:
            import base64 as _b64
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(_b64.b64decode(b64))
        else:
            LOG.warning("synapse 未返回图片数据")
            breaker(_note_fail)
            return None
        jpg = _to_jpeg(cache)
        final = jpg or cache
        breaker(_note_ok)
        LOG.info("synapse 出图完成 %s（%.1fMB）",
                 final.name, final.stat().st_size / 1048576)
        return final
    except Exception as exc:  # noqa: BLE001
        LOG.warning("synapse 落盘失败: %s", exc)
        breaker(_note_fail)
        return None


def _aistarslab_generate(prompt: str, cfg: dict, aspect: str, quality: str,
                         timeout: float, cache: Path,
                         affect_breaker: bool = True) -> Path | None:
    ac = cfg.get("aistarslab") or {}
    base = str(ac.get("baseURL") or "").rstrip("/")
    key = str(ac.get("apiKey") or "")
    model = str(ac.get("model") or "")
    channel = str(ac.get("channel") or "23")
    if not (base and key and model):
        return None

    def breaker(fn, *a):
        """降级线路的失败不应熔断主线路（它俩额度是各自独立的）。"""
        if affect_breaker:
            fn(*a)

    h = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    body = {"channel": channel, "model": model, "prompt": prompt,
            "aspectRatio": aspect, "quality": quality, "n": 1}
    try:
        r = requests.post(f"{base}/generation/create/image", headers=h, json=body, timeout=60)
        created = r.json() if r.content else {}
    except Exception as exc:  # noqa: BLE001
        LOG.warning("aistarslab 创建异常: %s", exc)
        breaker(_note_fail)
        return None

    if created.get("code") != 0:
        msg = str(created.get("msg") or "")
        LOG.warning("aistarslab 创建失败 HTTP %s: %s", r.status_code, msg[:160])
        if created.get("code") == 403 or "积分" in msg or "余额" in msg:
            breaker(_note_quota_exhausted, msg)
        else:
            breaker(_note_fail)
        return None

    tid = (created.get("data") or {}).get("taskId")
    if not tid:
        breaker(_note_fail)
        return None

    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(3.0)
        try:
            q = requests.get(f"{base}/generation/status",
                             params={"taskId": tid}, headers=h, timeout=45)
            d = (q.json() or {}).get("data") or {}
        except Exception:  # noqa: BLE001
            continue
        if d.get("status") == 3:
            outs = d.get("outputs") or []
            if outs and _download(str(outs[0]), cache):
                jpg = _to_jpeg(cache)
                final = jpg or cache
                breaker(_note_ok)
                LOG.info("aistarslab 出图完成 %s", final.name)
                return final
            breaker(_note_fail)
            return None
        if d.get("status") == 4:
            breaker(_note_fail)
            return None
    breaker(_note_fail)
    return None


# ------------------------------------------------------------------ 入口

def generate(prompt: str, aspect: str = DEFAULT_ASPECT,
             quality: str | None = None,
             timeout: float = DEFAULT_TIMEOUT,
             ref_image: Path | None = None,
             use_ref: bool = True) -> Path | None:
    """生成一张图并落盘，返回本地路径；失败返回 None。

    use_ref=True（默认）：带上 image_config.json 里 sanbao.personaRefUrl 那张基准照，
    保证每次出图是同一张脸（实测有效）。该 URL 需先经 /api/uploads/raw 上传取得。
    同样的 prompt 只生成一次（按 hash 复用已有文件），避免重复烧额度。
    """
    prompt = (prompt or "").strip()
    if not prompt:
        return None

    cfg = load_config()
    provider = str(cfg.get("provider") or "sanbao").lower()
    if quality is None:
        quality = str((cfg.get(provider) or {}).get("quality")
                      or ("high" if provider == "sanbao" else "1K"))

    tag = hashlib.sha256(f"{provider}|{prompt}|{aspect}|{quality}".encode("utf-8")).hexdigest()[:16]
    cache = IMAGE_DIR / f"gen_{tag}.png"
    if cache.exists() and cache.stat().st_size > 1024:
        LOG.info("生图命中缓存 %s", cache.name)
        return cache
    jpg_cached = cache.with_suffix(".jpg")
    if jpg_cached.exists() and jpg_cached.stat().st_size > 1024:
        LOG.info("生图命中缓存 %s", jpg_cached.name)
        return jpg_cached

    if cooling_down():
        LOG.info("生图处于熔断冷却期，本次跳过")
        return None

    eff_timeout = float(cfg.get("timeoutSec") or timeout)

    if provider == "sanbao":
        sc = cfg.get("sanbao") or {}
        # 配置里的 aspectRatio / cropToPortrait 优先（默认 16:9 + 裁竖构图）
        aspect = str(sc.get("aspectRatio") or aspect)
        do_crop = bool(sc.get("cropToPortrait", True))
        out = _sanbao_generate(prompt, cfg, aspect, quality, eff_timeout, cache,
                               use_ref=use_ref, crop_portrait=do_crop)
        if out:
            return out
        # 三宝失败且不是额度问题 → 退到 aistarslab 试一次。
        # 注意 affect_breaker=False：备用线路的额度/失败不该熔断主线
        # （两边额度独立；曾经因为备用线路「积分不足」把三宝也停了 6 小时）。
        if not cooling_down():
            LOG.info("三宝失败，尝试 synapse 备用线路")
            alt = _synapse_generate(prompt, cfg, aspect, eff_timeout, cache,
                                    affect_breaker=False)
            if alt:
                return alt
            # 备用也失败：把主线的熔断补记一次，避免无限重试
            _note_fail()
        return None

    return _synapse_generate(prompt, cfg, aspect, eff_timeout, cache)


def set_persona_ref(src: Path) -> bool:
    """把某张图设为人物基准照（转 JPEG 并限制尺寸）。"""
    try:
        from PIL import Image
        IMAGE_DIR.mkdir(parents=True, exist_ok=True)
        with Image.open(src) as im:
            im = im.convert("RGB")
            im.thumbnail((1024, 1365))
            im.save(PERSONA_REF, "JPEG", quality=90, optimize=True)
        LOG.info("人物基准照已设置: %s (%.0fKB)",
                 PERSONA_REF.name, PERSONA_REF.stat().st_size / 1024)
        return True
    except Exception as exc:  # noqa: BLE001
        LOG.warning("设置基准照失败: %s", exc)
        return False
