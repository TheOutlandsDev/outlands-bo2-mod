// Original bounded match tendencies. Native roster, combat and navigation remain owners.
#include common_scripts\utility;

start()
{
    if ( !isdedicated() || !getdvarint( "outlands_native_bots" ) || isdefined( level.outlands_rivals_started ) )
        return;
    if ( !getdvarint( "outlands_rivals" ) && !getdvarint( "outlands_rival_metrics" ) )
        return;
    level.outlands_rivals_started = 1;
    seed = getdvarint( "outlands_rival_seed" );
    if ( seed < 1 || seed > 65520 )
        seed = randomintrange( 1, 65521 );
    level.outlands_rival_seed = seed;
    level.outlands_rival_hash = hash_text( getdvar( "mapname" ) + "|" + getdvar( "g_gametype" ), seed );
    level.outlands_rival_ticks = 0;
    level.outlands_rival_goal_changes = 0;
    level.outlands_rival_duty_changes = 0;
    level.outlands_rival_category = getfunction( "maps/mp/_utility", "getweaponclass" );
    level.outlands_rival_native_grant = getfunction( "maps/mp/gametypes/_class", "giveloadout" );
    level.outlands_rival_armory_record = getfunction( "scripts/mp/outlands_armory", "record_for" );
    install_spawn_hook();
    println( "Outlands rivals: observed-roster planner ready; native combat and names retained." );
    level thread observe();
}

install_spawn_hook()
{
    if ( !enabled() || isdefined( level.outlands_rival_spawn_hook ) || !isdefined( level.spawnplayer ) ) return;
    // Compose with the existing spawn callback. Human Armory keeps its own callback.
    level.outlands_rival_stock_spawn = level.spawnplayer;
    level.spawnplayer = ::spawn_wrapper;
    level.outlands_rival_spawn_hook = 1;
}

spawn_wrapper()
{
    self endon( "disconnect" );
    level endon( "game_ended" );
    staged = -1;
    selected = "";
    if ( enabled() && self eligible() && !self custom_class_owned() && getdvarint( "outlands_bot_profiles" ) && isdefined( level.outlands_rival_native_grant ) )
    {
        deadline = gettime() + 2000;
        while ( !isdefined( self.pers["bot_loadout"] ) && gettime() < deadline ) wait 0.05;
        if ( enabled() && isdefined( self.pers["bot_loadout"] ) && isdefined( level.outlands_profiles_classes ) )
        {
            choices = self [[ level.outlands_profiles_classes ]]();
            if ( isdefined( choices ) && choices.size == 1 && isdefined( level.classmap[choices[0]] ) )
            {
                index = scripts\mp\outlands_bot_profiles::class_index( choices[0] );
                if ( index >= 0 && self classisvalid( index ) )
                {
                    self.pers["class"] = level.classmap[choices[0]];
                    self.pers["weapon"] = undefined;
                    staged = index;
                    selected = choices[0];
                }
            }
        }
    }
    self [[ level.outlands_rival_stock_spawn ]]();
    if ( staged >= 0 && enabled() && self eligible() && !self custom_class_owned() && isalive( self ) && isdefined( self.spawntime ) && gettime() - self.spawntime < 500 && isdefined( self.team ) && self classisvalid( staged ) )
    {
        // Use the native grant on a valid bot slot, including preset slots 5-9.
        // The enum/pers request alone can leave respawns on the default gun.
        self.pers["weapon"] = undefined;
        self [[ level.outlands_rival_native_grant ]]( self.team, "CLASS_CUSTOM" + ( staged + 1 ) );
        self thread verify_spawn_class( selected, staged );
    }
}

custom_class_owned()
{
    if ( isdefined( level.givecustomloadout ) && ( !isdefined( level.outlands_armory_hook_ready ) || !level.outlands_armory_hook_ready ) ) return true;
    if ( isdefined( level.outlands_rival_armory_record ) )
    {
        record = [[ level.outlands_rival_armory_record ]]( self );
        if ( isdefined( record ) ) return true;
    }
    return false;
}

