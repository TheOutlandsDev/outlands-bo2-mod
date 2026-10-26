// Original Outlands objective coordination. Native combat and interaction stay owners.
// Call start() once from the dedicated native-bot controller; no automatic init/main.
#include common_scripts\utility;

start()
{
    if ( !isdedicated() || !getdvarint( "outlands_native_bots" ) || !getdvarint( "outlands_squads" ) )
        return;
    if ( isdefined( level.outlands_squads_started ) )
        return;
    mode = getdvar( "g_gametype" );
    if ( mode != "dom" && mode != "ctf" && mode != "koth" && mode != "hq" && mode != "dem" )
        return;

    file = "maps/mp/bots/_bot_" + mode;
    think = getfunction( file, "bot_" + mode + "_think" );
    if ( !isdefined( think ) || isdefined( getdetour( think ) ) )
    {
        println( "Outlands squads: native objective hook unavailable or already owned; native fallback." );
        return;
    }
    level.outlands_squad_mode = mode;
    level.outlands_squad_think = think;
    level.outlands_squad_move = undefined;
    level.outlands_squad_selector = undefined;
    if ( mode == "dom" )
    {
        level.outlands_squad_owner = getfunction( "maps/mp/gametypes/dom", "getflagteam" );
        level.outlands_squad_move = getfunction( file, "bot_move_to_flag" );
        if ( !isdefined( level.outlands_squad_owner ) || !hook_available( level.outlands_squad_move ) )
            return;
    }
    if ( mode == "ctf" )
    {
        level.outlands_squad_owner = getfunction( "maps/mp/gametypes/_gameobjects", "getownerteam" );
        level.outlands_squad_home = getfunction( "maps/mp/gametypes/ctf", "ishome" );
        level.outlands_squad_selector = getfunction( file, "bot_should_patrol_flag" );
        if ( !isdefined( level.outlands_squad_owner ) || !isdefined( level.outlands_squad_home ) || !hook_available( level.outlands_squad_selector ) )
            return;
    }
    if ( mode == "hq" )
    {
        level.outlands_squad_selector = getfunction( file, "bot_should_patrol_hq" );
        if ( !hook_available( level.outlands_squad_selector ) )
            return;
    }

    level.outlands_squad_next_reassess = 0;
    level.outlands_squad_reassessments = 0;
    level.outlands_squad_goal_calls = 0;
    level.outlands_squad_invalid = 0;
    level.outlands_squad_targets = [];
    replacefunc( think, ::objective_think );
    if ( mode == "dom" )
        replacefunc( level.outlands_squad_move, ::dom_move );
    if ( mode == "ctf" || mode == "hq" )
        replacefunc( level.outlands_squad_selector, ::patrol_choice );
    level.outlands_squads_started = 1;
    level thread watch_switch();
    println( "Outlands squads: native objective coordination active; mode=" + mode );
}

hook_available( pointer )
{
    return isdefined( pointer ) && !isdefined( getdetour( pointer ) );
}

enabled()
{
    return isdedicated() && getdvarint( "outlands_native_bots" ) && getdvarint( "outlands_squads" );
}

bot_eligible()
{
    return isdefined( self ) && isplayer( self ) && self istestclient() && isdefined( self.team ) && ( self.team == "allies" || self.team == "axis" );
}

setting( name, fallback, low, high )
{
    value = fallback;
    if ( getdvar( name ) != "" )
        value = getdvarint( name );
    if ( value < low )
        value = low;
    if ( value > high )
        value = high;
    return value;
}

watch_switch()
{
    level endon( "game_ended" );
    was_enabled = true;
    for (;;)
    {
        now_enabled = enabled();
        if ( !now_enabled && was_enabled )
        {
            foreach ( player in get_players() )
            {
                if ( !isdefined( player ) || !isplayer( player ) || !player istestclient() )
                    continue;
                player release_goal();
                player.outlands_squad_role = "";
                player.outlands_squad_target = undefined;
                player.outlands_squad_goal_valid = 0;
            }
        }
        if ( now_enabled && !was_enabled )
            level.outlands_squad_next_reassess = 0;
        was_enabled = now_enabled;
        wait 0.5;
    }
}

release_goal()
{
    // Only this module's goal is ever cancelled, never native combat/objectives.
    if ( isdefined( self ) && isplayer( self ) && self istestclient() )
        self cancelgoal( "outlands_squad" );
}

