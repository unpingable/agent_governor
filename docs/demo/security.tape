# Security Scan Demo — VHS terminal recording
# https://github.com/charmbracelet/vhs
#
# Usage: vhs docs/demo/security.tape
# Output: docs/demo/security.gif

Output docs/demo/security.gif

Set FontSize 14
Set Width 900
Set Height 500
Set Theme "Dracula"
Set TypingSpeed 40ms

# Clean setup + create vulnerable file (all hidden)
Hide
Type `rm -rf /tmp/ag_demo_sec && mkdir /tmp/ag_demo_sec && cd /tmp/ag_demo_sec && governor init 2>/dev/null`
Enter
Sleep 500ms
Type `cat > handler.py << 'PYEOF'`
Enter
Type "import subprocess"
Enter
Type "import sqlite3"
Enter
Type ""
Enter
Type "def run_command(user_input):"
Enter
Type `    result = subprocess.run(f"echo {user_input}", shell=True, capture_output=True)`
Enter
Type "    return result.stdout"
Enter
Type ""
Enter
Type "def get_user(name):"
Enter
Type `    conn = sqlite3.connect("users.db")`
Enter
Type `    cursor = conn.execute(f"SELECT * FROM users WHERE name = '{name}'")`
Enter
Type "    return cursor.fetchone()"
Enter
Type ""
Enter
Type `API_KEY = "sk-proj-abc123def456"`
Enter
Type "PYEOF"
Enter
Sleep 500ms
Type "clear"
Enter
Sleep 300ms
Show

Type "cat handler.py"
Enter
Sleep 2s

Type ""
Enter
Sleep 200ms

Type "governor security scan -p handler.py"
Enter
Sleep 8s
