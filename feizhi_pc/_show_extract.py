import io
s = io.open("memory.py", encoding="utf-8").read()
i = s.index("EXTRACT_SYSTEM")
j = s.index('"""', s.index('"""', i) + 3) + 3
print(s[i:j])
