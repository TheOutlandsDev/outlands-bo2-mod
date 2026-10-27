// Original backend-only integration probe, installed only into disposable state.
// This file is never part of the live mod payload. It does not invent humans,
// award XP, change DDL or bypass native match-start notifications.
#include common_scripts\utility;

main()
{
    if ( !isdedicated() || getdvar( "outlands_backend_verification" ) != "1" || getdvar( "net_ip" ) != "127.0.0.1" )
        return;
    // The native gametype consumes these settings before normal match startup.
    setgametypesetting( "prematchperiod", 0 );
    setgametypesetting( "preroundperiod", 0 );
}

init()
{
    if ( !isdedicated() || getdvar( "outlands_backend_verification" ) != "1" || getdvar( "net_ip" ) != "127.0.0.1" )
        return;
    level.outlands_verify_completed = 0;
    level.outlands_verify_sequence = 0;
    level thread verify_native_match();
    level thread observe_native_end();
}

verify_native_match()
{
    level endon( "game_ended" );
    wait 8;
    target = 16;
    if ( getdvarint( "sv_maxclients" ) < target )
        target = getdvarint( "sv_maxclients" );
    players = get_players();
    count = 0;
    foreach ( player in players )
        if ( isdefined( player ) && isplayer( player ) && player istestclient() )
            count++;
    if ( count < target )
        cmdexec( "spawnbot " + ( target - count ) );
    // A fresh native baseline makes within-stage completion evidence possible
    // even if the first short contract finishes before the ten-second sample.
    sample( "sample" );
    if ( getdvarint( "outlands_verify_lobby" ) )
        level thread verify_lobby_balance();
    if ( getdvarint( "outlands_verify_air" ) )
        level thread verify_air_response();
    if ( getdvarint( "outlands_verify_expansion" ) )
        level thread verify_expansion();
    if ( getdvarint( "outlands_verify_ui" ) )
        level thread verify_ui();
    if ( getdvarint( "outlands_verify_armory" ) )
        level thread verify_armory();
    if ( getdvarint( "outlands_verify_armory_editor" ) )
        level thread verify_armory_editor();

    duration = getdvarint( "outlands_verify_seconds" );
    if ( duration < 30 )
        duration = 30;
    if ( duration > 300 )
        duration = 300;
    elapsed = 0;
    while ( elapsed < duration )
    {
        wait 10;
        elapsed += 10;
        if ( getdvarint( "outlands_verify_switches" ) )
        {
            if ( elapsed == 30 )
            {
                setdvar( "outlands_squads", 0 );
                setdvar( "outlands_contracts", 0 );
            }
            if ( elapsed == 40 )
                switch_sample( "disabled_start" );
            if ( elapsed == 50 )
                switch_sample( "disabled_end" );
            if ( elapsed == 60 )
            {
                setdvar( "outlands_squads", 1 );
                setdvar( "outlands_contracts", 1 );
            }
            if ( elapsed == 80 )
                switch_sample( "resumed" );
        }
        sample( "sample" );
    }
    level.outlands_verify_completed = 1;
    sample( "complete" );
    request_restart();
}

switch_sample( phase )
{
    kills = 0;
    roles = 0;
    owned_goals = 0;
    contract_kills = 0;
    contract_score = 0;
    completed = 0;
    foreach ( bot in get_players() )
    {
        if ( !isdefined( bot ) || !isplayer( bot ) || !bot istestclient() )
            continue;
        if ( isdefined( bot.kills ) )
            kills += bot.kills;
        if ( isdefined( bot.outlands_squad_role ) && bot.outlands_squad_role != "" )
            roles++;
        if ( isdefined( bot getgoal( "outlands_squad" ) ) )
            owned_goals++;
    }
    foreach ( team in array( "allies", "axis" ) )
    {
        contract_kills += level.outlands_contracts_delta_kills[team];
        contract_score += level.outlands_contracts_delta_score[team];
        completed += level.outlands_contracts_completed[team];
    }
    println( "OUTLANDS_SWITCH_V1|" + phase + "|" + kills + "|" + roles + "|" + owned_goals + "|" + level.outlands_contracts_active + "|" + contract_kills + "|" + contract_score + "|" + completed + "|" + level.outlands_squad_goal_calls );
}

observe_native_end()
{
    level waittill( "game_ended" );
    if ( level.outlands_verify_completed )
        return;
    wait 0.05;
    level.outlands_verify_completed = 1;
    sample( "complete" );
    request_restart();
}

request_restart()
{
    if ( getdvarint( "outlands_verify_restart" ) && !getdvarint( "outlands_verify_restarted" ) )
    {
        setdvar( "outlands_verify_restarted", 1 );
        println( "OUTLANDS_VERIFY_V1|restart_requested" );
        wait 2;
        // Full same-map reload, not a halftime/round-preserving restart.
        // map_restart variants can leave all-bot FFA occupants unspawned.
        cmdexec( "map " + getdvar( "mapname" ) );
    }
}

