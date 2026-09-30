bl_info = {
    "name": "Substance Texture Auto-Hookup",
    "author": "BilloDoom",
    "version": (1, 2, 0),
    "blender": (3, 3, 0),
    "location": "View3D > Sidebar > Substance Hookup",
    "description": "Auto-connect Substance Painter BaseColor/Metallic/Roughness/Normal maps to materials",
    "category": "Material",
}

import os
import re

import bpy
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
)
from bpy.types import Operator, Panel, PropertyGroup
from bpy_extras.io_utils import ImportHelper

MAP_KINDS = ("BaseColor", "Metallic", "Roughness", "Normal")

MAP_SUFFIX_ALIASES = {
    "basecolor": "BaseColor",
    "base_color": "BaseColor",
    "basecolour": "BaseColor",
    "base_colour": "BaseColor",
    "albedo": "BaseColor",
    "diffuse": "BaseColor",
    "diff": "BaseColor",
    "color": "BaseColor",
    "col": "BaseColor",
    "metallic": "Metallic",
    "metalness": "Metallic",
    "metallness": "Metallic",
    "metal": "Metallic",
    "mtl": "Metallic",
    "roughness": "Roughness",
    "rough": "Roughness",
    "rgh": "Roughness",
    "normal": "Normal",
    "normalmap": "Normal",
    "normal_map": "Normal",
    "normalgl": "Normal",
    "normal_gl": "Normal",
    "normalopengl": "Normal",
    "normal_opengl": "Normal",
    "normaldx": "Normal",
    "normal_dx": "Normal",
    "normaldirectx": "Normal",
    "normal_directx": "Normal",
    "nrm": "Normal",
    "nor": "Normal",
}

MAP_SOCKETS = {
    "BaseColor": "Base Color",
    "Metallic": "Metallic",
    "Roughness": "Roughness",
    "Normal": "Normal",
}

MAP_LAYOUT_Y = {
    "BaseColor": 340,
    "Metallic": 40,
    "Roughness": -260,
    "Normal": -560,
}

NON_COLOR_KINDS = ("Metallic", "Roughness", "Normal")

NODE_TAG = "sh_hookup_group"

_SUFFIX_RE = re.compile(
    r"^(?P<base>.+?)[_\-\s]+(?P<suffix>(?:%s))$"
    % "|".join(
        re.escape(key)
        for key in sorted(MAP_SUFFIX_ALIASES, key=len, reverse=True)
    ),
    re.IGNORECASE,
)

UDIM_TOKEN = "<UDIM>"

INTERPOLATION_ITEMS = [
    ('Linear', "Linear", "Smooth interpolation"),
    ('Closest', "Closest", "No interpolation, sharp pixels"),
    ('Cubic', "Cubic", "Smoother than linear, slower"),
    ('Smart', "Smart", "Bicubic for magnification, box for minification"),
]

NORMAL_SPACE_ITEMS = [
    ('OPENGL', "OpenGL", "Use the normal map as exported (Y+)"),
    ('DIRECTX', "DirectX", "Flip the green channel to convert DirectX (Y-) to OpenGL"),
]


def split_udim_filename(filename):
    """Return the texture stem and an optional UDIM tile number."""
    name = os.path.splitext(filename)[0]
    stem, separator, tile_text = name.rpartition(".")
    if separator and len(tile_text) == 4 and tile_text.isdigit():
        tile_number = int(tile_text)
        if tile_number >= 1001:
            return stem, tile_number
    return name, None


def classify_filename(filename):
    name, _tile_number = split_udim_filename(filename)
    match = _SUFFIX_RE.match(name)
    if not match:
        return None
    map_kind = MAP_SUFFIX_ALIASES.get(match.group("suffix").lower())
    if map_kind is None:
        return None
    return match.group("base"), map_kind


def udim_filepath(filepath):
    """Replace a recognized .1001-style tile number with Blender's token."""
    filename = os.path.basename(filepath)
    _stem, tile_number = split_udim_filename(filename)
    if tile_number is None:
        return filepath

    root, extension = os.path.splitext(filepath)
    root = root.rsplit(".", 1)[0]
    return "%s.%s%s" % (root, UDIM_TOKEN, extension)


