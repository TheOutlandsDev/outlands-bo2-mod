// Original Outlands fill controller using the native T6 spawnbot command.
// Exactly one controller owns population. Stock loadout/combat scripts remain.
// No human XP, unlocks or stats are written by this module.
#include common_scripts\utility;

main()
{
    if ( !isdedicated() )
        return;
    // Restore the saved native policy even when this module is disabled next map.
    if ( !getdvarint( "outlands_native_bots" ) )
    {
        update_stock_balance();
        return;
    }

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
    start_team_policy();
    start_extension( "scripts/mp/outlands_bot_profiles", "class and patrol profiles" );
    start_extension( "scripts/mp/outlands_bot_identity", "cosmetic identities" );
    start_extension( "scripts/mp/outlands_bot_careers", "persistent bot careers" );
    start_extension( "scripts/mp/outlands_squads", "coordinated objective squads" );
    start_extension( "scripts/mp/outlands_contracts", "match contracts" );
    println( "Outlands native bots: single-owner command fill controller active." );
    level thread fill_native_bots();
    level thread watch_native_loadout_probes();
}

start_extension( script, label )
{
    start = getfunction( script, "start" );
    if ( isdefined( start ) )
        [[ start ]]();
    else
        println( "Outlands native bots: optional " + label + " unavailable." );
}