sample( kind )
{
    bots = 0;
    humans = 0;
    alive = 0;
    playing = 0;
    identities = 0;
    roles = 0;
    careers = 0;
    kills = 0;
    deaths = 0;
    score = 0;
    moved = 0;
    invalid = 0;
    pools = 0;
    patrols = 0;
    players = get_players();
    foreach ( bot in players )
    {
        if ( !isdefined( bot ) || !isplayer( bot ) )
            continue;
        if ( !bot istestclient() )
        {
            humans++;
            continue;
        }
        bots++;
        if ( isalive( bot ) )
            alive++;
        if ( isdefined( bot.sessionstate ) && bot.sessionstate == "playing" )
            playing++;
        if ( isdefined( bot.outlands_identity_ready ) )
            identities++;
        if ( isdefined( bot.outlands_profile_role ) )
            roles++;
        if ( isdefined( bot.outlands_career_ready ) )
            careers++;
        if ( isdefined( bot.kills ) )
            kills += bot.kills;
        if ( isdefined( bot.deaths ) )
            deaths += bot.deaths;
        if ( isdefined( bot.score ) )
            score += bot.score;
        if ( isdefined( bot.outlands_profile_pool_logs ) && bot.outlands_profile_pool_logs > 0 )
            pools++;
        if ( isdefined( bot.outlands_profile_patrol_logs ) && bot.outlands_profile_patrol_logs > 0 )
            patrols++;
        if ( isdefined( bot.outlands_cosmetic_level ) && ( bot.outlands_cosmetic_level < 1 || bot.outlands_cosmetic_level > 55 ) )
            invalid++;
        if ( isdefined( bot.origin ) )
        {
            if ( !isdefined( bot.outlands_verify_origin ) )
                bot.outlands_verify_origin = bot.origin;
            else if ( distancesquared( bot.origin, bot.outlands_verify_origin ) > 4096 )
                moved++;
        }
    }
    prematch = -1;
    if ( isdefined( level.inprematchperiod ) )
        prematch = level.inprematchperiod;
    level.outlands_verify_sequence++;
    if ( getdvarint( "outlands_verify_chat_context" ) )
        sample_chat_context( players );
    println( "OUTLANDS_VERIFY_V2|" + kind + "|" + getdvar( "mapname" ) + "|" + getdvar( "g_gametype" ) + "|" + getdvarint( "outlands_verify_restarted" ) + "|" + bots + "|" + humans + "|" + alive + "|" + playing + "|" + identities + "|" + roles + "|" + careers + "|" + kills + "|" + deaths + "|" + score + "|" + moved + "|" + prematch + "|" + invalid + "|" + pools + "|" + patrols + "|" + getgametypesetting( "scorelimit" ) + "|" + feature_fields( players ) );
}

sample_chat_context( players )
{
    context_function = getfunction( "scripts/mp/outlands_chat", "task_context" );
    request_function = getfunction( "scripts/mp/outlands_chat", "request_chat" );
    team_function = getfunction( "scripts/mp/outlands_chat", "chat_team" );
    if ( !isdefined( context_function ) || !isdefined( request_function ) )
        return;
    seen = [];
    count = 0;
    foreach ( bot in players )
    {
        if ( !isdefined( bot ) || !isplayer( bot ) || !bot istestclient() || !isdefined( bot.name ) || !isdefined( bot.sessionstate ) || bot.sessionstate != "playing" )
            continue;
        foreach ( topic in array( "squad", "objective", "contract" ) )
        {
            context = [[ context_function ]]( bot, topic );
            role = "none";
            if ( isdefined( bot.outlands_squad_role ) )
                role = bot.outlands_squad_role;
            key = context.team + "_" + context.topic + "_" + role;
            if ( context.topic == "none" || isdefined( seen[key] ) || count >= 12 )
                continue;
            seen[key] = 1;
            count++;
            println( "OUTLANDS_CONTEXT_V1|" + ( bot getentitynumber() ) + "|" + bot.name + "|" + getdvar( "mapname" ) + "|" + getdvar( "g_gametype" ) + "|" + context.wire );
        }
        if ( !isdefined( level.outlands_context_primitive ) )
        {
            // Exercise the production zero-human refusal without a fake client.
            accepted = [[ request_function ]]( "banter", "match", "A current team task.", "", "contract" );
            if ( accepted || isdefined( level.outlands_chat_pending ) )
                println( "OUTLANDS_CHAT_GUARD_V1|failed" );
            else
                println( "OUTLANDS_CHAT_GUARD_V1|rejected" );
            setting = getdvarint( "outlands_chat_tactical" );
            setdvar( "outlands_chat_tactical", 0 );
            disabled = [[ context_function ]]( bot, "contract" );
            disabled_team = [[ team_function ]]( bot );
            if ( disabled_team == bot.pers["team"] && disabled_team != "none" )
                println( "OUTLANDS_CHAT_GUARD_V1|team_binding" );
            setdvar( "outlands_chat_tactical", setting );
            if ( disabled.wire == "none|none|none|-1|none|none|0|0|0|0|0" )
                println( "OUTLANDS_CHAT_GUARD_V1|context_disabled" );
            valid = getfunction( "scripts/mp/outlands_squads", "assignment_valid" );
            if ( isdefined( level.outlands_squads_started ) && isdefined( bot.outlands_squad_team ) && isdefined( valid ) )
            {
                // Same-frame rejected metadata fixture, with no native team,
                // score, goal, human-presence or progression mutation.
                original_team = bot.outlands_squad_team;
                bot.outlands_squad_team = "outlands_verification_stale";
                stale_valid = bot [[ valid ]]();
                stale_context = [[ context_function ]]( bot, "squad" );
                bot.outlands_squad_team = original_team;
                if ( !stale_valid && stale_context.topic == "none" )
                    println( "OUTLANDS_CHAT_GUARD_V1|stale_assignment" );
                else
                    println( "OUTLANDS_CHAT_GUARD_V1|failed" );
            }
            // A direct native primitive test is separate from production chat.
            // This probe exists only in network-isolated disposable storage.
            bot sayall( "Checking our next contract." );
            println( "OUTLANDS_CHAT_PRIMITIVE_V1|sayall" );
            level.outlands_context_primitive = 1;
        }
    }
}

