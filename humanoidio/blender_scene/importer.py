from typing import Callable, cast
import pathlib
import math
import bpy
import mathutils  # type: ignore
from .. import gltf
from .. import human_bones
from ..human_rig import humanoid_properties
from .mesh import create_mesh
from .armature import connect_bones


def convert_obj(src: gltf.Coordinate, dst: gltf.Coordinate, bl_obj: bpy.types.Object):
    if dst == gltf.Coordinate.BLENDER_ROTATE:
        if src == gltf.Coordinate.VRM0:
            bl_obj.rotation_euler = (math.pi * 0.5, 0, math.pi)
        elif src == gltf.Coordinate.VRM1:
            bl_obj.rotation_euler = (math.pi * 0.5, 0, 0)
        else:
            raise NotImplementedError()
    else:
        raise NotImplementedError()


def bl_traverse(bl_obj: bpy.types.Object, pred: Callable[[bpy.types.Object], None]):
    pred(bl_obj)

    for child in bl_obj.children:
        bl_traverse(child, pred)


def set_bone_weight(
    bl_object: bpy.types.Object, vert_idx: int, bone_name: str, weight_val: float
):
    if weight_val != 0.0:
        # It can be a problem to assign weights of 0
        # for bone index 0, if there is always 4 indices in joint_ tuple
        if bone_name:
            try:
                group = bl_object.vertex_groups[bone_name]
            except KeyError:
                group = bl_object.vertex_groups.new(name=bone_name)
            group.add((vert_idx,), weight_val, "ADD")


def build_unlit_shader(tree: bpy.types.NodeTree, image: bpy.types.Image | None):
    # clear
    nodes = tree.nodes
    for n in nodes:
        nodes.remove(n)
    links = tree.links
    # for l in links:
    #     print(l)
    #     links.remove(l)

    emission = tree.nodes.new(type="ShaderNodeEmission")
    output = nodes.new(type="ShaderNodeOutputMaterial")
    links.new(emission.outputs[0], output.inputs[0])

    if image:
        texture = cast(
            bpy.types.ShaderNodeTexImage, nodes.new(type="ShaderNodeTexImage")
        )
        texture.image = image
        links.new(texture.outputs[0], emission.inputs[0])


