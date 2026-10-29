import sys

sys.path.insert(0, r"<PROJECT_ROOT>\feizhi_pc")
sys.stdout.reconfigure(encoding="utf-8")

import voice

print("档位:", "/".join(voice.MOODS))
print("默认:", voice.DEFAULT_MOOD, " 兜底:", voice.FALLBACK_MOOD)
print()
print("style_for(害羞) 开头:", voice.style_for("害羞")[:90].replace("\n", " | "))
print()
unknown = voice.style_for("激动")
fallback = voice.style_for(voice.FALLBACK_MOOD)
print("未知档位是否回退到兜底:", unknown == fallback)
print("兜底是否是温柔:", voice.FALLBACK_MOOD == "温柔")