feature_fields( players )
{
    mode = getdvar( "g_gametype" );
    squads_enabled = 0;
    assigned = 0;
    attack = 0;
    defend = 0;
    support = 0;
    targeted = 0;
    goal_calls = 0;
    distinct = 0;
    squad_invalid = 0;
    team_bots = [];
    team_attack = [];
    team_defend = [];
    foreach ( team in array( "allies", "axis" ) )
    {
        team_bots[team] = 0;
        team_attack[team] = 0;
        team_defend[team] = 0;
    }
    if ( isdefined( level.outlands_squads_started ) && getdvarint( "outlands_squads" ) )
        squads_enabled = 1;
    if ( isdefined( level.outlands_squad_goal_calls ) )
        goal_calls = level.outlands_squad_goal_calls;
    if ( isdefined( level.outlands_squad_targets ) )
        distinct = level.outlands_squad_targets.size;
    if ( isdefined( level.outlands_squad_invalid ) )
        squad_invalid = level.outlands_squad_invalid;
    valid_assignment = getfunction( "scripts/mp/outlands_squads", "assignment_valid" );
    foreach ( bot in players )
    {
        if ( !isdefined( bot ) || !isplayer( bot ) || !bot istestclient() )
            continue;
        team = "none";
        if ( isdefined( bot.team ) && ( bot.team == "allies" || bot.team == "axis" ) )
        {
            team = bot.team;
            team_bots[team]++;
        }
        if ( !isdefined( bot.outlands_squad_role ) || bot.outlands_squad_role == "" )
            continue;
        // Native team changes can precede the next squad reassessment. A rejected
        // stale record is not an effective assignment. Retaining our own steering
        // goal or accepting that record is still a failure; final coverage must
        // recover to all sixteen current assignments.
        if ( !isdefined( bot.outlands_squad_team ) || !isdefined( bot.team ) || bot.outlands_squad_team != bot.team )
        {
            if ( !isdefined( valid_assignment ) || bot [[ valid_assignment ]]() || bot hasgoal( "outlands_squad" ) )
                squad_invalid++;
            else
                println( "OUTLANDS_SQUAD_REFRESH_V1|rejected_stale_team" );
            continue;
        }
        assigned++;
        role = bot.outlands_squad_role;
        if ( role == "attack" )
        {
            attack++;
            if ( team != "none" )
                team_attack[team]++;
        }
        else if ( role == "defend" )
        {
            defend++;
            if ( team != "none" )
                team_defend[team]++;
        }
        else if ( role == "support" )
            support++;
        else
            squad_invalid++;
        // Official objectives can be structs as well as entities. The module
        // validates live native collection membership before getgoal is used.
        if ( role != "support" && isdefined( valid_assignment ) && bot [[ valid_assignment ]]() && isdefined( bot.outlands_squad_goal_name ) && bot.outlands_squad_goal_name != "" )
        {
            goal = bot getgoal( bot.outlands_squad_goal_name );
            if ( isdefined( goal ) )
                targeted++;
        }
    }
    foreach ( team in array( "allies", "axis" ) )
        if ( team_attack[team] > 4 || team_defend[team] > 2 )
            squad_invalid++;

    contracts_enabled = 0;
    contract_active = 0;
    contract_completed = 0;
    contract_commendations = 0;
    contract_kills = 0;
    contract_score = 0;
    contract_points = 0;
    contract_invalid = 0;
    supported = mode == "tdm" || mode == "conf" || mode == "dom" || mode == "koth" || mode == "hq" || mode == "ctf" || mode == "dem";
    if ( getdvarint( "outlands_contracts" ) && supported && isdefined( level.outlands_contracts_started ) )
        contracts_enabled = 1;
    foreach ( team in array( "allies", "axis" ) )
    {
        if ( isdefined( level.outlands_contracts_completed ) && isdefined( level.outlands_contracts_completed[team] ) )
            contract_completed += level.outlands_contracts_completed[team];
        if ( isdefined( level.outlands_contracts_commendations ) && isdefined( level.outlands_contracts_commendations[team] ) )
            contract_commendations += level.outlands_contracts_commendations[team];
        if ( isdefined( level.outlands_contracts_delta_kills ) && isdefined( level.outlands_contracts_delta_kills[team] ) )
            contract_kills += level.outlands_contracts_delta_kills[team];
        if ( isdefined( level.outlands_contracts_delta_score ) && isdefined( level.outlands_contracts_delta_score[team] ) )
            contract_score += level.outlands_contracts_delta_score[team];
        if ( isdefined( level.outlands_contracts_delta_points ) && isdefined( level.outlands_contracts_delta_points[team] ) )
            contract_points += level.outlands_contracts_delta_points[team];
        if ( isdefined( level.outlands_contracts_invalid ) && isdefined( level.outlands_contracts_invalid[team] ) )
            contract_invalid += level.outlands_contracts_invalid[team];
        if ( !isdefined( level.outlands_contracts_records ) || !isdefined( level.outlands_contracts_records[team] ) )
            continue;
        record = level.outlands_contracts_records[team];
        contract_active++;
        if ( record.kind != "team_eliminations" && record.kind != "combined_score" && record.kind != "team_points" )
            contract_invalid++;
        else
        {
            native_metric = level.outlands_contracts_delta_points[team];
            if ( record.kind == "team_eliminations" )
                native_metric = level.outlands_contracts_delta_kills[team];
            else if ( record.kind == "combined_score" )
                native_metric = level.outlands_contracts_delta_score[team];
            if ( record.current != native_metric || record.current < record.baseline || record.progress != record.current - record.baseline || record.goal < 1 )
                contract_invalid++;
            if ( record.complete && record.progress < record.goal || !record.complete && record.progress >= record.goal )
                contract_invalid++;
            if ( record.completed_count != level.outlands_contracts_completed[team] || record.commendations != level.outlands_contracts_commendations[team] )
                contract_invalid++;
        }
    }
    return level.outlands_verify_sequence + "|" + squads_enabled + "|" + assigned + "|" + attack + "|" + defend + "|" + support + "|" + targeted + "|" + goal_calls + "|" + distinct + "|" + squad_invalid + "|" + contracts_enabled + "|" + contract_active + "|" + contract_completed + "|" + contract_commendations + "|" + contract_kills + "|" + contract_score + "|" + contract_points + "|" + contract_invalid + "|" + team_bots["allies"] + "|" + team_bots["axis"];
}


lobby_record( phase )
{
    pop = getfunction( "scripts/mp/outlands_native_bots", "population" );
    counts = [[ pop ]]();
    println( "OUTLANDS_LOBBY_V1|" + phase + "|" + counts.humans + "|" + counts.bots.size + "|" + counts.allies + "|" + counts.axis );
}

repair_lobby()
{
    pop = getfunction( "scripts/mp/outlands_native_bots", "population" );
    planner = getfunction( "scripts/mp/outlands_native_bots", "population_plan" );
    execute = getfunction( "scripts/mp/outlands_native_bots", "execute_population_plan" );
    for ( i = 0; i < 12; i++ )
    {
        counts = [[ pop ]]();
        if ( counts.humans != 0 )
            return false;
        if ( counts.bots.size == 16 && counts.allies == 8 && counts.axis == 8 )
            return true;
        plan = [[ planner ]]( counts, 16 );
        [[ execute ]]( plan );
        wait 1;
    }
    return false;
}

