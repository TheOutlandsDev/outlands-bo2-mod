// Original local chat bridge for The Outlands BO2 Mod.
// Native AI movement/combat and all human stats remain under the stock game.
// Python reads OUTLANDS_CHAT_V1 lines from the private console log and returns
// one fixed-format response dvar through loopback-restricted RCON.
#include common_scripts\utility;

main()
{
    if ( getdvar( "outlands_chat_enabled" ) == "" )
        setdvar( "outlands_chat_enabled", 0 );
    if ( getdvar( "outlands_chat_dialogue" ) == "" )
        setdvar( "outlands_chat_dialogue", 1 );
    if ( getdvar( "outlands_chat_tactical" ) == "" )
        setdvar( "outlands_chat_tactical", 1 );
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
    level.outlands_chat_topic = 0;
    level.outlands_chat_pending = undefined;
    level.outlands_chat_human_pending = undefined;
    level.outlands_chat_dialogue_pending = undefined;
    level.outlands_chat_request_times = [];
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
    allowed = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 _.,!?'-~";
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

request_chat( kind, speaker, text, parent_id, topic )
{
    if ( !getdvarint( "outlands_chat_enabled" ) || isdefined( level.outlands_chat_pending ) )
        return false;
    if ( gettime() < level.outlands_chat_next_request )
        return false;
    if ( kind != "reply" && isdefined( level.outlands_chat_human_pending ) )
        return false;
    if ( kind == "banter" && isdefined( level.outlands_chat_dialogue_pending ) )
        return false;
    if ( kind == "bot_reply" && ( !getdvarint( "outlands_chat_dialogue" ) || parent_id == "" || parent_id.size > 62 ) )
        return false;

    population = chat_population();
    if ( population.humans < 1 || population.bots.size < 1 )
        return false;
    eligible = [];
    preferred = [];
    for ( index = 0; index < population.bots.size; index++ )
    {
        candidate = population.bots[index];
        if ( kind == "bot_reply" && candidate.name == speaker )
            continue;
        if ( kind == "bot_reply" && ( !isdefined( level.outlands_chat_dialogue_pending ) || !isdefined( candidate.pers["team"] ) || candidate.pers["team"] != level.outlands_chat_dialogue_pending.team ) )
            continue;
        if ( isdefined( candidate.outlands_chat_next_request ) && gettime() < candidate.outlands_chat_next_request )
            continue;
        candidate_context = task_context( candidate, topic );
        if ( kind == "bot_reply" && candidate_context.topic != topic )
            continue;
        if ( kind == "bot_reply" && topic == "contract" && candidate_context.key != level.outlands_chat_dialogue_pending.context_key )
            continue;
        eligible[eligible.size] = candidate;
        if ( topic != "none" && candidate_context.topic == topic )
            preferred[preferred.size] = candidate;
    }
    if ( preferred.size > 0 )
        eligible = preferred;
    if ( eligible.size < 1 )
        return false;
    recent = [];
    for ( index = 0; index < level.outlands_chat_request_times.size; index++ )
    {
        if ( gettime() - level.outlands_chat_request_times[index] < 60000 )
            recent[recent.size] = level.outlands_chat_request_times[index];
    }
    level.outlands_chat_request_times = recent;
    maximum = bounded_seconds( "outlands_chat_max_per_minute", 4, 1, 6 );
    if ( recent.size >= maximum )
        return false;
    bot = eligible[randomint( eligible.size )];
    level.outlands_chat_sequence++;
    request = spawnstruct();
    request.id = level.outlands_chat_epoch + "_" + level.outlands_chat_sequence;
    if ( kind == "bot_reply" )
        request.id = parent_id + "_r";
    request.kind = kind;
    request.bot = bot;
    request.slot = bot getentitynumber();
    request.name = bot.name;
    request.created = gettime();
    context = task_context( bot, topic );
    request.context_key = context.key;
    request.topic = context.topic;
    request.team = context.team;
    level.outlands_chat_pending = request;
    cooldown = bounded_seconds( "outlands_chat_cooldown", 12, 10, 120 );
    level.outlands_chat_next_request = gettime() + cooldown * 1000;
    bot_cooldown = bounded_seconds( "outlands_chat_bot_cooldown", 60, 30, 3600 );
    bot.outlands_chat_next_request = gettime() + bot_cooldown * 1000;
    level.outlands_chat_request_times[level.outlands_chat_request_times.size] = gettime();

    println( "OUTLANDS_CHAT_V2|" + request.id + "|" + request.slot + "|" + request.name + "|" + kind + "|" + safe_field( getdvar( "mapname" ), 32 ) + "|" + safe_field( getdvar( "g_gametype" ), 16 ) + "|" + safe_field( speaker, 24 ) + "|" + safe_field( text, 240 ) + "|" + context.wire );
    return true;
}

queue_human_reply( player, text )
{
    // One latest public human message only. It takes priority over a queued
    // second bot turn; a model request already in flight may finish first.
    queued = spawnstruct();
    queued.player = player;
    queued.slot = player getentitynumber();
    queued.name = player.name;
    queued.text = text;
    queued.created = gettime();
    level.outlands_chat_human_pending = queued;
    level.outlands_chat_dialogue_pending = undefined;
}

dispatch_queued_chat()
{
    if ( !getdvarint( "outlands_chat_dialogue" ) )
        level.outlands_chat_dialogue_pending = undefined;
    if ( isdefined( level.outlands_chat_human_pending ) )
    {
        queued = level.outlands_chat_human_pending;
        player = queued.player;
        if ( gettime() - queued.created > 20000 || !isdefined( player ) || !isplayer( player ) || player istestclient() )
            level.outlands_chat_human_pending = undefined;
        else if ( ( player getentitynumber() ) != queued.slot || player.name != queued.name )
            level.outlands_chat_human_pending = undefined;
        else if ( request_chat( "reply", queued.name, queued.text, "", "none" ) )
            level.outlands_chat_human_pending = undefined;
        return;
    }
    if ( !isdefined( level.outlands_chat_dialogue_pending ) )
        return;
    dialogue = level.outlands_chat_dialogue_pending;
    speaker = dialogue.bot;
    if ( gettime() > dialogue.expires || !isdefined( speaker ) || !isplayer( speaker ) || !speaker istestclient() )
    {
        level.outlands_chat_dialogue_pending = undefined;
        return;
    }
    if ( ( speaker getentitynumber() ) != dialogue.slot || speaker.name != dialogue.name )
    {
        level.outlands_chat_dialogue_pending = undefined;
        return;
    }
    context = task_context( speaker, dialogue.topic );
    if ( context.key != dialogue.context_key || context.team != dialogue.team )
    {
        level.outlands_chat_dialogue_pending = undefined;
        return;
    }
    if ( gettime() >= dialogue.ready && request_chat( "bot_reply", dialogue.name, dialogue.text, dialogue.parent_id, dialogue.topic ) )
        level.outlands_chat_dialogue_pending = undefined;
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
        queue_human_reply( player, public_text );
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
        {
            topics = array( "squad", "objective", "contract", "none" );
            topic = topics[level.outlands_chat_topic % topics.size];
            level.outlands_chat_topic++;
            request_chat( "banter", "match", "A short natural team comment about your current task.", "", topic );
        }
    }
}

