Electron v086.4 - Case Dock + History Toggle + Mark Taxonomy Cleanup

Scope:
- Electron only. Backend untouched.
- Renamed Seed-facing UI to Case.
- Dock is now N / G / M / C.
- Removed redundant inner tab row from floating workspace panel.
- Mark panel no longer renders the old Range/Event dropdown block.
- Mark panel shows the clean taxonomy accordion/button workflow.
- Added History Marks ON/OFF toggle in the top toolbar.
- History Marks defaults OFF so saved/backend seed/case anchors no longer clutter the current working map.
- Current session marks still show normally.

Run:
npm install
npm run build
npm run dev