// Read-only diagnostics. Identity and class controllers own their independent
// bot-only presentation/profile work; the native game still owns respawning.
watch_native_loadout_probes()
{
    level endon( "game_ended" );
    for (;;)
    {
        if ( !getdvarint( "outlands_native_bots" ) )
        {
            wait 2;
            continue;
        }

        players = get_players();
        for ( index = 0; index < players.size; index++ )
        {
            bot = players[index];
            if ( !isdefined( bot ) || !isplayer( bot ) || !bot istestclient() )
                continue;
            if ( !isdefined( bot.name ) )
                continue;

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
    counts.allies = 0;
    counts.axis = 0;
    counts.spectators = 0;
    counts.unassigned = 0;
    counts.human_allies = 0;
    counts.human_axis = 0;
    counts.inactive_humans = 0;
    counts.pending_bots = 0;
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

        assigned = "none";
        if ( isdefined( player.sessionteam ) )
            assigned = player.sessionteam;
        if ( player istestclient() )
        {
            if ( assigned != "allies" && assigned != "axis" )
                counts.pending_bots++;
        }
        else if ( assigned == "allies" )
            counts.human_allies++;
        else if ( assigned == "axis" )
            counts.human_axis++;
        else
            counts.inactive_humans++;

        // Count team assignment independently of alive/dead state. Native
        // respawning owns dead players; they still occupy their team slots.
        if ( !isdefined( player.sessionteam ) )
            counts.unassigned++;
        else if ( player.sessionteam == "allies" )
            counts.allies++;
        else if ( player.sessionteam == "axis" )
            counts.axis++;
        else if ( player.sessionteam == "spectator" )
            counts.spectators++;
        else
            counts.unassigned++;
    }
    return counts;
}

fill_target()
{
    target = 16;
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
    retry_delay = 10;
    cooldown = 0;
    last_humans = -1;
    last_target = -1;
    last_population = "";

    for (;;)
    {
        update_stock_balance();
        if ( !getdvarint( "outlands_native_bots" ) )
        {
            failures = 0;
            cooldown = 0;
            retry_delay = 10;
            wait 2;
            continue;
        }

        counts = population();
        target = population_target( counts );
        if ( getdvarint( "outlands_status" ) )
        {
            snapshot = counts.humans + ":" + counts.bots.size + ":" + target + ":" + counts.allies + ":" + counts.axis + ":" + counts.spectators + ":" + counts.unassigned;
            if ( snapshot != last_population )
            {
                println( "Outlands native bots population: humans=" + counts.humans + " bots=" + counts.bots.size + " target=" + target + " allies=" + counts.allies + " axis=" + counts.axis + " spectators=" + counts.spectators + " unassigned=" + counts.unassigned + " human_allies=" + counts.human_allies + " human_axis=" + counts.human_axis + " mode=" + getdvar( "g_gametype" ) + " scorelimit=" + getgametypesetting( "scorelimit" ) );
                last_population = snapshot;
            }
        }
        // Human replacement and operator target changes invalidate earlier
        // failed-add observations. Recount before every native add/removal.
        if ( counts.humans != last_humans || target != last_target )
        {
            failures = 0;
            cooldown = 0;
            retry_delay = 10;
        }
        last_humans = counts.humans;
        last_target = target;
        if ( counts.humans < 1 )
        {
            failures = 0;
            cooldown = 0;
            retry_delay = 10;
            wait 2;
            continue;
        }

        plan = population_plan( counts, target );
        if ( plan.action == "remove" )
        {
            execute_population_plan( plan );
            wait 2;
            continue;
        }
        if ( plan.action == "none" )
        {
            failures = 0;
            cooldown = 0;
            retry_delay = 10;
            wait 2;
            continue;
        }
        // Poll throughout cooldown so a joining human or target change can
        // resume filling promptly, without a second competing controller.
        if ( cooldown > 0 )
        {
            cooldown -= 2;
            wait 2;
            continue;
        }

        before = counts.bots.size;
        execute_population_plan( plan );
        wait 2;
        after = population();
        if ( after.bots.size > before || after.humans != counts.humans || after.humans + after.bots.size >= fill_target() )
        {
            failures = 0;
            retry_delay = 10;
        }
        else
        {
            failures++;
            println( "Outlands native bots: native add did not increase test-client count, attempt " + failures + "/3." );
            if ( failures >= 3 )
            {
                cooldown = retry_delay;
                println( "Outlands native bots: native add retry in " + cooldown + " seconds; controller remains active." );
                retry_delay += 10;
                if ( retry_delay > 30 )
                    retry_delay = 30;
                failures = 0;
            }
        }
    }
}


// Cooperative placement and bot-only population repair share the one fill owner.
team_game()
{
    return isdefined( level.teambased ) && level.teambased && getdvar( "g_gametype" ) != "dm";
}

cooperative_teams()
{
    return team_game() && getdvarint( "outlands_native_bots" ) && getdvarint( "outlands_coop_teams" ) && isdefined( level.outlands_team_hooks );
}

balanced_teams()
{
    return team_game() && getdvarint( "outlands_native_bots" ) && getdvarint( "outlands_balance_teams" );
}

start_team_policy()
{
    if ( getdvar( "outlands_coop_teams" ) == "" )
        setdvar( "outlands_coop_teams", 1 );
    if ( getdvar( "outlands_balance_teams" ) == "" )
        setdvar( "outlands_balance_teams", 1 );
    if ( team_game() )
    {
        level.outlands_menu_auto = getfunction( "maps/mp/gametypes/_globallogic_ui", "menuautoassign" );
        level.outlands_menu_team = getfunction( "maps/mp/gametypes/_globallogic_ui", "menuteam" );
        if ( isdefined( level.outlands_menu_auto ) && isdefined( level.outlands_menu_team ) && !isdefined( getdetour( level.outlands_menu_auto ) ) && !isdefined( getdetour( level.outlands_menu_team ) ) )
        {
            replacefunc( level.outlands_menu_auto, ::cooperative_autoassign );
            replacefunc( level.outlands_menu_team, ::cooperative_menu_team );
            level.outlands_team_hooks = 1;
            println( "Outlands team policy: cooperative joins and bot-only balance hooks active." );
        }
        else
            println( "Outlands team policy: team callback unavailable or already owned; native fallback." );
    }
    update_stock_balance();
}

update_stock_balance()
{
    if ( cooperative_teams() )
    {
        if ( !isdefined( game["outlands_stock_balance"] ) )
            game["outlands_stock_balance"] = getdvar( "scr_teambalance" );
        setdvar( "scr_teambalance", 0 );
        level.teambalance = 0;
    }
    else if ( isdefined( game["outlands_stock_balance"] ) )
    {
        setdvar( "scr_teambalance", game["outlands_stock_balance"] );
        level.teambalance = getdvarint( "scr_teambalance" );
        game["outlands_stock_balance"] = undefined;
    }
}

// Count-only policy also has backend table checks; it never identifies bots as humans.
party_side( preferred, human_allies, human_axis, capacity )
{
    if ( preferred != "axis" )
        preferred = "allies";
    if ( preferred == "allies" && human_allies >= capacity && human_axis < capacity )
        return "axis";
    if ( preferred == "axis" && human_axis >= capacity && human_allies < capacity )
        return "allies";
    return preferred;
}

cohort_side( counts )
{
    if ( counts.human_allies > 0 && counts.human_axis == 0 )
        level.outlands_coop_side = "allies";
    else if ( counts.human_axis > 0 && counts.human_allies == 0 )
        level.outlands_coop_side = "axis";
    if ( !isdefined( level.outlands_coop_side ) )
        level.outlands_coop_side = "allies";
    return level.outlands_coop_side;
}

bot_on_team( counts, team )
{
    foreach ( bot in counts.bots )
        if ( isdefined( bot ) && bot istestclient() && isdefined( bot.sessionteam ) && bot.sessionteam == team )
            return bot;
    return undefined;
}

human_join_side()
{
    counts = population();
    preferred = cohort_side( counts );
    // Exclude this existing team member when re-opening their own team menu.
    if ( isdefined( self.sessionteam ) && self.sessionteam == "allies" )
        counts.human_allies--;
    if ( isdefined( self.sessionteam ) && self.sessionteam == "axis" )
        counts.human_axis--;
    capacity = int( getdvarint( "sv_maxclients" ) / 2 );
    if ( capacity < 1 )
        return preferred;
    selected = party_side( preferred, counts.human_allies, counts.human_axis, capacity );
    occupied = counts.allies;
    if ( selected == "axis" )
        occupied = counts.axis;
    if ( ( !isdefined( self.sessionteam ) || self.sessionteam != selected ) && occupied >= capacity )
    {
        bot = bot_on_team( counts, selected );
        if ( isdefined( bot ) && bot istestclient() )
            bot botleavegame();
    }
    return selected;
}

bot_join_side()
{
    counts = population();
    if ( isdefined( self.sessionteam ) && self.sessionteam == "allies" )
        counts.allies--;
    if ( isdefined( self.sessionteam ) && self.sessionteam == "axis" )
        counts.axis--;
    if ( counts.allies <= counts.axis )
        return "allies";
    return "axis";
}

native_menu_team( team )
{
    disabledetouronce( level.outlands_menu_team );
    self [[ level.outlands_menu_team ]]( team );
}

cooperative_autoassign( coming_from_menu )
{
    if ( cooperative_teams() && !self istestclient() )
    {
        self native_menu_team( self human_join_side() );
        return;
    }
    if ( balanced_teams() && self istestclient() )
    {
        self native_menu_team( self bot_join_side() );
        return;
    }
    disabledetouronce( level.outlands_menu_auto );
    self [[ level.outlands_menu_auto ]]( coming_from_menu );
}

cooperative_menu_team( team )
{
    if ( cooperative_teams() && !self istestclient() && ( team == "allies" || team == "axis" ) )
        team = self human_join_side();
    self native_menu_team( team );
}

population_target( counts )
{
    target = fill_target();
    if ( balanced_teams() )
    {
        active = target - counts.inactive_humans;
        if ( active < 0 )
            active = 0;
        target = counts.inactive_humans + active - ( active % 2 );
    }
    return target;
}

population_plan( counts, target )
{
    plan = spawnstruct();
    plan.action = "none";
    plan.team = "none";
    plan.bot = undefined;
    total = counts.humans + counts.bots.size;
    if ( team_game() && counts.pending_bots > 0 && total <= target )
        return plan;
    if ( balanced_teams() )
    {
        quota = int( ( target - counts.inactive_humans ) / 2 );
        if ( counts.allies > quota )
            plan.team = "allies";
        else if ( counts.axis > quota )
            plan.team = "axis";
        if ( plan.team != "none" )
            plan.bot = bot_on_team( counts, plan.team );
    }
    if ( total > target && !isdefined( plan.bot ) && counts.bots.size > 0 )
        plan.bot = counts.bots[counts.bots.size - 1];
    if ( isdefined( plan.bot ) )
        plan.action = "remove";
    else if ( total < target )
        plan.action = "add";
    return plan;
}

execute_population_plan( plan )
{
    if ( plan.action == "remove" && isdefined( plan.bot ) && isplayer( plan.bot ) && plan.bot istestclient() )
        plan.bot botleavegame();
    else if ( plan.action == "add" )
        cmdexec( "spawnbot 1" );
}
