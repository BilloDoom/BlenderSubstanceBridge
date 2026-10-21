"""Run with: blender --background --factory-startup --python tests/test_collection_export.py"""

import os
import sys
import tempfile
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
TEST_TEMP_ROOT = ROOT / ".test_tmp"
TEST_TEMP_ROOT.mkdir(exist_ok=True)

import substance_texture_hookup as addon


def add_mesh(name, collection):
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(
        [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)],
        [],
        [(0, 1, 2)],
    )
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    return obj


assert addon.safe_export_name('Stone:Wall/Panel') == "Stone_Wall_Panel"

addon.register()
try:
    scene = bpy.context.scene
    assert bpy.data.filepath == ""
    assert bpy.ops.sh.add_group() == {'FINISHED'}
    assert bpy.ops.sh.add_group() == {'FINISHED'}
    assert [group.group_name for group in scene.sh_settings.groups] == [
        "New Group",
        "New Group 2",
    ]
    material = bpy.data.materials.new("Stone Material")
    scene.sh_settings.groups[0].target_material = material.name
    assert scene.sh_settings.groups[0].group_name == material.name
    assert addon.resolve_export_directory(scene.sh_settings.groups[0]) == ""
    scene.sh_settings.groups.clear()

    high = bpy.data.collections.new("Stone High")
    high_child = bpy.data.collections.new("Stone High Detail")
    low = bpy.data.collections.new("Stone Low")
    scene.collection.children.link(high)
    high.children.link(high_child)
    scene.collection.children.link(low)

    high_object = add_mesh("HighObject", high_child)
    low_object = add_mesh("LowObject", low)
    unrelated = add_mesh("Unrelated", scene.collection)
    high.hide_viewport = True
    unrelated.select_set(True)
    scene.view_layers[0].objects.active = unrelated
    selected_before = list(bpy.context.selected_objects)

    with tempfile.TemporaryDirectory(
        prefix="substance_hookup_export_test_", dir=TEST_TEMP_ROOT
    ) as directory:
        blend_path = os.path.join(directory, "collection_export_test.blend")
        bpy.context.preferences.filepaths.file_preview_type = 'NONE'
        bpy.ops.wm.save_as_mainfile(filepath=blend_path)

        group = scene.sh_settings.groups.add()
        group.group_name = "Stone"
        group.high_collection = high
        group.low_collection = low
        group.export_directory = ""
        assert addon.resolve_export_directory(group) == directory

        result = bpy.ops.sh.export_collection(group_index=0, export_role='BOTH')
        assert result == {'FINISHED'}

        high_path = os.path.join(directory, "Stone_hp.fbx")
        low_path = os.path.join(directory, "Stone_lp.fbx")
        assert os.path.getsize(high_path) > 1000
        assert os.path.getsize(low_path) > 1000
        high_data = Path(high_path).read_bytes()
        low_data = Path(low_path).read_bytes()
        assert b"HighObject" in high_data
        assert b"LowObject" not in high_data
        assert b"Unrelated" not in high_data
        assert b"LowObject" in low_data
        assert b"HighObject" not in low_data
        assert b"Unrelated" not in low_data
        assert addon.collection_mesh_objects(high) == [high_object]
        assert addon.collection_mesh_objects(low) == [low_object]
        assert list(bpy.context.selected_objects) == selected_before
        assert scene.view_layers[0].objects.active == unrelated

        scene.sh_settings.export_extension = 'OBJ'
        result = bpy.ops.sh.export_collection(group_index=0, export_role='HP')
        assert result == {'FINISHED'}
        obj_path = os.path.join(directory, "Stone_hp.obj")
        obj_data = Path(obj_path).read_text(encoding="utf-8")
        assert "HighObject" in obj_data
        assert "LowObject" not in obj_data
        assert "Unrelated" not in obj_data
finally:
    addon.unregister()

print("Collection export tests passed")