verify_spawn_class( selected, index )
{
    self endon( "disconnect" ); self endon( "death" ); level endon( "game_ended" );
    deaths = 0;
    if ( isdefined( self.deaths ) ) deaths = int( self.deaths );
    wait 0.1;
    weapon = self getloadoutweapon( index, "primary" );
    wanted = strtok( weapon, "+" );
    owned = 0; carried = "none";
    foreach ( held in self getweaponslist( 1 ) )
    {
        parts = strtok( held, "+" );
        if ( parts.size && wanted.size && parts[0] == wanted[0] ) { owned = 1; carried = held; }
    }
    self scripts\mp\outlands_loadouts::record_equip( selected, weapon, carried, owned, deaths );
    scripts\mp\outlands_log::emit( "OUTLANDS_RIVAL_SPAWN_V1|" + getdvarint( "outlands_verify_restarted" ) + "|" + ( self getentitynumber() ) + "|" + self.name + "|" + selected + "|" + owned + "|" + deaths );
}

enabled()
{
    return isdedicated() && getdvarint( "outlands_native_bots" ) && getdvarint( "outlands_rivals" ) && isdefined( level.outlands_rival_hash );
}

eligible()
{
    return isdefined( self ) && isplayer( self ) && self istestclient() && isdefined( self.name );
}

hash_text( text, seed )
{
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 ._~-:|";
    value = seed;
    for ( i = 0; i < text.size; i++ )
    {
        code = 0;
        for ( j = 0; j < alphabet.size; j++ )
        {
            if ( getsubstr( text, i, i + 1 ) == getsubstr( alphabet, j, j + 1 ) )
            {
                code = j + 1;
                break;
            }
        }
        value = ( value * 131 + code ) % 65521;
    }
    return value;
}

apply_profile()
{
    if ( !enabled() || !self eligible() )
        return false;
    if ( isdefined( self.outlands_rival_alias ) && self.outlands_rival_alias == self.name )
    {
        return true;
    }
    fields = scripts\mp\outlands_rival_catalog::lookup( self.name );
    if ( !isdefined( fields ) || fields.size != 8 )
        return false;
    value = hash_text( self.name, level.outlands_rival_hash );
    self.outlands_rival_alias = self.name;
    self.outlands_rival_role = fields[1];
    self.outlands_profile_role = fields[1];
    self.outlands_rival_specialty = fields[2];
    self.outlands_rival_tier = fields[3];
    spread = 21;
    if ( fields[3] == "experienced" ) spread = 13;
    if ( fields[3] == "standout" ) spread = 9;
    self.outlands_rival_aggression = int( fields[4] ) + value % spread - int( spread / 2 );
    self.outlands_rival_teamwork = int( fields[5] ) + int( value / 21 ) % spread - int( spread / 2 );
    if ( self.outlands_rival_aggression < 10 ) self.outlands_rival_aggression = 10;
    if ( self.outlands_rival_aggression > 90 ) self.outlands_rival_aggression = 90;
    if ( self.outlands_rival_teamwork < 10 ) self.outlands_rival_teamwork = 10;
    if ( self.outlands_rival_teamwork > 90 ) self.outlands_rival_teamwork = 90;
    self.outlands_rival_route = int( value / 441 ) % 3;
    if ( value % 100 < 70 )
    {
        self.outlands_rival_route = 1;
        if ( fields[6] == "direct" ) self.outlands_rival_route = 0;
        if ( fields[6] == "wide" ) self.outlands_rival_route = 2;
    }
    commit = 14;
    if ( fields[3] == "developing" ) commit = 12;
    if ( fields[3] == "experienced" ) commit = 16;
    self.outlands_rival_commit = commit + value % 5;
    if ( fields[3] == "standout" ) self.outlands_rival_commit = 18 + value % 3;
    self.outlands_rival_priority = hash_text( self.name + ":priority", level.outlands_rival_hash );
    self.outlands_rival_favorites = strtok( fields[7], "," );
    self.outlands_rival_class_sequence = 0;
    self.outlands_rival_star = 0;
    self.outlands_profile_pool_logs = 0;
    self.outlands_profile_patrol_logs = 0;
    if ( !isdefined( self.outlands_rival_danger_watched ) )
    {
        self.outlands_rival_danger_watched = 1;
        self thread remember_danger();
    }
    return true;
}