reassess()
{
    if ( gettime() < level.outlands_squad_next_reassess )
        return;
    level.outlands_squad_next_reassess = gettime() + setting( "outlands_squad_reassess_seconds", 8, 3, 30 ) * 1000;
    level.outlands_squad_reassessments++;
    attackers = setting( "outlands_squad_attackers", 4, 1, 6 );
    defenders = setting( "outlands_squad_defenders", 2, 0, 3 );
    teams = array( "allies", "axis" );
    players = get_players();
    foreach ( team in teams )
    {
        ordinal = 0;
        foreach ( player in players )
        {
            if ( !isdefined( player ) || !player bot_eligible() || player.team != team )
                continue;
            role = "support";
            if ( ordinal < attackers )
                role = "attack";
            else if ( ordinal < attackers + defenders )
                role = "defend";
            player assign( role, ordinal );
            ordinal++;
        }
    }
}

assign( role, ordinal )
{
    target = undefined;
    target_id = -1;
    if ( role != "support" )
    {
        choices = objective_choices( role );
        if ( choices.size )
        {
            choice = choices[ordinal % choices.size];
            target = choice.object;
            target_id = choice.id;
        }
        else
            role = "support";
    }
    changed = !isdefined( self.outlands_squad_role ) || self.outlands_squad_role != role || !isdefined( self.outlands_squad_team ) || self.outlands_squad_team != self.team || !isdefined( self.outlands_squad_target_id ) || self.outlands_squad_target_id != target_id;
    if ( changed )
    {
        self release_goal();
        self.outlands_squad_next_goal = 0;
        self.outlands_squad_goal_valid = 0;
        self.outlands_squad_goal_name = "";
    }
    self.outlands_squad_role = role;
    self.outlands_squad_team = self.team;
    self.outlands_squad_target = target;
    self.outlands_squad_target_id = target_id;
    self.outlands_squad_target_mode = level.outlands_squad_mode;
    if ( isdefined( target ) )
        self.outlands_squad_target_origin = objective_origin( target );
    else
        self.outlands_squad_target_origin = undefined;
    if ( !isdefined( self.outlands_squad_goal_calls ) )
        self.outlands_squad_goal_calls = 0;
}

objective_choices( role )
{
    choices = [];
    mode = level.outlands_squad_mode;
    if ( mode == "dom" && isdefined( level.flags ) )
    {
        for ( i = 0; i < level.flags.size; i++ )
        {
            object = level.flags[i];
            if ( !isdefined( object ) || !isdefined( object.origin ) || !isdefined( object.radius ) )
                continue;
            owner = object [[ level.outlands_squad_owner ]]();
            if ( role == "defend" && owner != self.team || role == "attack" && owner == self.team )
                continue;
            choices[choices.size] = choice( object, i );
        }
    }
    if ( mode == "ctf" && isdefined( level.flags ) )
    {
        for ( i = 0; i < level.flags.size; i++ )
        {
            object = level.flags[i];
            if ( !isdefined( object ) || !isdefined( object.curorigin ) || !isdefined( object.trigger ) )
                continue;
            owner = object [[ level.outlands_squad_owner ]]();
            if ( role == "defend" && owner == self.team || role == "attack" && owner != self.team )
                choices[choices.size] = choice( object, i );
        }
    }
    if ( mode == "koth" && isdefined( level.zone ) && isdefined( level.zone.trig ) && isdefined( level.zone.gameobject ) && isdefined( level.zone.gameobject.curorigin ) )
        choices[0] = choice( level.zone, 0 );
    if ( mode == "hq" && isdefined( level.radio ) && isdefined( level.radio.baseorigin ) && isdefined( level.radio.gameobject ) )
        choices[0] = choice( level.radio, 0 );
    if ( mode == "dem" && isdefined( level.bombzones ) )
    {
        for ( i = 0; i < level.bombzones.size; i++ )
        {
            object = level.bombzones[i];
            if ( !isdefined( object ) || !isdefined( object.trigger ) || !isdefined( object.trigger.origin ) )
                continue;
            if ( isdefined( object.bombexploded ) && object.bombexploded )
                continue;
            choices[choices.size] = choice( object, i );
        }
    }
    return choices;
}

choice( object, index )
{
    result = spawnstruct();
    result.object = object;
    result.id = index;
    return result;
}

objective_origin( target )
{
    switch ( level.outlands_squad_mode )
    {
        case "dom": return target.origin;
        case "ctf": return target.curorigin;
        case "koth": return target.gameobject.curorigin;
        case "hq": return target.baseorigin;
        case "dem": return target.trigger.origin;
    }
    return undefined;
}