consume_responses()
{
    level endon( "game_ended" );
    for (;;)
    {
        wait 0.5;
        if ( !getdvarint( "outlands_chat_enabled" ) )
        {
            level.outlands_chat_pending = undefined;
            level.outlands_chat_human_pending = undefined;
            level.outlands_chat_dialogue_pending = undefined;
            setdvar( "outlands_chat_response", "" );
            continue;
        }
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
        dispatch_queued_chat();
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
    if ( request.kind == "bot_reply" && !getdvarint( "outlands_chat_dialogue" ) )
    {
        level.outlands_chat_pending = undefined;
        return;
    }
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
    context = task_context( bot, request.topic );
    if ( !isdefined( request.context_key ) || context.key != request.context_key )
        return;
    if ( request.topic != "none" && gettime() - request.created > 15000 )
        return;
    population = chat_population();
    if ( population.humans < 1 )
        return;

    level.outlands_chat_pending = undefined;
    bot sayall( fields[3] );
    println( "OUTLANDS_CHAT_ACK_V1|" + request.id + "|" + request.slot + "|" + request.name + "|" + request.kind );
    println( "Outlands chat: native speaker delivered one bounded response. kind=" + request.kind );
    // Only an accepted opener can schedule one second turn. Bot replies and
    // human replies never extend a conversation, and bot say events are ignored.
    if ( request.kind == "banter" && getdvarint( "outlands_chat_dialogue" ) && !isdefined( level.outlands_chat_human_pending ) )
    {
        dialogue = spawnstruct();
        dialogue.bot = bot;
        dialogue.slot = request.slot;
        dialogue.name = request.name;
        dialogue.text = fields[3];
        dialogue.parent_id = request.id;
        dialogue.topic = request.topic;
        dialogue.team = request.team;
        dialogue.context_key = request.context_key;
        delay = bounded_seconds( "outlands_chat_dialogue_delay", 14, 12, 30 );
        dialogue.ready = gettime() + delay * 1000;
        dialogue.expires = dialogue.ready + 20000;
        level.outlands_chat_dialogue_pending = dialogue;
    }
}

// Typed snapshot of this verified bot's current assignment and team board.
// No human identity, enemy scan, coordinates or assumed A/B/C labels enter it.
task_context( bot, topic )
{
    result = spawnstruct();
    result.topic = "none";
    result.team = "none";
    role = "none";
    target = -1;
    state = "none";
    kind = "none";
    phase = 0;
    progress = 0;
    goal = 0;
    complete = 0;
    remaining = 0;
    if ( isdefined( bot ) && isplayer( bot ) && bot istestclient() && getdvarint( "outlands_chat_tactical" ) && isdefined( bot.pers["team"] ) && ( bot.pers["team"] == "allies" || bot.pers["team"] == "axis" ) )
    {
        result.team = bot.pers["team"];
        valid = getfunction( "scripts/mp/outlands_squads", "assignment_valid" );
        if ( getdvarint( "outlands_squads" ) && isdefined( level.outlands_squads_started ) && isdefined( valid ) && bot [[ valid ]]() )
        {
            role = bot.outlands_squad_role;
            target = bot.outlands_squad_target_id;
            state = "active";
            mode = getdvar( "g_gametype" );
            if ( mode == "dom" && isdefined( level.outlands_squad_owner ) )
            {
                owner = bot.outlands_squad_target [[ level.outlands_squad_owner ]]();
                state = "neutral";
                if ( owner == result.team )
                    state = "friendly";
                else if ( owner == "allies" || owner == "axis" )
                    state = "enemy";
            }
            if ( mode == "ctf" && isdefined( level.outlands_squad_home ) )
            {
                state = "away";
                if ( bot.outlands_squad_target [[ level.outlands_squad_home ]]() )
                    state = "home";
            }
        }
        if ( getdvarint( "outlands_contracts" ) && isdefined( level.outlands_contracts_active ) && level.outlands_contracts_active && isdefined( level.outlands_contracts_records[result.team] ) && gettime() < level.outlands_contracts_deadline )
        {
            record = level.outlands_contracts_records[result.team];
            if ( record.kind == "team_eliminations" || record.kind == "combined_score" || record.kind == "team_points" )
            {
                kind = record.kind;
                phase = level.outlands_contracts_phase;
                progress = record.progress;
                goal = record.goal;
                complete = record.complete;
                remaining = int( ( level.outlands_contracts_deadline - gettime() ) / 1000 );
                if ( remaining < 1 )
                    remaining = 1;
            }
        }
        if ( ( topic == "squad" || topic == "objective" ) && ( role == "attack" || role == "defend" ) )
            result.topic = topic;
        if ( topic == "contract" && kind != "none" )
            result.topic = topic;
    }
    result.wire = result.topic + "|" + result.team + "|" + role + "|" + target + "|" + state + "|" + kind + "|" + phase + "|" + progress + "|" + goal + "|" + complete + "|" + remaining;
    if ( result.topic == "contract" )
        result.key = result.topic + "|" + result.team + "|" + kind + "|" + phase + "|" + complete;
    else if ( result.topic == "squad" || result.topic == "objective" )
        result.key = result.topic + "|" + result.team + "|" + role + "|" + target + "|" + state;
    else
        result.key = result.topic + "|" + result.team + "|" + role + "|" + target + "|" + state + "|" + kind + "|" + phase + "|" + complete;
    return result;
}