class Importer:
    def __init__(self, collection: bpy.types.Collection, conversion: gltf.Conversion):
        self.collection = collection
        self.conversion = conversion
        self.obj_map: dict[gltf.Node, bpy.types.Object] = {}
        self.mesh_map: dict[gltf.Mesh, bpy.types.Mesh] = {}
        self.skin_map: dict[gltf.Skin, bpy.types.Object] = {}
        self.materials: list[bpy.types.Material] = []

    def load(self, loader: gltf.Loader):
        textures: list[bpy.types.Image | None] = []
        for t in loader.textures:
            match t.data:
                case pathlib.Path():
                    if t.data.exists():
                        bl_image = bpy.data.images.load(
                            str(t.data), check_existing=True
                        )
                    else:
                        print(f"{t.data} not exists")
                        bl_image = bpy.data.images.new(t.data.name, width=2, height=2)
                    textures.append(bl_image)
                case gltf.TextureData() as data:
                    try:
                        from . import image_loader

                        w, h, raw = image_loader.load(data.mime, data.data)
                        bl_image = bpy.data.images.new(name=t.name, width=w, height=h)
                        bl_image.pixels = raw  # type: ignore
                        bl_image.update()
                        textures.append(bl_image)
                    except RuntimeError:
                        textures.append(None)

        # create materials
        for m in loader.materials:
            material = bpy.data.materials.new(m.name)
            material.use_nodes = True
            tree = material.node_tree

            build_unlit_shader(
                tree, textures[m.color_texture] if m.color_texture != None else None
            )
            # todo unlit and color texture
            self.materials.append(material)

        # create object for each node
        roots: list[bpy.types.Object] = []
        for root in loader.roots:
            bl_obj = self._create_tree(root)
            roots.append(bl_obj)

        # apply conversion
        self._apply_conversion(roots)

        if loader.vrm:
            # single skin humanoid model
            pass
        else:
            # non humanoid generic scene
            pass

        bl_humanoid_obj = self._create_humanoid(loader.roots)
        for root in roots:
            root.parent = bl_humanoid_obj

        bpy.ops.object.select_all(action="DESELECT")
        for n, o in self.obj_map.items():
            if o.type == "MESH" and n.skin:
                self._setup_skinning(n)

        # remove empties
        for root in loader.roots:
            self._remove_empty(root)

        for node in loader.nodes:
            if node.humanoid_bone:
                prop_name = humanoid_properties.prop_from_vrm(node.humanoid_bone)
                if prop_name:
                    humanoid = humanoid_properties.HumanoidProperties.from_obj(
                        bl_humanoid_obj
                    )
                    humanoid.set_bone(prop_name, node.name)
                else:
                    print(f"{node.name} ({node.humanoid_bone}) not found")

    def _create_tree(
        self, node: gltf.Node, parent: gltf.Node | None = None, level: int = 0
    ) -> bpy.types.Object:
        bl_obj = self._create_object(node)
        for child in node.children:
            self._create_tree(child, node, level + 1)
        return bl_obj

    def _create_object(self, node: gltf.Node) -> bpy.types.Object:
        if isinstance(node.mesh, gltf.Mesh):
            bl_mesh = self.mesh_map.get(node.mesh)
            is_create = False
            if not bl_mesh:
                is_create = True
                print(f"create: {node.mesh.name}")

                # Create an empty mesh and the object.
                name = node.mesh.name
                bl_mesh = bpy.data.meshes.new(name + "_mesh")
                self.mesh_map[node.mesh] = bl_mesh

            bl_obj = bpy.data.objects.new(node.name, bl_mesh)
            self.collection.objects.link(bl_obj)
            if is_create:
                if node.skin:
                    for joint in node.skin.joints:
                        bg = bl_obj.vertex_groups.new(name=joint.name)
                        bg.add((0,), 1.0, "ADD")

                for m in self.materials:
                    bl_mesh.materials.append(m)

                create_mesh(bl_mesh, node.mesh)

                # TODO: remove no use material
        else:
            # empty
            bl_obj: bpy.types.Object = bpy.data.objects.new(node.name, None)
            bl_obj.empty_display_size = 0.1
            self.collection.objects.link(bl_obj)

        # bl_obj.select_set(True)
        self.obj_map[node] = bl_obj
        # parent
        if node.parent:
            bl_obj.parent = self.obj_map[node.parent]

        # TRS
        bl_obj.location = node.translation
        bl_obj.rotation_quaternion = node.rotation
        bl_obj.scale = node.scale

        return bl_obj

    def _create_humanoid(self, roots: list[gltf.Node]) -> bpy.types.Object:
        """
        Armature for Humanoid
        """
        skins = [node.skin for root in roots for node in root.traverse() if node.skin]
        # create new node
        bl_skin = bpy.data.armatures.new("Humanoid")
        bl_skin.use_mirror_x = True
        bl_skin.show_axes = True
        # bl_skin.show_names = True
        bl_skin.display_type = "STICK"
        bl_obj = bpy.data.objects.new("Humanoid", bl_skin)
        bl_obj.show_in_front = True
        self.collection.objects.link(bl_obj)

        # enter edit mode
        bpy.context.view_layer.objects.active = bl_obj
        bl_obj.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT", toggle=False)

        # 1st pass: create bones
        bones: dict[gltf.Node, bpy.types.EditBone] = {}
        for skin in skins:
            for node in skin.joints:
                if node in bones:
                    continue
                bl_object = self.obj_map.get(node)
                if not bl_object:
                    # maybe removed as empty leaf
                    continue
                bl_bone = bl_skin.edit_bones.new(node.name)
                # get armature local matrix
                bl_bone.head = bl_object.matrix_world.translation
                bl_bone.tail = bl_bone.head + mathutils.Vector((0, 0.1, 0))
                bones[node] = bl_bone

        # 2nd pass: tail, connect
        connect_bones(bones)

        humaniod_map: dict[human_bones.HumanoidBones, gltf.Node] = {}
        for k, _ in bones.items():
            if k.humanoid_bone:
                humaniod_map[k.humanoid_bone] = k

        # set bone group
        # TODO:
        # with disposable_mode(bl_obj, 'POSE'):
        #     bone_group = bl_obj.pose.bone_groups.new(name='humanoid')
        #     bone_group.color_set = 'THEME01'
        #     for node in humaniod_map.values():
        #         b = bl_obj.pose.bones[node.name]
        #         b.bone_group = bone_group
        #         # property
        #         # b.pyimpex_humanoid_bone = node.humanoid_bone.name

        for skin in skins:
            self.skin_map[skin] = bl_obj
        bpy.ops.object.mode_set(mode="OBJECT")

        # #
        # # set metarig
        # #
        # with disposable_mode(bl_obj, 'EDIT'):
        #     # add heel
        #     def create_heel(bl_armature: bpy.types.Armature, name: str,
        #                     bl_parent: bpy.types.EditBone, tail_offset):
        #         bl_heel_l = bl_armature.edit_bones.new(name)
        #         bl_heel_l.use_connect = False
        #         # print(bl_parent)
        #         bl_heel_l.parent = bl_parent
        #         y = 0.1
        #         bl_heel_l.head = (bl_parent.head.x, y, 0)
        #         bl_heel_l.tail = (bl_parent.head.x + tail_offset, y, 0)

        #     bl_armature = bl_obj.data
        #     if isinstance(bl_armature, bpy.types.Armature):
        #         left_foot_node = humaniod_map[formats.HumanoidBones.leftFoot]
        #         create_heel(bl_armature, 'heel.L',
        #                     bl_armature.edit_bones[left_foot_node.name], 0.1)
        #         right_foot_node = humaniod_map[formats.HumanoidBones.rightFoot]
        #         create_heel(bl_armature, 'heel.R',
        #                     bl_armature.edit_bones[right_foot_node.name], -0.1)

        # with disposable_mode(bl_obj, 'POSE'):
        #     for k, v in bones.items():
        #         if k.humanoid_bone:
        #             b = bl_obj.pose.bones[k.name]
        #             try:
        #                 rigify_type = METALIG_MAP.get(k.humanoid_bone)
        #                 if rigify_type:
        #                     b.rigify_type = rigify_type
        #                 else:
        #                     print(k.humanoid_bone)
        #             except Exception as ex:
        #                 print(ex)
        #                 break

        # text: bpy.types.Text = bpy.data.texts.new('bind_rigify.py')
        # text.from_string(BIND_RIGIFY)

        return bl_obj

    def _setup_skinning(self, mesh_node: gltf.Node) -> None:
        if not isinstance(mesh_node.mesh, gltf.Mesh):
            return
        if not mesh_node.skin:
            return
        skin = mesh_node.skin
        bone_names: list[str] = [joint.name for joint in skin.joints]
        bl_object = self.obj_map[mesh_node]
        if not isinstance(bl_object.data, bpy.types.Mesh):
            return

        print(f"skinning: {bl_object}")
        vert_idx = [0]

        # for sm in mesh_node.mesh.submeshes:
        #     assert sm.vertices.JOINTS_0
        #     j = sm.vertices.JOINTS_0()
        #     assert sm.vertices.WEIGHTS_0
        #     w = sm.vertices.WEIGHTS_0()
        # set_skinning(mesh_node.mesh.boneweights)
        if mesh_node.mesh.boneweights:
            for v in mesh_node.mesh.boneweights:
                if v.weights.x > 0:
                    set_bone_weight(
                        bl_object, vert_idx[0], bone_names[int(v.joints.x)], v.weights.x
                    )
                if v.weights.y > 0:
                    set_bone_weight(
                        bl_object, vert_idx[0], bone_names[int(v.joints.y)], v.weights.y
                    )
                if v.weights.z > 0:
                    set_bone_weight(
                        bl_object, vert_idx[0], bone_names[int(v.joints.z)], v.weights.z
                    )
                if v.weights.w > 0:
                    set_bone_weight(
                        bl_object, vert_idx[0], bone_names[int(v.joints.w)], v.weights.w
                    )
                vert_idx[0] += 1

        modifier = bl_object.modifiers.new(name="Armature", type="ARMATURE")
        modifier.object = self.skin_map.get(skin)

    def _apply_conversion(self, roots: list[bpy.types.Object]):
        empty = bpy.data.objects.new("empty", None)
        self.collection.objects.link(empty)
        for bl_obj in roots:
            bl_obj.parent = empty
        convert_obj(self.conversion.src, self.conversion.dst, empty)

        def apply(o: bpy.types.Object):
            o.select_set(True)
            bpy.ops.object.transform_apply(location=False, rotation=True, scale=False)
            o.select_set(False)

        bpy.ops.object.select_all(action="DESELECT")
        bl_traverse(empty, apply)
        empty.select_set(True)
        bpy.ops.object.delete(use_global=False)

    def _remove_empty(self, node: gltf.Node):
        """
        深さ優先で、深いところから順に削除する
        """
        for i in range(len(node.children) - 1, -1, -1):
            child = node.children[i]
            self._remove_empty(child)

        if node.children:
            return
        if node.mesh:
            return

        # remove empty
        bl_obj = self.obj_map[node]
        bpy.data.objects.remove(bl_obj, do_unlink=True)
        if node.parent:
            node.parent.children.remove(node)
