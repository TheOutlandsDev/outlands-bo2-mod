// Original Outlands bot-career telemetry and cosmetic profile mailbox.
// Call start() explicitly. Native gameplay counters and all human stats are read-only.
// OUTLANDS_BOT_V1|session|event_id|kind|slot|alias|kills|deaths|score|map|mode
#include common_scripts\utility;

start()
{
    if ( !isdedicated() || !getdvarint( "outlands_native_bots" ) || !getdvarint( "outlands_bot_careers" ) )
        return;
    if ( isdefined( level.outlands_careers_started ) )
        return;

    level.outlands_careers_started = 1;
    level.outlands_careers_epoch = "b" + randomint( 1000000000 ) + "_" + gettime();
    level.outlands_careers_sequence = 0;
    level.outlands_careers_tick = 0;
    level.outlands_careers_records = [];
    level.outlands_careers_pending = undefined;
    level.outlands_careers_ending = 0;
    level.outlands_careers_paused = 0;
    level.outlands_careers_map = wire_token( getdvar( "mapname" ), 32 );
    level.outlands_careers_mode = wire_token( getdvar( "g_gametype" ), 16 );
    setdvar( "outlands_bot_profile_response", "" );
    println( "Outlands bot careers: bot-only snapshots and cosmetic restore mailbox active." );
    level thread watch_careers();
    level thread consume_profiles();
    level thread finish_careers();
}

careers_enabled()
{
    return isdedicated() && getdvarint( "outlands_native_bots" ) && getdvarint( "outlands_bot_careers" );
}

bounded_seconds( setting, fallback, minimum, maximum )
{
    value = fallback;
    if ( getdvar( setting ) != "" )
        value = getdvarint( setting );
    if ( value < minimum )
        value = minimum;
    if ( value > maximum )
        value = maximum;
    return value;
}

wire_token( text, maximum )
{
    if ( !isdefined( text ) || text.size < 1 || text.size > maximum )
        return "unknown";
    allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-";
    for ( index = 0; index < text.size; index++ )
    {
        if ( !issubstr( allowed, getsubstr( text, index, index + 1 ) ) )
            return "unknown";
    }
    return text;
}

fictional_alias( alias )
{
    if ( !isdefined( alias ) || alias.size < 1 || alias.size > 24 )
        return false;
    // Exact public roster only: enabling friend-name bots must not export names.
    roster = "|Trailblazer|MossCircuit|NightLedger|CopperWren|StaticBloom|RiftRunner|AshSignal|WinterByte|QuietSparks|CometRidge|NovaLatch|GravelPulse|PaperFalcon|OrbitMoth|CedarGhost|VelvetRook|IronTangent|SolarKite|maple_404|pocketNoodles|LoFiRanger|driftwood77|ByteSized|tundra.tom|SpareBattery|left_lane|CloudNine9|RustyOrbit|biscuitBandit|PINEDROP|slowmo_joe|PebbleDash|Rook.42|latencyLlama|teal_wolf|Snowcap87|vanta_echo|SodaCircuit|PepperPilot|nimbus.exe|SideQuestSam|mellowMako|RustedCompass|FIZZ_23|tapeDeck|ParcelFox|ember-lane|MostlyMoss|";
    if ( issubstr( alias, "|" ) )
        return false;
    return issubstr( roster, "|" + alias + "|" );
}

native_sample()
{
    if ( !isdedicated() || !isdefined( self ) || !isplayer( self ) || !self istestclient() )
        return undefined;
    if ( !isdefined( self.name ) || !fictional_alias( self.name ) )
        return undefined;
    if ( !isdefined( self.kills ) || !isdefined( self.deaths ) || !isdefined( self.score ) )
        return undefined;
    kills = int( self.kills );
    deaths = int( self.deaths );
    score = int( self.score );
    if ( kills < 0 || deaths < 0 || kills > 1000000 || deaths > 1000000 || score < -100000000 || score > 100000000 )
        return undefined;
    sample = spawnstruct();
    sample.kills = kills;
    sample.deaths = deaths;
    sample.score = score;
    return sample;
}

same_occupant( record )
{
    if ( !isdefined( record ) || !isdefined( record.bot ) || !isplayer( record.bot ) || !record.bot istestclient() )
        return false;
    if ( !isdefined( record.bot.name ) || record.bot.name != record.alias )
        return false;
    if ( record.bot getentitynumber() != record.slot )
        return false;
    return isdefined( record.bot.outlands_careers_session ) && record.bot.outlands_careers_session == record.session;
}

