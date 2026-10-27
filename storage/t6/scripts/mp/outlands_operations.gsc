// Original Outlands milestone adapter. Native human XP/DDL remain read-only.
// Native guid is private transport input, never sent to Ollama or public chat.
#include common_scripts\utility;

main()
{
    if ( getdvar( "outlands_operations" ) == "" )
        setdvar( "outlands_operations", 0 );
}

init()
{
    if ( !isdedicated() || isdefined( level.outlands_operations_started ) )
        return;
    level.outlands_operations_started = 1;
    level.outlands_operations_epoch = "o" + randomint( 1000000000 ) + "_" + gettime();
    level.outlands_operations_serial = 0;
    level.outlands_operations_records = [];
    level.outlands_operations_pending = undefined;
    setdvar( "outlands_operation_response", "" );
    level thread watch_operations();
    level thread commands();
    level thread consume();
    level thread finish();
}

human_ready( player )
{
    if ( !getdvarint( "outlands_operations" ) || !isdefined( player ) || !isplayer( player ) || player istestclient() )
        return false;
    if ( !isdefined( player.guid ) || !valid_guid( "" + player.guid ) || !isdefined( player.kills ) || !isdefined( player.score ) )
        return false;
    return isdefined( player.pers["team"] ) && ( player.pers["team"] == "allies" || player.pers["team"] == "axis" || ( player.pers["team"] == "free" && getdvar( "g_gametype" ) == "dm" ) );
}

valid_guid( text )
{
    if ( text.size < 1 || text.size > 32 )
        return false;
    nonzero = false;
    for ( i = 0; i < text.size; i++ )
    {
        c = getsubstr( text, i, i + 1 );
        if ( !issubstr( "0123456789abcdefABCDEF", c ) )
            return false;
        if ( c != "0" )
            nonzero = true;
    }
    return nonzero;
}

same_human( record )
{
    if ( !isdefined( record ) || !human_ready( record.player ) )
        return false;
    return ( record.player getentitynumber() ) == record.slot && "" + record.player.guid == record.guid && isdefined( record.player.outlands_operation_session ) && record.player.outlands_operation_session == record.session;
}

new_record( player, slot )
{
    level.outlands_operations_serial++;
    record = spawnstruct();
    record.player = player;
    record.slot = slot;
    record.guid = "" + player.guid;
    record.session = level.outlands_operations_epoch + "_" + slot + "_" + level.outlands_operations_serial;
    player.outlands_operation_session = record.session;
    record.sequence = 0;
    record.objective = 0;
    record.support = 0;
    record.phase = -1;
    record.credited_phase = -1;
    record.next_send = gettime();
    record.started = 0;
    record.command = "none";
    record.track = "none";
    record.last_command = -10000;
    record.team = player.pers["team"];
    record.restored = 0;
    return record;
}

watch_operations()
{
    level endon( "game_ended" );
    for (;;)
    {
        if ( !getdvarint( "outlands_operations" ) )
        {
            level.outlands_operations_records = [];
            level.outlands_operations_pending = undefined;
            setdvar( "outlands_operation_response", "" );
            wait 2;
            continue;
        }
        players = get_players();
        foreach ( player in players )
        {
            if ( !human_ready( player ) )
                continue;
            slot = player getentitynumber();
            if ( slot < 0 || slot > 17 )
                continue;
            record = level.outlands_operations_records[slot];
            if ( !same_human( record ) || record.player != player || record.team != player.pers["team"] )
            {
                record = new_record( player, slot );
                level.outlands_operations_records[slot] = record;
            }
            if ( isdefined( level.outlands_contracts_phase ) && record.phase != level.outlands_contracts_phase )
            {
                record.phase = level.outlands_contracts_phase;
                record.phase_score = int( player.score );
            }
        }
        for ( slot = 0; slot <= 17; slot++ )
        {
            record = level.outlands_operations_records[slot];
            if ( isdefined( record ) && !same_human( record ) )
                level.outlands_operations_records[slot] = undefined;
        }
        if ( !isdefined( level.outlands_operations_pending ) )
        {
            candidate = undefined;
            for ( slot = 0; slot <= 17; slot++ )
            {
                record = level.outlands_operations_records[slot];
                if ( !same_human( record ) || gettime() < record.next_send )
                    continue;
                if ( !isdefined( candidate ) || record.next_send < candidate.next_send )
                    candidate = record;
            }
            if ( isdefined( candidate ) )
                request( candidate );
        }
        wait 2;
    }
}