skew_lobby()
{
    pop = getfunction( "scripts/mp/outlands_native_bots", "population" );
    select = getfunction( "scripts/mp/outlands_native_bots", "bot_on_team" );
    spawn_bot = getfunction( "maps/mp/bots/_bot", "spawn_bot" );
    counts = [[ pop ]]();
    bot = [[ select ]]( counts, "axis" );
    if ( !isdefined( bot ) || !bot istestclient() || !isdefined( spawn_bot ) )
        return false;
    println( "OUTLANDS_LOBBY_DIAG_V1|selected|" + bot.sessionteam );
    // Replace a real axis bot using native explicit-team creation. Existing
    // ranked menus deliberately disallow manual team changes after combat.
    bot botleavegame();
    wait 0.5;
    [[ spawn_bot ]]( "allies" );
    for ( i = 0; i < 20; i++ )
    {
        wait 0.5;
        counts = [[ pop ]]();
        if ( counts.humans != 0 )
            return false;
        if ( counts.bots.size == 16 && counts.allies == 9 && counts.axis == 7 )
            return true;
    }
    println( "OUTLANDS_LOBBY_DIAG_V1|skew_failed|" + counts.allies + "|" + counts.axis );
    return false;
}

verify_lobby_balance()
{
    level endon( "game_ended" );
    pop = getfunction( "scripts/mp/outlands_native_bots", "population" );
    select = getfunction( "scripts/mp/outlands_native_bots", "bot_on_team" );
    side = getfunction( "scripts/mp/outlands_native_bots", "party_side" );
    planner = getfunction( "scripts/mp/outlands_native_bots", "population_plan" );
    if ( !isdefined( level.outlands_team_hooks ) || !isdefined( side ) )
    {
        println( "OUTLANDS_PARTY_POLICY_V1|failed" );
        return;
    }
    // Count-only fixtures do not create or relabel human connections.
    capacity = getfunction( "scripts/mp/outlands_native_bots", "party_capacity" );
    policy = [[ side ]]( "allies", 0, 0, 8 ) == "allies";
    policy = policy && [[ side ]]( "allies", 2, 0, 8 ) == "allies";
    policy = policy && [[ side ]]( "axis", 0, 2, 8 ) == "axis";
    policy = policy && [[ side ]]( "allies", 7, 0, 8 ) == "allies";
    policy = policy && [[ side ]]( "allies", 8, 0, 8 ) == "axis";
    policy = policy && [[ side ]]( "axis", 0, 8, 8 ) == "allies";
    policy = policy && [[ capacity ]]( 16, 0 ) == 8;
    policy = policy && [[ capacity ]]( 16, 1 ) == 7;
    policy = policy && [[ capacity ]]( 8, 0 ) == 4;
    policy = policy && [[ capacity ]]( 16, -1 ) == 8;
    if ( !policy )
    {
        println( "OUTLANDS_PARTY_POLICY_V1|failed" );
        return;
    }
    println( "OUTLANDS_PARTY_POLICY_V1|pass" );
    for ( i = 0; i < 40; i++ )
    {
        counts = [[ pop ]]();
        if ( counts.bots.size == 16 && counts.allies == 8 && counts.axis == 8 )
            break;
        wait 0.5;
    }
    wait 3;
    counts = [[ pop ]]();
    lobby_record( "baseline" );
    bot = [[ select ]]( counts, "allies" );
    if ( !isdefined( bot ) || !bot istestclient() )
        return;
    bot botleavegame();
    wait 1;
    lobby_record( "deficit" );
    if ( !repair_lobby() )
        return;
    lobby_record( "refilled" );
    if ( !skew_lobby() )
        return;
    lobby_record( "imbalanced" );
    if ( !repair_lobby() )
        return;
    lobby_record( "rebalanced" );
    setdvar( "outlands_balance_teams", 0 );
    setdvar( "outlands_coop_teams", 0 );
    wait 2;
    if ( !skew_lobby() )
        return;
    counts = [[ pop ]]();
    plan = [[ planner ]]( counts, 16 );
    if ( plan.action != "none" )
        return;
    lobby_record( "disabled" );
    setdvar( "outlands_balance_teams", 1 );
    setdvar( "outlands_coop_teams", 1 );
    if ( !repair_lobby() )
        return;
    lobby_record( "resumed" );
    // Exercise the real controller tick while native-bot ownership is off.
    setdvar( "outlands_native_bots", 0 );
    wait 3;
    restored = getdvarint( "scr_teambalance" ) == 1;
    setdvar( "outlands_native_bots", 1 );
    wait 3;
    if ( restored && getdvarint( "scr_teambalance" ) == 0 )
        println( "OUTLANDS_BALANCE_RESTORE_V1|pass" );
    else
        println( "OUTLANDS_BALANCE_RESTORE_V1|failed" );
}

// Script entities test the native detour and timers, not real aircraft combat.
verify_air_response()
{
    level endon( "game_ended" );
    wait 25;
    filter = getfunction( "maps/mp/bots/_bot_combat", "threat_should_ignore" );
    classify = getfunction( "scripts/mp/outlands_bot_profiles", "air_support_target" );
    bot = undefined;
    foreach ( player in get_players() )
        if ( isdefined( player ) && isplayer( player ) && player istestclient() && isdefined( player.bot ) )
        {
            bot = player;
            break;
        }
    if ( !isdefined( bot ) || !isdefined( level.outlands_profiles_air_ignore ) )
    {
        println( "OUTLANDS_AIR_POLICY_V1|failed" );
        return;
    }
    delay = getdvar( "outlands_bot_air_reaction_ms" );
    chance = getdvar( "outlands_bot_air_response_chance" );
    target = spawn( "script_origin", ( 0, 0, 0 ) );
    other = spawn( "script_origin", ( 0, 0, 0 ) );
    target.targetname = "uav";
    other.targetname = "counteruav";
    setdvar( "outlands_bot_air_reaction_ms", 1000 );
    setdvar( "outlands_bot_air_response_chance", 100 );
    delayed = bot [[ filter ]]( target );
    multiple = bot [[ filter ]]( other );
    // The same target must retain its deadline across interleaved candidates.
    ready = bot.outlands_air_gates[target getentitynumber()].ready;
    wait 2;
    resumed = !bot [[ filter ]]( target );
    stable = ready == bot.outlands_air_gates[target getentitynumber()].ready;
    setdvar( "outlands_bot_air_reaction_ms", 0 );
    setdvar( "outlands_bot_air_response_chance", 0 );
    declined = bot [[ filter ]]( target );
    setdvar( "outlands_bot_air_response_chance", 100 );
    stock = !bot [[ filter ]]( target );
    // Native ignore deadlines continue to win even when the mod gate is off.
    bot.bot.ignore_entity[target getentitynumber()] = gettime() + 1000;
    native_ignored = bot [[ filter ]]( target );
    bot.bot.ignore_entity[target getentitynumber()] = 0;
    ground = ![[ classify ]]( bot );
    target.targetname = "remote_mortar";
    ground = ground && ![[ classify ]]( target );
    setdvar( "outlands_bot_air_reaction_ms", delay );
    setdvar( "outlands_bot_air_response_chance", chance );
    target delete();
    other delete();
    if ( delayed && multiple && resumed && stable && declined && stock && native_ignored && ground )
        println( "OUTLANDS_AIR_POLICY_V1|pass" );
    else
        println( "OUTLANDS_AIR_POLICY_V1|failed" );
}