new_record( bot, slot, sample )
{
    level.outlands_careers_sequence++;
    record = spawnstruct();
    record.bot = bot;
    record.slot = slot;
    record.alias = bot.name;
    record.session = level.outlands_careers_epoch + "_" + slot + "_" + level.outlands_careers_sequence;
    record.sequence = 0;
    record.sample = sample;
    record.baseline = sample;
    record.hello_sent = 0;
    record.restored = 0;
    record.restore_at = gettime();
    record.next_snapshot = gettime() + bounded_seconds( "outlands_bot_career_snapshot_seconds", 30, 5, 120 ) * 1000;
    bot.outlands_careers_session = record.session;
    return record;
}

event_line( record, event_id, kind, sample )
{
    return "OUTLANDS_BOT_V1|" + record.session + "|" + event_id + "|" + kind + "|" + record.slot + "|" + record.alias + "|" + sample.kills + "|" + sample.deaths + "|" + sample.score + "|" + level.outlands_careers_map + "|" + level.outlands_careers_mode;
}

emit_snapshot( record, kind )
{
    if ( !record.hello_sent )
        return;
    record.sequence++;
    println( event_line( record, record.session + "_" + record.sequence, kind, record.sample ) );
}

retire_record( record )
{
    emit_snapshot( record, "depart" );
    if ( isdefined( level.outlands_careers_pending ) && level.outlands_careers_pending.record.session == record.session )
        level.outlands_careers_pending = undefined;
}

restore_priority( record )
{
    if ( !record.hello_sent )
        return 0;
    if ( !record.restored )
        return 1;
    return 2;
}

request_profile( record )
{
    if ( !same_occupant( record ) || isdefined( level.outlands_careers_pending ) )
        return;
    if ( !record.hello_sent )
    {
        record.sequence++;
        record.hello_id = record.session + "_" + record.sequence;
        record.hello_sent = 1;
    }
    request = spawnstruct();
    request.record = record;
    request.id = record.hello_id;
    request.created = gettime();
    level.outlands_careers_pending = request;
    // Retries and refreshes reuse both ID and the original baseline sample.
    println( event_line( record, record.hello_id, "hello", record.baseline ) );
}

watch_careers()
{
    level endon( "game_ended" );
    wait 1;
    for (;;)
    {
        if ( !careers_enabled() )
        {
            // New sessions on reenabling prevent awarding disabled-period play.
            level.outlands_careers_records = [];
            level.outlands_careers_pending = undefined;
            level.outlands_careers_paused = 1;
            setdvar( "outlands_bot_profile_response", "" );
            wait 1;
            continue;
        }
        level.outlands_careers_paused = 0;
        level.outlands_careers_tick++;
        players = get_players();
        foreach ( bot in players )
        {
            if ( !isdefined( bot ) || !isplayer( bot ) || !bot istestclient() )
                continue;
            slot = bot getentitynumber();
            if ( slot < 0 || slot > 17 )
                continue;
            sample = bot native_sample();
            if ( !isdefined( sample ) )
                continue;
            record = level.outlands_careers_records[slot];
            if ( isdefined( record ) && ( !same_occupant( record ) || record.bot != bot ) )
            {
                retire_record( record );
                record = undefined;
            }
            if ( !isdefined( record ) )
            {
                record = new_record( bot, slot, sample );
                level.outlands_careers_records[slot] = record;
            }
            record.sample = sample;
            record.seen = level.outlands_careers_tick;
            if ( record.hello_sent && gettime() >= record.next_snapshot )
            {
                emit_snapshot( record, "snapshot" );
                record.next_snapshot = gettime() + bounded_seconds( "outlands_bot_career_snapshot_seconds", 30, 5, 120 ) * 1000;
            }
        }
        for ( slot = 0; slot <= 17; slot++ )
        {
            record = level.outlands_careers_records[slot];
            if ( !isdefined( record ) )
                continue;
            if ( !isdefined( record.seen ) || record.seen != level.outlands_careers_tick )
            {
                retire_record( record );
                level.outlands_careers_records[slot] = undefined;
            }
        }
        if ( !isdefined( level.outlands_careers_pending ) )
        {
            // Restore new connections before refreshing established rivals.
            candidate = undefined;
            for ( slot = 0; slot <= 17; slot++ )
            {
                record = level.outlands_careers_records[slot];
                if ( !isdefined( record ) || !same_occupant( record ) || gettime() < record.restore_at )
                    continue;
                if ( !isdefined( candidate ) || restore_priority( record ) < restore_priority( candidate ) )
                    candidate = record;
            }
            if ( isdefined( candidate ) )
                request_profile( candidate );
        }
        wait 1;
    }
}

