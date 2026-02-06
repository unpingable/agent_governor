# Code Mode Demo — VHS terminal recording
# https://github.com/charmbracelet/vhs
#
# Usage: vhs docs/demo/code.tape
# Output: docs/demo/code.gif

Output docs/demo/code.gif

Set FontSize 14
Set Width 900
Set Height 500
Set Theme "Dracula"
Set TypingSpeed 40ms

# Clean setup
Hide
Type "rm -rf /tmp/ag_demo_code && mkdir /tmp/ag_demo_code && cd /tmp/ag_demo_code"
Enter
Sleep 500ms
Type "clear"
Enter
Sleep 300ms
Show

Type "governor init"
Enter
Sleep 800ms

Type "governor propose -c 'type=decision,topic=api-style,choice=REST'"
Enter
Sleep 1s

# Verify and apply (hidden — UUID plumbing)
Hide
Type `ID=$(governor status --json | python3 -c "import sys,json; print(json.load(sys.stdin)[0]['id'])")`
Enter
Sleep 200ms
Type `governor verify "$ID" 2>&1`
Enter
Sleep 500ms
Type `governor apply "$ID" 2>&1`
Enter
Sleep 500ms
Type "clear"
Enter
Sleep 300ms
Show

Type "governor decisions"
Enter
Sleep 1500ms

Type ""
Enter
Sleep 200ms

Type "governor propose -c 'type=decision,topic=api-style,choice=GraphQL'"
Enter
Sleep 800ms

Hide
Type `ID2=$(governor status --json | python3 -c "import sys,json; d=json.load(sys.stdin); print([p['id'] for p in d if p['state']=='proposed'][0])")`
Enter
Sleep 200ms
Show

Type `governor verify "$ID2"`
Enter
Sleep 8s
