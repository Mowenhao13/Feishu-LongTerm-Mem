#!/usr/bin/env python3
"""Update all wiki doc content from local markdown files."""
import subprocess
import re
import sys
import os

MD_DIR = "/Users/halllo/projects/local/feishu-mem/examples/waltstephen-ArgusBot-DeepWiki"

# Mapping: obj_token -> md_filename
DOCS = {
    # Top-level (21)
    "J80adCgWiov2wvxL48ocwaZvnlf": "Overview.md",
    "AJ2HdtazvoFbkzxjJefcDDdsnXf": "Getting-Started.md",
    "OaBUdrIKaoT8cnxonaFc9hO5nQf": "Architecture.md",
    "P8nKdDypcoI3MuxcIoRcIJ8Wnef": "Core-Components.md",
    "MF3gd4h2qo5gGOxQoA9cH07VnJf": "Command-System-Overview.md",
    # "SpK7dVqM2otky3xXiXBcAkqjnRM": "6. Agent System" - SKIPPED (empty)
    "QcsadbCBVoLUV9xm81jcJ1Nknkg": "Advanced-Topics.md",
    "ICgmd2MLVol6oMx1Bq6cCEAVnHe": "Control-and-Communication.md",
    "K3usdqt80o13nCxScj5crmQhnae": "Configuration-Files.md",
    "HVljdbtwAo5Kbpxd8JUcOXmVnnd": "Local-Control.md",
    "QIu9dwqXSofYz6xLflCcmkE2nmd": "AutoLoopOrchestrator.md",
    "YGptdGoHjox555xFMtOcYb7tnSS": "Codex-Runner-Integration.md",
    "VC74d8bBuok4sCx4YgBcf5Rhnld": "File-Structure-Reference.md",
    "DiqEduZJio4RaZxEBFpcsK6Yntc": "Model-Catalog-and-Presets.md",
    "QZxbdVPPLoCKKRx1gUscSyUFnCG": "Event-Types-Reference.md",
    "JdVNdCHyQovpSnxIkhvc7h1VnYd": "Token-Locking-and-Multi-Instance-Safety.md",
    "DnFqd9hbUoMwpfxg7X5cfAronng": "Stall-Watchdog.md",
    "Ah9CdNQVoodDfKxrHcucHrhnnqh": "Feishu-Integration.md",
    "IxKydZWBRo9jolxmKnqcc8oKnyd": "Telegram-Integration.md",
    "GZY5dCBiYouR8LxLKu8cSmyhnCb": "Copilot-Proxy-Integration.md",
    "PVEWdfICDoeWzFxrSw7cnybinRD": "Reference.md",
    # Children of 2. Getting Started
    "Z4BIdp0JAonUF7xlHUKcbBIwn0g": "Installation-and-Initial-Setup.md",
    "RtZHdpFcEoGunAxwQMIcLC6gnrd": "Quickstart-Tutorial.md",
    "Ew6Rd0ygtoLo7RxFUVKcXGiFnxe": "Configuration-Overview.md",
    # Children of 3. Architecture
    "HruGdx30ioRYsDxkRvWcQG0FnQV": "System-Overview.md",
    "SdMcddtBjovyQbxB23CcrQrBngh": "Daemon-Mode-Architecture.md",
    "QdSzdfYMNoY1i2xQuhPcfxD4nwg": "CLI-Mode-Architecture.md",
    "AsIIdlxqrocIe8xEoffcwNDRncc": "Multi-Agent-Loop-System.md",
    "W7ZsdZTKIoDylfxMdsccaKxfnVd": "State-Management-and-Persistence.md",
    # Children of 5. Command System Overview
    "OFnPdd3VAoWiP7xOweHcEsaAnVb": "Command-Reference.md",
    "A3iadCMI7oV5A7xoH17c1MbxnkB": "CLI-Arguments-Reference.md",
    # Children of 6. Agent System
    "ZZTHdxirtox71Ex6nxFcMxuxndc": "Planner-Sub-Agent.md",
    "Ea8HdjbkOoBwyBxwLbqc8lnVn8c": "Reviewer-Sub-Agent.md",
    "DEm2drtSyoDVYrxfh5ecIxycndc": "BTW-Side-Agent.md",
    # Children of 7. Advanced Topics
    "BmORdZO6Fo2IesxAnUqcmSnunQb": "Session-Management-and-Resumption.md",
    "CYfid41wEoCpsIxu2ogc0yuonqg": "State-Persistence-Details.md",
    "HyHIdGn1yoLP0OxNIXvcgN8Jn4c": "Automated-Planning-System.md",
    "RKg2d8yH1oMqnKxHMjUcBnpkn8e": "Error-Recovery-and-Resilience.md",
    # Children of 9. Configuration Files
    "KORqd5RiEocqUhx3NPQcwjsQnte": "Configuration-Overview.md",
    "BsMxdyRquojQD6xMn2vcx4zxnyg": "Models-and-AI-Configuration.md",
}

