// Optional original personal-account adapter. Native stats are read-only.
// No OAuth tokens or pairing codes are written into console diagnostics.
#include common_scripts\utility;

init()
{
    if ( !isdedicated() || !getdvarint( "outlands_accounts" ) )
        return;
    level.outlands_account_epoch = "account_session_" + randomint( 1000000000 ) + "_" + gettime();
    level.outlands_account_serial = 0;
    level.outlands_account_records = [];
    setdvar( "outlands_account_response", "" );
    level thread watch();
    level thread commands();
    level thread consume();
    println( "OUTLANDS_ACCOUNT_READY_V1" );
}

human( player )
{
    return scripts\mp\outlands_ui::eligible( player ) && isdefined( player.guid ) && scripts\mp\outlands_operations::valid_guid( "" + player.guid );
}

parse_command( text )
{
    return scripts\mp\outlands_ui::normalize_command( text ) == "!outlands link";
}

same( record )
{
    if ( !isdefined( record ) || !human( record.player ) )
        return false;
    return ( record.player getentitynumber() ) == record.slot && "" + record.player.guid == record.guid;
}

emit( record, kind )
{
    if ( !same( record ) )
        return;
    record.sequence++;
    xp = -1;
    rank = -1;
    prestige = -1;
    value = record.player GetDStat( "playerstatslist", "RANKXP", "StatValue" );
    if ( isdefined( value ) && value >= 0 && value <= 2147483647 )
        xp = int( value );
    if ( isdefined( record.player.pers["rank"] ) && record.player.pers["rank"] >= 0 && record.player.pers["rank"] <= 54 )
        rank = int( record.player.pers["rank"] ) + 1;
    if ( isdefined( record.player.pers["prestige"] ) && record.player.pers["prestige"] >= 0 && record.player.pers["prestige"] <= 11 )
        prestige = int( record.player.pers["prestige"] );
    if ( kind == "link" )
    {
        record.request = record.session + "_" + record.sequence;
        record.requested = gettime();
    }
    println( "OUTLANDS_ACCOUNT_V1|" + record.session + "|" + record.sequence + "|" + kind + "|" + record.slot + "|" + record.guid + "|" + xp + "|" + rank + "|" + prestige );
}

watch()
{
    level endon( "game_ended" );
    for (;;)
    {
        foreach ( player in get_players() )
        {
            if ( !human( player ) )
                continue;
            slot = player getentitynumber();
            if ( slot < 0 || slot > 17 )
                continue;
            record = level.outlands_account_records[slot];
            if ( !same( record ) || record.player != player )
            {
                level.outlands_account_serial++;
                record = spawnstruct();
                record.player = player;
                record.guid = "" + player.guid;
                record.slot = slot;
                record.session = level.outlands_account_epoch + "_" + slot + "_" + level.outlands_account_serial;
                record.sequence = 0;
                record.next = gettime() + 15000;
                record.last_link = -10000;
                level.outlands_account_records[slot] = record;
                emit( record, "hello" );
            }
            if ( gettime() >= record.next )
            {
                emit( record, "snapshot" );
                record.next = gettime() + 15000;
            }
        }
        // Silent/disconnected/map-ended sessions expire their live status in
        // the account core. No fictional user or catch-up observation is sent.
        wait 2;
    }
}

commands()
{
    level endon( "game_ended" );
    for (;;)
    {
        level waittill( "say", text, player, hidden, team_chat );
        if ( !human( player ) || !parse_command( text ) )
            continue;
        slot = player getentitynumber();
        if ( slot < 0 || slot > 17 )
            continue;
        record = level.outlands_account_records[slot];
        if ( !same( record ) || record.player != player || gettime() - record.last_link < 10000 )
            continue;
        record.last_link = gettime();
        emit( record, "link" );
        player iprintln( "Outlands account: requesting a private pairing code." );
    }
}

consume()
{
    level endon( "game_ended" );
    for (;;)
    {
        wait 0.25;
        text = getdvar( "outlands_account_response" );
        if ( text == "" )
            continue;
        setdvar( "outlands_account_response", "" );
        println( "OUTLANDS_ACCOUNT_MAILBOX_V1" );
        if ( text.size > 220 )
            continue;
        fields = strtok( text, "|" );
        if ( fields.size != 3 || text != fields[0] + "|" + fields[1] + "|" + fields[2] || fields[2].size != 32 )
            continue;
        slot = int( fields[1] );
        if ( slot < 0 || slot > 17 || fields[1] != "" + slot )
            continue;
        record = level.outlands_account_records[slot];
        if ( !same( record ) || !isdefined( record.request ) || fields[0] != record.request || gettime() - record.requested > 10000 )
            continue;
        valid = true;
        for ( i = 0; i < fields[2].size; i++ )
            if ( !issubstr( "0123456789ABCDEF", getsubstr( fields[2], i, i + 1 ) ) )
                valid = false;
        if ( !valid )
            continue;
        record.request = undefined;
        record.player iprintln( "Private Outlands pairing code: " + fields[2] );
        record.player iprintln( "Enter in your signed-in Outlands account. Expires in 3 minutes." );
    }
}
