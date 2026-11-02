// Original optional streak support. Native earnings, use rules and rewards own state.
#include common_scripts\utility;

start()
{
    if ( !isdedicated() || !getdvarint( "outlands_native_bots" ) || !getdvarint( "outlands_bot_streaks" ) || isdefined( level.outlands_streaks_started ) ) return;
    level.outlands_streaks_started = 1;
    level.outlands_streak_supply = getfunction( "maps/mp/bots/_bot", "bot_use_supply_drop" );
    if ( isdefined( level.outlands_streak_supply ) && !isdefined( getdetour( level.outlands_streak_supply ) ) )
    {
        replacefunc( level.outlands_streak_supply, ::supply_use );
        println( "Outlands streaks: guarded native supply deployment ready." );
    }
    level thread watch_bots();
}

enabled()
{
    return getdvarint( "outlands_native_bots" ) && getdvarint( "outlands_bot_streaks" );
}

eligible()
{
    return isdefined( self ) && isplayer( self ) && self istestclient();
}

watch_bots()
{
    level endon( "game_ended" );
    for (;;)
    {
        foreach ( bot in get_players() )
        {
            if ( !bot eligible() || isdefined( bot.outlands_streak_listener ) ) continue;
            bot.outlands_streak_listener = 1;
            bot thread watch_packages();
        }
        wait 0.5;
    }
}

watch_packages()
{
    self endon( "disconnect" ); level endon( "game_ended" );
    for (;;)
    {
        self waittill( "bot_crate_landed", crate );
        if ( !enabled() || !isdefined( crate ) || !isdefined( crate.owner ) || crate.owner != self || isdefined( self.outlands_streak_retrieving ) ) continue;
        self.outlands_streak_retrieving = 1;
        self thread retrieve( crate );
    }
}

// Only the native landing notification supplies the bot's own known package.
// No crate/enemy scan, instant reward, teleport or remote capture notification.
retrieve( crate )
{
    self endon( "disconnect" ); level endon( "game_ended" );
    deadline = gettime() + scripts\mp\outlands_squads::setting( "outlands_bot_package_timeout_ms", 25000, 10000, 45000 );
    slot = self getentitynumber();
    called = 0;
    while ( enabled() && gettime() < deadline && isdefined( crate ) && isdefined( crate.owner ) && crate.owner == self )
    {
        if ( isalive( self ) && isdefined( self.bot ) && !self isremotecontrolling() && !( isdefined( self.isplanting ) && self.isplanting ) && !( isdefined( self.isdefusing ) && self.isdefusing ) )
        {
            fighting = isdefined( self.bot.threat ) && isdefined( self.bot.threat.entity );
            carrying = false;
            if ( getdvar( "g_gametype" ) == "ctf" && isdefined( level.flags ) )
                foreach ( flag in level.flags ) if ( isdefined( flag.carrier ) && flag.carrier == self ) carrying = true;
            if ( !fighting && !carrying && !isdefined( crate.hacker ) && findpath( self.origin, crate.origin, self, 0, 1 ) )
            {
                self addgoal( crate.origin, 24, 3, "outlands_package" );
                if ( !called )
                {
                    called = 1;
                    scripts\mp\outlands_log::emit( "OUTLANDS_STREAK_RETRIEVE_V1|" + slot + "|" + int( distancesquared( self.origin, crate.origin ) ) );
                }
                // Stock bot_update_crate owns crouch/use/hold time and reward.
                if ( distancesquared( self.origin, crate.origin ) <= getdvarfloat( "player_useRadius" ) * getdvarfloat( "player_useRadius" ) )
                    self.bot.update_crate = 0;
            }
            else self cancelgoal( "outlands_package" );
        }
        else self cancelgoal( "outlands_package" );
        wait 0.5;
    }
    self cancelgoal( "outlands_package" );
    self.outlands_streak_retrieving = undefined;
}

charges( weapon )
{
    clip = self getweaponammoclip( weapon );
    if ( clip > 0 ) return clip;
    // Native inventory markers can hold their charge in the quantity ledger
    // until selected. A zero clip alone does not mean an unearned marker.
    if ( self getinventoryweapon() == weapon && isdefined( self.pers["killstreak_quantity"][weapon] ) )
        return self.pers["killstreak_quantity"][weapon];
    return 0;
}

supply_use( weapon )
{
    if ( !enabled() || !self eligible() || ( weapon != "supplydrop_mp" && weapon != "inventory_supplydrop_mp" ) )
    {
        disabledetouronce( level.outlands_streak_supply );
        return self [[ level.outlands_streak_supply ]]( weapon );
    }
    if ( !isalive( self ) || !self hasweapon( weapon ) || self charges( weapon ) <= 0 || self isremotecontrolling() ) return;
    self endon( "death" ); self endon( "disconnect" ); level endon( "game_ended" );
    // Native's five-second spawn-only window misses packages earned mid-life.
    // Try local legal ground under open sky; never conjure a drop/reward.
    forward = anglestoforward( ( 0, self.angles[1], 0 ) );
    point = self.origin + vectorscale( forward, 256 );
    sky = point + ( 0, 0, 2048 );
    if ( !sighttracepassed( point, sky, 0, undefined ) || !sighttracepassed( self.origin, sky, 0, undefined ) || bullettracepassed( point, point - ( 0, 0, 48 ), 0, undefined ) ) return;
    self addgoal( self.origin, 24, 4, "killstreak" );
    self lookat( point );
    if ( self getcurrentweapon() != weapon )
    {
        self switchtoweapon( weapon );
        self waittill_any_timeout( 2.5, "weapon_change_complete" );
    }
    if ( self getcurrentweapon() == weapon )
    {
        before = self charges( weapon );
        deadline = gettime() + 5000;
        // Selection can precede the ready animation. Bounded normal fire pulses
        // allow the native marker to finish deploying before switching back.
        while ( enabled() && gettime() < deadline && self getcurrentweapon() == weapon && self charges( weapon ) >= before )
        {
            self pressattackbutton();
            wait 0.5;
        }
        scripts\mp\outlands_log::emit( "OUTLANDS_STREAK_SUPPLY_V1|" + ( self getentitynumber() ) + "|" + before + "|" + ( self charges( weapon ) ) + "|" + ( gettime() - self.spawntime ) );
    }
    if ( isdefined( self.lastnonkillstreakweapon ) ) self switchtoweapon( self.lastnonkillstreakweapon );
    self clearlookat();
    self cancelgoal( "killstreak" );
}