assignment_valid()
{
    if ( !enabled() || !self bot_eligible() || !isdefined( self.outlands_squad_role ) || !isdefined( self.outlands_squad_team ) || self.outlands_squad_team != self.team )
        return false;
    if ( self.outlands_squad_role != "attack" && self.outlands_squad_role != "defend" )
        return false;
    if ( !isdefined( self.outlands_squad_target ) || !isdefined( self.outlands_squad_target_id ) || !isdefined( self.outlands_squad_target_mode ) || self.outlands_squad_target_mode != level.outlands_squad_mode )
        return false;
    choices = self objective_choices( self.outlands_squad_role );
    foreach ( current in choices )
    {
        if ( current.id == self.outlands_squad_target_id && current.object == self.outlands_squad_target )
            return true;
    }
    return false;
}

urgent_native()
{
    if ( !isalive( self ) || !isdefined( self.bot ) )
        return true;
    if ( self isremotecontrolling() )
        return true;
    if ( isdefined( self.isplanting ) && self.isplanting || isdefined( self.isdefusing ) && self.isdefusing )
        return true;
    if ( level.outlands_squad_mode == "ctf" && isdefined( level.flags ) )
    {
        foreach ( flag in level.flags )
        {
            if ( isdefined( flag.carrier ) && flag.carrier == self )
                return true;
        }
    }
    return false;
}

native_think()
{
    disabledetouronce( level.outlands_squad_think );
    self [[ level.outlands_squad_think ]]();
}

objective_think()
{
    if ( !enabled() || !self bot_eligible() )
    {
        if ( isdefined( self ) && isplayer( self ) && self istestclient() )
            self release_goal();
        self native_think();
        return;
    }
    reassess();
    if ( !isdefined( self.outlands_squad_team ) || self.outlands_squad_team != self.team )
        level.outlands_squad_next_reassess = 0;
    self.outlands_squad_goal_valid = 0;
    if ( !self assignment_valid() || self urgent_native() )
    {
        self release_goal();
        self native_think();
        return;
    }

    // Native Demolition decides plant/defuse/guard from this native zone field.
    // Active interactions and armed bombs always retain native priority below.
    if ( level.outlands_squad_mode == "dem" && !self armed_bomb_present() && !self hasgoal( "bomb" ) )
        self.goal_flag = self.outlands_squad_target;

    // Low-priority perimeter duty is for Domination and Hardpoint defenders.
    // Combat/emergency goals keep higher native priorities. No enemy scan here.
    if ( self.outlands_squad_role == "defend" && ( level.outlands_squad_mode == "dom" || level.outlands_squad_mode == "koth" ) )
    {
        if ( self perimeter_goal() )
            return;
    }
    self release_goal();
    before = self native_goal_snapshot();
    self native_think();
    if ( !self assignment_valid() || self urgent_native() )
        return;
    after = self native_goal_snapshot();
    if ( isdefined( after ) && ( !isdefined( before ) || after.name != before.name || distancesquared( after.origin, before.origin ) > 1 ) )
        self acknowledge_goal( after.name );
    else if ( isdefined( after ) )
    {
        self.outlands_squad_goal_name = after.name;
        self.outlands_squad_goal_valid = 1;
    }
}

armed_bomb_present()
{
    if ( !isdefined( level.bombzones ) )
        return false;
    foreach ( zone in level.bombzones )
    {
        if ( isdefined( zone.bombplanted ) && zone.bombplanted && ( !isdefined( zone.bombexploded ) || !zone.bombexploded ) )
            return true;
    }
    return false;
}

perimeter_goal()
{
    if ( !self assignment_valid() )
        return false;
    // A visible/current native attacker and emergency interactions release duty.
    if ( isdefined( self.bot.attacker ) )
    {
        self release_goal();
        return false;
    }
    origin = objective_origin( self.outlands_squad_target );
    if ( !isdefined( origin ) )
        return false;
    if ( isdefined( self.outlands_squad_next_goal ) && gettime() < self.outlands_squad_next_goal && isdefined( self getgoal( "outlands_squad" ) ) )
    {
        self.outlands_squad_goal_name = "outlands_squad";
        self.outlands_squad_goal_valid = 1;
        return true;
    }
    self.outlands_squad_next_goal = gettime() + setting( "outlands_squad_goal_seconds", 3, 1, 8 ) * 1000;
    inner = 160;
    if ( level.outlands_squad_mode == "dom" && self.outlands_squad_target.radius + 64 > inner )
        inner = self.outlands_squad_target.radius + 64;
    if ( level.outlands_squad_mode == "koth" && isdefined( self.outlands_squad_target.trig.goal_radius ) && self.outlands_squad_target.trig.goal_radius + 64 > inner )
        inner = self.outlands_squad_target.trig.goal_radius + 64;
    if ( inner > 768 )
        return false;
    nodes = getnodesinradiussorted( origin, inner + 384, inner, 128, "Path" );
    if ( !nodes.size )
        return false;
    offset = ( self getentitynumber() ) % nodes.size;
    attempts = nodes.size;
    if ( attempts > 12 )
        attempts = 12;
    for ( i = 0; i < attempts; i++ )
    {
        node = nodes[( offset + i ) % nodes.size];
        if ( !isdefined( node ) || !isdefined( node.origin ) || !findpath( self.origin, node.origin, self, 0, 1 ) )
            continue;
        self addgoal( node, 32, 2, "outlands_squad" );
        self acknowledge_goal( "outlands_squad" );
        return self.outlands_squad_goal_valid;
    }
    return false;
}

