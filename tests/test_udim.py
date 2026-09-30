"""Run with: blender --background --factory-startup --python tests/test_udim.py"""

import os
import sys
import tempfile
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import substance_texture_hookup as addon


def create_tile(filepath, color):
    image = bpy.data.images.new(Path(filepath).stem, width=2, height=2)
    image.generated_color = color
    image.filepath_raw = filepath
    image.file_format = 'PNG'
    image.save()
    bpy.data.images.remove(image)


assert addon.classify_filename("Stone_BaseColor.png") == ("Stone", "BaseColor")
assert addon.classify_filename("Stone_BaseColor.1001.png") == ("Stone", "BaseColor")
assert addon.classify_filename("Stone_NormalOpenGL.1012.exr") == ("Stone", "Normal")
assert addon.classify_filename("Stone_BaseColor.0999.png") is None
assert addon.classify_filename("Stone_Height.1001.png") is None
assert addon.udim_filepath("/textures/Stone_BaseColor.1002.png").endswith(
    "/textures/Stone_BaseColor.<UDIM>.png"
)

with tempfile.TemporaryDirectory(prefix="substance_hookup_udim_test_") as directory:
    for tile, color in ((1001, (1.0, 0.0, 0.0, 1.0)), (1002, (0.0, 1.0, 0.0, 1.0))):
        create_tile(
            os.path.join(directory, "Stone_BaseColor.%d.png" % tile),
            color,
        )

    filepath = os.path.join(directory, "Stone_BaseColor.<UDIM>.png")
    assert [number for number, _path in addon.find_udim_tiles(filepath)] == [1001, 1002]
    image = addon.load_image(filepath)
    assert image.source == 'TILED'
    assert image.filepath.endswith("Stone_BaseColor.<UDIM>.png")
    assert [tile.number for tile in image.tiles] == [1001, 1002]

    addon.register()
    try:
        group = bpy.context.scene.sh_settings.groups.add()
        group.group_name = "Stone"
        entry = group.textures.add()
        entry.map_kind = "BaseColor"
        entry.filepath = filepath

        material = bpy.data.materials.new("Stone")
        connected, missing = addon.wire_group_to_material(group, material, True)
        assert connected == ["BaseColor"]
        assert missing == []

        image_nodes = [node for node in material.node_tree.nodes if node.type == 'TEX_IMAGE']
        assert len(image_nodes) == 1
        assert image_nodes[0].image == image
        assert image_nodes[0].image.source == 'TILED'
    finally:
        addon.unregister()

print("UDIM tests passed")