def is_udim_filepath(filepath):
    return UDIM_TOKEN in os.path.basename(filepath)


def find_udim_tiles(filepath):
    """Find the on-disk tiles represented by a <UDIM> filepath."""
    normalized = bpy.path.abspath(filepath)
    directory = os.path.dirname(normalized)
    filename = os.path.basename(normalized)
    if UDIM_TOKEN not in filename:
        return []

    prefix, suffix = filename.split(UDIM_TOKEN, 1)
    pattern = re.compile(
        r"^%s(?P<tile>\d{4})%s$" % (re.escape(prefix), re.escape(suffix))
    )

    try:
        filenames = os.listdir(directory)
    except OSError:
        return []

    tiles = []
    for candidate in filenames:
        match = pattern.match(candidate)
        if not match:
            continue
        tile_number = int(match.group("tile"))
        if tile_number >= 1001:
            tiles.append((tile_number, os.path.join(directory, candidate)))
    return sorted(tiles)


def texture_filepath_exists(filepath):
    if is_udim_filepath(filepath):
        return bool(find_udim_tiles(filepath))
    return os.path.exists(bpy.path.abspath(filepath))


def find_best_material_match(name):
    name_lower = name.lower()
    exact = bpy.data.materials.get(name)
    if exact:
        return exact
    for mat in bpy.data.materials:
        if mat.name.lower() == name_lower:
            return mat
    for mat in bpy.data.materials:
        other = mat.name.lower()
        if name_lower in other or other in name_lower:
            return mat
    return None


class SH_TextureEntry(PropertyGroup):
    map_kind: StringProperty()
    filepath: StringProperty(subtype='FILE_PATH')
    enabled: BoolProperty(
        name="Use",
        description="Include this map when applying the hookup",
        default=True,
    )


class SH_MaterialGroup(PropertyGroup):
    group_name: StringProperty(name="Detected Name")
    textures: CollectionProperty(type=SH_TextureEntry)
    target_material: StringProperty(name="Target Material")
    expanded: BoolProperty(default=True)
    interpolation: EnumProperty(
        name="Interpolation",
        description="Image texture interpolation applied to every map in this group",
        items=INTERPOLATION_ITEMS,
        default='Linear',
    )
    normal_space: EnumProperty(
        name="Normal Space",
        description="Tangent space convention of the normal map",
        items=NORMAL_SPACE_ITEMS,
        default='OPENGL',
    )
    normal_strength: FloatProperty(
        name="Normal Strength",
        description="Strength value set on the Normal Map node",
        default=1.0,
        min=0.0,
        soft_max=2.0,
    )

    def get_entry(self, map_kind):
        for entry in self.textures:
            if entry.map_kind == map_kind:
                return entry
        return None


class SH_Settings(PropertyGroup):
    groups: CollectionProperty(type=SH_MaterialGroup)
    active_index: IntProperty(default=0)
    last_directory: StringProperty(subtype='DIR_PATH')
    default_interpolation: EnumProperty(
        name="Default Interpolation",
        description="Interpolation assigned to newly detected groups",
        items=INTERPOLATION_ITEMS,
        default='Linear',
    )
    default_normal_space: EnumProperty(
        name="Default Normal Space",
        description="Normal space assigned to newly detected groups",
        items=NORMAL_SPACE_ITEMS,
        default='OPENGL',
    )
    auto_match_materials: BoolProperty(
        name="Auto Match Materials",
        description="Guess a target material by name when textures are imported",
        default=True,
    )
    replace_existing: BoolProperty(
        name="Replace Previous Nodes",
        description="Remove nodes created by an earlier run of this add-on before wiring",
        default=True,
    )
    show_options: BoolProperty(name="Options", default=False)


def snapshot_settings(settings):
    state = {}
    for grp in settings.groups:
        state[grp.group_name] = {
            "target_material": grp.target_material,
            "interpolation": grp.interpolation,
            "normal_space": grp.normal_space,
            "normal_strength": grp.normal_strength,
            "expanded": grp.expanded,
            "enabled": {entry.map_kind: entry.enabled for entry in grp.textures},
        }
    return state