verify_expansion()
{
    level endon( "game_ended" );
    // Native bot connections arrive after spawnbot returns. Require actual
    // occupants before checking bot exclusion or formatting native context.
    players = get_players();
    attempts = 0;
    while ( players.size < 16 && attempts < 30 )
    {
        wait 1;
        attempts++;
        players = get_players();
    }
    valid = getfunction( "scripts/mp/outlands_operations", "valid_guid" );
    human = getfunction( "scripts/mp/outlands_operations", "human_ready" );
    tier = getfunction( "scripts/mp/outlands_operations", "tier" );
    number = getfunction( "scripts/mp/outlands_operations", "number" );
    ok = isdefined( level.outlands_operations_started ) && isdefined( valid ) && isdefined( human ) && isdefined( tier ) && isdefined( number );
    if ( ok )
    {
        ok = players.size == 16 && [[ valid ]]( "a12b34" ) && ![[ valid ]]( "0" ) && ![[ valid ]]( "a;quit" );
        ok = ok && [[ tier ]]( 24, "assault" ) == 0 && [[ tier ]]( 25, "assault" ) == 1 && [[ tier ]]( 100, "assault" ) == 2 && [[ tier ]]( 250, "assault" ) == 3;
        ok = ok && [[ tier ]]( 3, "objective" ) == 1 && [[ tier ]]( 10, "support" ) == 2;
        ok = ok && [[ number ]]( "1000000000", 1000000000 ) && ![[ number ]]( "-1", 1000000000 ) && ![[ number ]]( "01", 1000000000 );
        players = get_players();
        foreach ( bot in players )
            if ( isdefined( bot ) && isplayer( bot ) && bot istestclient() && [[ human ]]( bot ) )
                ok = false;
        if ( isdefined( level.outlands_operations_pending ) || getarraykeys( level.outlands_operations_records ).size > 0 )
            ok = false;
    }
    formatter = getfunction( "scripts/mp/outlands_chat", "event_line" );
    context_function = getfunction( "scripts/mp/outlands_chat", "task_context" );
    if ( !isdefined( formatter ) || !isdefined( context_function ) )
        ok = false;
    else
    {
        players = get_players();
        if ( players.size < 1 )
            ok = false;
        else
        {
            context = [[ context_function ]]( players[0], "contract" );
            names = array( "NightLedger", "CopperWren", "StaticBloom", "RiftRunner" );
            for ( turn = 1; turn <= 4; turn++ )
            {
                request = spawnstruct();
                request.id = "nativefixture";
                request.kind = "banter";
                speaker = "match";
                text = "A synthetic scene hint.";
                if ( turn > 1 )
                {
                    request.id = "nativefixture_r" + turn;
                    request.kind = "bot_reply";
                    speaker = names[turn - 2];
                    text = "Fair, same here.";
                }
                request.slot = turn;
                request.name = names[turn - 1];
                request.turn = turn;
                request.turn_limit = 4;
                // Exercise the production formatter without requesting speech,
                // inventing human connections or entering the worker transport.
                println( "OUTLANDS_DIALOGUE_FIXTURE_V1|" + [[ formatter ]]( request, speaker, text, context ) );
            }
        }
    }
    if ( ok )
        println( "OUTLANDS_EXPANSION_V1|pass" );
    else
        println( "OUTLANDS_EXPANSION_V1|failed" );
}

