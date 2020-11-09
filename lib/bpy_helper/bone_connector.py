from typing import Dict, Optional
import bpy
import mathutils
from .. import pyscene, formats


class BoneConnector:
    '''
    ボーンを適当に接続したり、しない場合でも tail を設定してやる
    '''
    def __init__(self, bones: Dict[pyscene.Node, bpy.types.EditBone]):
        self.bones = bones

    def extend_tail(self, node: pyscene.Node):
        '''
        親ボーンと同じ方向にtailを延ばす
        '''
        bl_bone = self.bones[node]
        if node.parent:
            bl_parent = self.bones[node.parent]
            tail_offset = (bl_bone.head - bl_parent.head)  # type: ignore
            bl_bone.tail = bl_bone.head + tail_offset

    def connect_tail(self, node: pyscene.Node, tail: pyscene.Node):
        bl_bone = self.bones[node]
        bl_tail = self.bones[tail]
        bl_bone.tail = bl_tail.head
        bl_tail.parent = bl_bone
        bl_tail.use_connect = True

    def traverse(self, node: pyscene.Node, parent: Optional[pyscene.Node],
                 is_connect: bool):
        # connect
        if parent:
            # print(f'connect {parent} => {node}')
            bl_parent = self.bones[parent]
            bl_bone = self.bones[node]
            bl_bone.parent = bl_parent
            if is_connect:
                if bl_parent.head != bl_bone.head:
                    bl_parent.tail = bl_bone.head
                else:
                    bl_parent.tail = bl_bone.head + mathutils.Vector((0, 0, 1e-4))

                bl_bone.use_connect = True

        if node.children:
            # recursive
            connect_child_index = None
            if any(child.humanoid_bone for child in node.children):
                # humanioid
                for i, child in enumerate(node.children):
                    if child.humanoid_bone:
                        if child.humanoid_bone in [
                                formats.HumanoidBones.hips,
                                formats.HumanoidBones.leftUpperLeg,
                                formats.HumanoidBones.rightUpperLeg,
                                formats.HumanoidBones.leftShoulder,
                                formats.HumanoidBones.rightShoulder,
                                formats.HumanoidBones.leftEye,
                                formats.HumanoidBones.rightEye,
                        ]:
                            continue
                        connect_child_index = i
                        break
            else:
                for i, child in enumerate(node.children):
                    if child.name in [
                            'J_Adj_L_FaceEyeSet', 'J_Adj_R_FaceEyeSet'
                    ]:
                        continue
                    # とりあえず
                    connect_child_index = i
                    break

            # select connect child
            for i, child in enumerate(node.children):
                self.traverse(child, node, i == connect_child_index)
        else:
            # stop recursive
            self.extend_tail(node)


def connect_bones(bones: Dict[pyscene.Node, bpy.types.EditBone]):

    nodes = bones.keys()
    roots = []
    for node in nodes:
        if not node.parent:
            roots.append(node)
        elif node.parent not in nodes:
            roots.append(node)

    connector = BoneConnector(bones)
    for root in roots:
        connector.traverse(root, None, False)