def restore_group(grp, state):
    grp.target_material = state["target_material"]
    grp.interpolation = state["interpolation"]
    grp.normal_space = state["normal_space"]
    grp.normal_strength = state["normal_strength"]
    grp.expanded = state["expanded"]


class SH_OT_SelectTextures(Operator, ImportHelper):
    bl_idname = "sh.select_textures"
    bl_label = "Select Substance Textures"
    bl_description = "Select exported texture files (BaseColor/Metallic/Roughness/Normal)"
    bl_options = {'REGISTER', 'UNDO'}

    filter_glob: StringProperty(
        default="*.png;*.jpg;*.jpeg;*.tif;*.tiff;*.exr;*.tga;*.bmp;*.webp",
        options={'HIDDEN'},
    )
    files: CollectionProperty(type=bpy.types.OperatorFileListElement)
    directory: StringProperty(subtype='DIR_PATH')

    def invoke(self, context, event):
        settings = context.scene.sh_settings
        if settings.last_directory:
            self.directory = settings.last_directory
            self.filepath = settings.last_directory
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        settings = context.scene.sh_settings
        previous = snapshot_settings(settings)

        detected = {}
        skipped = 0

        for item in self.files:
            result = classify_filename(item.name)
            if result is None:
                skipped += 1
                continue
            mat_name, map_kind = result
            filepath = udim_filepath(os.path.join(self.directory, item.name))
            maps = detected.setdefault(mat_name, {})
            previous_filepath = maps.get(map_kind)
            if previous_filepath is None or is_udim_filepath(filepath):
                maps[map_kind] = filepath

        if not detected:
            self.report({'WARNING'}, "No BaseColor/Metallic/Roughness/Normal textures recognized.")
            return {'CANCELLED'}

        settings.groups.clear()
        settings.last_directory = self.directory

        for mat_name in sorted(detected):
            grp = settings.groups.add()
            grp.group_name = mat_name
            grp.interpolation = settings.default_interpolation
            grp.normal_space = settings.default_normal_space

            state = previous.get(mat_name)
            if state:
                restore_group(grp, state)
            elif settings.auto_match_materials:
                guess = find_best_material_match(mat_name)
                grp.target_material = guess.name if guess else ""

            for map_kind in MAP_KINDS:
                filepath = detected[mat_name].get(map_kind)
                if filepath is None:
                    continue
                entry = grp.textures.add()
                entry.map_kind = map_kind
                entry.filepath = filepath
                if state:
                    entry.enabled = state["enabled"].get(map_kind, True)

        message = "Detected %d material group(s)." % len(detected)
        if skipped:
            message += " Ignored %d unrecognized file(s)." % skipped
        self.report({'INFO'}, message)
        return {'FINISHED'}


class SH_OT_AutoMatch(Operator):
    bl_idname = "sh.auto_match"
    bl_label = "Auto Match Materials"
    bl_description = "Guess a target material for every group by name"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        matched = 0
        for grp in context.scene.sh_settings.groups:
            guess = find_best_material_match(grp.group_name)
            if guess:
                grp.target_material = guess.name
                matched += 1
        self.report({'INFO'}, "Matched %d group(s)." % matched)
        return {'FINISHED'}


class SH_OT_NewMaterial(Operator):
    bl_idname = "sh.new_material"
    bl_label = "New Material"
    bl_description = "Create a material named after this group and assign it"
    bl_options = {'REGISTER', 'UNDO'}

    group_index: IntProperty()

    def execute(self, context):
        settings = context.scene.sh_settings
        if not 0 <= self.group_index < len(settings.groups):
            return {'CANCELLED'}
        grp = settings.groups[self.group_index]
        material = bpy.data.materials.new(name=grp.group_name)
        material.use_nodes = True
        grp.target_material = material.name
        self.report({'INFO'}, "Created material '%s'." % material.name)
        return {'FINISHED'}


