// Original match-local Outlands team contracts. Explicit start(), no auto init.
// Reads native counters; never awards native XP, score, unlocks or DDL stats.
// Native sources: plutoniummod/t6-scripts MP/Core/maps/mp/gametypes/
// _globallogic_score.gsc (game["teamScores"]) and _hud_message.gsc (iprintln).
#include common_scripts\utility;

start()
{
    if ( !isdedicated() || isdefined( level.outlands_contracts_started ) )
        return;
    level.outlands_contracts_started = 1;
    level.outlands_contracts_active = 0;
    level.outlands_contracts_phase = 0;
    level.outlands_contracts_sequence = 0;
    level.outlands_contracts_records = [];
    level.outlands_contracts_player_records = [];
    level.outlands_contracts_delta_kills = [];
    level.outlands_contracts_delta_score = [];
    level.outlands_contracts_delta_points = [];
    level.outlands_contracts_last_points = [];
    level.outlands_contracts_completed = [];
    level.outlands_contracts_failed = [];
    level.outlands_contracts_commendations = [];
    level.outlands_contracts_invalid = [];
    level.outlands_contracts_rebases = [];
    foreach ( team in array( "allies", "axis" ) )
    {
        level.outlands_contracts_delta_kills[team] = 0;
        level.outlands_contracts_delta_score[team] = 0;
        level.outlands_contracts_delta_points[team] = 0;
        level.outlands_contracts_completed[team] = 0;
        level.outlands_contracts_failed[team] = 0;
        level.outlands_contracts_commendations[team] = 0;
        level.outlands_contracts_invalid[team] = 0;
        level.outlands_contracts_rebases[team] = 0;
    }
    level thread watch_contracts();
}

bounded_setting( name, fallback, minimum, maximum )
{
    value = fallback;
    if ( getdvar( name ) != "" )
        value = getdvarint( name );
    if ( value < minimum )
        value = minimum;
    if ( value > maximum )
        value = maximum;
    return value;
}

supported_mode()
{
    mode = getdvar( "g_gametype" );
    return mode == "tdm" || mode == "conf" || mode == "dom" || mode == "koth" || mode == "hq" || mode == "ctf" || mode == "dem";
}

ready()
{
    if ( !getdvarint( "outlands_contracts" ) || !supported_mode() || !isdefined( level.teambased ) || !level.teambased )
        return false;
    if ( isdefined( level.multiteam ) && level.multiteam )
        return false;
    if ( isdefined( level.inprematchperiod ) && level.inprematchperiod )
        return false;
    if ( isdefined( level.gameended ) && level.gameended )
        return false;
    return true;
}

team_of( player )
{
    if ( !isdefined( player.pers["team"] ) )
        return "none";
    team = player.pers["team"];
    if ( team == "allies" || team == "axis" )
        return team;
    return "none";
}

watch_contracts()
{
    level endon( "game_ended" );
    for (;;)
    {
        if ( !ready() )
        {
            // A disabled interval is not part of a contract. Fresh adjacent
            // baselines are required when enabled again; no catch-up awards.
            level.outlands_contracts_active = 0;
            level.outlands_contracts_records = [];
            level.outlands_contracts_player_records = [];
            level.outlands_contracts_last_points = [];
            wait 2;
            continue;
        }

        sample_native_counters();
        if ( !level.outlands_contracts_active )
        {
            level.outlands_contracts_active = 1;
            begin_phase();
        }
        if ( gettime() >= level.outlands_contracts_deadline )
        {
            // Observations at/after the deadline never complete the old task.
            // The final unsampled interval is conservatively excluded; the
            // next phase starts at the just-observed native ledger baseline.
            expire_phase();
            begin_phase();
        }
        else
            update_contracts();
        wait 2;
    }
}

sample_native_counters()
{
    players = get_players();
    foreach ( player in players )
    {
        if ( !isdefined( player ) || !isplayer( player ) )
            continue;
        team = team_of( player );
        if ( team == "none" || !isdefined( player.kills ) || !isdefined( player.score ) )
            continue;
        slot = player getentitynumber();
        if ( slot < 0 || slot > 63 )
            continue;
        kills = int( player.kills );
        score = int( player.score );
        previous = level.outlands_contracts_player_records[slot];
        same = isdefined( previous ) && isdefined( previous.player ) && previous.player == player && previous.team == team;
        if ( same )
            same = isdefined( player.outlands_contract_session ) && player.outlands_contract_session == previous.session;

        valid = kills >= 0 && kills <= 1000000 && score >= -100000000 && score <= 100000000;
        if ( !valid )
        {
            level.outlands_contracts_invalid[team]++;
            level.outlands_contracts_player_records[slot] = undefined;
            continue;
        }
        if ( same )
        {
            kill_delta = kills - previous.kills;
            score_delta = score - previous.score;
            // Each metric rebases independently after a reset/penalty: a
            // decrease earns no credit for that metric, while a valid positive
            // change in the other metric can count. Impossible two-second
            // jumps invalidate the whole sample instead of completing a task.
            if ( kill_delta < 0 || score_delta < 0 )
                level.outlands_contracts_rebases[team]++;
            if ( kill_delta > 256 || score_delta > 100000 )
                level.outlands_contracts_invalid[team]++;
            else
            {
                if ( kill_delta > 0 )
                    level.outlands_contracts_delta_kills[team] += kill_delta;
                if ( score_delta > 0 )
                    level.outlands_contracts_delta_score[team] += score_delta;
            }
        }
        else
        {
            level.outlands_contracts_sequence++;
            player.outlands_contract_session = level.outlands_contracts_sequence;
        }
        record = spawnstruct();
        record.player = player;
        record.team = team;
        record.session = player.outlands_contract_session;
        record.kills = kills;
        record.score = score;
        level.outlands_contracts_player_records[slot] = record;
    }

    foreach ( team in array( "allies", "axis" ) )
    {
        if ( !isdefined( game["teamScores"] ) || !isdefined( game["teamScores"][team] ) )
            continue;
        points = int( game["teamScores"][team] );
        if ( points < 0 || points > 1000000 )
        {
            level.outlands_contracts_invalid[team]++;
            level.outlands_contracts_last_points[team] = undefined;
            continue;
        }
        if ( isdefined( level.outlands_contracts_last_points[team] ) )
        {
            delta = points - level.outlands_contracts_last_points[team];
            if ( delta < 0 )
                level.outlands_contracts_rebases[team]++;
            if ( delta > 1000 )
                level.outlands_contracts_invalid[team]++;
            else if ( delta > 0 )
                level.outlands_contracts_delta_points[team] += delta;
        }
        level.outlands_contracts_last_points[team] = points;
    }
}

