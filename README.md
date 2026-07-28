# LiteMaptica

LiteMaptica is an Apple-Silicon-native desktop application for reconstructing evidenced Minecraft structures from video or ordered picture folders and exporting version-correct `.litematic` schematics. It is designed around a strict rule: unseen space is never invented.

This repository currently delivers the **Foundation vertical slice**:

- Tauri 2 + React + TypeScript desktop shell with a Three.js voxel viewer.
- Persistent JSON-RPC Python engine and matching headless CLI.
- Versioned `.litemap` project directories backed by SQLite.
- Separate automated proposals and transactional manual edit/undo layers.
- A signed-by-repository supported-version catalog and verified vanilla asset downloader.
- Deterministic Litematic NBT writing, bit packing, and round-trip validation.
- Checkpointed job state and explicit capability reports for media/reconstruction adapters.

The UI can create a project, import local video or a naturally filename-ordered JPG/PNG/WebP picture folder, inspect a sample evidence-backed reconstruction, paint/erase blocks, undo/redo, and export a validated schematic. Imported pictures are copied into the project and registered as source frames for the same camera and geometry stages used after video frame extraction. Camera reconstruction, dense geometry, and full vanilla surface solving are represented by stable contracts and capability-gated stages; they are not claimed complete until their packaged native binaries and golden compatibility corpus land.

## Development

Requirements: macOS 14+, Apple Silicon for the release target, Bun, Rust, and Python 3.11+.

```sh
bun install
bun run dev
```

In another terminal, exercise the engine directly:

```sh
PYTHONPATH=engine python3 -m litemap_engine.cli versions
PYTHONPATH=engine python3 -m litemap_engine.cli create /tmp/demo.litemap --name Demo --minecraft-version 26.2
PYTHONPATH=engine python3 -m litemap_engine.cli demo /tmp/demo.litemap
PYTHONPATH=engine python3 -m litemap_engine.cli export /tmp/demo.litemap /tmp/demo.litematic
```

Run all checks with `bun run check`. For the desktop application use `bun run tauri dev`.

## Project guarantees

Authoritative reconstruction, evidence, manual edits, and job checkpoints live in `project.sqlite3`; disposable caches are isolated under `cache/`. Every occupied automated voxel requires evidence rows. Export composes compatible manual edits over the automated layer, trims to one `Reconstruction` region, treats unknown cells as air, and validates the serialized NBT before returning success.

## Licensing and third-party components

LiteMaptica is GPL-3.0-only. See [LICENSE](LICENSE). Minecraft assets are not distributed with this repository. Users download the selected vanilla client from Mojang on demand and the engine verifies the hash published in Mojang's version manifest. Optional production builds may package FFmpeg, yt-dlp, COLMAP/OpenMVS, LightGlue/SuperPoint, and Depth Anything V2 subject to their respective licenses and notices.
