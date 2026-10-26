// Original Outlands native class-selection and patrol-cadence profiles.
// Call start() once from the existing fill controller. No automatic init/main.
// Native loadout generation, combat, objective goals and recovery remain owners.
#include common_scripts\utility;

start()
{
    if ( !isdedicated() || !getdvarint( "outlands_native_bots" ) || !getdvarint( "outlands_bot_profiles" ) )
        return;
    if ( isdefined( level.outlands_profiles_started ) )
        return;

    classes = getfunction( "maps/mp/bots/_bot", "bot_build_classes" );
    patrol = getfunction( "maps/mp/bots/_bot", "bot_update_patrol" );
    category = getfunction( "maps/mp/_utility", "getweaponclass" );
    rockets = getfunction( "maps/mp/bots/_bot_combat", "threat_requires_rocket" );
    drone = getfunction( "maps/mp/bots/_bot_combat", "threat_is_qrdrone" );
    warthog = getfunction( "maps/mp/bots/_bot_combat", "threat_is_warthog" );

    // Missing helpers or another mod's detour leave the stock behavior intact.
    if ( !isdefined( classes ) || !isdefined( patrol ) || !isdefined( category ) || !isdefined( rockets ) || !isdefined( drone ) || !isdefined( warthog ) )
    {
        println( "Outlands bot profiles: native helper unavailable; profile features disabled." );
        return;
    }
    if ( isdefined( getdetour( classes ) ) || isdefined( getdetour( patrol ) ) )
    {
        println( "Outlands bot profiles: native helper already detoured; profile features disabled." );
        return;
    }

    level.outlands_profiles_classes = classes;
    level.outlands_profiles_patrol = patrol;
    level.outlands_profiles_category = category;
    level.outlands_profiles_rockets = rockets;
    level.outlands_profiles_drone = drone;
    level.outlands_profiles_warthog = warthog;
    replacefunc( classes, ::profile_class_pool );
    replacefunc( patrol, ::profile_patrol_update );
    level.outlands_profiles_started = 1;
    println( "Outlands bot profiles: native class pools and optional patrol cadence active; objective/recovery brain unchanged." );
}

profile_enabled()
{
    return isdedicated() && getdvarint( "outlands_native_bots" ) && getdvarint( "outlands_bot_profiles" ) && isdefined( self ) && isplayer( self ) && self istestclient();
}

native_class_pool()
{
    // Skip only this next call, with no wait between bypass and native call.
    disabledetouronce( level.outlands_profiles_classes );
    return self [[ level.outlands_profiles_classes ]]();
}

assign_profile()
{
    if ( !self profile_enabled() || isdefined( self.outlands_profile_role ) )
        return;

    roll = randomint( 100 );
    if ( roll < 25 )
        role = "rusher";
    else if ( roll < 55 )
        role = "assault";
    else if ( roll < 80 )
        role = "objective";
    else if ( roll < 95 )
        role = "support";
    else
        role = "marksman";

    // Limit marksman profiles, not native emergency anti-air class choices.
    limit = 2;
    if ( getdvar( "outlands_bot_marksman_limit" ) != "" )
        limit = getdvarint( "outlands_bot_marksman_limit" );
    if ( limit < 0 )
        limit = 0;
    if ( limit > 4 )
        limit = 4;
    if ( role == "marksman" )
    {
        count = 0;
        players = get_players();
        foreach ( player in players )
        {
            if ( !isdefined( player ) || !isplayer( player ) || !player istestclient() )
                continue;
            if ( isdefined( player.outlands_profile_role ) && player.outlands_profile_role == "marksman" )
                count++;
        }
        if ( count >= limit )
            role = "assault";
    }
    self.outlands_profile_role = role;
    self.outlands_profile_pool_logs = 0;
    self.outlands_profile_patrol_logs = 0;
    println( "Outlands bot profile: slot=" + ( self getentitynumber() ) + " role=" + role );
}

native_air_threat()
{
    if ( !isdefined( self.bot ) || !isdefined( self.bot.attacker ) )
        return false;
    threat = self.bot.attacker;
    return [[ level.outlands_profiles_rockets ]]( threat ) || [[ level.outlands_profiles_drone ]]( threat ) || [[ level.outlands_profiles_warthog ]]( threat );
}

