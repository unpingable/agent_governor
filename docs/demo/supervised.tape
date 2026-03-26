# Supervised Session Demo — VHS terminal recording
# https://github.com/charmbracelet/vhs
#
# Usage: vhs docs/demo/supervised.tape
# Output: docs/demo/supervised.gif
#
# NOTE: This runs a real supervised Claude Code session.
# Requires: claude CLI, governor installed, ANTHROPIC_API_KEY set.

Output docs/demo/supervised.gif

Set FontSize 14
Set Width 1000
Set Height 600
Set Theme "Dracula"
Set TypingSpeed 35ms

# Use the pre-built demo script which handles the real session
Hide
Type "cd /home/jbeck/git/agent_gov"
Enter
Sleep 300ms
Type "clear"
Enter
Sleep 300ms
Show

Type "python3 contrib/demo_session.py"
Enter
Sleep 52s