metric( team, kind )
{
    if ( kind == "team_eliminations" )
        return level.outlands_contracts_delta_kills[team];
    if ( kind == "combined_score" )
        return level.outlands_contracts_delta_score[team];
    return level.outlands_contracts_delta_points[team];
}

phase_kind()
{
    kinds = array( "team_eliminations", "combined_score", "team_points" );
    count = 3;
    if ( getdvar( "g_gametype" ) == "tdm" )
        count = 2;
    seed = bounded_setting( "outlands_contract_seed", 13, 0, 9999 );
    return kinds[( seed + level.outlands_contracts_phase - 1 ) % count];
}

contract_goal( kind )
{
    goal = 12;
    if ( kind == "combined_score" )
        goal = 1000;
    else if ( kind == "team_points" )
    {
        mode = getdvar( "g_gametype" );
        if ( mode == "ctf" || mode == "dem" )
            goal = 1;
        else if ( mode == "conf" )
            goal = 6;
    }
    scale = bounded_setting( "outlands_contract_goal_scale", 100, 25, 400 );
    goal = int( goal * scale / 100 );
    if ( goal < 1 )
        goal = 1;
    return goal;
}

begin_phase()
{
    level.outlands_contracts_phase++;
    level.outlands_contracts_deadline = gettime() + bounded_setting( "outlands_contract_seconds", 90, 30, 300 ) * 1000;
    kind = phase_kind();
    foreach ( team in array( "allies", "axis" ) )
    {
        record = spawnstruct();
        record.kind = kind;
        record.goal = contract_goal( kind );
        record.baseline = metric( team, kind );
        record.current = record.baseline;
        record.progress = 0;
        record.complete = 0;
        record.completed_count = level.outlands_contracts_completed[team];
        record.failed_count = level.outlands_contracts_failed[team];
        record.commendations = level.outlands_contracts_commendations[team];
        record.invalid = level.outlands_contracts_invalid[team];
        record.last_hint = gettime();
        record.observed = gettime();
        level.outlands_contracts_records[team] = record;
        announce( team, "^3Team contract: " + description( kind, record.goal ) );
        diagnostic( "begin", team, record );
    }
}

update_contracts()
{
    foreach ( team in array( "allies", "axis" ) )
    {
        record = level.outlands_contracts_records[team];
        record.current = metric( team, record.kind );
        record.observed = gettime();
        record.progress = record.current - record.baseline;
        record.invalid = level.outlands_contracts_invalid[team];
        if ( !record.complete && record.progress >= record.goal )
        {
            record.complete = 1;
            level.outlands_contracts_completed[team]++;
            level.outlands_contracts_commendations[team]++;
            record.completed_count = level.outlands_contracts_completed[team];
            record.commendations = level.outlands_contracts_commendations[team];
            announce( team, "^2Contract complete! Team commendations: " + record.commendations );
            diagnostic( "complete", team, record );
            milestone = getfunction( "scripts/mp/outlands_operations", "contract_completed" );
            if ( isdefined( milestone ) )
                [[ milestone ]]( team, record.kind, level.outlands_contracts_phase );
        }
        if ( !record.complete && gettime() - record.last_hint >= 30000 )
        {
            record.last_hint = gettime();
            remaining = int( ( level.outlands_contracts_deadline - gettime() ) / 1000 );
            announce( team, "^3Contract: " + description( record.kind, record.goal ) + " | " + record.progress + "/" + record.goal + " | " + remaining + "s" );
        }
    }
}

expire_phase()
{
    foreach ( team in array( "allies", "axis" ) )
    {
        record = level.outlands_contracts_records[team];
        if ( record.complete )
            continue;
        level.outlands_contracts_failed[team]++;
        record.failed_count = level.outlands_contracts_failed[team];
        announce( team, "^7Contract expired: " + record.progress + "/" + record.goal + ". Next task incoming." );
        diagnostic( "expired", team, record );
    }
}

description( kind, goal )
{
    if ( kind == "team_eliminations" )
        return "earn " + goal + " team eliminations";
    if ( kind == "combined_score" )
        return "earn " + goal + " combined scoreboard score";
    // Native match points vary by gametype; they are not capture counts.
    return "earn " + goal + " team match points";
}

announce( team, text )
{
    players = get_players();
    foreach ( player in players )
    {
        if ( !isdefined( player ) || !isplayer( player ) || player istestclient() || team_of( player ) != team )
            continue;
        player iprintln( text );
    }
}

diagnostic( event, team, record )
{
    println( "OUTLANDS_CONTRACT_V1|" + event + "|" + level.outlands_contracts_phase + "|" + team + "|" + record.kind + "|" + record.baseline + "|" + record.current + "|" + record.goal + "|" + record.progress + "|" + record.completed_count + "|" + record.failed_count + "|" + record.commendations + "|" + record.invalid );
}
