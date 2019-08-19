import bpy
import os
import mathutils

from bpy_extras.io_utils import (
        ImportHelper,
        ExportHelper,
        orientation_helper,
        path_reference_mode,
        axis_conversion,
        )

from bpy.props import (
        StringProperty,
        BoolProperty,
        FloatProperty,
        EnumProperty,
        )

@orientation_helper(axis_forward='-Z', axis_up='Y')
class exportObj_OT_Operator(bpy.types.Operator, ExportHelper):
    bl_idname = "view3d.export_to_ue4"
    bl_label = "Export with adjusted Origin to UE4"
    bl_options = {'UNDO', 'PRESET'}
    bl_description = "Moves selected Object to 0,0,0 and calls the FBX exporter. On successful Export it will return the Object to its original position."

    filename_ext = ".fbx"
    filter_glob: StringProperty(default="*.fbx", options={'HIDDEN'})

    # Lots of standard Blender code so we can provide the original File-Save Dialog
    ui_tab: EnumProperty(
            items=(('MAIN', "Main", "Main basic settings"),
                   ('GEOMETRY', "Geometries", "Geometry-related settings"),
                   ('ARMATURE', "Armatures", "Armature-related settings"),
                   ('ANIMATION', "Animation", "Animation-related settings"),
                   ),
            name="ui_tab",
            description="Export options categories",
            )

    use_selection: BoolProperty(
            name="Selected Objects",
            description="Export selected and visible objects only",
            default=True,
            )
    use_active_collection: BoolProperty(
            name="Active Collection",
            description="Export only objects from the active collection (and its children)",
            default=False,
            )
    global_scale: FloatProperty(
            name="Scale",
            description="Scale all data (Some importers do not support scaled armatures!)",
            min=0.001, max=1000.0,
            soft_min=0.01, soft_max=1000.0,
            default=1.0,
            )
    apply_unit_scale: BoolProperty(
            name="Apply Unit",
            description="Take into account current Blender units settings (if unset, raw Blender Units values are used as-is)",
            default=True,
            )
    apply_scale_options: EnumProperty(
            items=(('FBX_SCALE_NONE', "All Local",
                    "Apply custom scaling and units scaling to each object transformation, FBX scale remains at 1.0"),
                   ('FBX_SCALE_UNITS', "FBX Units Scale",
                    "Apply custom scaling to each object transformation, and units scaling to FBX scale"),
                   ('FBX_SCALE_CUSTOM', "FBX Custom Scale",
                    "Apply custom scaling to FBX scale, and units scaling to each object transformation"),
                   ('FBX_SCALE_ALL', "FBX All",
                    "Apply custom scaling and units scaling to FBX scale"),
                   ),
            name="Apply Scalings",
            description="How to apply custom and units scalings in generated FBX file "
                        "(Blender uses FBX scale to detect units on import, "
                        "but many other applications do not handle the same way)",
            )
    bake_space_transform: BoolProperty(
            name="!EXPERIMENTAL! Apply Transform",
            description="Bake space transform into object data, avoids getting unwanted rotations to objects when "
                        "target space is not aligned with Blender's space "
                        "(WARNING! experimental option, use at own risks, known broken with armatures/animations)",
            default=False,
            )

    object_types: EnumProperty(
            name="Object Types",
            options={'ENUM_FLAG'},
            items=(('EMPTY', "Empty", ""),
                   ('CAMERA', "Camera", ""),
                   ('LIGHT', "Lamp", ""),
                   ('ARMATURE', "Armature", "WARNING: not supported in dupli/group instances"),
                   ('MESH', "Mesh", ""),
                   ('OTHER', "Other", "Other geometry types, like curve, metaball, etc. (converted to meshes)"),
                   ),
            description="Which kind of object to export",
            default={'EMPTY', 'CAMERA', 'LIGHT', 'ARMATURE', 'MESH', 'OTHER'},
            )

    use_mesh_modifiers: BoolProperty(
            name="Apply Modifiers",
            description="Apply modifiers to mesh objects (except Armature ones) - "
                        "WARNING: prevents exporting shape keys",
            default=True,
            )
    use_mesh_modifiers_render: BoolProperty(
            name="Use Modifiers Render Setting",
            description="Use render settings when applying modifiers to mesh objects (DISABLED in Blender 2.8)",
            default=True,
            )
    mesh_smooth_type: EnumProperty(
            name="Smoothing",
            items=(('OFF', "Normals Only", "Export only normals instead of writing edge or face smoothing data"),
                   ('FACE', "Face", "Write face smoothing"),
                   ('EDGE', "Edge", "Write edge smoothing"),
                   ),
            description="Export smoothing information "
                        "(prefer 'Normals Only' option if your target importer understand split normals)",
            default='OFF',
            )
    use_mesh_edges: BoolProperty(
            name="Loose Edges",
            description="Export loose edges (as two-vertices polygons)",
            default=False,
            )
    use_tspace: BoolProperty(
            name="Tangent Space",
            description="Add binormal and tangent vectors, together with normal they form the tangent space "
                        "(will only work correctly with tris/quads only meshes!)",
            default=False,
            )
    use_custom_props: BoolProperty(
            name="Custom Properties",
            description="Export custom properties",
            default=False,
            )
    add_leaf_bones: BoolProperty(
            name="Add Leaf Bones",
            description="Append a final bone to the end of each chain to specify last bone length "
                        "(use this when you intend to edit the armature from exported data)",
            default=True # False for commit!
            )
    primary_bone_axis: EnumProperty(
            name="Primary Bone Axis",
            items=(('X', "X Axis", ""),
                   ('Y', "Y Axis", ""),
                   ('Z', "Z Axis", ""),
                   ('-X', "-X Axis", ""),
                   ('-Y', "-Y Axis", ""),
                   ('-Z', "-Z Axis", ""),
                   ),
            default='Y',
            )
    secondary_bone_axis: EnumProperty(
            name="Secondary Bone Axis",
            items=(('X', "X Axis", ""),
                   ('Y', "Y Axis", ""),
                   ('Z', "Z Axis", ""),
                   ('-X', "-X Axis", ""),
                   ('-Y', "-Y Axis", ""),
                   ('-Z', "-Z Axis", ""),
                   ),
            default='X',
            )
    use_armature_deform_only: BoolProperty(
            name="Only Deform Bones",
            description="Only write deforming bones (and non-deforming ones when they have deforming children)",
            default=False,
            )
    armature_nodetype: EnumProperty(
            name="Armature FBXNode Type",
            items=(('NULL', "Null", "'Null' FBX node, similar to Blender's Empty (default)"),
                   ('ROOT', "Root", "'Root' FBX node, supposed to be the root of chains of bones..."),
                   ('LIMBNODE', "LimbNode", "'LimbNode' FBX node, a regular joint between two bones..."),
                  ),
            description="FBX type of node (object) used to represent Blender's armatures "
                        "(use Null one unless you experience issues with other app, other choices may no import back "
                        "perfectly in Blender...)",
            default='NULL',
            )
    bake_anim: BoolProperty(
            name="Baked Animation",
            description="Export baked keyframe animation",
            default=True,
            )
    bake_anim_use_all_bones: BoolProperty(
            name="Key All Bones",
            description="Force exporting at least one key of animation for all bones "
                        "(needed with some target applications, like UE4)",
            default=True,
            )
    bake_anim_use_nla_strips: BoolProperty(
            name="NLA Strips",
            description="Export each non-muted NLA strip as a separated FBX's AnimStack, if any, "
                        "instead of global scene animation",
            default=True,
            )
    bake_anim_use_all_actions: BoolProperty(
            name="All Actions",
            description="Export each action as a separated FBX's AnimStack, instead of global scene animation "
                        "(note that animated objects will get all actions compatible with them, "
                        "others will get no animation at all)",
            default=True,
            )
    bake_anim_force_startend_keying: BoolProperty(
            name="Force Start/End Keying",
            description="Always add a keyframe at start and end of actions for animated channels",
            default=True,
            )
    bake_anim_step: FloatProperty(
            name="Sampling Rate",
            description="How often to evaluate animated values (in frames)",
            min=0.01, max=100.0,
            soft_min=0.1, soft_max=10.0,
            default=1.0,
            )
    bake_anim_simplify_factor: FloatProperty(
            name="Simplify",
            description="How much to simplify baked values (0.0 to disable, the higher the more simplified)",
            min=0.0, max=100.0,  # No simplification to up to 10% of current magnitude tolerance.
            soft_min=0.0, soft_max=10.0,
            default=1.0,  # default: min slope: 0.005, max frame step: 10.
            )
    path_mode: path_reference_mode
    embed_textures: BoolProperty(
            name="Embed Textures",
            description="Embed textures in FBX binary file (only for \"Copy\" path mode!)",
            default=False,
            )
    batch_mode: EnumProperty(
            name="Batch Mode",
            items=(('OFF', "Off", "Active scene to file"),
                   ('SCENE', "Scene", "Each scene as a file"),
                   ('COLLECTION', "Collection",
                    "Each collection (data-block ones) as a file, does not include content of children collections"),
                   ('SCENE_COLLECTION', "Scene Collections",
                    "Each collection (including master, non-data-block ones) of each scene as a file, "
                    "including content from children collections"),
                   ('ACTIVE_SCENE_COLLECTION', "Active Scene Collections",
                    "Each collection (including master, non-data-block one) of the active scene as a file, "
                    "including content from children collections"),
                   ),
            )
    use_batch_own_dir: BoolProperty(
            name="Batch Own Dir",
            description="Create a dir for each exported file",
            default=True,
            )
    use_metadata: BoolProperty(
            name="Use Metadata",
            default=True,
            options={'HIDDEN'},
            )
    
    # To make it look pretty
    def draw(self, context):
        layout = self.layout

        layout.prop(self, "ui_tab", expand=True)
        if self.ui_tab == 'MAIN':
            layout.prop(self, "use_selection")
            layout.prop(self, "use_active_collection")

            col = layout.column(align=True)
            row = col.row(align=True)
            row.prop(self, "global_scale")
            sub = row.row(align=True)
            sub.prop(self, "apply_unit_scale", text="", icon='NDOF_TRANS')
            col.prop(self, "apply_scale_options")

            layout.prop(self, "axis_forward")
            layout.prop(self, "axis_up")

            layout.separator()
            layout.prop(self, "object_types")
            layout.prop(self, "bake_space_transform")
            layout.prop(self, "use_custom_props")

            layout.separator()
            row = layout.row(align=True)
            row.prop(self, "path_mode")
            sub = row.row(align=True)
            sub.enabled = (self.path_mode == 'COPY')
            sub.prop(self, "embed_textures", text="", icon='PACKAGE' if self.embed_textures else 'UGLYPACKAGE')
            row = layout.row(align=True)
            row.prop(self, "batch_mode")
            sub = row.row(align=True)
            sub.prop(self, "use_batch_own_dir", text="", icon='NEWFOLDER')
        elif self.ui_tab == 'GEOMETRY':
            layout.prop(self, "use_mesh_modifiers")
            sub = layout.row()
            sub.enabled = self.use_mesh_modifiers and False  # disabled in 2.8...
            sub.prop(self, "use_mesh_modifiers_render")
            layout.prop(self, "mesh_smooth_type")
            layout.prop(self, "use_mesh_edges")
            sub = layout.row()
            #~ sub.enabled = self.mesh_smooth_type in {'OFF'}
            sub.prop(self, "use_tspace")
        elif self.ui_tab == 'ARMATURE':
            layout.prop(self, "use_armature_deform_only")
            layout.prop(self, "add_leaf_bones")
            layout.prop(self, "primary_bone_axis")
            layout.prop(self, "secondary_bone_axis")
            layout.prop(self, "armature_nodetype")
        elif self.ui_tab == 'ANIMATION':
            layout.prop(self, "bake_anim")
            col = layout.column()
            col.enabled = self.bake_anim
            col.prop(self, "bake_anim_use_all_bones")
            col.prop(self, "bake_anim_use_nla_strips")
            col.prop(self, "bake_anim_use_all_actions")
            col.prop(self, "bake_anim_force_startend_keying")
            col.prop(self, "bake_anim_step")
            col.prop(self, "bake_anim_simplify_factor")


    def execute(self, context):

        #Get selected Object
        selected_object = bpy.context.active_object

        #Store original position
        position = selected_object.matrix_world.to_translation()

        #Move Object to Origin
        selected_object.location = mathutils.Vector((0.0,0.0,0.0))

        #Open File save dialog
        bpy.ops.export_scene.fbx(filepath=self.filepath, 
                check_existing=self.check_existing, 
                filter_glob=self.filter_glob, 
                ui_tab=self.ui_tab, 
                use_selection=self.use_selection, 
                use_active_collection=self.use_active_collection, 
                global_scale=self.global_scale, 
                apply_unit_scale=self.apply_unit_scale, 
                apply_scale_options=self.apply_scale_options, 
                bake_space_transform=self.bake_space_transform, 
                object_types=self.object_types, 
                use_mesh_modifiers=self.use_mesh_modifiers, 
                use_mesh_modifiers_render=self.use_mesh_modifiers_render, 
                mesh_smooth_type=self.mesh_smooth_type, 
                use_mesh_edges=self.use_mesh_edges, 
                use_tspace=self.use_tspace, 
                use_custom_props=self.use_custom_props, 
                add_leaf_bones=self.add_leaf_bones, 
                primary_bone_axis=self.primary_bone_axis, 
                secondary_bone_axis=self.secondary_bone_axis, 
                use_armature_deform_only=self.use_armature_deform_only, 
                armature_nodetype=self.armature_nodetype, 
                bake_anim=self.bake_anim, 
                bake_anim_use_all_bones=self.bake_anim_use_all_bones, 
                bake_anim_use_nla_strips=self.bake_anim_use_nla_strips, 
                bake_anim_use_all_actions=self.bake_anim_use_all_actions, 
                bake_anim_force_startend_keying=self.bake_anim_force_startend_keying, 
                bake_anim_step=self.bake_anim_step, 
                bake_anim_simplify_factor=self.bake_anim_simplify_factor, 
                path_mode=self.path_mode, 
                embed_textures=self.embed_textures, 
                batch_mode=self.batch_mode, 
                use_batch_own_dir=self.use_batch_own_dir, 
                use_metadata=self.use_metadata, 
                axis_forward=self.axis_forward, 
                axis_up=self.axis_up)

        # Reset Position
        selected_object.location = position
        return {'FINISHED'}