// Calls production presenters/HUD methods with actual native bots. It never
// changes their identity/type or inserts a synthetic human career observation.
verify_armory_editor()
{
    level endon( "game_ended" );
    wait 7;
    selected = undefined;
    foreach ( bot in get_players() )
        if ( isdefined( bot ) && bot istestclient() && isalive( bot ) && scripts\mp\outlands_armory::can_customize( bot ) )
        {
            selected = bot;
            break;
        }
    if ( !isdefined( selected ) || !scripts\mp\outlands_armory::enabled() )
    {
        println( "OUTLANDS_ARMORY_EDITOR_V1|failed|hooks_or_player" );
        return;
    }
    refs = scripts\mp\outlands_armory::empty_refs();
    catalog_ok = true;
    for ( i = 0; i < 7; i++ )
    {
        slot = level.outlands_armory_slots[i];
        choices = level.outlands_armory_choices[slot];
        println( "OUTLANDS_ARMORY_EDITOR_CHECK|catalog|" + slot + "|" + choices.size );
        foreach ( ref in choices )
            if ( ref != "none" && scripts\mp\outlands_armory::item_unlocked( selected, ref, slot ) )
            {
                refs[i] = ref;
                break;
            }
        if ( refs[i] == "none" )
            catalog_ok = false;
    }
    view = scripts\mp\outlands_armory::validate_refs( selected, refs );
    bad = scripts\mp\outlands_armory::copy_refs( refs );
    bad[0] = "not_a_weapon";
    invalid = scripts\mp\outlands_armory::validate_refs( selected, bad );
    bad[0] = refs[1];
    wrong = scripts\mp\outlands_armory::validate_refs( selected, bad );
    excluded = !scripts\mp\outlands_armory::eligible( selected ) && !scripts\mp\outlands_armory_ui::dispatch( selected, "toggle" );
    record = scripts\mp\outlands_armory::new_record( selected );
    record.fixture = 1;
    record.restored = 1;
    record.revision = 1;
    record.draft = scripts\mp\outlands_armory::copy_refs( refs );
    record.saved = scripts\mp\outlands_armory::copy_refs( refs );
    record.queued = scripts\mp\outlands_armory::copy_refs( refs );
    record.queued_spawn = 0;
    record.fixture_grants = 0;
    level.outlands_armory_records[record.slot] = record;
    // Synthetic mailbox replies exercise the native parser without sending
    // any bot through the human worker or the human identity ledger.
    pending = spawnstruct();
    pending.record = record;
    pending.id = "fixture_request";
    pending.kind = "save";
    pending.sent = gettime();
    pending.spawn = 0;
    pending.refs = scripts\mp\outlands_armory::copy_refs( refs );
    pending.revision = 0;
    record.command = "save";
    level.outlands_armory_pending = pending;
    setdvar( "outlands_armory_response", "wrong_id|" + record.slot + "|queued|1|" + scripts\mp\outlands_armory::join_refs( refs ) );
    scripts\mp\outlands_armory::consume_response();
    mailbox_ok = isdefined( level.outlands_armory_pending );
    setdvar( "outlands_armory_response", "fixture_request|" + record.slot + "|queued|1|" + scripts\mp\outlands_armory::join_refs( refs ) );
    scripts\mp\outlands_armory::consume_response();
    mailbox_ok = mailbox_ok && isdefined( record.queued ) && record.revision == 1 && record.command == "none";
    pending.revision = 1;
    record.command = "save";
    level.outlands_armory_pending = pending;
    scripts\mp\outlands_armory::cancel_record( record, "FIXTURE CANCEL" );
    setdvar( "outlands_armory_response", "fixture_request|" + record.slot + "|queued|2|" + scripts\mp\outlands_armory::join_refs( refs ) );
    scripts\mp\outlands_armory::consume_response();
    mailbox_ok = mailbox_ok && !isdefined( record.queued ) && record.revision == 1;
    pending.id = "fixture_mailbox_" + getdvarint( "outlands_verify_restarted" );
    pending.kind = "cancel";
    pending.sent = gettime();
    record.command = "cancel";
    level.outlands_armory_pending = pending;
    println( "OUTLANDS_ARMORY_MAILBOX_V1|" + pending.id + "|" + record.slot + "|" + scripts\mp\outlands_armory::join_refs( refs ) );
    attempts = 0;
    while ( isdefined( level.outlands_armory_pending ) && attempts < 100 )
    {
        wait 0.025;
        attempts++;
    }
    remote_ok = !isdefined( level.outlands_armory_pending ) && record.status == "OUTLANDS CLASS CANCELLED / STOCK CLASS ACTIVE";
    mailbox_ok = mailbox_ok && remote_ok;
    if ( remote_ok )
        println( "OUTLANDS_ARMORY_MAILBOX_ACK_V1|" + pending.id );
    record.command = "none";
    record.queued = scripts\mp\outlands_armory::copy_refs( refs );
    record.queued_spawn = 0;
    // Refuse a formerly accepted class that is now unknown/restricted at the
    // final grant boundary, before any inventory mutation.
    before_invalid = selected getcurrentweapon();
    record.last_claim = scripts\mp\outlands_armory::copy_refs( bad );
    record.armed = 1;
    record.in_spawn = 1;
    refused = selected scripts\mp\outlands_armory::grant_callback();
    invalid_ok = !isdefined( refused ) && !record.armed && !isdefined( record.queued ) && before_invalid == ( selected getcurrentweapon() );
    record.in_spawn = 0;
    record.command = "none";
    record.queued = scripts\mp\outlands_armory::copy_refs( refs );
    record.queued_spawn = 0;
    hud_ok = true;
    for ( cycle = 0; cycle < 6; cycle++ )
    {
        state = scripts\mp\outlands_armory_ui::create_editor( selected );
        if ( state.elements.size != 25 )
            hud_ok = false;
        for ( row = 0; row < 7; row++ )
        {
            state.row = row;
            scripts\mp\outlands_armory_ui::draw_editor( state, record );
            if ( state.values[row].outlands_ref != refs[row] || state.selector.y != -105 + row * 29 )
                hud_ok = false;
        }
        owned = state.elements;
        scripts\mp\outlands_ui::destroy_hud( state );
        scripts\mp\outlands_ui::destroy_hud( state );
        foreach ( hud in owned )
            if ( isdefined( hud ) )
                hud_ok = false;
    }
    current = selected getcurrentweapon();
    ammo = selected getweaponammoclip( current );
    // Calling the custom grant outside the wrapped native spawn must refuse.
    outside = selected scripts\mp\outlands_armory::grant_callback();
    unchanged = !isdefined( outside ) && current == ( selected getcurrentweapon() ) && ammo == ( selected getweaponammoclip( current ) );
    first = 0;
    second = 0;
    for ( life = 0; life < 2; life++ )
    {
        record.fixture_matched = 0;
        selected suicide();
        attempts = 0;
        while ( !record.fixture_matched && attempts < 200 )
        {
            wait 0.1;
            attempts++;
        }
        if ( life == 0 )
            first = record.fixture_matched && record.fixture_grants == 1 && record.spawn == 1;
        else
            second = record.fixture_matched && record.fixture_grants == 2 && record.spawn == 2;
    }
    if ( catalog_ok && view.valid && view.points == 7 && !invalid.valid && !wrong.valid && excluded && hud_ok && unchanged && first && second && mailbox_ok && invalid_ok )
        println( "OUTLANDS_ARMORY_EDITOR_V2|pass|7|25|6|2|0" );
    else
        println( "OUTLANDS_ARMORY_EDITOR_V2|failed|" + catalog_ok + "|" + view.valid + "|" + view.points + "|" + excluded + "|" + hud_ok + "|" + unchanged + "|" + first + "|" + second + "|" + mailbox_ok );
    scripts\mp\outlands_armory::cancel_record( record, "FIXTURE FINISHED" );
    level.outlands_armory_records[record.slot] = undefined;
}

