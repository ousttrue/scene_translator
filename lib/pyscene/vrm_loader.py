from typing import NamedTuple, Optional, List
from enum import Enum

import bpy
from .. import formats
from .index_map import IndexMap
from .node import Node


class VrmExpressionPreset(Enum):
    unknown = "unknown"
    neutral = "neutral"
    a = "a"
    i = "i"
    u = "u"
    e = "e"
    o = "o"
    blink = "blink"
    joy = "joy"
    angry = "angry"
    sorrow = "sorrow"
    fun = "fun"
    lookup = "lookup"
    lookdown = "lookdown"
    lookleft = "lookleft"
    lookright = "lookright"
    blink_l = "blink_l"
    blink_r = "blink_r"


class VrmMorphBinding(NamedTuple):
    node: Node
    name: str
    weight: float


class VrmExpression:
    def __init__(self, preset: VrmExpressionPreset,
                 name: Optional[str]) -> None:
        self.preset = preset
        self.name = name
        self.morph_bindings: List[VrmMorphBinding] = []

    def __str__(self) -> str:
        if self.preset == VrmExpressionPreset.unknown:
            return f'custom: {self.name}'
        else:
            return f'{self.preset}'

    def __repr__(self) -> str:
        if self.preset == VrmExpressionPreset.unknown:
            return f'VrmExpression({self.preset}, "{self.name}")'
        else:
            return f'VrmExpression({self.preset})'


class Vrm:
    def __init__(self) -> None:
        self.expressions: List[VrmExpression] = []


def load_vrm(index_map: IndexMap, gltf: formats.gltf.glTF) -> Optional[Vrm]:
    if not gltf.extensions:
        return None
    if not gltf.extensions.VRM:
        return None

    vrm = Vrm()
    for blendshape in gltf.extensions.VRM.blendShapeMaster.blendShapeGroups:
        if not isinstance(blendshape.name, str):
            raise Exception()
        if not blendshape.presetName:
            raise Exception()
        expression = VrmExpression(VrmExpressionPreset(blendshape.presetName),
                                   blendshape.name)
        vrm.expressions.append(expression)

        for b in blendshape.binds:
            if not isinstance(b.mesh, int):
                raise Exception()
            if not isinstance(b.index, int):
                raise Exception()
            mesh = index_map.mesh[b.mesh]
            node = index_map.node_from_mesh(mesh)
            if not node:
                raise Exception()

            name = mesh.morphtargets[b.index].name

            expression.morph_bindings.append(
                VrmMorphBinding(node, name, b.weight * 0.01))

    return vrm
