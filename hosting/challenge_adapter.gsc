// Original opt-in challenge preview. Installed only in disposable state for now.
// Uses the engine's additional death-callback list; never replaces native rank,
// combat, DDL, kill callbacks or player inventory. Private logs only.
#include common_scripts\utility;

main()
{
    if ( getdvar( "outlands_challenges" ) == "" )
        setdvar( "outlands_challenges", 0 );
    if ( getdvar( "outlands_challenge_accounts" ) == "" )
        setdvar( "outlands_challenge_accounts", 0 );
}

init()
{
    if ( !isdedicated() || !getdvarint( "outlands_challenges" ) || isdefined( level.outlands_challenges_started ) )
        return;
    token = getdvar( "outlands_challenge_token" );
    if ( token.size != 64 )
        return;
    if ( getdvarint( "outlands_challenge_accounts" ) && !getdvarint( "outlands_accounts" ) )
        return;
    level.outlands_challenges_started = 1;
    level.outlands_challenge_epoch = "ch" + randomint( 1000000000 ) + "_" + gettime();
    level.outlands_challenge_serial = 0;
    level.outlands_challenge_records = [];
    level.outlands_challenge_deaths = 0;
    level.outlands_challenge_bot_rejections = 0;
    level.outlands_challenge_emitted_kills = 0;
    level.outlands_challenge_account_kills = 0;
    level.outlands_challenge_bind_requests = 0;
    level.outlands_challenge_grants_applied = 0;
    setdvar( "outlands_challenge_grant", "" );
    if ( getdvarint( "outlands_challenge_accounts" ) )
        level thread consume_grants();
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
    if ( getdvarint( "outlands_challenge_accounts" ) ) return;
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
        record.account_session = ""; record.grant = ""; record.grant_deadline = 0;
        record.next_bind = 0; record.bind_sequence = 0;
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
                if ( getdvarint( "outlands_challenge_accounts" ) )
                {
                    request_binding( record );
                    continue;
                }
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

account_record( record )
{
    if ( !human( record.player ) || !isdefined( level.outlands_account_records ) ) return undefined;
    account = level.outlands_account_records[record.slot];
    if ( !scripts\mp\outlands_accounts::same( account ) || account.player != record.player ) return undefined;
    if ( tolower( account.guid ) != record.guid ) return undefined;
    return account;
}

request_binding( record )
{
    account = account_record( record );
    if ( !isdefined( account ) )
    {
        record.grant = ""; record.account_session = "";
        return;
    }
    if ( record.account_session != account.session )
    {
        record.account_session = account.session; record.grant = "";
        record.next_bind = 0; record.request = undefined;
    }
    if ( record.grant != "" && gettime() + 120000 < record.grant_deadline ) return;
    if ( gettime() < record.next_bind ) return;
    record.next_bind = gettime() + 5000;
    record.bind_sequence++;
    record.request = record.session + "_b" + record.bind_sequence;
    record.requested = gettime();
    level.outlands_challenge_bind_requests++;
    scripts\mp\outlands_log::emit( "OUTLANDS_CHALLENGE_BIND_V1|" + getdvar( "outlands_challenge_token" ) + "|" + record.request + "|" + record.slot + "|" + record.account_session + "|" + record.guid );
}

valid_chars( text, alphabet, minimum, maximum )
{
    if ( text.size < minimum || text.size > maximum ) return false;
    for ( i = 0; i < text.size; i++ )
        if ( !issubstr( alphabet, getsubstr( text, i, i + 1 ) ) ) return false;
    return true;
}

parse_grant( text )
{
    if ( text.size > 300 ) return undefined;
    f = strtok( text, "|" );
    if ( f.size != 5 || text != f[0] + "|" + f[1] + "|" + f[2] + "|" + f[3] + "|" + f[4] ) return undefined;
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-";
    if ( !valid_chars( f[0], alphabet, 1, 64 ) || !valid_chars( f[2], alphabet, 16, 100 ) ) return undefined;
    if ( !valid_chars( f[3], "0123456789abcdef", 64, 64 ) ) return undefined;
    slot = int( f[1] ); seconds = int( f[4] );
    if ( slot < 0 || slot > 17 || f[1] != "" + slot || seconds < 1 || seconds > 21600 || f[4] != "" + seconds ) return undefined;
    value = spawnstruct(); value.request = f[0]; value.slot = slot;
    value.account_session = f[2]; value.grant = f[3]; value.seconds = seconds;
    return value;
}

consume_grants()
{
    level endon( "game_ended" );
    for (;;)
    {
        wait 0.25;
        text = getdvar( "outlands_challenge_grant" );
        if ( text == "" ) continue;
        setdvar( "outlands_challenge_grant", "" );
        value = parse_grant( text );
        if ( !isdefined( value ) ) continue;
        // Consumption ACK contains no grant or account identifier.
        scripts\mp\outlands_log::emit( "OUTLANDS_CHALLENGE_BIND_ACK_V1|" + value.request );
        record = level.outlands_challenge_records[value.slot];
        if ( !isdefined( record ) ) continue;
        account = account_record( record );
        if ( !isdefined( account ) || value.account_session != account.session || value.account_session != record.account_session ) continue;
        if ( !isdefined( record.request ) || value.request != record.request || gettime() - record.requested > 10000 ) continue;
        first = record.grant == "";
        record.grant = value.grant; record.grant_deadline = gettime() + value.seconds * 1000;
        record.request = undefined; level.outlands_challenge_grants_applied++;
        if ( first ) record.player iprintln( "Outlands AN-94 challenge active for your verified account." );
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
    if ( getdvarint( "outlands_challenge_accounts" ) )
    {
        account = account_record( record );
        if ( !isdefined( account ) || record.grant == "" || gettime() >= record.grant_deadline || record.account_session != account.session ) return;
        record.sequence++;
        scripts\mp\outlands_log::emit( "OUTLANDS_CHALLENGE_KILL_V2|" + getdvar( "outlands_challenge_token" ) + "|" + record.grant + "|" + record.account_session + "|" + level.outlands_challenge_epoch + "|" + record.session + "|" + record.sequence + "|an94_mp|1|1|1|1" );
        level.outlands_challenge_account_kills++;
        return;
    }
    emit( record, "kill", "an94_mp", 1, 1, 1 );
    level.outlands_challenge_emitted_kills++;
}