verify_armory()
{
    level endon( "game_ended" );
    inspect_fn = getfunction( "scripts/mp/outlands_armory", "inspect_native_slot" );
    stage_fn = getfunction( "scripts/mp/outlands_armory", "stage_native_reference" );
    eligible_fn = getfunction( "scripts/mp/outlands_armory", "eligible" );
    slot_fn = getfunction( "scripts/mp/outlands_armory", "valid_slot" );
    if ( !isdefined( inspect_fn ) || !isdefined( stage_fn ) || !isdefined( eligible_fn ) || !isdefined( slot_fn ) )
    {
        println( "OUTLANDS_ARMORY_V1|failed|missing_adapter" );
        return;
    }
    wait 5;
    selected = undefined;
    selected_view = undefined;
    valid = 0;
    foreach ( bot in get_players() )
    {
        if ( !isdefined( bot ) || !bot istestclient() || !isalive( bot ) || bot.sessionstate != "playing" )
            continue;
        for ( index = 0; index < 5; index++ )
        {
            view = [[ inspect_fn ]]( bot, index );
            if ( !view.ready || !isdefined( bot.curclass ) || bot.curclass == "CLASS_CUSTOM" + ( index + 1 ) )
                continue;
            if ( view.primary == "weapon_null_mp" || view.primary == "" )
                continue;
            selected = bot;
            selected_view = view;
            break;
        }
        if ( isdefined( selected ) )
            break;
    }
    if ( !isdefined( selected ) )
    {
        println( "OUTLANDS_ARMORY_V1|failed|no_eligible_native_slot" );
        return;
    }
    for ( index = 0; index < 5; index++ )
    {
        view = [[ inspect_fn ]]( selected, index );
        if ( view.ready )
            valid++;
    }
    invalid_low = [[ inspect_fn ]]( selected, -1 );
    invalid_high = [[ inspect_fn ]]( selected, 5 );
    excluded = ![[ eligible_fn ]]( selected ) && !invalid_low.ready && !invalid_high.ready && ![[ slot_fn ]]( 1.5 );
    before = selected getcurrentweapon();
    before_ammo = selected getweaponammoclip( before );
    staged = [[ stage_fn ]]( selected, selected_view.index );
    unchanged = before == ( selected getcurrentweapon() ) && before_ammo == ( selected getweaponammoclip( before ) );
    expected = "CLASS_CUSTOM" + ( selected_view.index + 1 );
    selected.outlands_armory_probe_spawned = 0;
    selected thread observe_armory_spawn();
    wait 0.05;
    selected suicide();
    attempts = 0;
    while ( !selected.outlands_armory_probe_spawned && attempts < 200 )
    {
        wait 0.1;
        attempts++;
    }
    spawned = selected.outlands_armory_probe_spawned && isalive( selected );
    matched = spawned && selected.curclass == expected && selected hasweapon( selected_view.primary );
    if ( matched && selected_view.secondary != "weapon_null_mp" && selected_view.secondary != "" )
        matched = selected hasweapon( selected_view.secondary );
    if ( matched )
    {
        if ( selected.specialty.size != selected_view.perks.size )
            matched = false;
        else
            for ( i = 0; i < selected_view.perks.size; i++ )
                if ( selected.specialty[i] != selected_view.perks[i] )
                    matched = false;
    }
    if ( valid > 0 && staged && unchanged && spawned && matched && excluded )
        println( "OUTLANDS_ARMORY_V1|pass|" + valid + "|1|1|1|1|1" );
    else
        println( "OUTLANDS_ARMORY_V1|failed|" + valid + "|" + staged + "|" + unchanged + "|" + spawned + "|" + matched + "|" + excluded );
}

observe_armory_spawn()
{
    self endon( "disconnect" );
    self waittill( "spawned_player" );
    self.outlands_armory_probe_spawned = 1;
}