def clean_content(text):
    # Remove "Relevant source files" section at top
    lines = text.split('\n')
    cleaned_lines = []
    skip_relevant_section = False
    relevant_count = 0
    
    for i, line in enumerate(lines):
        if line.strip() == 'Relevant source files' and i < 5:
            skip_relevant_section = True
            continue
        if skip_relevant_section:
            # Skip list items that start with - [ or are blank after header
            if line.startswith('- [') or line.strip() == '':
                if line.strip() == '' and relevant_count > 0:
                    skip_relevant_section = False
                continue
            else:
                skip_relevant_section = False
        
        cleaned_lines.append(line)
    
    text = '\n'.join(cleaned_lines)
    
    # Remove **Sources:** sections at bottom
    text = re.sub(r'\n\*\*Sources\*\*:.*$', '', text, flags=re.MULTILINE | re.DOTALL)
    text = re.sub(r'\n\*\*Sources\*\*.*$', '', text, flags=re.MULTILINE | re.DOTALL)
    
    # Clean up multiple trailing blank lines
    text = re.sub(r'\n{4,}$', '\n\n', text)
    
    return text.strip()


def update_doc(obj_token, md_file):
    file_path = os.path.join(MD_DIR, md_file)
    if not os.path.exists(file_path):
        print(f"SKIP (file not found): {md_file}")
        return "SKIP"
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    cleaned = clean_content(content)
    
    # Write cleaned content to temp file for @file syntax
    tmpfile = "/tmp/_wiki_content_temp.md"
    with open(tmpfile, 'w', encoding='utf-8') as f:
        f.write(cleaned)
    
    print(f"Updating {md_file} (obj_token: {obj_token[:12]}...)... ", end="", flush=True)
    
    try:
        result = subprocess.run(
            ["lark-cli", "docs", "+update", "--api-version", "v2", 
             "--doc", obj_token, "--mode", "overwrite",
             "--markdown", "@" + tmpfile],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            print("OK")
            return "OK"
        else:
            print(f"FAILED: {result.stderr[:300]}")
            return "FAILED"
    except Exception as e:
        print(f"EXCEPTION: {e}")
        return "EXCEPTION"


if __name__ == "__main__":
    results = {}
    for obj_token, md_file in DOCS.items():
        results[md_file] = update_doc(obj_token, md_file)
    
    ok = sum(1 for v in results.values() if v == "OK")
    skip = sum(1 for v in results.values() if v == "SKIP")
    fail = sum(1 for v in results.values() if v in ("FAILED", "EXCEPTION"))
    
    print(f"\n=== SUMMARY ===")
    print(f"OK: {ok}, SKIP: {skip}, FAILED: {fail}")
    if fail > 0:
        print(f"\nFailed files:")
        for k, v in results.items():
            if v in ("FAILED", "EXCEPTION"):
                print(f"  FAILED: {k}")
