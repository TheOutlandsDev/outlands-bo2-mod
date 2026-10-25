// Original Outlands fill controller using the native T6 spawnbot command.
// Exactly one controller owns population. Stock loadout/combat scripts remain.
// No human XP, unlocks or stats are written by this module.
#include common_scripts\utility;

main()
{
    if ( !isdedicated() || !getdvarint( "outlands_native_bots" ) )
        return;

    // Native _bot::init still installs its loadout listener before these gates.
    // Do not let its automatic manager compete with this controller.
    setdvar( "bot_friends", 0 );
    setdvar( "bot_enemies", 0 );
    level.outlands_native_bots_active = 1;
}

init()
{
    if ( !isdefined( level.outlands_native_bots_active ) )
        return;
    if ( isdefined( level.outlands_native_bots_controller_started ) )
        return;

    level.outlands_native_bots_controller_started = 1;
    apply_native_difficulty();
    println( "Outlands native bots: single-owner command fill controller active." );
    level thread fill_native_bots();
    level thread watch_native_personas();
}

// Presentation comes from native bots.txt. Chat voice and optional display
// levels never alter native movement, aim, loadout eligibility or human stats.
watch_native_personas()
{
    level endon( "game_ended" );
    for (;;)
    {
        if ( !getdvarint( "outlands_native_bots" ) )
            return;

        players = get_players();
        for ( index = 0; index < players.size; index++ )
        {
            bot = players[index];
            if ( !isdefined( bot ) || !isplayer( bot ) || !bot istestclient() )
                continue;
            if ( !isdefined( bot.name ) )
                continue;

            if ( !isdefined( bot.outlands_persona ) )
            {
                bot.outlands_alias = bot.name;
                bot.outlands_persona = persona_for_alias( bot.name );
                println( "Outlands native bot persona: slot=" + ( bot getentitynumber() ) + " name=" + bot.outlands_alias + " voice=" + bot.outlands_persona );
            }
            if ( !isdefined( bot.outlands_cosmetic_level_started ) )
            {
                bot.outlands_cosmetic_level_started = 1;
                bot thread watch_cosmetic_level();
            }
            if ( !isdefined( bot.outlands_loadout_probe_started ) )
            {
                bot.outlands_loadout_probe_started = 1;
                bot thread watch_native_loadouts();
            }
        }
        wait 2;
    }
}

watch_native_loadouts()
{
    self endon( "disconnect" );
    level endon( "game_ended" );
    if ( !isdedicated() || !self istestclient() || !getdvarint( "outlands_status" ) )
        return;

    samples = 0;
    if ( self log_native_loadout() )
        samples++;
    while ( samples < 3 )
    {
        self waittill( "spawned_player" );
        wait 0.1;
        if ( !getdvarint( "outlands_status" ) )
            return;
        if ( self log_native_loadout() )
            samples++;
    }
}

log_native_loadout()
{
    if ( !isdedicated() || !self istestclient() || !getdvarint( "outlands_status" ) )
        return false;
    if ( !isdefined( self.sessionstate ) || self.sessionstate != "playing" )
        return false;

    class_name = "unknown";
    if ( isdefined( self.pers["class"] ) )
        class_name = self.pers["class"];
    class_index = -1;
    primary = "unknown";
    secondary = "unknown";
    if ( isdefined( self.class_num ) && self.class_num >= 0 && self.class_num <= 9 )
    {
        class_index = self.class_num;
        primary = self getloadoutweapon( class_index, "primary" );
        secondary = self getloadoutweapon( class_index, "secondary" );
    }
    println( "Outlands native bot loadout: slot=" + ( self getentitynumber() ) + " name=" + self.name + " class=" + class_name + " index=" + class_index + " current=" + ( self getcurrentweapon() ) + " primary=" + primary + " secondary=" + secondary );
    return true;
}

watch_cosmetic_level()
{
    self endon( "disconnect" );
    level endon( "game_ended" );
    if ( !isdedicated() || !self istestclient() || !getdvarint( "outlands_bot_levels" ) )
        return;

    // Let the stock bot rank/loadout initialization finish first. Never call
    // syncxpstat or write pers rank/XP: the chosen level is display-only.
    attempts = 0;
    while ( !isdefined( self.pers["bot_loadout"] ) && attempts < 100 )
    {
        wait 0.1;
        attempts++;
    }
    if ( !isdefined( self.pers["bot_loadout"] ) || !self istestclient() )
        return;

    maximum = 55;
    if ( isdefined( level.maxrank ) && level.maxrank + 1 < maximum )
        maximum = level.maxrank + 1;
    low = 1;
    high = maximum;
    if ( getdvar( "outlands_bot_level_min" ) != "" )
        low = getdvarint( "outlands_bot_level_min" );
    if ( getdvar( "outlands_bot_level_max" ) != "" )
        high = getdvarint( "outlands_bot_level_max" );
    if ( low < 1 )
        low = 1;
    if ( low > maximum )
        low = maximum;
    if ( high < low )
        high = low;
    if ( high > maximum )
        high = maximum;

    self.outlands_cosmetic_level = randomintrange( low, high + 1 );
    self apply_cosmetic_level();
    println( "Outlands native bot display: slot=" + ( self getentitynumber() ) + " name=" + self.name + " cosmetic level=" + self.outlands_cosmetic_level );
    for (;;)
    {
        self waittill( "spawned_player" );
        wait 0.05;
        if ( !getdvarint( "outlands_bot_levels" ) )
            return;
        self apply_cosmetic_level();
    }
}