class SH_OT_SetMaps(Operator):
    bl_idname = "sh.set_maps"
    bl_label = "Set Maps"
    bl_description = "Enable or disable maps"
    bl_options = {'REGISTER', 'UNDO'}

    enable: BoolProperty(default=True)
    group_index: IntProperty(default=-1)

    def execute(self, context):
        settings = context.scene.sh_settings
        if self.group_index >= 0:
            if not 0 <= self.group_index < len(settings.groups):
                return {'CANCELLED'}
            targets = [settings.groups[self.group_index]]
        else:
            targets = list(settings.groups)
        for grp in targets:
            for entry in grp.textures:
                entry.enabled = self.enable
        return {'FINISHED'}


class SH_OT_RemoveGroup(Operator):
    bl_idname = "sh.remove_group"
    bl_label = "Remove Group"
    bl_description = "Remove this group from the list"
    bl_options = {'REGISTER', 'UNDO'}

    group_index: IntProperty()

    def execute(self, context):
        settings = context.scene.sh_settings
        if not 0 <= self.group_index < len(settings.groups):
            return {'CANCELLED'}
        settings.groups.remove(self.group_index)
        return {'FINISHED'}


class SH_OT_ClearGroups(Operator):
    bl_idname = "sh.clear_groups"
    bl_label = "Clear List"
    bl_description = "Clear every detected texture group"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        context.scene.sh_settings.groups.clear()
        return {'FINISHED'}


def get_or_create_principled(material):
    if not material.use_nodes:
        material.use_nodes = True

    node_tree = material.node_tree

    for node in node_tree.nodes:
        if node.type == 'BSDF_PRINCIPLED':
            return node, node_tree

    bsdf = node_tree.nodes.new("ShaderNodeBsdfPrincipled")
    output = None
    for node in node_tree.nodes:
        if node.type == 'OUTPUT_MATERIAL':
            output = node
            break
    if output is None:
        output = node_tree.nodes.new("ShaderNodeOutputMaterial")
        output.location = (bsdf.location.x + 400, bsdf.location.y)
    node_tree.links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])
    return bsdf, node_tree


def remove_tagged_nodes(node_tree, group_name):
    for node in [n for n in node_tree.nodes if n.get(NODE_TAG) == group_name]:
        node_tree.nodes.remove(node)


def normalized_image_filepath(filepath):
    return os.path.normcase(os.path.normpath(bpy.path.abspath(filepath)))


def load_image(filepath):
    normalized = bpy.path.abspath(filepath)
    normalized_key = normalized_image_filepath(filepath)
    for image in bpy.data.images:
        if (
            image.filepath
            and normalized_image_filepath(image.filepath) == normalized_key
            and (not is_udim_filepath(filepath) or image.source == 'TILED')
        ):
            return image

    if is_udim_filepath(filepath):
        tiles = find_udim_tiles(filepath)
        if not tiles:
            raise RuntimeError(
                "No UDIM tiles found for '%s'." % os.path.basename(filepath)
            )

        first_tile = next(
            (path for number, path in tiles if number == 1001), tiles[0][1]
        )
        existing_images = set(bpy.data.images)
        result = bpy.ops.image.open(
            filepath=first_tile,
            directory=os.path.dirname(first_tile),
            files=[{"name": os.path.basename(first_tile)}],
            check_existing=False,
            relative_path=False,
            use_udim_detecting=True,
        )
        if 'FINISHED' not in result:
            raise RuntimeError(
                "Blender could not load UDIM tiles for '%s'."
                % os.path.basename(filepath)
            )

        for image in bpy.data.images:
            if (
                image.filepath
                and normalized_image_filepath(image.filepath) == normalized_key
                and image.source == 'TILED'
            ):
                return image

        created = [image for image in bpy.data.images if image not in existing_images]
        if len(created) == 1 and created[0].source == 'TILED':
            return created[0]
        raise RuntimeError(
            "Blender did not create a tiled image for '%s'."
            % os.path.basename(filepath)
        )

    return bpy.data.images.load(normalized, check_existing=True)