verify_ui()
{
    level endon( "game_ended" );
    players = get_players();
    attempts = 0;
    while ( players.size < 16 && attempts < 30 )
    {
        wait 1;
        attempts++;
        players = get_players();
    }
    career_fn = getfunction( "scripts/mp/outlands_ui", "career_view" );
    task_fn = getfunction( "scripts/mp/outlands_ui", "contract_view" );
    create_fn = getfunction( "scripts/mp/outlands_ui", "create_hud" );
    draw_fn = getfunction( "scripts/mp/outlands_ui", "draw_view" );
    destroy_fn = getfunction( "scripts/mp/outlands_ui", "destroy_hud" );
    eligible_fn = getfunction( "scripts/mp/outlands_ui", "eligible" );
    page_fn = getfunction( "scripts/mp/outlands_ui", "parse_action" );
    goal_fn = getfunction( "scripts/mp/outlands_ui", "milestone_goal" );
    width_fn = getfunction( "scripts/mp/outlands_ui", "bar_width" );
    queue_fn = getfunction( "scripts/mp/outlands_operations", "queue_command" );
    command_fn = getfunction( "scripts/mp/outlands_chat", "ui_command" );
    ok = isdefined( career_fn ) && isdefined( task_fn ) && isdefined( create_fn ) && isdefined( draw_fn ) && isdefined( destroy_fn ) && isdefined( eligible_fn ) && isdefined( page_fn ) && isdefined( goal_fn ) && isdefined( width_fn ) && isdefined( queue_fn ) && isdefined( command_fn );
    if ( !ok || players.size != 16 )
    {
        println( "OUTLANDS_UI_V1|failed|missing_helpers" );
        return;
    }
    foreach ( bot in players )
        if ( !bot istestclient() || [[ eligible_fn ]]( bot ) || [[ queue_fn ]]( bot, "select", "assault" ) )
            ok = false;
    ok = ok && [[ page_fn ]]( "!outlands" ) == "toggle" && [[ page_fn ]]( "!outlands contracts" ) == "contracts" && [[ page_fn ]]( "!outlands focus" ) == "focus" && [[ page_fn ]]( "!outlands career;quit" ) == "none";
    ok = ok && [[ command_fn ]]( "!outlands" ) && [[ command_fn ]]( "!outlands contracts" ) && [[ command_fn ]]( "!track objective" ) && ![[ command_fn ]]( "good round" ) && ![[ command_fn ]]( "!outlandsjunk" );
    ok = ok && [[ goal_fn ]]( 24, "assault" ) == 25 && [[ goal_fn ]]( 25, "assault" ) == 100 && [[ goal_fn ]]( 100, "assault" ) == 250 && [[ goal_fn ]]( 999, "assault" ) == 250 && [[ goal_fn ]]( 3, "support" ) == 10;
    ok = ok && [[ width_fn ]]( 0, 25 ) == 0 && [[ width_fn ]]( 25, 25 ) == 330 && [[ width_fn ]]( 1000000000, 25 ) == 330 && [[ width_fn ]]( 1, 0 ) == 0;
    println( "OUTLANDS_UI_CHECK|commands_goals|" + ok );
    loading = [[ career_fn ]]( undefined, 1000, 1 );
    disabled = [[ career_fn ]]( undefined, 1000, 0 );
    ok = ok && !loading.ready && loading.status == "LOADING CAREER" && !disabled.ready && disabled.status == "OPERATIONS DISABLED";
    println( "OUTLANDS_UI_CHECK|loading|" + ok );
    record = spawnstruct();
    record.restored = 1;
    record.acknowledged = 1000;
    record.totals = array( 32, 2, 1 );
    record.selected = "objective";
    record.command = "none";
    career = [[ career_fn ]]( record, 1000, 1 );
    ok = ok && career.ready && career.milestones == 1 && career.selected == "objective";
    println( "OUTLANDS_UI_CHECK|career|" + ok );
    stale = [[ career_fn ]]( record, 46001, 1 );
    future = [[ career_fn ]]( record, 999, 1 );
    ok = ok && !stale.ready && !future.ready && !isdefined( stale.totals );
    println( "OUTLANDS_UI_CHECK|freshness|" + ok );
    record.selected = "injected";
    invalid = [[ career_fn ]]( record, 1000, 1 );
    ok = ok && !invalid.ready;
    record.selected = "support";
    record.totals = array( 25, 3, 3 );
    complete = [[ career_fn ]]( record, 1000, 1 );
    ok = ok && complete.ready && complete.milestones == 3 && complete.status == "BROKEN SIGNAL COMPLETE - FIELD REGULAR";
    record.command = "select";
    saving = [[ career_fn ]]( record, 1000, 1 );
    ok = ok && saving.status == "SAVING FOCUS - WAIT FOR CONFIRMATION" && saving.selected == "support";
    record.totals = array( -1, 3, 3 );
    invalid = [[ career_fn ]]( record, 1000, 1 );
    ok = ok && !invalid.ready;
    println( "OUTLANDS_UI_CHECK|career_states|" + ok );
    contract = spawnstruct();
    contract.kind = "team_points";
    contract.progress = 7;
    contract.goal = 12;
    contract.complete = 0;
    contract.observed = 1000;
    task = [[ task_fn ]]( contract, 1000, 31000, 1, 1 );
    ok = ok && task.ready && task.seconds == 30 && task.progress == 7 && task.goal == 12;
    println( "OUTLANDS_UI_CHECK|contract|" + ok );
    stale_task = [[ task_fn ]]( contract, 6001, 31000, 1, 1 );
    ffa = [[ task_fn ]]( contract, 1000, 31000, 1, 0 );
    expired = [[ task_fn ]]( contract, 31000, 31000, 1, 1 );
    ok = ok && !stale_task.ready && !ffa.ready && !expired.ready && !isdefined( expired.progress );
    contract.complete = 1;
    invalid_task = [[ task_fn ]]( contract, 1000, 31000, 1, 1 );
    ok = ok && !invalid_task.ready;
    contract.progress = 12;
    completed_task = [[ task_fn ]]( contract, 1000, 31000, 1, 1 );
    ok = ok && completed_task.ready && completed_task.status == "TEAM CONTRACT COMPLETE";
    println( "OUTLANDS_UI_CHECK|contract_states|" + ok );
    for ( cycle = 0; cycle < 6; cycle++ )
    {
        state = [[ create_fn ]]( players[0] );
        println( "OUTLANDS_UI_CHECK|allocation|" + state.elements.size );
        if ( state.elements.size != 29 || !state.open )
            ok = false;
        [[ draw_fn ]]( state, loading, ffa );
        if ( state.heading.outlands_text != "OUTLANDS / OPERATIONS" || state.status.outlands_text != "LOADING CAREER" )
            ok = false;
        if ( state.rows[0].value.alpha != 0 || state.rows[0].empty.alpha != 1 || state.rows[0].bar.alpha != 0 )
            ok = false;
        [[ draw_fn ]]( state, disabled, expired );
        [[ draw_fn ]]( state, stale, stale_task );
        [[ draw_fn ]]( state, career, task );
        if ( state.rows[0].value.alpha != 1 || state.rows[0].empty.alpha != 0 || state.rows[0].bar.alpha != 1 )
            ok = false;
        [[ draw_fn ]]( state, saving, task );
        [[ draw_fn ]]( state, complete, completed_task );
        state.page = "contracts";
        [[ draw_fn ]]( state, complete, ffa );
        if ( state.rows[2].empty.alpha != 0 || state.rows[0].value.alpha != 0 )
            ok = false;
        [[ draw_fn ]]( state, complete, expired );
        [[ draw_fn ]]( state, complete, task );
        [[ draw_fn ]]( state, complete, completed_task );
        owned = state.elements;
        [[ destroy_fn ]]( state );
        [[ destroy_fn ]]( state );
        foreach ( hud in owned )
            if ( isdefined( hud ) )
                ok = false;
        if ( state.open || state.elements.size != 0 )
            ok = false;
        wait 0.05;
    }
    simultaneous = [];
    foreach ( bot in players )
    {
        state = [[ create_fn ]]( bot );
        simultaneous[simultaneous.size] = state;
        [[ draw_fn ]]( state, complete, completed_task );
        if ( state.elements.size != 29 )
            ok = false;
    }
    foreach ( state in simultaneous )
    {
        owned = state.elements;
        [[ destroy_fn ]]( state );
        foreach ( hud in owned )
            if ( isdefined( hud ) )
                ok = false;
    }
    if ( ok )
        println( "OUTLANDS_UI_V1|pass|29|6|16|0" );
    else
        println( "OUTLANDS_UI_V1|failed|presenter_or_cleanup" );
}
