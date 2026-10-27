// Original diagnostic source. Reads live rank XP; never changes player stats.
// Optional read-only probe for in-session XP; verify persistence after a restart.

#include common_scripts\utility;

init()
{
    // Aggregate, read-only portal telemetry. Never includes names, chat, GUIDs,
    // player XP or loadouts. The optional exporter follows only new records.
    if ( isdedicated() )
        level thread watch_portal();
    if ( getdvar( "outlands_status" ) == "" )
        setdvar( "outlands_status", 1 );

    if ( !getdvarint( "outlands_status" ) )
        return;

    println( "[Outlands] Progression probe active. Rank cap=" + getdvarint( "scr_max_rank" ) + " minimum prestige=" + getdvarint( "scr_min_prestige" ) );
    level thread watch_connections();
}

portal_integer( value, maximum )
{
    if ( !isdefined( value ) || value < 0 )
        return 0;
    if ( value > maximum )
        return maximum;
    return int( value );
}

portal_contract( team )
{
    empty = "none|0|0|0";
    if ( !isdefined( level.outlands_contracts_active ) || !level.outlands_contracts_active || !isdefined( level.outlands_contracts_records ) )
        return empty;
    record = level.outlands_contracts_records[team];
    if ( !isdefined( record ) || !isdefined( record.kind ) || !isdefined( record.observed ) || gettime() - record.observed > 5000 )
        return empty;
    if ( record.kind != "team_eliminations" && record.kind != "combined_score" && record.kind != "team_points" )
        return empty;
    return record.kind + "|" + portal_integer( record.goal, 100000000 ) + "|" + portal_integer( record.progress, 100000000 ) + "|" + portal_integer( record.complete, 1 );
}

portal_snapshot()
{
    humans = 0;
    bots = 0;
    allies = 0;
    axis = 0;
    foreach ( player in get_players() )
    {
        if ( !isdefined( player ) || !isplayer( player ) )
            continue;
        if ( player istestclient() )
            bots++;
        else
            humans++;
        if ( isdefined( player.pers["team"] ) && player.pers["team"] == "allies" )
            allies++;
        if ( isdefined( player.pers["team"] ) && player.pers["team"] == "axis" )
            axis++;
    }
    a_score = 0;
    b_score = 0;
    if ( isdefined( game["teamScores"] ) )
    {
        a_score = portal_integer( game["teamScores"]["allies"], 100000000 );
        b_score = portal_integer( game["teamScores"]["axis"], 100000000 );
    }
    remaining = 0;
    if ( isdefined( level.outlands_contracts_deadline ) )
        remaining = portal_integer( ( level.outlands_contracts_deadline - gettime() ) / 1000, 300 );
    state = "playing";
    if ( !isdefined( game["state"] ) || game["state"] != "playing" || ( isdefined( level.inprematchperiod ) && level.inprematchperiod ) )
        state = "waiting";
    if ( isdefined( level.gameended ) && level.gameended )
        state = "ended";
    return "OUTLANDS_PORTAL_V1|" + getdvar( "mapname" ) + "|" + getdvar( "g_gametype" ) + "|" + state + "|" + gettime() + "|" + humans + "|" + bots + "|" + allies + "|" + axis + "|" + a_score + "|" + b_score + "|" + remaining + "|" + portal_contract( "allies" ) + "|" + portal_contract( "axis" );
}

watch_portal()
{
    level endon( "game_ended" );
    wait 6;
    for (;;)
    {
        println( portal_snapshot() );
        wait 5;
    }
}

watch_connections()
{
    for ( ;; )
    {
        level waittill( "connected", player );
        player thread watch_rank_xp();
    }
}

watch_rank_xp()
{
    self endon( "disconnect" );
    self waittill( "spawned_player" );
    wait 1;

    if ( isdefined( self.pers["isBot"] ) && self.pers["isBot"] )
        return;

    ranked = 0;
    if ( isdefined( level.rankedmatch ) )
        ranked = level.rankedmatch;

    println( "[Outlands] Human spawned. ranked=" + ranked + " native bot host=" + ( self ishostforbots() ) );
    self iprintln( "^2Outlands T6 probe loaded | ranked=" + ranked );
    previous_xp = -1;

    for ( ;; )
    {
        if ( !getdvarint( "outlands_status" ) )
            return;

        // Normal score events award XP through the engine. The pers value is
        // a connection-time snapshot, so read the current DDL stat directly.
        current_xp = self GetDStat( "playerstatslist", "RANKXP", "StatValue" );
        if ( isdefined( current_xp ) )
        {
            if ( current_xp != previous_xp )
            {
                println( "[Outlands] Human DDL rank XP=" + current_xp );
                self iprintln( "^3Outlands T6 live rank XP: " + current_xp );
                previous_xp = current_xp;
            }
        }

        wait 5;
    }
}
