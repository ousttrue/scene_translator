import scene_translator
import bpy

print('register')
scene_translator.register()

print('call')
bpy.ops.scene_translator.exporter()

print('unregister')
scene_translator.unregister()