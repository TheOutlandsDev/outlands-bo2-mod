// Original local chat bridge for The Outlands BO2 Mod.
// Native AI movement/combat and all human stats remain under the stock game.
// Python reads OUTLANDS_CHAT_V1 lines from the private console log and returns
// one fixed-format response dvar through loopback-restricted RCON.
#include common_scripts\utility;

main()
{
    if ( getdvar( "outlands_chat_enabled" ) == "" )
        setdvar( "outlands_chat_enabled", 0 );
}

init()
{
    if ( !isdedicated() || !getdvarint( "outlands_chat_enabled" ) )
        return;
    if ( isdefined( level.outlands_chat_started ) )
        return;

    level.outlands_chat_started = 1;
    level.outlands_chat_epoch = "m" + randomint( 1000000000 ) + "_" + gettime();
    level.outlands_chat_sequence = 0;
    level.outlands_chat_pending = undefined;
    level.outlands_chat_next_request = gettime() + 15000;
    setdvar( "outlands_chat_response", "" );
    println( "Outlands chat: local bridge active; native AI speakers, one pending request maximum." );
    level thread watch_public_chat();
    level thread periodic_banter();
    level thread consume_responses();
}

bounded_seconds( name, fallback, minimum, maximum )
{
    value = fallback;
    if ( getdvar( name ) != "" )
        value = getdvarint( name );
    if ( value < minimum )
        value = minimum;
    if ( value > maximum )
        value = maximum;
    return value;
}

safe_field( text, maximum )
{
    if ( !isdefined( text ) )
        return "";
    allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 _.!?'-~";
    result = "";
    // Bound raw scanning as well as output; never copy controls or pipes.
    limit = text.size;
    if ( limit > 512 )
        limit = 512;
    for ( index = 0; index < limit && result.size < maximum; index++ )
    {
        character = getsubstr( text, index, index + 1 );
        if ( character == "^" && index + 1 < limit )
        {
            index++;
            continue;
        }
        if ( issubstr( allowed, character ) )
            result += character;
    }
    return result;
}

safe_reply( text )
{
    if ( !isdefined( text ) || text.size < 1 || text.size > 120 )
        return false;
    allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 .,!?'-";
    has_word = false;
    for ( index = 0; index < text.size; index++ )
    {
        character = getsubstr( text, index, index + 1 );
        if ( !issubstr( allowed, character ) )
            return false;
        if ( issubstr( "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789", character ) )
            has_word = true;
    }
    return has_word;
}

chat_population()
{
    population = spawnstruct();
    population.humans = 0;
    population.bots = [];
    players = get_players();
    for ( index = 0; index < players.size; index++ )
    {
        player = players[index];
        if ( !isdefined( player ) || !isplayer( player ) )
            continue;
        if ( !player istestclient() )
        {
            population.humans++;
            continue;
        }
        if ( !isdefined( player.name ) || player.name == "" )
            continue;
        if ( !isdefined( player.sessionstate ) || player.sessionstate != "playing" )
            continue;
        // Exact name must survive the wire format without alteration.
        if ( safe_field( player.name, 24 ) == player.name )
            population.bots[population.bots.size] = player;
    }
    return population;
}

request_chat( kind, speaker, text )
{
    if ( !getdvarint( "outlands_chat_enabled" ) || isdefined( level.outlands_chat_pending ) )
        return;
    if ( gettime() < level.outlands_chat_next_request )
        return;

    population = chat_population();
    if ( population.humans < 1 || population.bots.size < 1 )
        return;
    bot = population.bots[randomint( population.bots.size )];
    level.outlands_chat_sequence++;
    request = spawnstruct();
    request.id = level.outlands_chat_epoch + "_" + level.outlands_chat_sequence;
    request.bot = bot;
    request.slot = bot getentitynumber();
    request.name = bot.name;
    request.created = gettime();
    level.outlands_chat_pending = request;
    cooldown = bounded_seconds( "outlands_chat_cooldown", 20, 10, 120 );
    level.outlands_chat_next_request = gettime() + cooldown * 1000;

    println( "OUTLANDS_CHAT_V1|" + request.id + "|" + request.slot + "|" + request.name + "|" + kind + "|" + safe_field( getdvar( "mapname" ), 32 ) + "|" + safe_field( getdvar( "g_gametype" ), 16 ) + "|" + safe_field( speaker, 24 ) + "|" + safe_field( text, 240 ) );
}

watch_public_chat()
{
    level endon( "game_ended" );
    for (;;)
    {
        level waittill( "say", message, player, was_hidden, is_team_chat );
        if ( !getdvarint( "outlands_chat_enabled" ) )
            continue;
        if ( !isdefined( player ) || !isplayer( player ) || player istestclient() )
            continue;
        // Fail closed if the runtime does not supply privacy-mode flags.
        if ( !isdefined( was_hidden ) || was_hidden || !isdefined( is_team_chat ) || is_team_chat )
            continue;
        if ( !isdefined( message ) || message.size < 1 )
            continue;
        // Some T6 chat messages have one leading control character.
        if ( getsubstr( message, 0, 1 ) == "/" )
            continue;
        if ( message.size > 1 && getsubstr( message, 1, 2 ) == "/" )
            continue;
        public_text = safe_field( message, 240 );
        if ( public_text == "" )
            continue;
        request_chat( "reply", player.name, public_text );
    }
}

periodic_banter()
{
    level endon( "game_ended" );
    for (;;)
    {
        interval = bounded_seconds( "outlands_chat_interval", 60, 30, 600 );
        wait interval;
        if ( getdvarint( "outlands_chat_enabled" ) )
            request_chat( "banter", "match", "A brief in-character reaction to this multiplayer match." );
    }
}

consume_responses()
{
    level endon( "game_ended" );
    for (;;)
    {
        wait 0.5;
        response = getdvar( "outlands_chat_response" );
        if ( response != "" )
        {
            // Consume once even if malformed, stale or disabled.
            setdvar( "outlands_chat_response", "" );
            if ( getdvarint( "outlands_chat_enabled" ) )
                accept_response( response );
        }
        if ( isdefined( level.outlands_chat_pending ) )
        {
            timeout = bounded_seconds( "outlands_chat_timeout", 45, 10, 120 );
            if ( gettime() - level.outlands_chat_pending.created > timeout * 1000 )
            {
                level.outlands_chat_pending = undefined;
                println( "Outlands chat: pending request expired without speech." );
            }
        }
    }
}

accept_response( response )
{
    if ( !isdefined( level.outlands_chat_pending ) || response.size > 240 )
        return;
    fields = strtok( response, "|" );
    if ( fields.size != 4 )
        return;
    if ( response != fields[0] + "|" + fields[1] + "|" + fields[2] + "|" + fields[3] )
        return;
    request = level.outlands_chat_pending;
    if ( fields[0] != request.id || fields[1] != "" + request.slot || fields[2] != request.name )
        return;
    timeout = bounded_seconds( "outlands_chat_timeout", 45, 10, 120 );
    if ( gettime() - request.created > timeout * 1000 )
        return;
    bot = request.bot;
    if ( !isdefined( bot ) || !isplayer( bot ) || !bot istestclient() )
        return;
    if ( ( bot getentitynumber() ) != request.slot || bot.name != request.name )
        return;
    if ( !safe_reply( fields[3] ) )
        return;
    population = chat_population();
    if ( population.humans < 1 )
        return;

    level.outlands_chat_pending = undefined;
    bot sayall( fields[3] );
    println( "Outlands chat: native speaker delivered one bounded response." );
}
