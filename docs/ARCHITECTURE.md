# Architecture and implementation status

## Trust boundaries

The Tauri process owns one supervised, persistent engine child. JSON-RPC requests are newline-delimited JSON on standard input/output; engine diagnostics use standard error so they cannot corrupt protocol framing. External tools are invoked only with argument arrays. The webview never launches a process or writes a schematic directly.

Each `.litemap` directory is user-visible and portable. `project.json` holds low-frequency configuration and pipeline hashes. SQLite holds authoritative high-volume state and uses WAL, foreign keys, transactions, and integrity checks. `cache/` is the only disposable subtree. Automated voxel replacement and the manual overlay are separate transactions, so a reconstruction rerun cannot erase user work.

## Gate status

| Gate | Status | Included now |
| --- | --- | --- |
| Foundation | Functional vertical slice | Desktop shell, project schema, catalog/downloader, evidence store, viewer/editor, NBT export and round-trip |
| Media | Contract + safe adapters | Local video and ordered picture-folder import, metadata/trim enforcement, rights-gated yt-dlp adapter, checkpointed job records |
| Geometry | Capability gated | Stage/checkpoint contract, calibration persistence, grid/ray utility tests; native pipelines not bundled |
| Block solving | Contract + evidence invariant | Proposal/state/evidence schema and confidence utilities; complete template resolver/scorer not implemented |
| Release | Configuration only | macOS 14 target metadata; signing, updater, arm64 onedir and notarization need release credentials/build farm |

## Engine methods

The public method families are `project.*`, `assets.*`, `source.*`, `jobs.*`, `calibration.*`, `scene.*`, `editing.*`, and `export.*`. `development.load_demo` is deliberately marked non-public and exercises an evidence-backed end-to-end fixture.

## Reconstruction adapter boundary

Production camera and dense reconstruction belongs behind stages `sparse` and `dense`. Development builds report missing native capabilities and pause with a recoverable event; they do not fabricate a successful reconstruction. Future adapters must write checkpoint artifacts before marking a stage complete and must use original frames for material evidence even when normalized frames are used for camera matching.

## Export compatibility

The repository catalog pins the tested Java `DataVersion` and Litematic format/subversion. Export uses air at palette index zero, x-fastest/y-outermost ordering, cross-long bit packing, one trimmed `Reconstruction` region, and empty entity/tick lists. It is parsed and checked before atomic rename. A later release gate must additionally round-trip through `litemapy` and load every catalog fixture in matching Litematica versions.
