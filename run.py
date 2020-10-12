import scene_translator
import bpy

print('register')
scene_translator.register()

print('call')
bpy.ops.object.move_x()

print('unregister')
scene_translator.unregister()