remember_danger()
{
    self endon( "disconnect" );
    level endon( "game_ended" );
    self.outlands_rival_danger = [];
    turn = 0;
    for (;;)
    {
        self waittill( "death" );
        if ( !self eligible() || !isdefined( self.origin ) ) continue;
        record = spawnstruct();
        record.origin = self.origin;
        record.until = gettime() + 45000;
        self.outlands_rival_danger[turn % 2] = record;
        self.outlands_rival_position_until = 0;
        turn++;
    }
}

perimeter_node( nodes, objective )
{
    // Separate, opt-in three-map experiment. No enemy positions are consulted.
    if ( !enabled() || !getdvarint( "outlands_rival_movement" ) || !self apply_profile() )
        return undefined;
    map = getdvar( "mapname" );
    if ( map != "mp_raid" && map != "mp_hijacked" && map != "mp_carrier" )
        return undefined;
    if ( isdefined( self.outlands_rival_position ) && isdefined( self.outlands_rival_position_objective ) && distancesquared( objective, self.outlands_rival_position_objective ) <= 1 && isdefined( self.outlands_rival_position_until ) && gettime() < self.outlands_rival_position_until )
        if ( findpath( self.origin, self.outlands_rival_position.origin, self, 0, 1 ) )
            return self.outlands_rival_position;
    started = gettime();
    offset = ( ( self getentitynumber() ) + self.outlands_rival_route * 7 ) % nodes.size;
    attempts = nodes.size;
    if ( attempts > 6 ) attempts = 6;
    best = undefined;
    best_cost = 1000000000;
    reachable = 0;
    for ( i = 0; i < attempts; i++ )
    {
        node = nodes[( offset + i ) % nodes.size];
        if ( !isdefined( node ) || !isdefined( node.origin ) || !findpath( self.origin, node.origin, self, 0, 1 ) )
            continue;
        reachable++;
        nearby = 0;
        foreach ( friend in get_players() )
        {
            if ( !isdefined( friend ) || friend == self || !isplayer( friend ) || !isalive( friend ) || !isdefined( friend.team ) || friend.team != self.team )
                continue;
            close = isdefined( friend.origin ) && distancesquared( friend.origin, node.origin ) < 16384;
            if ( friend istestclient() && isdefined( friend.outlands_rival_position ) && isdefined( friend.outlands_rival_position_until ) && gettime() < friend.outlands_rival_position_until )
                if ( distancesquared( friend.outlands_rival_position.origin, node.origin ) < 16384 ) close = true;
            if ( close ) nearby++;
        }
        danger = 0;
        foreach ( record in self.outlands_rival_danger )
            if ( isdefined( record ) && gettime() < record.until && distancesquared( node.origin, record.origin ) < 65536 )
            {
                seconds = int( ( record.until - gettime() ) / 1000 );
                if ( seconds > danger ) danger = seconds;
            }
        travel = int( distancesquared( self.origin, node.origin ) );
        target = int( distancesquared( objective, node.origin ) );
        bias = int( target / 65536 );
        if ( self.outlands_rival_route == 0 ) bias = int( target / 32768 );
        if ( self.outlands_rival_route == 2 ) bias = 0 - bias;
        cost = int( travel / 16384 ) + nearby * 400 + danger * 10 + bias;
        if ( cost < best_cost )
        {
            best = node; best_cost = cost;
            best_nearby = nearby; best_danger = danger; best_travel = travel; best_target = target;
        }
    }
    if ( !isdefined( best ) ) return undefined;
    self.outlands_rival_position = best;
    self.outlands_rival_position_objective = objective;
    self.outlands_rival_position_until = gettime() + self.outlands_rival_commit * 1000;
    scripts\mp\outlands_log::emit( "OUTLANDS_RIVAL_ROUTE_V1|" + ( self getentitynumber() ) + "|" + attempts + "|" + reachable + "|" + best_nearby + "|" + best_danger + "|" + self.outlands_rival_route + "|" + best_travel + "|" + best_target + "|" + best_cost + "|" + ( gettime() - started ) );
    return best;
}