// Called only by the verified native contract controller at completion.
contract_completed( team, kind, phase )
{
    if ( !getdvarint( "outlands_operations" ) || ( kind != "team_points" && kind != "combined_score" ) )
        return;
    for ( slot = 0; slot <= 17; slot++ )
    {
        record = level.outlands_operations_records[slot];
        if ( !same_human( record ) || record.team != team || record.player.pers["team"] != team || !record.started || !record.restored )
            continue;
        // Requires an adjacent baseline and personal score contribution during
        // this phase. Team points do not masquerade as individual captures.
        if ( record.phase != phase || record.credited_phase == phase || !isdefined( record.phase_score ) || int( record.player.score ) <= record.phase_score )
            continue;
        record.credited_phase = phase;
        if ( kind == "team_points" )
            record.objective++;
        else
            record.support++;
        if ( record.next_send > gettime() )
            record.next_send = gettime();
    }
}

request( record )
{
    if ( !same_human( record ) || isdefined( level.outlands_operations_pending ) )
        return;
    kills = int( record.player.kills );
    if ( kills < 0 || kills > 1000000 )
        return;
    kind = "snapshot";
    track = "none";
    if ( !record.started )
    {
        kind = "hello";
        record.started = 1;
    }
    else if ( record.command != "none" )
    {
        kind = record.command;
        track = record.track;
        record.command = "none";
        record.track = "none";
    }
    record.sequence++;
    pending = spawnstruct();
    pending.record = record;
    pending.id = record.session + "_" + record.sequence;
    pending.created = gettime();
    pending.retries = 0;
    pending.line = "OUTLANDS_OP_V1|" + record.session + "|" + record.sequence + "|" + kind + "|" + record.slot + "|" + record.guid + "|" + kills + "|" + record.objective + "|" + record.support + "|" + track;
    level.outlands_operations_pending = pending;
    println( pending.line );
}

commands()
{
    level endon( "game_ended" );
    for (;;)
    {
        level waittill( "say", text, player, hidden, team_chat );
        if ( !human_ready( player ) || !isdefined( hidden ) || hidden || !isdefined( team_chat ) || team_chat || !isdefined( text ) )
            continue;
        if ( text.size > 1 && getsubstr( text, 0, 1 ) != "!" )
            text = getsubstr( text, 1 );
        if ( text != "!career" && text != "!track assault" && text != "!track objective" && text != "!track support" )
            continue;
        slot = player getentitynumber();
        record = level.outlands_operations_records[slot];
        if ( !same_human( record ) || !record.restored || gettime() - record.last_command < 5000 )
            continue;
        record.last_command = gettime();
        record.command = "show";
        record.track = "none";
        if ( text != "!career" )
        {
            record.command = "select";
            record.track = getsubstr( text, 7 );
        }
        record.next_send = gettime();
    }
}

number( text, maximum )
{
    if ( text.size < 1 || text.size > 10 )
        return false;
    for ( i = 0; i < text.size; i++ )
        if ( !issubstr( "0123456789", getsubstr( text, i, i + 1 ) ) )
            return false;
    value = int( text );
    return value >= 0 && value <= maximum && text == "" + value;
}