dom_move( flag )
{
    destination = flag;
    if ( enabled() && self bot_eligible() && self assignment_valid() && self.outlands_squad_role == "attack" && !self urgent_native() )
    {
        target = self.outlands_squad_target;
        // The native helper asserts a nonempty node pool. Check it first.
        if ( level.script == "mp_frostbite" )
            nodes = getnodesinradius( target.origin, target.radius, 0, 32 );
        else
            nodes = getnodesinradius( target.origin, target.radius, 0 );
        if ( nodes.size )
            destination = target;
    }
    disabledetouronce( level.outlands_squad_move );
    self [[ level.outlands_squad_move ]]( destination );
    if ( enabled() && self bot_eligible() && self assignment_valid() && destination == self.outlands_squad_target )
        self acknowledge_goal( "dom_flag" );
}

patrol_choice()
{
    disabledetouronce( level.outlands_squad_selector );
    native = self [[ level.outlands_squad_selector ]]();
    if ( !enabled() || !self bot_eligible() || !self assignment_valid() || self urgent_native() )
        return native;
    if ( self.outlands_squad_role == "support" )
        return native;
    if ( level.outlands_squad_mode == "ctf" )
    {
        // Stolen/dropped flags and carriers keep the stock emergency decision.
        mine = undefined;
        foreach ( flag in level.flags )
        {
            if ( flag [[ level.outlands_squad_owner ]]() == self.team )
                mine = flag;
        }
        if ( !isdefined( mine ) || !mine [[ level.outlands_squad_home ]]() )
            return native;
        return self.outlands_squad_role == "defend";
    }
    if ( level.outlands_squad_mode == "hq" )
    {
        // Native contention checks still control whether an owned HQ is safe.
        if ( self.outlands_squad_role == "attack" )
            return false;
    }
    return native;
}

native_goal_snapshot()
{
    names = [];
    switch ( level.outlands_squad_mode )
    {
        case "dom": names = array( "dom_flag" ); break;
        case "ctf": names = array( "ctf_flag", "ctf_flag_patrol" ); break;
        case "koth": names = array( "koth_hill" ); break;
        case "hq": names = array( "hq_radio", "hq_patrol" ); break;
        case "dem": names = array( "bomb", "dem_guard" ); break;
    }
    target_origin = objective_origin( self.outlands_squad_target );
    if ( !isdefined( target_origin ) )
        return undefined;
    foreach ( name in names )
    {
        origin = self getgoal( name );
        if ( !isdefined( origin ) || distancesquared( origin, target_origin ) > 2359296 )
            continue;
        result = spawnstruct();
        result.name = name;
        result.origin = origin;
        return result;
    }
    return undefined;
}

acknowledge_goal( name )
{
    if ( !self assignment_valid() )
        return;
    origin = self getgoal( name );
    target_origin = objective_origin( self.outlands_squad_target );
    if ( !isdefined( origin ) || !isdefined( target_origin ) || distancesquared( origin, target_origin ) > 2359296 )
    {
        level.outlands_squad_invalid++;
        return;
    }
    self.outlands_squad_goal_name = name;
    self.outlands_squad_goal_valid = 1;
    self.outlands_squad_goal_origin = origin;
    self.outlands_squad_goal_calls++;
    level.outlands_squad_goal_calls++;
    id = self.outlands_squad_target_id;
    seen = false;
    foreach ( previous in level.outlands_squad_targets )
    {
        if ( previous == id )
            seen = true;
    }
    if ( !seen && level.outlands_squad_targets.size < 32 )
        level.outlands_squad_targets[level.outlands_squad_targets.size] = id;
}
