# Guardrail Demo — VHS terminal recording
# https://github.com/charmbracelet/vhs
#
# Usage: vhs docs/demo/guardrail.tape
# Output: docs/demo/guardrail.gif

Output docs/demo/guardrail.gif

Set FontSize 14
Set Width 1000
Set Height 600
Set Theme "Dracula"
Set TypingSpeed 35ms

Hide
Type "cd /home/jbeck/git/agent_gov"
Enter
Sleep 300ms
Type "clear"
Enter
Sleep 300ms
Show

Type "python3 contrib/demo_guardrail.py"
Enter
Sleep 48s
