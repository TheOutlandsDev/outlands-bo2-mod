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
        sample( "sample" );
    }
    level.outlands_verify_completed = 1;
    sample( "complete" );
    request_restart();
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
    println( "OUTLANDS_VERIFY_V1|" + kind + "|" + getdvar( "mapname" ) + "|" + getdvar( "g_gametype" ) + "|" + getdvarint( "outlands_verify_restarted" ) + "|" + bots + "|" + humans + "|" + alive + "|" + playing + "|" + identities + "|" + roles + "|" + careers + "|" + kills + "|" + deaths + "|" + score + "|" + moved + "|" + prematch + "|" + invalid + "|" + pools + "|" + patrols + "|" + getgametypesetting( "scorelimit" ) );
}
