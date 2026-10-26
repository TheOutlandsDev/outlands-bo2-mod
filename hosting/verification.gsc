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
        map_restart( 1 );
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
        if ( !isdefined( bot.outlands_squad_team ) || !isdefined( bot.team ) || bot.outlands_squad_team != bot.team )
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
