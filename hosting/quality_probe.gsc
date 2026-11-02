// Original read-only bot quality probe. Installed only in disposable verification.
#include common_scripts\utility;

init()
{
    if ( !isdedicated() || getdvar( "outlands_backend_verification" ) != "1" || getdvar( "outlands_verify_quality" ) != "1" || getdvar( "net_ip" ) != "127.0.0.1" ) return;
    level thread observe();
}

eligible()
{
    return isdefined( self ) && isplayer( self ) && self istestclient();
}

emit( text )
{
    println( "\n" + text + "\n" );
}

bullet_weapon( weapon )
{
    if ( !isdefined( weapon ) || weapon == "none" || weapon == "" ) return false;
    group = weaponclass( weapon );
    return group == "rifle" || group == "smg" || group == "mg" || group == "spread" || group == "pistol" || group == "sniper";
}

fire_events()
{
    self endon( "disconnect" ); level endon( "game_ended" );
    for (;;)
    {
        self waittill( "weapon_fired", weapon );
        if ( !isalive( self ) || !bullet_weapon( weapon ) ) continue;
        self.outlands_q["shots"]++;
        if ( isdefined( self.outlands_q_target ) && !self.outlands_q_first_shot )
        {
            latency = gettime() - self.outlands_q_seen;
            self.outlands_q_first_shot = 1;
            self.outlands_q["first_shots"]++;
            self.outlands_q["shot_latency_sum"] += latency;
            emit( "OUTLANDS_QUALITY_LATENCY_V1|" + level.outlands_q_stage + "|" + ( self getentitynumber() ) + "|shot|" + latency + "|" + self.outlands_q["first_shots"] );
        }
    }
}

damage_events()
{
    self endon( "disconnect" ); level endon( "game_ended" );
    for (;;)
    {
        self waittill( "damage", damage, attacker, direction, point, mod, unused1, unused2, unused3, weapon );
        if ( !isdefined( attacker ) || !attacker eligible() || attacker == self || !isdefined( attacker.outlands_q ) || !bullet_weapon( weapon ) || !isdefined( self.team ) || !isdefined( attacker.team ) || self.team == attacker.team ) continue;
        attacker.outlands_q["hits"]++;
        attacker.outlands_q["damage"] += int( damage );
        if ( isdefined( attacker.outlands_q_target ) && attacker.outlands_q_target == self && !attacker.outlands_q_first_hit )
        {
            latency = gettime() - attacker.outlands_q_seen;
            attacker.outlands_q_first_hit = 1;
            attacker.outlands_q["first_hits"]++;
            attacker.outlands_q["hit_latency_sum"] += latency;
            emit( "OUTLANDS_QUALITY_LATENCY_V1|" + level.outlands_q_stage + "|" + ( attacker getentitynumber() ) + "|hit|" + latency + "|" + attacker.outlands_q["first_hits"] );
        }
    }
}

objective_zone()
{
    if ( getdvar( "g_gametype" ) == "dom" && isdefined( level.flags ) )
        foreach ( flag in level.flags )
            if ( isdefined( flag ) && isdefined( flag.origin ) && isdefined( flag.radius ) && distancesquared( self.origin, flag.origin ) <= flag.radius * flag.radius ) return true;
    if ( getdvar( "g_gametype" ) == "koth" && isdefined( level.zone ) && isdefined( level.zone.gameobject ) && isdefined( level.zone.gameobject.curorigin ) && isdefined( level.zone.trig ) && isdefined( level.zone.trig.goal_radius ) )
        return distancesquared( self.origin, level.zone.gameobject.curorigin ) <= level.zone.trig.goal_radius * level.zone.trig.goal_radius;
    return false;
}