refresh_standouts()
{
    foreach ( team in array( "allies", "axis" ) )
    {
        chosen = undefined;
        foreach ( bot in get_players() )
        {
            if ( !isdefined( bot ) || !bot apply_profile() || !isdefined( bot.team ) || bot.team != team )
                continue;
            bot.outlands_rival_star = 0;
            if ( bot.outlands_rival_specialty != "none" && ( !isdefined( chosen ) || bot.outlands_rival_priority < chosen.outlands_rival_priority || bot.outlands_rival_priority == chosen.outlands_rival_priority && ( bot getentitynumber() ) < ( chosen getentitynumber() ) ) )
                chosen = bot;
        }
        if ( isdefined( chosen ) )
            chosen.outlands_rival_star = 1;
    }
}

emit_plan()
{
    if ( !self eligible() || !isdefined( self.outlands_rival_alias ) || !isdefined( self.team ) || ( self.team != "allies" && self.team != "axis" ) )
        return;
    signature = self.team + "|" + self.outlands_rival_star;
    if ( isdefined( self.outlands_rival_emitted ) && self.outlands_rival_emitted == signature )
        return;
    self.outlands_rival_emitted = signature;
    scripts\mp\outlands_log::emit( "OUTLANDS_RIVAL_PLAN_V1|" + getdvar( "mapname" ) + "|" + getdvar( "g_gametype" ) + "|" + level.outlands_rival_seed + "|" + ( self getentitynumber() ) + "|" + self.name + "|" + self.team + "|" + self.outlands_rival_role + "|" + self.outlands_rival_specialty + "|" + self.outlands_rival_tier + "|" + self.outlands_rival_aggression + "|" + self.outlands_rival_teamwork + "|" + self.outlands_rival_route + "|" + self.outlands_rival_commit + "|" + self.outlands_rival_star );
}

class_pool( choices )
{
    if ( !self apply_profile() || !choices.size )
        return choices;
    self.outlands_rival_class_sequence++;
    total = 0;
    weights = [];
    pool = "";
    foreach ( candidate in choices )
    {
        index = scripts\mp\outlands_bot_profiles::class_index( candidate );
        weight = 4;
        duplicates = 0;
        weapon = "";
        if ( index >= 0 )
            weapon = self getloadoutweapon( index, "primary" );
        if ( isdefined( weapon ) && weapon != "" )
        {
            parts = strtok( weapon, "+" );
            if ( parts.size ) weapon = parts[0];
            for ( favorite_index = 0; favorite_index < self.outlands_rival_favorites.size; favorite_index++ )
                if ( weapon == self.outlands_rival_favorites[favorite_index] )
                    weight += 12 - 4 * favorite_index;
            // Reduce duplication using teammate selections, never enemy loadouts.
            foreach ( other in get_players() )
                if ( isdefined( other ) && other != self && other eligible() && isdefined( other.team ) && isdefined( self.team ) && other.team == self.team && isdefined( other.outlands_rival_selected_primary ) && other.outlands_rival_selected_primary == weapon )
                {
                    duplicates++;
                    weight = int( weight / 2 );
                    if ( weight < 1 ) weight = 1;
                }
        }
        weights[weights.size] = weight;
        total += weight;
        if ( pool != "" ) pool += ",";
        pool += candidate + ":" + weapon + ":" + duplicates + ":" + weight;
    }
    roll = hash_text( self.name + ":class:" + self.outlands_rival_class_sequence, level.outlands_rival_hash ) % total;
    for ( i = 0; i < choices.size; i++ )
    {
        if ( roll < weights[i] )
        {
            index = scripts\mp\outlands_bot_profiles::class_index( choices[i] );
            if ( index >= 0 )
            {
                parts = strtok( self getloadoutweapon( index, "primary" ), "+" );
                if ( parts.size ) self.outlands_rival_selected_primary = parts[0];
            }
            scripts\mp\outlands_log::emit( "OUTLANDS_RIVAL_CLASS_V1|" + level.outlands_rival_seed + "|" + ( self getentitynumber() ) + "|" + self.name + "|" + self.outlands_rival_class_sequence + "|" + choices[i] + "|" + pool );
            // Only return a member of the already native-derived valid pool.
            return array( choices[i] );
        }
        roll -= weights[i];
    }
    return choices;
}

