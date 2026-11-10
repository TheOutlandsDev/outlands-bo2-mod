// Disposable negative-ownership probe: real bot deaths never earn human rewards.
#include common_scripts\utility;
main() {}
init()
{
    if ( getdvar( "outlands_backend_verification" ) != "1" || getdvar( "net_ip" ) != "127.0.0.1" ) return;
    level thread observe();
}
observe()
{
    level endon( "game_ended" );
    wait 12;
    for (;;)
    {
        registered = 0;
        if ( isdefined( level.outlands_challenge_registered ) ) registered = level.outlands_challenge_registered;
        excluded = 0;
        foreach ( player in get_players() )
            if ( isdefined( player ) && isplayer( player ) && player istestclient() && !scripts\mp\outlands_challenge_preview::human( player ) ) excluded++;
        basevalid = scripts\mp\outlands_challenge_preview::base_weapon( "an94_mp+reflex" ) == "an94_mp";
        scripts\mp\outlands_log::emit( "OUTLANDS_CHALLENGE_GUARD_V1|" + registered + "|" + level.outlands_challenge_deaths + "|" + level.outlands_challenge_bot_rejections + "|" + level.outlands_challenge_emitted_kills + "|" + basevalid + "|" + excluded );
        wait 5;
    }
}