observe()
{
    level endon( "game_ended" );
    level.outlands_q_stage = getdvarint( "outlands_verify_restarted" );
    fields = array( "alive_ms", "moving_ms", "threat_ms", "visible_ms", "on_target_ms", "objective_ms", "idle_travel_ms", "shots", "hits", "damage", "first_shots", "shot_latency_sum", "first_hits", "hit_latency_sum", "distance_units", "crowded_ms", "goal_changes" );
    goals = array( "outlands_squad", "dom_flag", "koth_hill", "hq_radio", "hq_patrol", "ctf_flag", "ctf_flag_patrol", "bomb", "dem_guard", "wander" );
    tick = 0; previous = gettime(); started = previous;
    for (;;)
    {
        wait 0.25;
        now = gettime(); dt = now - previous; previous = now;
        // A long loading stall is not attributed to AI movement or combat.
        if ( dt < 1 || dt > 1000 ) continue;
        players = get_players();
        foreach ( bot in players )
        {
            if ( !bot eligible() ) continue;
            if ( !isdefined( bot.outlands_q ) )
            {
                bot.outlands_q = [];
                foreach ( key in fields ) bot.outlands_q[key] = 0;
                bot.outlands_q_idle_since = 0;
                bot.outlands_q_first_shot = 0; bot.outlands_q_first_hit = 0;
                bot thread fire_events(); bot thread damage_events();
            }
            if ( !isalive( bot ) )
            {
                bot.outlands_q_origin = undefined; bot.outlands_q_target = undefined;
                bot.outlands_q_idle_since = 0;
                continue;
            }
            bot.outlands_q["alive_ms"] += dt;
            same_life = isdefined( bot.outlands_q_spawn ) && bot.outlands_q_spawn == bot.spawntime;
            step = 0;
            if ( same_life && isdefined( bot.outlands_q_origin ) ) step = distance( bot.origin, bot.outlands_q_origin );
            bot.outlands_q_origin = bot.origin; bot.outlands_q_spawn = bot.spawntime;
            if ( step > 2 && step < 512 )
            {
                bot.outlands_q["moving_ms"] += dt;
                bot.outlands_q["distance_units"] += int( step );
            }
            zone = bot objective_zone();
            if ( zone ) bot.outlands_q["objective_ms"] += dt;
            target = undefined;
            if ( isdefined( bot.bot ) && isdefined( bot.bot.threat ) && isdefined( bot.bot.threat.entity ) )
            {
                enemy = bot.bot.threat.entity;
                if ( isplayer( enemy ) && isalive( enemy ) ) target = enemy;
            }
            changed = !same_life || !isdefined( bot.outlands_q_target ) || !isdefined( target ) || bot.outlands_q_target != target;
            if ( isdefined( target ) && ( changed || !isdefined( bot.outlands_q_target_spawn ) || bot.outlands_q_target_spawn != target.spawntime ) )
            {
                bot.outlands_q_seen = now; bot.outlands_q_first_shot = 0; bot.outlands_q_first_hit = 0;
                bot.outlands_q_target_spawn = target.spawntime;
            }
            bot.outlands_q_target = target;
            if ( isdefined( target ) )
            {
                bot.outlands_q["threat_ms"] += dt;
                if ( isdefined( bot.bot.threat.time_recent_sight ) && now - bot.bot.threat.time_recent_sight <= 250 )
                {
                    bot.outlands_q["visible_ms"] += dt;
                    direction = vectornormalize( ( target getplayercamerapos() ) - ( bot getplayercamerapos() ) );
                    dot = vectordot( anglestoforward( bot getplayerangles() ), direction );
                    if ( dot >= 0.98 ) bot.outlands_q["on_target_ms"] += dt;
                }
            }
            goal = undefined; reached = false;
            foreach ( name in goals )
            {
                location = bot getgoal( name );
                if ( isdefined( location ) ) { goal = location; reached = bot atgoal( name ); break; }
            }
            if ( isdefined( goal ) && isdefined( bot.outlands_q_goal ) && same_life && distancesquared( goal, bot.outlands_q_goal ) > 16384 ) bot.outlands_q["goal_changes"]++;
            bot.outlands_q_goal = goal;
            candidate = same_life && isdefined( goal ) && !reached && !zone && !isdefined( target ) && step <= 2 && !bot isremotecontrolling();
            if ( candidate )
            {
                if ( !bot.outlands_q_idle_since ) bot.outlands_q_idle_since = now;
                if ( now - bot.outlands_q_idle_since >= 3000 ) bot.outlands_q["idle_travel_ms"] += dt;
            }
            else bot.outlands_q_idle_since = 0;
            if ( step > 2 && step < 512 )
                foreach ( other in players )
                    if ( isdefined( other ) && other != bot && other eligible() && isalive( other ) && isdefined( other.team ) && other.team == bot.team && distancesquared( bot.origin, other.origin ) < 4096 ) { bot.outlands_q["crowded_ms"] += dt; break; }
        }
        tick++;
        if ( tick % 20 == 0 )
            foreach ( bot in players )
            {
                if ( !bot eligible() || !isdefined( bot.outlands_q ) ) continue;
                text = "OUTLANDS_QUALITY_V1|" + level.outlands_q_stage + "|" + tick + "|" + ( bot getentitynumber() ) + "|" + ( now - started );
                foreach ( key in fields ) text += "|" + bot.outlands_q[key];
                kills = 0; deaths = 0;
                if ( isdefined( bot.kills ) ) kills = bot.kills;
                if ( isdefined( bot.deaths ) ) deaths = bot.deaths;
                emit( text + "|" + kills + "|" + deaths );
            }
    }
}