consume()
{
    level endon( "game_ended" );
    for (;;)
    {
        response = getdvar( "outlands_operation_response" );
        if ( response != "" )
        {
            setdvar( "outlands_operation_response", "" );
            if ( getdvarint( "outlands_operations" ) && isdefined( level.outlands_operations_pending ) )
                accept( response );
        }
        if ( isdefined( level.outlands_operations_pending ) )
        {
            pending = level.outlands_operations_pending;
            if ( !same_human( pending.record ) )
                level.outlands_operations_pending = undefined;
            else if ( gettime() - pending.created > 5000 )
            {
                // Reuse the exact observation after a worker restart or UDP
                // loss; the ledger commits before replying and deduplicates it.
                if ( pending.retries < 3 )
                {
                    pending.retries++;
                    pending.created = gettime();
                    println( pending.line );
                }
                else
                {
                    pending.record.next_send = gettime() + 15000;
                    // No acknowledged hello means a new baseline on retry.
                    if ( !pending.record.restored )
                        pending.record.started = 0;
                    level.outlands_operations_pending = undefined;
                }
            }
        }
        wait 0.25;
    }
}

accept( response )
{
    if ( response.size > 192 )
        return;
    fields = strtok( response, "|" );
    if ( fields.size != 7 )
        return;
    canonical = fields[0] + "|" + fields[1] + "|" + fields[2] + "|" + fields[3] + "|" + fields[4] + "|" + fields[5] + "|" + fields[6];
    if ( response != canonical || !number( fields[1], 17 ) || !number( fields[2], 1000000000 ) || !number( fields[3], 1000000000 ) || !number( fields[4], 1000000000 ) || !number( fields[6], 1 ) )
        return;
    if ( fields[5] != "assault" && fields[5] != "objective" && fields[5] != "support" )
        return;
    pending = level.outlands_operations_pending;
    record = pending.record;
    if ( fields[0] != pending.id || int( fields[1] ) != record.slot || !same_human( record ) || gettime() - pending.created > 5000 )
        return;
    values = array( int( fields[2] ), int( fields[3] ), int( fields[4] ) );
    changed = !record.restored;
    if ( record.restored )
        changed = tier( values[0], "assault" ) != tier( record.totals[0], "assault" ) || tier( values[1], "objective" ) != tier( record.totals[1], "objective" ) || tier( values[2], "support" ) != tier( record.totals[2], "support" ) || fields[5] != record.selected;
    record.totals = values;
    record.selected = fields[5];
    record.restored = 1;
    record.next_send = gettime() + 15000;
    if ( changed || issubstr( pending.line, "|show|" ) )
    {
        record.player iprintln( "^3Outlands career ^7Assault " + values[0] + " | Objective " + values[1] + " | Support " + values[2] );
        record.player iprintln( "^7Tracking: " + record.selected + " | !career / !track assault, objective, support" );
    }
    if ( int( fields[6] ) == 1 && ( !isdefined( record.operation_complete ) || !record.operation_complete ) )
        record.player iprintlnbold( "^2Broken Signal complete - Field Regular" );
    record.operation_complete = int( fields[6] );
    level.outlands_operations_pending = undefined;
    println( "Outlands operations: validated one private milestone restore." );
}

finish()
{
    level waittill( "game_ended" );
    // Final observations cannot wait for the display mailbox during rotation.
    // Any previously in-flight sample has a lower sequence and is idempotent.
    for ( slot = 0; slot <= 17; slot++ )
    {
        record = level.outlands_operations_records[slot];
        if ( !same_human( record ) || !record.restored )
            continue;
        record.sequence++;
        println( "OUTLANDS_OP_V1|" + record.session + "|" + record.sequence + "|snapshot|" + record.slot + "|" + record.guid + "|" + int( record.player.kills ) + "|" + record.objective + "|" + record.support + "|none" );
    }
}


tier( value, track )
{
    thresholds = array( 3, 10, 25 );
    if ( track == "assault" )
        thresholds = array( 25, 100, 250 );
    result = 0;
    foreach ( threshold in thresholds )
        if ( value >= threshold )
            result++;
    return result;
}