small_uint( text, maximum )
{
    if ( !isdefined( text ) || text.size < 1 || text.size > 2 )
        return false;
    for ( index = 0; index < text.size; index++ )
    {
        if ( !issubstr( "0123456789", getsubstr( text, index, index + 1 ) ) )
            return false;
    }
    value = int( text );
    return value <= maximum && text == "" + value;
}

valid_role( role )
{
    return role == "rusher" || role == "assault" || role == "objective" || role == "support" || role == "marksman";
}

consume_profiles()
{
    level endon( "game_ended" );
    for (;;)
    {
        response = getdvar( "outlands_bot_profile_response" );
        if ( response != "" )
        {
            setdvar( "outlands_bot_profile_response", "" );
            if ( careers_enabled() && isdefined( level.outlands_careers_pending ) )
                accept_profile( response );
        }
        if ( isdefined( level.outlands_careers_pending ) )
        {
            request = level.outlands_careers_pending;
            timeout = bounded_seconds( "outlands_bot_career_restore_seconds", 15, 5, 30 ) * 1000;
            if ( !careers_enabled() || !same_occupant( request.record ) || gettime() - request.created > timeout )
            {
                request.record.restore_at = gettime() + 30000;
                level.outlands_careers_pending = undefined;
            }
        }
        wait 0.25;
    }
}

accept_profile( response )
{
    if ( !careers_enabled() || !isdefined( level.outlands_careers_pending ) )
        return;
    if ( response.size > 192 )
        return;
    parts = strtok( response, "|" );
    if ( parts.size != 6 )
        return;
    canonical = parts[0] + "|" + parts[1] + "|" + parts[2] + "|" + parts[3] + "|" + parts[4] + "|" + parts[5];
    if ( canonical != response || !small_uint( parts[1], 17 ) || !small_uint( parts[3], 55 ) || !small_uint( parts[4], 10 ) || !valid_role( parts[5] ) )
        return;
    rank_level = int( parts[3] );
    prestige = int( parts[4] );
    if ( rank_level < 1 )
        return;
    if ( isdefined( level.maxrank ) && rank_level > level.maxrank + 1 )
        return;
    if ( isdefined( level.maxprestige ) && prestige > level.maxprestige )
        return;
    request = level.outlands_careers_pending;
    record = request.record;
    timeout = bounded_seconds( "outlands_bot_career_restore_seconds", 15, 5, 30 ) * 1000;
    if ( gettime() - request.created > timeout || !same_occupant( record ) )
        return;
    if ( parts[0] != request.id || int( parts[1] ) != record.slot || parts[2] != record.alias )
        return;
    active = level.outlands_careers_records[record.slot];
    if ( !isdefined( active ) || active.session != record.session || !same_occupant( active ) )
        return;
    // Identical hello refreshes are idempotent. A delayed reply must not lower
    // an already restored career within this connection, including prestige.
    if ( isdefined( record.bot.outlands_career_ready ) && isdefined( record.bot.outlands_career_level ) && isdefined( record.bot.outlands_career_prestige ) )
    {
        old_rank = record.bot.outlands_career_prestige * 55 + record.bot.outlands_career_level;
        if ( prestige * 55 + rank_level < old_rank )
            return;
    }

    // Cosmetic metadata only. The identity owner validates before display.
    record.bot.outlands_career_level = rank_level;
    record.bot.outlands_career_prestige = prestige;
    record.bot.outlands_career_role = parts[5];
    record.bot.outlands_career_ready = 1;
    record.restored = 1;
    record.restore_at = gettime() + 60000;
    level.outlands_careers_pending = undefined;
    record.bot notify( "outlands_career_restored" );
    println( "Outlands bot careers: validated one cosmetic profile restore." );
}

finish_careers()
{
    level waittill( "game_ended" );
    level.outlands_careers_ending = 1;
    level.outlands_careers_pending = undefined;
    setdvar( "outlands_bot_profile_response", "" );
    if ( !careers_enabled() )
        return;
    // Final native counters may settle at frame end; never inspect a new human.
    wait 0.05;
    for ( slot = 0; slot <= 17; slot++ )
    {
        record = level.outlands_careers_records[slot];
        if ( !isdefined( record ) )
            continue;
        if ( same_occupant( record ) )
        {
            sample = record.bot native_sample();
            if ( isdefined( sample ) )
                record.sample = sample;
        }
        emit_snapshot( record, "match_end" );
    }
}