duty_score( duty )
{
    if ( !self apply_profile() )
        return undefined;
    bonus = 0;
    role = self.outlands_rival_role;
    if ( duty == "attack" )
    {
        if ( role == "objective" ) bonus = 70;
        if ( role == "rusher" ) bonus = 55;
        if ( role == "assault" ) bonus = 30;
        if ( role == "support" ) bonus = 10;
        score = self.outlands_rival_aggression + bonus + 30 * self.outlands_rival_star;
    }
    else
    {
        if ( role == "objective" ) bonus = 20;
        if ( role == "assault" ) bonus = 25;
        if ( role == "support" ) bonus = 65;
        if ( role == "marksman" ) bonus = 55;
        score = self.outlands_rival_teamwork + bonus;
    }
    if ( isdefined( self.outlands_squad_role ) )
    {
        if ( self.outlands_squad_role == duty )
            score += 12;
        if ( isdefined( self.outlands_rival_commit_until ) && gettime() < self.outlands_rival_commit_until && self scripts\mp\outlands_squads::assignment_valid() )
        {
            if ( self.outlands_squad_role == duty ) score += 1000;
            else score -= 1000;
        }
    }
    return score;
}

observe()
{
    level endon( "game_ended" );
    wait 1;
    for (;;)
    {
        if ( enabled() )
        {
            install_spawn_hook();
            refresh_standouts();
            foreach ( bot in get_players() )
                if ( isdefined( bot ) && bot apply_profile() )
                    bot emit_plan();
        }
        if ( getdvarint( "outlands_rival_metrics" ) )
            measure();
        wait 2;
    }
}

