// Original bot-only variety policy; native generation owns unlocks and Pick-10.
#include common_scripts\utility;

start()
{
    if ( !isdedicated() || !getdvarint( "outlands_native_bots" ) || !getdvarint( "outlands_bot_loadout_variety" ) || isdefined( level.outlands_loadouts_started ) ) return;
    pointer = getfunction( "maps/mp/bots/_bot_loadout", "bot_choose_weapon" );
    if ( !isdefined( pointer ) || isdefined( getdetour( pointer ) ) ) return;
    level.outlands_loadouts_stage = getdvarint( "outlands_verify_restarted" );
    level.outlands_loadout_choose = pointer;
    replacefunc( pointer, ::choose_weapon );
    level.outlands_loadouts_started = 1;
    println( "Outlands loadouts: native primary diversity and class exploration ready." );
}

enabled()
{
    return getdvarint( "outlands_native_bots" ) && getdvarint( "outlands_bot_loadout_variety" ) && isdefined( level.outlands_loadouts_started );
}

eligible()
{
    return isdefined( self ) && isplayer( self ) && self istestclient();
}

native_choose( class, items )
{
    disabledetouronce( level.outlands_loadout_choose );
    return self [[ level.outlands_loadout_choose ]]( class, items );
}

choose_weapon( class, items )
{
    if ( !enabled() || !self eligible() || class < 0 || class > 4 || !isdefined( items ) || !items.size ) return self native_choose( class, items );
    // This array already passed native unlock, banned-item and allocation rules.
    if ( tablelookup( level.statstableid, 3, items[0], 13 ) != "primary" ) return self native_choose( class, items );
    if ( !isdefined( self.outlands_loadout_history ) ) self.outlands_loadout_history = [];
    filtered = []; wire = "";
    foreach ( item in items )
    {
        if ( !isdefined( self.outlands_loadout_history[item] ) || self.outlands_loadout_history[item] == class ) filtered[filtered.size] = item;
        if ( wire != "" ) wire += ",";
        wire += item;
    }
    candidates = filtered;
    if ( !candidates.size ) candidates = items;
    chosen = self native_choose( class, candidates );
    if ( isdefined( chosen ) )
    {
        self.outlands_loadout_history[chosen] = class;
        scripts\mp\outlands_log::emit( "OUTLANDS_LOADOUT_BUILD_V1|" + level.outlands_loadouts_stage + "|" + ( self getentitynumber() ) + "|" + class + "|" + chosen + "|" + wire );
    }
    return chosen;
}

candidate_choices( native, strict )
{
    if ( !enabled() || !self eligible() ) return strict;
    choices = strict;
    deaths = 0;
    if ( isdefined( self.deaths ) ) deaths = int( self.deaths );
    seed = 17;
    if ( isdefined( level.outlands_rival_hash ) ) seed = level.outlands_rival_hash;
    roll = scripts\mp\outlands_rivals::hash_text( self.name + ":explore:" + deaths, seed ) % 100;
    percent = scripts\mp\outlands_squads::setting( "outlands_bot_explore_percent", 35, 0, 60 );
    if ( self.outlands_profile_role != "marksman" && roll < percent )
    {
        broad = [];
        foreach ( candidate in native )
        {
            index = scripts\mp\outlands_bot_profiles::class_index( candidate );
            if ( index < 0 || !self classisvalid( index ) ) continue;
            group = [[ level.outlands_profiles_category ]]( self getloadoutweapon( index, "primary" ) );
            if ( group == "weapon_assault" || group == "weapon_smg" || group == "weapon_lmg" || group == "weapon_cqb" ) broad[broad.size] = candidate;
        }
        if ( broad.size ) choices = broad;
    }
    fresh = [];
    foreach ( candidate in choices )
    {
        index = scripts\mp\outlands_bot_profiles::class_index( candidate );
        if ( index < 0 ) continue;
        variant = self getloadoutweapon( index, "primary" );
        if ( !isdefined( self.outlands_loadout_last_variant ) || variant != self.outlands_loadout_last_variant ) fresh[fresh.size] = candidate;
    }
    if ( fresh.size ) return fresh;
    return choices;
}

record_equip( selected, expected, actual, owned, deaths )
{
    if ( !enabled() || !self eligible() ) return;
    if ( owned ) self.outlands_loadout_last_variant = expected;
    scripts\mp\outlands_log::emit( "OUTLANDS_LOADOUT_EQUIP_V1|" + level.outlands_loadouts_stage + "|" + ( self getentitynumber() ) + "|" + deaths + "|" + selected + "|" + expected + "|" + actual + "|" + owned );
}
