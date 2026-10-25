// Original diagnostic source. Reads live rank XP; never changes player stats.
// Loaded and init() executed on Raid in Proton and isolated Docker smoke tests.
// Gameplay and progression persistence remain untested.

init()
{
    if ( getdvar( "outlands_status" ) == "" )
        setdvar( "outlands_status", 1 );

    if ( !getdvarint( "outlands_status" ) )
        return;

    println( "[Outlands] Progression probe active. Rank cap=" + getdvarint( "scr_max_rank" ) + " minimum prestige=" + getdvarint( "scr_min_prestige" ) );
    level thread watch_connections();
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
