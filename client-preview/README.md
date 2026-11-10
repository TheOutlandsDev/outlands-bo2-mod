# Original native-menu preview source

This is a namespaced Lua/LUI menu module and an OAT zone recipe, not an installed
or engine-accepted client package. No stock menu, game asset or native save is
replaced. The module uses the native in-game menu, button list, back handling
and text primitives. It shows unavailable progress and a disabled equip action.
No camo appearance or earned ownership is claimed.

A verified client loading hook is still required. The official Plutonium raw
assets demonstrate T6 Lua menus and OAT linking against an owned `ui_mp.ff`, but
they do not demonstrate automatic evaluation of this new namespaced rawfile.
Do not rename the output to `plutonium_mp.ff`, overwrite `ui_mp.ff`, or distribute
an extracted stock menu to manufacture a loading path.

Once an isolated loading hook is verified, load this module and call `register()`
after native LUI dependencies initialize. Its factory is named
`OutlandsArmoryPreview`. `unregister()` closes owned screens and removes only
its own factory. If a different factory already owns that name, registration
refuses to replace it. Repeated opens for the same controller reuse the screen.

Offline checks execute the original module in a Lua 5.4 state with small API
stubs to exercise registration, focus events, back delegation and cleanup. This
is not HavokScript or actual Windows/Linux rendering acceptance. With a client,
verify package loading first, then 720p/1080p text, keyboard/controller focus,
back/resume, respawn/map-change cleanup and complete package removal. A future
trusted view-model adapter must display unavailable data explicitly and must
never accept browser/client assertions as unlock evidence.

References:

- https://github.com/plutoniummod/client-raw-assets/blob/master/t6/raw/ui_mp/t6/hud/class.lua
- https://github.com/plutoniummod/client-raw-assets/blob/master/t6/build.bat
- https://github.com/Laupetin/OpenAssetTools
