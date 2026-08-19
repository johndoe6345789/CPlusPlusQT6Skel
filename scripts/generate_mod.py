# Moved here with the Qt6 frontend: it generates assets/audio/retro-gaming.mod,
# which only this project consumes. Paths were relative to the monorepo root.
from pathlib import Path

header = """\
IMPM
00 Song Title
01 Retro Beats
"""

patterns = [
    "C-5 00 00  - 00 00",
    "E-5 00 00  - 00 00",
    "G-5 00 00  - 00 00",
    "B-4 00 00  - 00 00",
]

Path("assets/audio").mkdir(parents=True, exist_ok=True)
with Path("assets/audio/retro-gaming.mod").open("w") as mod:
    mod.write(header)
    for idx, pattern in enumerate(patterns, 1):
        mod.write(f"\nPattern {idx:02d}: {pattern}\n")

print("Generated retro-gaming.mod", Path("assets/audio/retro-gaming.mod").absolute())
