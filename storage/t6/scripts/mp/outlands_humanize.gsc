// Optional native combat tuning and short objective holds. No human inputs/stats.
#include common_scripts\utility;

start()
{
    if ( !isdedicated() || !getdvarint( "outlands_native_bots" ) || isdefined( level.outlands_human_started ) ) return;
    if ( !getdvarint( "outlands_bot_humanize" ) && !getdvarint( "outlands_bot_objective_roam" ) && !getdvarint( "outlands_human_metrics" ) ) return;
    level.outlands_human_started = 1;
    level.outlands_human_stage = getdvarint( "outlands_verify_restarted" );
    level.outlands_ai_preset = scripts\mp\outlands_human_catalog::preset_name( getdvar( "outlands_ai_preset" ) );
    println( "Outlands AI: match preset=" + level.outlands_ai_preset );
    level.outlands_human_difficulty_calls = 0;
    level.outlands_human_aim_calls = 0;
    level.outlands_human_look_calls = 0;
    level.outlands_human_repositions = 0;
    level.outlands_human_arrivals = 0;
    level.outlands_human_ticks = 0;
    if ( getdvarint( "outlands_bot_humanize" ) ) install_hooks();
    level thread observe();
}

enabled()
{
    return getdvarint( "outlands_native_bots" ) && getdvarint( "outlands_bot_humanize" ) && isdefined( level.outlands_human_hooks );
}

eligible()
{
    return isdefined( self ) && isplayer( self ) && self istestclient() && isdefined( self.name );
}

tuning()
{
    if ( !self eligible() ) return undefined;
    if ( isdefined( self.outlands_human_tuning_name ) && self.outlands_human_tuning_name == self.name ) return self.outlands_human_tuning;
    fields = scripts\mp\outlands_rival_catalog::lookup( self.name );
    if ( !isdefined( fields ) || fields.size != 8 ) return undefined;
    // Native difficulty, convergence ms, correction rate, error, smoothing ms,
    // native thinking interval and native FOV threshold. Never Veteran/fu.
    result = scripts\mp\outlands_human_catalog::combat( fields[3], level.outlands_ai_preset );
    if ( isdefined( result ) )
    {
        result[5] = 0.2; result[6] = -0.1736;
        if ( result[0] == "easy" ) { result[5] = 0.5; result[6] = 0.4226; }
        if ( result[0] == "normal" ) { result[5] = 0.25; result[6] = 0.0872; }
    }
    if ( isdefined( result ) )
    {
        self.outlands_human_tuning_name = self.name;
        self.outlands_human_tuning = result;
    }
    return result;
}

install_hooks()
{
    level.outlands_human_difficulty = getfunction( "maps/mp/bots/_bot", "bot_get_difficulty" );
    level.outlands_human_converge = getfunction( "maps/mp/bots/_bot_combat", "bot_get_converge_time" );
    level.outlands_human_rate = getfunction( "maps/mp/bots/_bot_combat", "bot_get_converge_rate" );
    level.outlands_human_error = getfunction( "maps/mp/bots/_bot_combat", "bot_get_aim_error" );
    level.outlands_human_look = getfunction( "maps/mp/bots/_bot_combat", "bot_update_lookat" );
    foreach ( pointer in array( level.outlands_human_difficulty, level.outlands_human_converge, level.outlands_human_rate, level.outlands_human_error, level.outlands_human_look ) )
    {
        if ( !isdefined( pointer ) || isdefined( getdetour( pointer ) ) )
        {
            println( "Outlands humanization: native helper missing or owned; native fallback." );
            return;
        }
    }
    replacefunc( level.outlands_human_difficulty, ::difficulty );
    replacefunc( level.outlands_human_converge, ::converge );
    replacefunc( level.outlands_human_rate, ::correction_rate );
    replacefunc( level.outlands_human_error, ::aim_error );
    replacefunc( level.outlands_human_look, ::combat_look );
    level.outlands_human_hooks = 1;
    println( "Outlands humanization: guarded native combat helpers ready." );
}

