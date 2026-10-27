// Original Armory feasibility adapter. No main/init and no public commands.
// Native slots remain native-owned; arbitrary class materialization is gated.
// No human DDL, inventory, unlock, rank or XP writes occur in this module.

valid_slot( index )
{
    return isdefined( index ) && int( index ) == index && index >= 0 && index < 5;
}

eligible( player )
{
    if ( !isdefined( player ) || !isplayer( player ) || player istestclient() )
        return false;
    return isdefined( player.pers["team"] ) && ( player.pers["team"] == "allies" || player.pers["team"] == "axis" || player.pers["team"] == "free" );
}

inspect_native_slot( player, index )
{
    result = spawnstruct();
    result.ready = 0;
    result.native_valid = 0;
    result.index = -1;
    if ( !isdefined( player ) || !isplayer( player ) || !valid_slot( index ) )
        return result;
    // Native validity is separate from authoritative human unlock acceptance.
    // Do not infer earned attachment/perk ownership from this flag alone.
    if ( !player classisvalid( index ) )
        return result;
    result.index = index;
    result.native_valid = 1;
    result.primary = player getloadoutweapon( index, "primary" );
    result.secondary = player getloadoutweapon( index, "secondary" );
    result.perks = player getloadoutperks( index );
    result.ready = isdefined( result.primary ) && isdefined( result.secondary ) && isdefined( result.perks );
    return result;
}

stage_native_reference( player, index )
{
    // Private all-bot probe only. This is a native slot-selection feasibility
    // experiment, not the custom-class equip adapter used by a live player.
    if ( !getdvarint( "outlands_backend_verification" ) || getdvar( "net_ip" ) != "127.0.0.1" || !isdefined( player ) || !isplayer( player ) || !player istestclient() )
        return false;
    view = inspect_native_slot( player, index );
    if ( !view.ready || player.sessionstate != "playing" || !isalive( player ) || !isdefined( game["state"] ) || game["state"] != "playing" )
        return false;
    // Stock menuclass also sets these fields but can regrant weapons in its
    // grace-period path. Stage the reference only; stock spawning owns grants.
    selected = "CLASS_CUSTOM" + ( index + 1 );
    player.pers["class"] = selected;
    player.class = selected;
    player.pers["weapon"] = undefined;
    player.pers["changed_class"] = 1;
    return true;
}