def add_image_node(node_tree, filepath, non_color, location, label, interpolation, group_name):
    node = node_tree.nodes.new("ShaderNodeTexImage")
    node.location = location
    node.label = label
    node.hide = False
    node[NODE_TAG] = group_name

    image = load_image(filepath)
    node.image = image
    node.interpolation = interpolation
    image.colorspace_settings.name = 'Non-Color' if non_color else 'sRGB'
    return node


def clear_input_links(node_tree, socket):
    for link in list(socket.links):
        node_tree.links.remove(link)


def wire_group_to_material(group, material, replace_existing):
    bsdf, node_tree = get_or_create_principled(material)

    if replace_existing:
        remove_tagged_nodes(node_tree, group.group_name)

    origin_x = bsdf.location.x - 500
    origin_y = bsdf.location.y
    connected = []
    missing = []

    for map_kind in MAP_KINDS:
        entry = group.get_entry(map_kind)
        if entry is None or not entry.enabled:
            continue

        socket_name = MAP_SOCKETS[map_kind]
        if socket_name not in bsdf.inputs:
            continue

        if not texture_filepath_exists(entry.filepath):
            missing.append(os.path.basename(entry.filepath))
            continue

        image_node = add_image_node(
            node_tree,
            entry.filepath,
            map_kind in NON_COLOR_KINDS,
            (origin_x, origin_y + MAP_LAYOUT_Y[map_kind]),
            "%s_%s" % (group.group_name, map_kind),
            group.interpolation,
            group.group_name,
        )

        target_input = bsdf.inputs[socket_name]
        clear_input_links(node_tree, target_input)

        if map_kind == "Normal":
            source = image_node.outputs["Color"]

            if group.normal_space == 'DIRECTX':
                image_node.location = (origin_x - 400, origin_y + MAP_LAYOUT_Y[map_kind])
                separate = node_tree.nodes.new("ShaderNodeSeparateColor")
                separate.location = (origin_x - 200, origin_y + MAP_LAYOUT_Y[map_kind])
                separate[NODE_TAG] = group.group_name
                invert = node_tree.nodes.new("ShaderNodeInvert")
                invert.location = (origin_x - 200, origin_y + MAP_LAYOUT_Y[map_kind] - 200)
                invert[NODE_TAG] = group.group_name
                combine = node_tree.nodes.new("ShaderNodeCombineColor")
                combine.location = (origin_x, origin_y + MAP_LAYOUT_Y[map_kind])
                combine[NODE_TAG] = group.group_name

                node_tree.links.new(image_node.outputs["Color"], separate.inputs[0])
                node_tree.links.new(separate.outputs[1], invert.inputs["Color"])
                node_tree.links.new(separate.outputs[0], combine.inputs[0])
                node_tree.links.new(invert.outputs["Color"], combine.inputs[1])
                node_tree.links.new(separate.outputs[2], combine.inputs[2])
                source = combine.outputs[0]

            normal_map = node_tree.nodes.new("ShaderNodeNormalMap")
            normal_map.location = (origin_x + 300, origin_y + MAP_LAYOUT_Y[map_kind])
            normal_map.inputs["Strength"].default_value = group.normal_strength
            normal_map[NODE_TAG] = group.group_name
            node_tree.links.new(source, normal_map.inputs["Color"])
            node_tree.links.new(normal_map.outputs["Normal"], target_input)
        else:
            node_tree.links.new(image_node.outputs["Color"], target_input)

        connected.append(map_kind)

    return connected, missing


class SH_OT_ApplyHookup(Operator):
    bl_idname = "sh.apply_hookup"
    bl_label = "Apply"
    bl_description = "Wire the checked maps into the assigned materials"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.sh_settings

        if not len(settings.groups):
            self.report({'WARNING'}, "No texture groups to apply. Select textures first.")
            return {'CANCELLED'}

        applied = 0
        warnings = []

        for grp in settings.groups:
            if not grp.target_material:
                warnings.append("'%s': no material assigned." % grp.group_name)
                continue

            material = bpy.data.materials.get(grp.target_material)
            if material is None:
                warnings.append(
                    "'%s': material '%s' not found." % (grp.group_name, grp.target_material)
                )
                continue

            if not any(entry.enabled for entry in grp.textures):
                warnings.append("'%s': every map is unchecked." % grp.group_name)
                continue

            try:
                connected, missing = wire_group_to_material(
                    grp, material, settings.replace_existing
                )
            except RuntimeError as exc:
                warnings.append("'%s': %s" % (grp.group_name, exc))
                continue

            if missing:
                warnings.append(
                    "'%s': missing file(s) %s." % (grp.group_name, ", ".join(missing))
                )

            if connected:
                applied += 1
            else:
                warnings.append("'%s': nothing connected." % grp.group_name)

        for warning in warnings:
            self.report({'WARNING'}, warning)

        if applied:
            self.report({'INFO'}, "Applied textures to %d material(s)." % applied)
            return {'FINISHED'}
        return {'CANCELLED'}