difficulty()
{
    p = undefined;
    if ( enabled() ) p = self tuning();
    if ( isdefined( p ) )
    {
        level.outlands_human_difficulty_calls++;
        self.outlands_human_touched = 1;
        return p[0];
    }
    disabledetouronce( level.outlands_human_difficulty );
    return self [[ level.outlands_human_difficulty ]]();
}

converge()
{
    p = undefined;
    if ( enabled() ) p = self tuning();
    if ( isdefined( p ) ) { level.outlands_human_aim_calls++; return p[1]; }
    disabledetouronce( level.outlands_human_converge );
    return self [[ level.outlands_human_converge ]]();
}

correction_rate()
{
    p = undefined;
    if ( enabled() ) p = self tuning();
    if ( isdefined( p ) ) return p[2];
    disabledetouronce( level.outlands_human_rate );
    return self [[ level.outlands_human_rate ]]();
}

aim_error()
{
    p = undefined;
    if ( enabled() ) p = self tuning();
    if ( isdefined( p ) ) return p[3];
    disabledetouronce( level.outlands_human_error );
    return self [[ level.outlands_human_error ]]();
}

combat_look( origin, frac )
{
    p = undefined;
    if ( enabled() ) p = self tuning();
    filtered = origin;
    if ( isdefined( p ) && isdefined( origin ) && isalive( self ) && isdefined( self.bot ) && isdefined( self.bot.threat ) && isdefined( self.bot.threat.entity ) )
    {
        now = gettime();
        if ( !isdefined( self.outlands_human_look_time ) || now - self.outlands_human_look_time > 1000 || !isdefined( self.outlands_human_look_entity ) || self.outlands_human_look_entity != self.bot.threat.entity || !isdefined( self.outlands_human_look_spawn ) || self.outlands_human_look_spawn != self.spawntime )
        {
            camera = self getplayercamerapos();
            forward = anglestoforward( self getplayerangles() );
            self.outlands_human_look_origin = camera + vectorscale( forward, distance( camera, origin ) );
            self.outlands_human_look_time = now - 50;
        }
        elapsed = now - self.outlands_human_look_time;
        blend = elapsed / ( p[4] * 1.0 );
        if ( blend < 0.1 ) blend = 0.1;
        if ( blend > 0.75 ) blend = 0.75;
        previous = self.outlands_human_look_origin;
        filtered = previous + vectorscale( origin - previous, blend );
        if ( getdvarint( "outlands_human_metrics" ) && ( !isdefined( self.outlands_human_aim_traces ) || self.outlands_human_aim_traces < 2 ) && distancesquared( previous, origin ) > 100 )
        {
            if ( !isdefined( self.outlands_human_aim_traces ) ) self.outlands_human_aim_traces = 0;
            scripts\mp\outlands_log::emit( "OUTLANDS_HUMAN_AIM_V1|" + level.outlands_human_stage + "|" + ( self getentitynumber() ) + "|" + elapsed + "|" + p[4] + "|" + int( blend * 1000 ) + "|" + int( distancesquared( previous, origin ) ) + "|" + int( distancesquared( previous, filtered ) ) );
            self.outlands_human_aim_traces++;
        }
        self.outlands_human_look_origin = filtered;
        self.outlands_human_look_time = now;
        self.outlands_human_look_entity = self.bot.threat.entity;
        self.outlands_human_look_spawn = self.spawntime;
        level.outlands_human_look_calls++;
    }
    disabledetouronce( level.outlands_human_look );
    self [[ level.outlands_human_look ]]( filtered, frac );
}

