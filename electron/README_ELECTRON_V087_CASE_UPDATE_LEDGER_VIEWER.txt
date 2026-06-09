Electron v087 - Case Update + Event Ledger Viewer

Changes:
- Narrative dock panel is now an Event Ledger Viewer for the active timeframe.
- Shows raw saved event rows with click-to-jump behavior.
- Adds Range Compiler Preview for explicit Set M/W/D High/Low anchors.
- Case Manager now tracks an active case ID.
- Save Case updates the active case when backend v147 is installed.
- Save As New deliberately creates a fresh case container.
- Recent cases are selectable and set the active case.
- Save Bundle remains the atomic event ledger truth.

Backend note:
- For persistent Case Update, install backend v147.
- Without backend v147, the app will not create a duplicate when attempting an update, but the update cannot persist server-side.
