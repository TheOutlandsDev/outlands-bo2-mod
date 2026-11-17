"""Execute original Lua navigation with API stubs; no engine/UI acceptance."""
import ctypes
import ctypes.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = ctypes.util.find_library('lua5.4')


@unittest.skipUnless(LIBRARY, 'Optional Lua 5.4 runtime is unavailable; real client acceptance remains pending')
class MenuPreviewTests(unittest.TestCase):
    def test_ownership_native_back_focus_and_removal(self):
        lua = ctypes.CDLL(LIBRARY)
        lua.luaL_newstate.restype = ctypes.c_void_p
        lua.luaL_openlibs.argtypes = [ctypes.c_void_p]
        lua.luaL_loadstring.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        lua.luaL_loadstring.restype = ctypes.c_int
        lua.lua_pcallk.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_longlong, ctypes.c_void_p]
        lua.lua_pcallk.restype = ctypes.c_int
        lua.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_size_t)]
        lua.lua_tolstring.restype = ctypes.c_char_p
        lua.lua_close.argtypes = [ctypes.c_void_p]
        path = ROOT/'client-preview/raw/ui_mp/outlands/armory_preview.lua'
        script = '''
local closeCount, focusCount, backCount = 0, 0, 0
local function label()
 return {setLeftRight=function() end,setTopBottom=function() end,setFont=function() end,
         setText=function() end,setRGB=function() end}
end
LUI = {createMenu={}, UIText={new=label}}
CoD = {Menu={TitleHeight=60},textSize={Default=24},fonts={Default='font'}}
CoD.InGameMenu={New=function(name, controller, title)
 local menu={handlers={},elements={}}
 function menu:close() closeCount=closeCount+1 end
 function menu:addButtonPrompts() end
 function menu:addElement(e) table.insert(self.elements,e) end
 function menu:registerEventHandler(name, handler) self.handlers[name]=handler end
 function menu:processEvent(event)
  if event.name=='button_prompt_back' then backCount=backCount+1;self:close();return true end
  return self.handlers[event.name](self,event)
 end
 return menu
end}
CoD.ButtonList={new=function()
 local list={buttons={}}
 function list:addButton(name)
  local button={name=name,disable=function(self) self.disabled=true end,
                setActionEventName=function(self,n) self.action=n end}
  table.insert(self.buttons,button);return button
 end
 function list:processEvent(event) assert(event.name=='gain_focus_skip_disabled');focusCount=focusCount+1 end
 return list
end}
local preview=dofile(PATH)
assert(preview.view().equip==false)
assert(preview.view().status:find('UNAVAILABLE'))
assert(preview.register());assert(not preview.register())
local menu=LUI.createMenu.OutlandsArmoryPreview(0)
assert(LUI.createMenu.OutlandsArmoryPreview(0)==menu)
assert(focusCount==1 and #menu.elements==5)
assert(menu.elements[5].buttons[1].disabled)
menu:processEvent({name='outlands_preview_back',controller=0})
assert(backCount==1 and closeCount==1)
menu:close();assert(closeCount==1)
LUI.createMenu.OutlandsArmoryPreview(0)
preview.unregister();assert(closeCount==2)
assert(LUI.createMenu.OutlandsArmoryPreview==nil)
preview.unregister();assert(closeCount==2)
local other=function() end
LUI.createMenu.OutlandsArmoryPreview=other
assert(not preview.register());preview.unregister()
assert(LUI.createMenu.OutlandsArmoryPreview==other)
'''.replace('PATH', json.dumps(str(path)))
        state = lua.luaL_newstate()
        self.assertTrue(state)
        try:
            lua.luaL_openlibs(state)
            status = lua.luaL_loadstring(state, script.encode())
            if status == 0: status = lua.lua_pcallk(state, 0, 0, 0, 0, None)
            error = lua.lua_tolstring(state, -1, None) if status else None
            self.assertEqual(status, 0, error.decode() if error else '')
        finally:
            lua.lua_close(state)


if __name__ == '__main__': unittest.main()
