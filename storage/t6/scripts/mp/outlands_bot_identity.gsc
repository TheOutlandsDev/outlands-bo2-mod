// Original bot-only display identities. Called explicitly by the fill owner.
// No automatic init(), DDL writes, XP awards or native loadout-rank changes.
#include common_scripts\utility;

start()
{
    if ( !isdedicated() )
        return;
    if ( isdefined( level.outlands_identity_started ) )
        return;

    level.outlands_identity_started = 1;
    level thread watch_identity();
}

watch_identity()
{
    level endon( "game_ended" );
    for (;;)
    {
        if ( !getdvarint( "outlands_native_bots" ) || !getdvarint( "outlands_bot_levels" ) )
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
            if ( isdefined( bot.outlands_identity_started ) )
                continue;

            bot.outlands_identity_started = 1;
            bot thread assign_identity();
        }
        wait 2;
    }
}

assign_identity()
{
    self endon( "disconnect" );
    level endon( "game_ended" );
    if ( !isdedicated() || !self istestclient() )
        return;

    // Stock initialization owns brain rank, unlock eligibility and loadouts.
    // Retry a slow initialization later instead of inventing a loadout marker.
    attempts = 0;
    while ( !isdefined( self.pers["bot_loadout"] ) && attempts < 200 )
    {
        wait 0.1;
        attempts++;
    }
    if ( !isdefined( self.pers["bot_loadout"] ) || !self istestclient() )
    {
        self.outlands_identity_started = undefined;
        return;
    }

    maximum_level = 55;
    if ( isdefined( level.maxrank ) && level.maxrank >= 0 && level.maxrank + 1 < maximum_level )
        maximum_level = level.maxrank + 1;
    levels = setting_range( "outlands_bot_level_min", "outlands_bot_level_max", 1, maximum_level, 1, maximum_level );

    // The stock rank script reads this limit from mp/rankIconTable.csv.
    // Never request an unverified prestige index or one above the BO2 range.
    maximum_prestige = 0;
    if ( isdefined( level.maxprestige ) && level.maxprestige > 0 )
        maximum_prestige = level.maxprestige;
    if ( maximum_prestige > 11 )
        maximum_prestige = 11;
    // Index 11 is optional, rare and only paired with the native maximum rank.
    if ( levels.high < maximum_level && maximum_prestige > 10 )
        maximum_prestige = 10;
    default_prestige = maximum_prestige;
    if ( default_prestige > 10 )
        default_prestige = 10;
    prestiges = setting_range( "outlands_bot_prestige_min", "outlands_bot_prestige_max", 0, default_prestige, 0, maximum_prestige );

    if ( !isdefined( self.outlands_identity_ready ) )
    {
        self.outlands_cosmetic_level = weighted_range( levels.low, levels.high,
            array( 1, 16, 36, 51 ), array( 15, 35, 50, 55 ), array( 35, 40, 20, 5 ) );
        self.outlands_cosmetic_prestige = weighted_range( prestiges.low, prestiges.high,
            array( 0, 1, 4, 7, 10, 11 ), array( 0, 3, 6, 9, 10, 11 ), array( 50, 30, 12, 6, 2, 1 ) );
        if ( self.outlands_cosmetic_prestige == 11 )
            self.outlands_cosmetic_level = maximum_level;
        if ( isdefined( self.name ) )
            self.outlands_identity_alias = self.name;
        self.outlands_identity_ready = 1;
    }
    self apply_identity();
    println( "Outlands native bot identity: slot=" + ( self getentitynumber() ) + " level=" + self.outlands_cosmetic_level + " prestige=" + self.outlands_cosmetic_prestige );

    for (;;)
    {
        self waittill( "spawned_player" );
        wait 0.1;
        self apply_identity();
    }
}

apply_identity()
{
    if ( !isdedicated() || !isplayer( self ) || !self istestclient() )
        return;
    if ( !getdvarint( "outlands_native_bots" ) || !getdvarint( "outlands_bot_levels" ) )
        return;
    if ( !isdefined( self.outlands_identity_ready ) )
        return;

    // Native _rank.gsc uses setrank(rank_index, prestige). This display call
    // deliberately leaves pers rank/XP/prestige, DDL and class data unchanged.
    self setrank( self.outlands_cosmetic_level - 1, self.outlands_cosmetic_prestige );
}

setting_range( low_setting, high_setting, default_low, default_high, minimum, maximum )
{
    result = spawnstruct();
    result.low = default_low;
    result.high = default_high;
    if ( getdvar( low_setting ) != "" )
        result.low = getdvarint( low_setting );
    if ( getdvar( high_setting ) != "" )
        result.high = getdvarint( high_setting );
    if ( result.low < minimum )
        result.low = minimum;
    if ( result.low > maximum )
        result.low = maximum;
    if ( result.high < result.low )
        result.high = result.low;
    if ( result.high > maximum )
        result.high = maximum;
    return result;
}

weighted_range( minimum, maximum, lows, highs, weights )
{
    total = 0;
    for ( index = 0; index < lows.size; index++ )
    {
        if ( highs[index] >= minimum && lows[index] <= maximum )
            total += weights[index];
    }
    if ( total <= 0 )
        return randomintrange( minimum, maximum + 1 );

    roll = randomint( total );
    for ( index = 0; index < lows.size; index++ )
    {
        if ( highs[index] < minimum || lows[index] > maximum )
            continue;
        if ( roll >= weights[index] )
        {
            roll -= weights[index];
            continue;
        }
        low = lows[index];
        high = highs[index];
        if ( low < minimum )
            low = minimum;
        if ( high > maximum )
            high = maximum;
        return randomintrange( low, high + 1 );
    }
    return minimum;
}
