-- Original Outlands-only Lua module. Loading/registration must be supplied by a
-- verified client hook; this file never overrides a stock menu or writes stats.
local Preview = { name = "OutlandsArmoryPreview" }
local owned = {}
local factory = nil

function Preview.view()
    return {
        title = "OUTLANDS ARMORY - DEVELOPMENT PREVIEW",
        weapon = "AN-94 / OUTLANDS DUSK",
        requirement = "25 verified enemy headshot kills with the AN-94",
        status = "PROGRESS UNAVAILABLE - CLIENT DATA LINK PENDING",
        appearance = "TEXT PREVIEW - CAMO ASSET NOT INSTALLED",
        equip = false
    }
end

function Preview.register()
    if not (LUI and LUI.createMenu and LUI.UIText and CoD and CoD.InGameMenu
            and CoD.ButtonList and CoD.Menu and CoD.textSize and CoD.fonts) then
        return false
    end
    if LUI.createMenu[Preview.name] ~= nil then return false end
    factory = function(controller)
        if owned[controller] then return owned[controller] end
        local view = Preview.view()
        local menu = CoD.InGameMenu.New(Preview.name, controller, view.title)
        owned[controller] = menu
        local originalClose = menu.close
        local closed = false
        menu.close = function(self)
            if closed then return end
            closed = true
            owned[controller] = nil
            originalClose(self)
        end
        menu:addButtonPrompts()
        local lines = { view.weapon, view.requirement, view.status, view.appearance }
        for index, value in ipairs(lines) do
            local label = LUI.UIText.new()
            label:setLeftRight(true, false, 40, 1180)
            local top = CoD.Menu.TitleHeight + 20 + (index - 1) * 40
            label:setTopBottom(true, false, top, top + CoD.textSize.Default)
            label:setFont(CoD.fonts.Default)
            label:setText(value)
            if index == 1 then label:setRGB(1, 0.45, 0.05) end
            menu:addElement(label)
        end
        local list = CoD.ButtonList.new({ leftAnchor = true, rightAnchor = false,
            left = 40, right = 440, topAnchor = true, bottomAnchor = false,
            top = CoD.Menu.TitleHeight + 220, bottom = CoD.Menu.TitleHeight + 400 })
        menu:addElement(list)
        local locked = list:addButton("EQUIP UNAVAILABLE - DEVELOPMENT PREVIEW")
        locked:disable()
        local back = list:addButton("BACK")
        back:setActionEventName("outlands_preview_back")
        menu:registerEventHandler("outlands_preview_back", function(self, event)
            -- Preserve the native back handler and focus ownership.
            return self:processEvent({ name = "button_prompt_back", controller = event.controller })
        end)
        list:processEvent({ name = "gain_focus_skip_disabled" })
        return menu
    end
    LUI.createMenu[Preview.name] = factory
    return true
end

function Preview.unregister()
    local menus = {}
    for _, menu in pairs(owned) do menus[#menus + 1] = menu end
    for _, menu in ipairs(menus) do menu:close() end
    if LUI and LUI.createMenu and LUI.createMenu[Preview.name] == factory then
        LUI.createMenu[Preview.name] = nil
    end
    factory = nil
end

return Preview
