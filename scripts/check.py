"""Zero-dependency prepush checks for users without pytest."""
import ast
import json
from pathlib import Path
from subprocess import run
root=Path(__file__).resolve().parents[1]
files=list((root/'agentcompany').glob('*.py'))
for file in files:ast.parse(file.read_text())
assert len(files)>=5
for required in ('README.md','Dockerfile','compose.yaml','.env.example','LICENSE','web/index.html','web/styles.css','web/app.js'):
    assert (root/required).exists(),required
result=run(['node','--check',str(root/'web/app.js')],check=False)
assert result.returncode==0
print('PASS: Python syntax, JavaScript syntax, and required project files')