measure()
{
    // Read-only observations. Low movement alone is never called a path failure.
    bots = 0; planned = 0; moving = 0; travel = 0; stuck = 0; crowded = 0;
    weapons = []; unique = 0; stars_a = 0; stars_b = 0; invalid = 0;
    started = gettime();
    players = get_players();
    foreach ( bot in players )
    {
        if ( !isdefined( bot ) || !bot eligible() )
            continue;
        bots++;
        if ( isdefined( bot.outlands_rival_alias ) && enabled() )
        {
            planned++;
            if ( isdefined( bot.team ) && bot.outlands_rival_star )
            {
                if ( bot.team == "allies" ) stars_a++;
                if ( bot.team == "axis" ) stars_b++;
            }
        }
        if ( !isalive( bot ) || !isdefined( bot.origin ) )
        {
            bot.outlands_rival_stationary = 0;
            bot.outlands_rival_last_origin = undefined;
            continue;
        }
        if ( isdefined( bot.spawntime ) && ( !isdefined( bot.outlands_rival_sample_spawn ) || bot.outlands_rival_sample_spawn != bot.spawntime ) )
        {
            bot.outlands_rival_sample_spawn = bot.spawntime;
            bot.outlands_rival_last_origin = undefined;
            bot.outlands_rival_last_goal = undefined;
            bot.outlands_rival_stationary = 0;
        }
        if ( isdefined( level.outlands_rival_category ) && isdefined( bot.spawntime ) && gettime() - bot.spawntime >= 1000 && !bot isremotecontrolling() )
        {
            // Actual carried primaries: preset class_num may be 10-14, not 0-9.
            primary = false;
            foreach ( held in bot getweaponslist( 1 ) )
            {
                parts = strtok( held, "+" );
                if ( !parts.size ) continue;
                weapon = parts[0];
                group = [[ level.outlands_rival_category ]]( weapon );
                if ( group != "weapon_assault" && group != "weapon_smg" && group != "weapon_lmg" && group != "weapon_sniper" && group != "weapon_cqb" && group != "weapon_shotgun" ) continue;
                primary = true;
                if ( !isdefined( weapons[weapon] ) ) { unique++; weapons[weapon] = 1; }
            }
            if ( !primary )
            {
                invalid++;
                // Bounded bot-only diagnostics retain the actual combat inventory.
                if ( !isdefined( bot.outlands_rival_inventory_logs ) ) bot.outlands_rival_inventory_logs = 0;
                if ( bot.outlands_rival_inventory_logs < 4 )
                {
                    held_text = "";
                    foreach ( item in bot getweaponslist( 1 ) ) held_text += item + ",";
                    scripts\mp\outlands_log::emit( "OUTLANDS_RIVAL_INVENTORY_V1|" + ( bot getentitynumber() ) + "|" + ( gettime() - bot.spawntime ) + "|" + bot.health + "|" + bot getcurrentweapon() + "|" + held_text );
                    bot.outlands_rival_inventory_logs++;
                }
            }
        }
        displaced = false;
        if ( isdefined( bot.outlands_rival_last_origin ) && distancesquared( bot.origin, bot.outlands_rival_last_origin ) > 1024 )
            displaced = true;
        if ( displaced ) moving++;
        goal = undefined;
        foreach ( name in array( "outlands_squad", "dom_flag", "ctf_flag", "ctf_flag_patrol", "koth_hill", "hq_radio", "hq_patrol", "bomb", "dem_guard", "enemy_patrol" ) )
        {
            candidate = bot getgoal( name );
            if ( isdefined( candidate ) ) { goal = candidate; break; }
        }
        wants_travel = isdefined( goal ) && distancesquared( bot.origin, goal ) > 65536;
        in_combat = isdefined( bot.bot ) && isdefined( bot.bot.attacker );
        defending = isdefined( bot.outlands_squad_role ) && bot.outlands_squad_role == "defend";
        if ( wants_travel && !in_combat && !defending )
        {
            travel++;
            if ( !isdefined( bot.outlands_rival_stationary ) || displaced ) bot.outlands_rival_stationary = 0;
            else bot.outlands_rival_stationary += 2;
            if ( bot.outlands_rival_stationary >= 10 ) stuck++;
        }
        else bot.outlands_rival_stationary = 0;
        if ( isdefined( goal ) && isdefined( bot.outlands_rival_last_goal ) && distancesquared( goal, bot.outlands_rival_last_goal ) > 16384 )
            level.outlands_rival_goal_changes++;
        bot.outlands_rival_last_goal = goal;
        bot.outlands_rival_last_origin = bot.origin;
        if ( displaced && isdefined( bot.team ) )
            foreach ( other in players )
                if ( isdefined( other ) && other != bot && other eligible() && isalive( other ) && isdefined( other.team ) && other.team == bot.team && isdefined( other.origin ) && distancesquared( bot.origin, other.origin ) < 4096 )
                    crowded++;
    }
    level.outlands_rival_ticks++;
    scripts\mp\outlands_log::emit( "OUTLANDS_RIVAL_METRICS_V1|" + getdvarint( "outlands_verify_restarted" ) + "|" + level.outlands_rival_ticks + "|" + bots + "|" + planned + "|" + unique + "|" + stars_a + "|" + stars_b + "|" + moving + "|" + travel + "|" + stuck + "|" + crowded + "|" + level.outlands_rival_goal_changes + "|" + level.outlands_rival_duty_changes + "|" + ( gettime() - started ) + "|" + invalid );
}
