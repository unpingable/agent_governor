# Fiction Mode Demo — VHS terminal recording
# https://github.com/charmbracelet/vhs
#
# Usage: vhs docs/demo/fiction.tape
# Output: docs/demo/fiction.gif

Output docs/demo/fiction.gif

Set FontSize 14
Set Width 900
Set Height 500
Set Theme "Dracula"
Set TypingSpeed 40ms

# Clean setup
Hide
Type "rm -rf /tmp/ag_demo_fiction && mkdir /tmp/ag_demo_fiction && cd /tmp/ag_demo_fiction"
Enter
Sleep 500ms
Type "clear"
Enter
Sleep 300ms
Show

Type "governor init"
Enter
Sleep 800ms

Type "governor continuity anchor add --id elena-eyes --type canon -d 'Elena has green eyes' -f 'blue eyes' -s reject"
Enter
Sleep 800ms

Type "governor continuity anchor add --id magic-rule --type canon -d 'Magic requires spoken words' -f 'silent spell' -f 'wordless magic' -s reject"
Enter
Sleep 800ms

Type ""
Enter
Sleep 200ms

Type "echo 'Elena brushed her blue eyes with the back of her hand and cast a silent spell.' > chapter-3.md"
Enter
Sleep 500ms

Type "governor check chapter-3.md --mode fiction"
Enter
Sleep 8s
