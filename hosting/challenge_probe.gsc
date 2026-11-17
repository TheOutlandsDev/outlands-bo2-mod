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
        if ( getdvarint( "outlands_challenge_accounts" ) )
        {
            checks = grant_parser_checks();
            scripts\mp\outlands_log::emit( "OUTLANDS_CHALLENGE_ACCOUNT_GUARD_V1|" + checks + "|" + level.outlands_challenge_grants_applied + "|" + level.outlands_challenge_account_kills + "|" + level.outlands_challenge_bind_requests );
        }
        wait 5;
    }
}

grant_parser_checks()
{
    checks = 0;
    grant = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
    prefix = "canary_challenge_request|0|synthetic_session_001|";
    if ( isdefined( scripts\mp\outlands_challenge_preview::parse_grant( prefix + grant + "|120" ) ) ) checks++;
    foreach ( text in array( prefix + grant + "|0", prefix + grant + "|21601", prefix + grant + "|0120", prefix + "bad|120", "bad||synthetic_session_001|" + grant + "|120" ) )
        if ( !isdefined( scripts\mp\outlands_challenge_preview::parse_grant( text ) ) ) checks++;
    return checks;
}
