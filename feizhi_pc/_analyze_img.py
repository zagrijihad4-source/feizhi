from PIL import Image
import numpy as np
p = "images/gen_d25896b221a9faec.jpg"
im = Image.open(p).convert("RGB")
a = np.asarray(im).astype(int)
h, w, _ = a.shape
bg = a[4, 4]
print("尺寸 %dx%d  背景色 %s" % (w, h, tuple(bg)))
# 与背景差异明显的像素
diff = np.abs(a - bg).sum(axis=2)
mask = diff > 40
rows = np.where(mask.any(axis=1))[0]
cols = np.where(mask.any(axis=0))[0]
print("非背景 bbox: y %d..%d   x %d..%d" % (rows.min(), rows.max(), cols.min(), cols.max()))
# 每行的非背景像素数，找人物密度变化
dens = mask.sum(axis=1)
for y in range(0, h, 50):
    print("  y=%4d  宽度%4d  %s" % (y, dens[y], "#" * min(60, dens[y] // 14)))
# 肤色行（下巴大致位置：肤色像素明显变少的那一行）
skin = (a[:,:,0] > 205) & (a[:,:,1] > 165) & (a[:,:,2] > 145) & (a[:,:,0] > a[:,:,2] + 15)
sd = skin.sum(axis=1)
nz = np.where(sd > 8)[0]
if len(nz):
    print("肤色像素 y 范围: %d .. %d" % (nz.min(), nz.max()))
