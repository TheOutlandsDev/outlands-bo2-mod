// Original opt-in challenge preview. Installed only in disposable state for now.
// Uses the engine's additional death-callback list; never replaces native rank,
// combat, DDL, kill callbacks or player inventory. Private logs only.
#include common_scripts\utility;

main()
{
    if ( getdvar( "outlands_challenges" ) == "" )
        setdvar( "outlands_challenges", 0 );
}

init()
{
    if ( !isdedicated() || !getdvarint( "outlands_challenges" ) || isdefined( level.outlands_challenges_started ) )
        return;
    token = getdvar( "outlands_challenge_token" );
    if ( token.size != 64 )
        return;
    level.outlands_challenges_started = 1;
    level.outlands_challenge_epoch = "ch" + randomint( 1000000000 ) + "_" + gettime();
    level.outlands_challenge_serial = 0;
    level.outlands_challenge_records = [];
    level.outlands_challenge_deaths = 0;
    level.outlands_challenge_bot_rejections = 0;
    level.outlands_challenge_emitted_kills = 0;
    level thread register();
}

human( player )
{
    return scripts\mp\outlands_ui::eligible( player ) && isdefined( player.guid ) && scripts\mp\outlands_operations::valid_guid( "" + player.guid );
}

register()
{
    level endon( "game_ended" );
    while ( !isdefined( level.onplayerkilledextraunthreadedcbs ) )
        wait 0.05;
    level.onplayerkilledextraunthreadedcbs[level.onplayerkilledextraunthreadedcbs.size] = ::on_killed;
    level.outlands_challenge_registered = 1;
    level thread watch();
    scripts\mp\outlands_log::emit( "OUTLANDS_CHALLENGE_READY_V1" );
}

emit( record, kind, weapon, enemy, headshot, confirmed )
{
    record.sequence++;
    scripts\mp\outlands_log::emit( "OUTLANDS_CHALLENGE_V1|" + getdvar( "outlands_challenge_token" ) + "|" + level.outlands_challenge_epoch + "|" + record.session + "|" + record.sequence + "|" + kind + "|" + record.slot + "|" + record.guid + "|" + weapon + "|1|" + enemy + "|" + headshot + "|" + confirmed );
}

record_for( player )
{
    slot = player getentitynumber();
    record = level.outlands_challenge_records[slot];
    if ( !isdefined( record ) || !isdefined( record.player ) || record.player != player || record.guid != tolower( "" + player.guid ) )
    {
        if ( isdefined( record ) )
            emit( record, "depart", "none", 0, 0, 0 );
        level.outlands_challenge_serial++;
        record = spawnstruct(); record.player = player; record.slot = slot;
        record.guid = tolower( "" + player.guid );
        record.session = level.outlands_challenge_epoch + "_" + slot + "_" + level.outlands_challenge_serial;
        record.sequence = 0; record.next = gettime() + 10000;
        level.outlands_challenge_records[slot] = record;
        emit( record, "hello", "none", 0, 0, 0 );
    }
    return record;
}

watch()
{
    level endon( "game_ended" );
    for (;;)
    {
        if ( getdvarint( "outlands_challenges" ) )
        {
            foreach ( player in get_players() )
            {
                if ( !human( player ) )
                    continue;
                record = record_for( player );
                if ( gettime() >= record.next )
                {
                    emit( record, "hello", "none", 0, 0, 0 );
                    record.next = gettime() + 10000;
                }
            }
        }
        wait 0.25;
    }
}

base_weapon( weapon )
{
    if ( !isdefined( weapon ) )
        return "none";
    parts = strtok( weapon, "+" );
    if ( !parts.size ) return "none";
    return parts[0];
}

on_killed( inflictor, attacker, damage, means, weapon, direction, location, offset, animation )
{
    if ( !getdvarint( "outlands_challenges" ) ) return;
    level.outlands_challenge_deaths++;
    if ( !human( attacker ) )
    {
        level.outlands_challenge_bot_rejections++;
        return;
    }
    if ( !isdefined( self ) || !isplayer( self ) || self == attacker || !isdefined( level.teambased ) ) return;
    if ( !isdefined( self.team ) || !isdefined( attacker.team ) || self.team == "spectator" || attacker.team == "spectator" ) return;
    if ( level.teambased && self.team == attacker.team ) return;
    if ( base_weapon( weapon ) != "an94_mp" || location != "head" ) return;
    if ( means != "MOD_HEAD_SHOT" && means != "MOD_RIFLE_BULLET" ) return;
    if ( !isdefined( self.deathcount ) ) return;
    if ( isdefined( self.outlands_challenge_seen_death ) && self.outlands_challenge_seen_death == self.deathcount ) return;
    self.outlands_challenge_seen_death = self.deathcount;
    record = record_for( attacker );
    emit( record, "kill", "an94_mp", 1, 1, 1 );
    level.outlands_challenge_emitted_kills++;
}