global_tuning()
{
    names = array( "bot_YawSpeed", "bot_MinReactionTime", "bot_MaxReactionTime" );
    preset = scripts\mp\outlands_human_catalog::engine( level.outlands_ai_preset );
    values = array( "" + preset[0], "" + preset[1], "" + preset[2] );
    if ( enabled() && !isdefined( level.outlands_human_saved ) )
    {
        level.outlands_human_saved = [];
        for ( i = 0; i < names.size; i++ )
        {
            level.outlands_human_saved[i] = getdvar( names[i] );
            setdvar( names[i], values[i] );
        }
        scripts\mp\outlands_log::emit( "OUTLANDS_HUMAN_NATIVE_V1|" + level.outlands_human_stage + "|" + int( getdvarfloat( "bot_YawSpeed" ) * 100 + 0.5 ) + "|" + getdvarint( "bot_MinReactionTime" ) + "|" + getdvarint( "bot_MaxReactionTime" ) );
    }
    if ( !enabled() && isdefined( level.outlands_human_saved ) )
    {
        for ( i = 0; i < names.size; i++ )
            if ( getdvar( names[i] ) == values[i] ) setdvar( names[i], level.outlands_human_saved[i] );
        level.outlands_human_saved = undefined;
    }
}

// A new position within the same guard assignment, after a short arrived hold.
// No second movement thread, enemy scan or intervention during combat.
roam_node( nodes, objective )
{
    if ( !getdvarint( "outlands_bot_objective_roam" ) || !self eligible() || !isdefined( self.team ) || !nodes.size ) return undefined;
    now = gettime();
    if ( !isdefined( self.outlands_human_roam_objective ) || distancesquared( objective, self.outlands_human_roam_objective ) > 1 || !isdefined( self.outlands_human_roam_spawn ) || self.outlands_human_roam_spawn != self.spawntime )
    {
        self.outlands_human_roam_objective = objective;
        self.outlands_human_roam_spawn = self.spawntime;
        self.outlands_human_roam_node = undefined;
        self.outlands_human_roam_hold = undefined;
        self.outlands_human_roam_phase = 0;
    }
    settings = scripts\mp\outlands_human_catalog::guard( level.outlands_ai_preset );
    hold_ms = settings[0] + ( ( self getentitynumber() ) % 4 ) * int( ( settings[1] - settings[0] ) / 3 );
    step_sq = settings[3] * settings[3];
    cause = 0; dwell = 0;
    if ( isdefined( self.outlands_human_roam_node ) )
    {
        if ( self atgoal( "outlands_squad" ) )
        {
            if ( !isdefined( self.outlands_human_roam_hold ) )
            {
                self.outlands_human_roam_hold = now + hold_ms;
                level.outlands_human_arrivals++;
            }
            if ( now < self.outlands_human_roam_hold ) return self.outlands_human_roam_node;
            cause = 1;
            dwell = now - self.outlands_human_roam_hold + hold_ms;
        }
        else if ( now - self.outlands_human_roam_selected < settings[2] ) return self.outlands_human_roam_node;
        else cause = 2;
    }
    self.outlands_human_roam_phase++;
    // Prefer a nearby alternate post. Arbitrary far-side posts can consume the
    // whole travel budget on narrow, busy maps. Rank locally before path probes.
    candidates = [];
    foreach ( node in nodes )
    {
        if ( !isdefined( node ) || !isdefined( node.origin ) || distancesquared( self.origin, node.origin ) < step_sq ) continue;
        if ( isdefined( self.outlands_human_roam_node ) && distancesquared( node.origin, self.outlands_human_roam_node.origin ) < step_sq ) continue;
        candidates[candidates.size] = node;
    }
    tried = [];
    attempts = candidates.size;
    if ( attempts > 12 ) attempts = 12;
    for ( i = 0; i < attempts; i++ )
    {
        best = -1; cost = 999999999;
        for ( j = 0; j < candidates.size; j++ )
        {
            if ( isdefined( tried[j] ) ) continue;
            // Small deterministic variation cannot outweigh a long commute.
            score = distancesquared( self.origin, candidates[j].origin ) + ( ( j + self.outlands_human_roam_phase * 7 + ( self getentitynumber() ) ) % 5 ) * 1024;
            if ( score < cost ) { best = j; cost = score; }
        }
        if ( best < 0 ) return undefined;
        node = candidates[best];
        tried[best] = 1;
        if ( !findpath( self.origin, node.origin, self, 0, 1 ) ) continue;
        self.outlands_human_roam_node = node;
        self.outlands_human_roam_selected = now;
        self.outlands_human_roam_hold = undefined;
        level.outlands_human_repositions++;
        scripts\mp\outlands_log::emit( "OUTLANDS_HUMAN_ROAM_V1|" + ( self getentitynumber() ) + "|" + int( distancesquared( self.origin, node.origin ) ) + "|" + int( distancesquared( node.origin, objective ) ) + "|" + cause + "|" + dwell );
        return node;
    }
    return undefined;
}