profile_class_pool()
{
    native = self native_class_pool();
    if ( !self profile_enabled() || !isdefined( self.pers["bot_loadout"] ) )
        return native;
    self assign_profile();
    if ( !isdefined( self.outlands_profile_role ) || self native_air_threat() )
        return native;

    choices = [];
    details = "";
    observed = "";
    foreach ( candidate in native )
    {
        index = class_index( candidate );
        if ( index < 0 )
            continue;
        weapon = self getloadoutweapon( index, "primary" );
        if ( !isdefined( weapon ) || weapon == "" || weapon == "none" )
            continue;
        group = [[ level.outlands_profiles_category ]]( weapon );
        if ( !isdefined( group ) )
            continue;
        observed = observed + " " + candidate + "=" + group;
        if ( profile_accepts( self.outlands_profile_role, group ) )
        {
            choices[choices.size] = candidate;
            details = details + " " + candidate + "=" + weapon;
        }
    }

    // These preset names are initialized by native on_bot_connect, including
    // bots whose current native rank has not unlocked Create-a-Class.
    if ( !choices.size )
    {
        choices = preset_pool( self.outlands_profile_role );
        details = " native preset fallback; groups=" + observed;
    }
    if ( getdvarint( "outlands_status" ) && self.outlands_profile_pool_logs < 3 )
    {
        println( "Outlands bot class pool: slot=" + ( self getentitynumber() ) + " role=" + self.outlands_profile_role + " choices=" + choices.size + details );
        self.outlands_profile_pool_logs++;
    }
    return choices;
}

class_index( name )
{
    switch ( name )
    {
        case "custom0": return 0;
        case "custom1": return 1;
        case "custom2": return 2;
        case "custom3": return 3;
        case "custom4": return 4;
        case "class_assault": return 5;
        case "class_smg": return 6;
        case "class_lmg": return 7;
        case "class_cqb": return 8;
        case "class_sniper": return 9;
    }
    return -1;
}

profile_accepts( role, group )
{
    switch ( role )
    {
        case "rusher": return group == "weapon_smg" || group == "weapon_cqb";
        case "assault": return group == "weapon_assault";
        case "objective": return group == "weapon_assault" || group == "weapon_smg";
        case "support": return group == "weapon_lmg" || group == "weapon_assault";
        case "marksman": return group == "weapon_sniper";
    }
    return false;
}

preset_pool( role )
{
    switch ( role )
    {
        case "rusher": return array( "class_smg", "class_cqb" );
        case "objective": return array( "class_assault", "class_smg" );
        case "support": return array( "class_lmg", "class_assault" );
        case "marksman": return array( "class_sniper" );
    }
    return array( "class_assault" );
}

profile_patrol_update()
{
    enabled = self profile_enabled() && getdvarint( "outlands_bot_patrol_profiles" );
    before = -1;
    if ( enabled && isdefined( self.bot ) && isdefined( self.bot.update_patrol ) )
        before = self.bot.update_patrol;

    // Native code retains all goal selection, enemy visibility and cancellation.
    disabledetouronce( level.outlands_profiles_patrol );
    self [[ level.outlands_profiles_patrol ]]();
    if ( !enabled || !isdefined( self.bot ) || !isdefined( self.bot.update_patrol ) )
        return;
    if ( before == self.bot.update_patrol || self.bot.update_patrol <= gettime() )
        return;
    self assign_profile();
    if ( !isdefined( self.outlands_profile_role ) )
        return;

    low = 5000;
    high = 10000;
    switch ( self.outlands_profile_role )
    {
        case "rusher":
            low = 2000;
            high = 4000;
            break;
        case "assault":
            low = 4000;
            high = 7000;
            break;
        case "objective":
            low = 7000;
            high = 11000;
            break;
        case "support":
            low = 8000;
            high = 12000;
            break;
        case "marksman":
            low = 10000;
            high = 15000;
            break;
    }
    interval = randomintrange( low, high + 1 );
    self.bot.update_patrol = gettime() + interval;
    if ( getdvarint( "outlands_status" ) && self.outlands_profile_patrol_logs < 3 )
    {
        println( "Outlands bot patrol cadence: slot=" + ( self getentitynumber() ) + " role=" + self.outlands_profile_role + " next_ms=" + interval + " native goals unchanged" );
        self.outlands_profile_patrol_logs++;
    }
}
