Electron v087.20 - Structural Mapping Cleanup

Purpose:
- Prepare UI for structure-only mapping.
- Rename Map Settings to Display Settings.
- Hide hard reset behind a collapsed Danger Zone.
- Remove active strategy interpretation fields from Display Settings.
- Keep visual helper controls only.

Important doctrine:
Mapping stores structural movement only:
- ranges
- BOS up/down
- active range changes
- old range memory
- parent-child range links

Analytics later derives:
- sweeps
- P2/P3
- OBs
- mitigation
- profiles
- objectives
- probabilities

Backend required:
- backend_v153_structure_range_hierarchy.zip