observe()
{
    level endon( "game_ended" );
    wait 1;
    for (;;)
    {
        global_tuning();
        bots = 0; tuned = 0; holds = 0; samples = 0; large = 0; peak = 0;
        foreach ( bot in get_players() )
        {
            if ( !isdefined( bot ) || !bot eligible() ) continue;
            bots++;
            p = bot tuning();
            if ( enabled() && isdefined( p ) )
            {
                tuned++;
                if ( isdefined( bot.bot ) ) { bot.bot.think_interval = p[5]; bot.bot.fov = p[6]; }
                if ( !isdefined( bot.outlands_human_profile_logged ) )
                {
                    scripts\mp\outlands_log::emit( "OUTLANDS_HUMAN_PROFILE_V1|" + level.outlands_human_stage + "|" + ( bot getentitynumber() ) + "|" + bot.name + "|" + p[0] + "|" + p[1] + "|" + p[2] + "|" + p[3] + "|" + p[4] );
                    bot.outlands_human_profile_logged = 1;
                }
            }
            else if ( isdefined( bot.outlands_human_touched ) && isdefined( bot.bot ) )
            {
                bot.bot.think_interval = 0.25; bot.bot.fov = 0.0872;
                if ( level.bot_difficulty == "easy" ) { bot.bot.think_interval = 0.5; bot.bot.fov = 0.4226; }
                if ( level.bot_difficulty == "hard" ) { bot.bot.think_interval = 0.2; bot.bot.fov = -0.1736; }
                if ( level.bot_difficulty == "fu" ) { bot.bot.think_interval = 0.1; bot.bot.fov = -0.9396; }
                bot.outlands_human_touched = undefined;
            }
            if ( !isalive( bot ) ) { bot.outlands_human_yaw = undefined; continue; }
            if ( bot atgoal( "outlands_squad" ) || bot atgoal( "hq_patrol" ) || bot atgoal( "hq_radio" ) || bot atgoal( "koth_hill" ) || bot atgoal( "dom_flag" ) ) holds++;
            angles = bot getplayerangles();
            if ( isdefined( bot.outlands_human_yaw ) && isdefined( bot.outlands_human_yaw_spawn ) && bot.outlands_human_yaw_spawn == bot.spawntime )
            {
                delta = angles[1] - bot.outlands_human_yaw;
                if ( delta < 0 ) delta = 0 - delta;
                if ( delta > 180 ) delta = 360 - delta;
                samples++;
                if ( delta > 90 ) large++;
                if ( delta > peak ) peak = int( delta );
            }
            bot.outlands_human_yaw = angles[1];
            bot.outlands_human_yaw_spawn = bot.spawntime;
        }
        level.outlands_human_ticks++;
        if ( getdvarint( "outlands_human_metrics" ) )
            scripts\mp\outlands_log::emit( "OUTLANDS_HUMAN_METRICS_V1|" + level.outlands_human_stage + "|" + level.outlands_human_ticks + "|" + bots + "|" + tuned + "|" + level.outlands_human_difficulty_calls + "|" + level.outlands_human_aim_calls + "|" + level.outlands_human_look_calls + "|" + level.outlands_human_repositions + "|" + level.outlands_human_arrivals + "|" + holds + "|" + samples + "|" + large + "|" + peak );
        wait 0.5;
    }
}
