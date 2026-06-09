# Electron v086.14 - Case Save Confirmation + Guard

- Case Manager now shows explicit saved confirmation after saving.
- Case save button disables while saving to prevent double-click duplicate posts.
- Save Bundle also disables while in-flight to stop duplicate bundle writes.
- Case saves no longer render Seed/Case anchor overlays on the chart.
- Case is treated as a bookmark/container; Save Bundle atomic events remain the plotted truth.
- Backend untouched.
