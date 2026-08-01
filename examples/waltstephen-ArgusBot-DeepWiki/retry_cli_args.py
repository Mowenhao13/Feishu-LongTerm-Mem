#!/usr/bin/env python3
"""Upload CLI-Arguments-Reference.md in chunks to avoid API internal errors."""
import subprocess
import os

WORK_DIR = "/Users/halllo/projects/local/feishu-mem"
DOC_TOKEN = "XVEFwBpkLi84eYkFQKsc1tQSnCf"
SRC_FILE = "/Users/halllo/projects/local/feishu-mem/examples/waltstephen-ArgusBot-DeepWiki/CLI-Arguments-Reference.md"

with open(SRC_FILE) as f:
    text = f.read()

# Clean content
lines = text.split('\n')
cleaned = []
skip_relevant = False
skip_rules = False

for line in lines:
    if line.strip() == "Relevant source files":
        skip_relevant = True
        continue
    if skip_relevant:
        if line.startswith("- [") or line.strip() == "":
            continue
        else:
            skip_relevant = False
    if line.strip().startswith("Rules relevant"):
        skip_rules = True
        continue
    if skip_rules:
        continue
    if line.strip().startswith("**Sources:**"):
        continue
    cleaned.append(line)

while cleaned and cleaned[-1].strip() == "":
    cleaned.pop()

full_text = '\n'.join(cleaned)

# Split at H2 boundaries to keep chunks meaningful
# Find H2 section starts
h2_indices = [0]
for i, line in enumerate(cleaned):
    if line.startswith("## "):
        h2_indices.append(i)

print(f"Total chars: {len(full_text)}")
print(f"H2 sections: {len(h2_indices)}")

# Write the first chunk (overwrite) and then append the rest
chunk1 = '\n'.join(cleaned[:h2_indices[len(h2_indices)//2]])
chunk2 = '\n'.join(cleaned[h2_indices[len(h2_indices)//2]:])

print(f"Chunk 1: {len(chunk1)} chars")
print(f"Chunk 2: {len(chunk2)} chars")

# Write chunk1
temp1 = os.path.join(WORK_DIR, "_temp_chunk1.md")
with open(temp1, 'w') as f:
    f.write(chunk1)

cmd1 = [
    "lark-cli", "docs", "+update",
    "--api-version", "v2",
    "--doc", DOC_TOKEN,
    "--command", "overwrite",
    "--content", "@_temp_chunk1.md",
    "--doc-format", "markdown",
]
result1 = subprocess.run(cmd1, capture_output=True, text=True, timeout=60, cwd=WORK_DIR)
if result1.returncode == 0:
    print("✅ Chunk 1 uploaded successfully")
else:
    print(f"❌ Chunk 1 failed: {result1.stderr[:500]}")
    os.unlink(temp1)
    exit(1)

os.unlink(temp1)

# Write chunk2
temp2 = os.path.join(WORK_DIR, "_temp_chunk2.md")
with open(temp2, 'w') as f:
    f.write(chunk2)

cmd2 = [
    "lark-cli", "docs", "+update",
    "--api-version", "v2",
    "--doc", DOC_TOKEN,
    "--command", "append",
    "--content", "@_temp_chunk2.md",
    "--doc-format", "markdown",
]
result2 = subprocess.run(cmd2, capture_output=True, text=True, timeout=60, cwd=WORK_DIR)
if result2.returncode == 0:
    print("✅ Chunk 2 appended successfully")
else:
    print(f"❌ Chunk 2 failed: {result2.stderr[:500]}")

os.unlink(temp2)
