# Substance Texture Auto-Hookup

Blender add-on that groups Substance Painter texture exports by material name and wires
BaseColor / Metallic / Roughness / Normal into a Principled BSDF.

## Install

**Blender 4.2+ (drag & drop)** — drag `dist/substance_texture_hookup-1.1.0.zip` from Explorer
onto the Blender window and confirm the install dialog.

**Blender 3.3 – 4.1** — `Edit > Preferences > Add-ons > Install...` and pick
`dist/substance_texture_hookup-1.1.0-legacy.zip` (or `dist/substance_texture_hookup.py`),
then enable *Substance Texture Auto-Hookup*.

The panel lives in `View3D > Sidebar (N) > Substance Hookup`.

## Usage

1. **Select Substance Textures** — multi-select the exported files. Filenames are parsed as
   `MaterialName_Suffix.ext`; the material part may contain underscores.
2. Each detected group shows a checkbox per map. **All maps are checked by default** —
   uncheck any you don't want wired.
3. Pick a target material (`prop_search` dropdown), or `+` to create one named after the group.
4. **Apply**.

Recognized suffixes (case-insensitive): `BaseColor`, `Base_Color`, `Albedo`, `Diffuse`, `Color`,
`Metallic`, `Metalness`, `Metal`, `Roughness`, `Rough`, `Normal`, `NormalOpenGL`, `NormalDirectX`,
`nrm`, and a few short aliases. Anything else (Height, AO, Opacity, …) is ignored.

## Behavior notes

- BaseColor is loaded as sRGB; Metallic, Roughness and Normal as Non-Color.
- Normal maps route through a Normal Map node with an adjustable strength. Setting
  *Space* to **DirectX** inserts a green-channel inversion chain.
- **Replace Previous Nodes** (Options) removes nodes a previous run created for the same
  group before rewiring, so re-applying does not stack duplicates.
- Missing files are reported and skipped rather than aborting the run.

## Per-file memory

All state — detected groups, per-map checkboxes, target materials, interpolation, normal
settings, last browsed directory and the Options defaults — lives on `Scene.sh_settings`, so it
is saved inside the `.blend` and restored on reopen. Re-running the file selector preserves the
settings of any group whose name is detected again.

## Build

```bash
python build.py
```

Compiles `src/substance_texture_hookup/__init__.py` as a syntax check and writes the three
artifacts into `dist/`.
