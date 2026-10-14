import os
import re

tools_dir = 'backend/src/tools'
pattern = re.compile(r'(?:api[_-]?key|secret|token)\s*=\s*[\'"][^\'\"]+[\'"]', re.I)

found = []
for file_to_check in ['webapp/server.py', 'nori_monitor.py']:
    if os.path.exists(file_to_check):
        with open(file_to_check, encoding='utf-8', errors='ignore') as fh:
            for idx, line in enumerate(fh):
                if pattern.search(line) and not line.strip().startswith('#'):
                    if 'environ' not in line and 'None' not in line and '""' not in line and "''" not in line:
                        found.append((file_to_check, idx+1, line.strip()))
for root, _, files in os.walk(tools_dir):
    for f in files:
        if f.endswith('.py'):
            path = os.path.join(root, f)
            with open(path, encoding='utf-8', errors='ignore') as fh:
                for idx, line in enumerate(fh):
                    if pattern.search(line) and not line.strip().startswith('#'):
                        if 'environ' not in line and 'None' not in line and '""' not in line and "''" not in line:
                            found.append((path, idx+1, line.strip()))

print(f"Total findings: {len(found)}")
for p, l, text in found:
    print(f"{p}:{l} -> {text[:100]}")