class SH_PT_MainPanel(Panel):
    bl_label = "Substance Hookup"
    bl_idname = "SH_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Substance Hookup"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.sh_settings

        layout.operator("sh.select_textures", icon='FILEBROWSER')

        header = layout.row()
        header.prop(
            settings,
            "show_options",
            icon='TRIA_DOWN' if settings.show_options else 'TRIA_RIGHT',
            emboss=False,
        )
        if settings.show_options:
            box = layout.box()
            col = box.column(align=True)
            col.prop(settings, "default_interpolation")
            col.prop(settings, "default_normal_space")
            col.prop(settings, "auto_match_materials")
            col.prop(settings, "replace_existing")

        if not len(settings.groups):
            layout.label(text="No textures selected yet.", icon='INFO')
            return

        layout.separator()

        row = layout.row(align=True)
        row.label(text="Groups (%d)" % len(settings.groups))
        row.operator("sh.auto_match", text="", icon='FILE_REFRESH')
        op = row.operator("sh.set_maps", text="", icon='CHECKBOX_HLT')
        op.enable = True
        op.group_index = -1
        op = row.operator("sh.set_maps", text="", icon='CHECKBOX_DEHLT')
        op.enable = False
        op.group_index = -1

        for index, grp in enumerate(settings.groups):
            box = layout.box()

            head = box.row(align=True)
            head.prop(
                grp,
                "expanded",
                text="",
                icon='TRIA_DOWN' if grp.expanded else 'TRIA_RIGHT',
                emboss=False,
            )
            head.label(text=grp.group_name, icon='MATERIAL')
            head.operator("sh.remove_group", text="", icon='X').group_index = index

            if not grp.expanded:
                continue

            col = box.column(align=True)
            grid = col.grid_flow(columns=2, even_columns=True, align=True)
            for map_kind in MAP_KINDS:
                entry = grp.get_entry(map_kind)
                if entry is None:
                    sub = grid.row()
                    sub.enabled = False
                    sub.label(text=map_kind, icon='BLANK1')
                else:
                    grid.prop(entry, "enabled", text=map_kind)

            col.separator()

            assign = col.row(align=True)
            assign.prop_search(
                grp, "target_material", bpy.data, "materials", text="", icon='MATERIAL'
            )
            assign.operator("sh.new_material", text="", icon='ADD').group_index = index

            col.prop(grp, "interpolation", text="Interp")

            normal_entry = grp.get_entry("Normal")
            if normal_entry is not None and normal_entry.enabled:
                col.prop(grp, "normal_space", text="Space")
                col.prop(grp, "normal_strength", text="Strength")

        layout.separator()
        row = layout.row(align=True)
        row.scale_y = 1.3
        row.operator("sh.apply_hookup", icon='NODETREE')
        row.operator("sh.clear_groups", text="", icon='TRASH')


classes = (
    SH_TextureEntry,
    SH_MaterialGroup,
    SH_Settings,
    SH_OT_SelectTextures,
    SH_OT_AutoMatch,
    SH_OT_NewMaterial,
    SH_OT_SetMaps,
    SH_OT_RemoveGroup,
    SH_OT_ClearGroups,
    SH_OT_ApplyHookup,
    SH_PT_MainPanel,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.sh_settings = PointerProperty(type=SH_Settings)


def unregister():
    if hasattr(bpy.types.Scene, "sh_settings"):
        del bpy.types.Scene.sh_settings
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