apply_cosmetic_level()
{
    if ( !isdedicated() || !self istestclient() || !getdvarint( "outlands_bot_levels" ) )
        return;
    if ( !isdefined( self.outlands_cosmetic_level ) )
        return;
    // Native _bot::bot_set_rank uses this same API; rank indexes are zero-based.
    self setrank( self.outlands_cosmetic_level - 1 );
}

persona_for_alias( alias )
{
    switch ( alias )
    {
        case "Trailblazer": return "upbeat flanker, brief confident callouts";
        case "MossCircuit": return "calm support, friendly and observant";
        case "NightLedger": return "dry strategist, measured and concise";
        case "CopperWren": return "cheerful teammate, light wordplay";
        case "StaticBloom": return "energetic rusher, playful without insults";
        case "RiftRunner": return "competitive flanker, respects good plays";
        case "AshSignal": return "quiet anchor, useful short callouts";
        case "WinterByte": return "cool analyst, understated humor";
        case "QuietSparks": return "reserved teammate, encouraging when it counts";
        case "CometRidge": return "optimistic challenger, quick reactions in chat";
        case "NovaLatch": return "curious tactician, asks short friendly questions";
        case "GravelPulse": return "steady veteran, practical and patient";
        case "PaperFalcon": return "witty improviser, never hostile";
        case "OrbitMoth": return "relaxed night owl, odd gentle humor";
        case "CedarGhost": return "polite scout, low-key precise callouts";
        case "VelvetRook": return "composed planner, courteous competition";
        case "IronTangent": return "direct objective player, team-first comments";
        case "SolarKite": return "bright optimist, celebrates teammates";
    }
    return "calm adaptive teammate, short friendly comments";
}

apply_native_difficulty()
{
    difficulty = 1;
    if ( getdvar( "outlands_bot_difficulty" ) != "" )
        difficulty = getdvarint( "outlands_bot_difficulty" );
    if ( difficulty < 0 || difficulty > 3 )
        difficulty = 1;

    modes = array( "easy", "normal", "hard", "fu" );
    setdvar( "bot_difficulty", difficulty );
    level.bot_difficulty = modes[difficulty];

    // Apply only native difficulty tuning, not bot/loadout initialization.
    tune = getfunction( "maps/mp/bots/_bot", "bot_set_difficulty" );
    if ( isdefined( tune ) )
        [[ tune ]]();
    else
        println( "Outlands native bots: native difficulty tuning helper unavailable." );
}

population()
{
    counts = spawnstruct();
    counts.humans = 0;
    counts.bots = [];
    players = get_players();
    for ( index = 0; index < players.size; index++ )
    {
        player = players[index];
        if ( !isdefined( player ) || !isplayer( player ) )
            continue;
        if ( player istestclient() )
            counts.bots[counts.bots.size] = player;
        else
            counts.humans++;
    }
    return counts;
}

fill_target()
{
    target = 12;
    if ( getdvar( "outlands_bot_fill" ) != "" )
        target = getdvarint( "outlands_bot_fill" );
    maximum = getdvarint( "sv_maxclients" );
    if ( target < 0 )
        target = 0;
    if ( target > maximum )
        target = maximum;
    return target;
}

fill_native_bots()
{
    level endon( "game_ended" );
    wait 1;
    failures = 0;

    for (;;)
    {
        if ( !getdvarint( "outlands_native_bots" ) )
            return;

        counts = population();
        if ( counts.humans < 1 )
        {
            failures = 0;
            wait 2;
            continue;
        }

        target = fill_target();
        total = counts.humans + counts.bots.size;
        if ( total > target && counts.bots.size > 0 )
        {
            bot = counts.bots[counts.bots.size - 1];
            if ( isdefined( bot ) && bot istestclient() )
                bot botleavegame();
            wait 2;
            continue;
        }
        if ( total >= target )
        {
            failures = 0;
            wait 2;
            continue;
        }

        before = counts.bots.size;
        cmdexec( "spawnbot 1" );
        wait 2;
        after = population();
        if ( after.bots.size > before )
            failures = 0;
        else
        {
            failures++;
            println( "Outlands native bots: native add did not increase test-client count, attempt " + failures + "/3." );
            if ( failures >= 3 )
            {
                println( "Outlands native bots: stopped after three failed native adds." );
                return;
            }
        }
    }
}
