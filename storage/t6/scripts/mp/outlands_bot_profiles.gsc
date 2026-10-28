// Original Outlands native class-selection and patrol-cadence profiles.
// Call start() once from the existing fill controller. No automatic init/main.
// Native loadout generation, combat, objective goals and recovery remain owners.
#include common_scripts\utility;

start()
{
    if ( !isdedicated() || !getdvarint( "outlands_native_bots" ) || !getdvarint( "outlands_bot_profiles" ) )
        return;
    if ( isdefined( level.outlands_profiles_started ) )
        return;

    classes = getfunction( "maps/mp/bots/_bot", "bot_build_classes" );
    patrol = getfunction( "maps/mp/bots/_bot", "bot_update_patrol" );
    category = getfunction( "maps/mp/_utility", "getweaponclass" );
    rockets = getfunction( "maps/mp/bots/_bot_combat", "threat_requires_rocket" );
    drone = getfunction( "maps/mp/bots/_bot_combat", "threat_is_qrdrone" );
    warthog = getfunction( "maps/mp/bots/_bot_combat", "threat_is_warthog" );

    // Missing helpers or another mod's detour leave the stock behavior intact.
    if ( !isdefined( classes ) || !isdefined( patrol ) || !isdefined( category ) || !isdefined( rockets ) || !isdefined( drone ) || !isdefined( warthog ) )
    {
        println( "Outlands bot profiles: native helper unavailable; profile features disabled." );
        return;
    }
    if ( isdefined( getdetour( classes ) ) || isdefined( getdetour( patrol ) ) )
    {
        println( "Outlands bot profiles: native helper already detoured; profile features disabled." );
        return;
    }

    level.outlands_profiles_classes = classes;
    level.outlands_profiles_patrol = patrol;
    level.outlands_profiles_category = category;
    level.outlands_profiles_rockets = rockets;
    level.outlands_profiles_drone = drone;
    level.outlands_profiles_warthog = warthog;
    replacefunc( classes, ::profile_class_pool );
    replacefunc( patrol, ::profile_patrol_update );
    // Narrow optional hook; another mod's threat filter remains authoritative.
    air_ignore = getfunction( "maps/mp/bots/_bot_combat", "threat_should_ignore" );
    if ( isdefined( air_ignore ) && !isdefined( getdetour( air_ignore ) ) )
    {
        level.outlands_profiles_air_ignore = air_ignore;
        replacefunc( air_ignore, ::profile_air_ignore );
    }
    level.outlands_profiles_started = 1;
    start_ground_support();
    println( "Outlands bot profiles: native class pools and optional patrol cadence active; objective/recovery brain unchanged." );
}

profile_enabled()
{
    return isdedicated() && getdvarint( "outlands_native_bots" ) && getdvarint( "outlands_bot_profiles" ) && isdefined( self ) && isplayer( self ) && self istestclient();
}

native_class_pool()
{
    // Skip only this next call, with no wait between bypass and native call.
    disabledetouronce( level.outlands_profiles_classes );
    return self [[ level.outlands_profiles_classes ]]();
}

assign_profile()
{
    if ( !self profile_enabled() )
        return;
    career = getdvarint( "outlands_bot_careers" ) && isdefined( self.outlands_career_ready ) && isdefined( self.outlands_career_role ) && !isdefined( self.outlands_career_role_applied );
    if ( isdefined( self.outlands_profile_role ) && !career )
        return;

    roll = randomint( 100 );
    if ( roll < 25 )
        role = "rusher";
    else if ( roll < 55 )
        role = "assault";
    else if ( roll < 80 )
        role = "objective";
    else if ( roll < 95 )
        role = "support";
    else
        role = "marksman";

    if ( career )
    {
        saved = self.outlands_career_role;
        if ( saved == "rusher" || saved == "assault" || saved == "objective" || saved == "support" || saved == "marksman" )
            role = saved;
        self.outlands_career_role_applied = 1;
    }

    // Limit marksman profiles, not native emergency anti-air class choices.
    limit = 2;
    if ( getdvar( "outlands_bot_marksman_limit" ) != "" )
        limit = getdvarint( "outlands_bot_marksman_limit" );
    if ( limit < 0 )
        limit = 0;
    if ( limit > 4 )
        limit = 4;
    if ( role == "marksman" )
    {
        count = 0;
        players = get_players();
        foreach ( player in players )
        {
            if ( !isdefined( player ) || !isplayer( player ) || !player istestclient() || player == self )
                continue;
            if ( isdefined( player.outlands_profile_role ) && player.outlands_profile_role == "marksman" )
                count++;
        }
        if ( count >= limit )
            role = "assault";
    }
    self.outlands_profile_role = role;
    self.outlands_profile_pool_logs = 0;
    self.outlands_profile_patrol_logs = 0;
    println( "Outlands bot profile: slot=" + ( self getentitynumber() ) + " role=" + role );
}

native_air_threat()
{
    if ( !isdefined( self.bot ) || !isdefined( self.bot.attacker ) )
        return false;
    threat = self.bot.attacker;
    return [[ level.outlands_profiles_rockets ]]( threat ) || [[ level.outlands_profiles_drone ]]( threat ) || [[ level.outlands_profiles_warthog ]]( threat );
}

profile_class_pool()
{
    native = self native_class_pool();
    if ( !self profile_enabled() || !isdefined( self.pers["bot_loadout"] ) )
        return native;
    self assign_profile();
    if ( !isdefined( self.outlands_profile_role ) || self native_air_threat() )
        return native;

    choices = [];
    details = "";
    observed = "";
    foreach ( candidate in native )
    {
        index = class_index( candidate );
        if ( index < 0 )
            continue;
        weapon = self getloadoutweapon( index, "primary" );
        if ( !isdefined( weapon ) || weapon == "" || weapon == "none" )
            continue;
        group = [[ level.outlands_profiles_category ]]( weapon );
        if ( !isdefined( group ) )
            continue;
        observed = observed + " " + candidate + "=" + group;
        if ( profile_accepts( self.outlands_profile_role, group ) )
        {
            choices[choices.size] = candidate;
            details = details + " " + candidate + "=" + weapon;
        }
    }

    // These preset names are initialized by native on_bot_connect, including
    // bots whose current native rank has not unlocked Create-a-Class.
    if ( !choices.size )
    {
        choices = preset_pool( self.outlands_profile_role );
        details = " native preset fallback; groups=" + observed;
    }
    if ( getdvarint( "outlands_status" ) && self.outlands_profile_pool_logs < 3 )
    {
        println( "Outlands bot class pool: slot=" + ( self getentitynumber() ) + " role=" + self.outlands_profile_role + " choices=" + choices.size + details );
        self.outlands_profile_pool_logs++;
    }
    return choices;
}

class_index( name )
{
    switch ( name )
    {
        case "custom0": return 0;
        case "custom1": return 1;
        case "custom2": return 2;
        case "custom3": return 3;
        case "custom4": return 4;
        case "class_assault": return 5;
        case "class_smg": return 6;
        case "class_lmg": return 7;
        case "class_cqb": return 8;
        case "class_sniper": return 9;
    }
    return -1;
}

profile_accepts( role, group )
{
    switch ( role )
    {
        case "rusher": return group == "weapon_smg" || group == "weapon_cqb";
        case "assault": return group == "weapon_assault";
        case "objective": return group == "weapon_assault" || group == "weapon_smg";
        case "support": return group == "weapon_lmg" || group == "weapon_assault";
        case "marksman": return group == "weapon_sniper";
    }
    return false;
}

preset_pool( role )
{
    switch ( role )
    {
        case "rusher": return array( "class_smg", "class_cqb" );
        case "objective": return array( "class_assault", "class_smg" );
        case "support": return array( "class_lmg", "class_assault" );
        case "marksman": return array( "class_sniper" );
    }
    return array( "class_assault" );
}

profile_patrol_update()
{
    enabled = self profile_enabled() && getdvarint( "outlands_bot_patrol_profiles" );
    before = -1;
    if ( enabled && isdefined( self.bot ) && isdefined( self.bot.update_patrol ) )
        before = self.bot.update_patrol;

    // Native code retains all goal selection, enemy visibility and cancellation.
    disabledetouronce( level.outlands_profiles_patrol );
    self [[ level.outlands_profiles_patrol ]]();
    if ( !enabled || !isdefined( self.bot ) || !isdefined( self.bot.update_patrol ) )
        return;
    if ( before == self.bot.update_patrol || self.bot.update_patrol <= gettime() )
        return;
    self assign_profile();
    if ( !isdefined( self.outlands_profile_role ) )
        return;

    low = 5000;
    high = 10000;
    switch ( self.outlands_profile_role )
    {
        case "rusher":
            low = 2000;
            high = 4000;
            break;
        case "assault":
            low = 4000;
            high = 7000;
            break;
        case "objective":
            low = 7000;
            high = 11000;
            break;
        case "support":
            low = 8000;
            high = 12000;
            break;
        case "marksman":
            low = 10000;
            high = 15000;
            break;
    }
    interval = randomintrange( low, high + 1 );
    self.bot.update_patrol = gettime() + interval;
    if ( getdvarint( "outlands_status" ) && self.outlands_profile_patrol_logs < 3 )
    {
        println( "Outlands bot patrol cadence: slot=" + ( self getentitynumber() ) + " role=" + self.outlands_profile_role + " next_ms=" + interval + " native goals unchanged" );
        self.outlands_profile_patrol_logs++;
    }
}

// Per-target reaction pause and modest participation reduction for air support.
// Preserve the native ignore result, classification, lock-on and damage rules.
air_support_target( entity )
{
    if ( !isdefined( entity ) || isplayer( entity ) )
        return false;
    if ( isdefined( entity.targetname ) && ( entity.targetname == "uav" || entity.targetname == "counteruav" ) )
        return true;
    if ( isdefined( entity.helitype ) && entity.helitype == "qrdrone" )
        return false;
    return isdefined( entity.classname ) && entity.classname == "script_vehicle" && isdefined( entity.vehicleclass ) && ( entity.vehicleclass == "helicopter" || entity.vehicleclass == "plane" );
}

profile_air_ignore( entity )
{
    disabledetouronce( level.outlands_profiles_air_ignore );
    ignored = self [[ level.outlands_profiles_air_ignore ]]( entity );
    if ( ignored || !self profile_enabled() || !air_support_target( entity ) )
        return ignored;
    delay = 2500;
    chance = 80;
    if ( getdvar( "outlands_bot_air_reaction_ms" ) != "" )
        delay = getdvarint( "outlands_bot_air_reaction_ms" );
    if ( getdvar( "outlands_bot_air_response_chance" ) != "" )
        chance = getdvarint( "outlands_bot_air_response_chance" );
    delay = int( max( 0, min( 8000, delay ) ) );
    chance = int( max( 0, min( 100, chance ) ) );
    // These values restore stock selection immediately, even with cached state.
    if ( delay == 0 && chance == 100 )
        return false;
    if ( !isdefined( self.outlands_air_gates ) )
        self.outlands_air_gates = [];
    slot = entity getentitynumber();
    settings = delay + ":" + chance;
    gate = self.outlands_air_gates[slot];
    if ( !isdefined( gate ) || !isdefined( gate.entity ) || gate.entity != entity || gate.settings != settings )
    {
        gate = spawnstruct();
        gate.entity = entity;
        gate.settings = settings;
        gate.responds = randomint( 100 ) < chance;
        gate.ready = gettime() + delay;
        if ( delay > 0 )
            gate.ready += randomint( int( delay / 2 ) + 1 );
        self.outlands_air_gates[slot] = gate;
    }
    return !gate.responds || gettime() < gate.ready;
}

// Ground streak support uses only a turret already encountered by a native bot.
// One living specialist per team may swap an existing tactical on spawn; native
// item locks, equipment restrictions, throw physics and damage remain owners.
start_ground_support()
{
    emp = getfunction( "maps/mp/bots/_bot_combat", "bot_combat_throw_emp" );
    danger = getfunction( "maps/mp/bots/_bot_combat", "bot_turret_set_dangerous" );
    flank = getfunction( "maps/mp/bots/_bot_combat", "turret_get_attack_node" );
    allowed = getfunction( "maps/mp/gametypes/_class", "isequipmentallowed" );
    look = getfunction( "maps/mp/bots/_bot", "bot_update_lookat" );
    if ( !isdefined( emp ) || !isdefined( danger ) || !isdefined( flank ) || !isdefined( allowed ) || !isdefined( look ) )
        return;
    if ( isdefined( getdetour( emp ) ) || isdefined( getdetour( danger ) ) || isdefined( getdetour( look ) ) )
        return;
    level.outlands_ground_emp = emp;
    level.outlands_ground_danger = danger;
    level.outlands_ground_flank = flank;
    level.outlands_ground_allowed = allowed;
    level.outlands_ground_look = look;
    level.outlands_ground_threats = [];
    level.outlands_ground_specialists = [];
    level.outlands_ground_emp_requests = 0;
    level.outlands_ground_emp_projectiles = 0;
    level.outlands_ground_emp_index = int( tablelookup( "mp/statstable.csv", 4, "emp_grenade", 0 ) );
    replacefunc( emp, ::ground_emp_throw );
    replacefunc( danger, ::ground_notice_turret );
    replacefunc( look, ::ground_look );
    level thread watch_ground_support();
    level thread ground_end_cleanup();
    println( "Outlands ground support: guarded EMP and single-team specialist hooks ready." );
}

// Turn toward a remembered visible ground threat instead of letting ordinary
// patrol look updates continually replace the specialist's target. Native
// combat remains in control whenever a live player becomes the threat.
ground_look()
{
    target = self ground_look_target();
    if ( isdefined( target ) )
    {
        self lookat( target.origin + ( 0, 0, 48 ) );
        return;
    }
    disabledetouronce( level.outlands_ground_look );
    self [[ level.outlands_ground_look ]]();
}

ground_look_target()
{
    if ( !self ground_enabled() || !isalive( self ) || self ground_ammo() <= 0 || self ground_busy() )
        return undefined;
    owner = level.outlands_ground_specialists[self.team];
    record = self ground_record();
    if ( !isdefined( owner ) || owner != self || !isdefined( record ) )
        return undefined;
    target = record.entity;
    if ( distancesquared( self.origin, target.origin ) > 810000 || !bullettracepassed( self.origin + ( 0, 0, 48 ), target.origin + ( 0, 0, 48 ), 0, self ) )
        return undefined;
    return target;
}

ground_enabled()
{
    return self profile_enabled() && level.teambased && getdvarint( "outlands_bot_ground_support" ) && isdefined( self.team ) && ( self.team == "allies" || self.team == "axis" );
}

ground_hostile( turret )
{
    if ( !isdefined( turret ) || isplayer( turret ) || turret.classname != "auto_turret" )
        return false;
    if ( !isdefined( turret.turrettype ) || ( turret.turrettype != "microwave" && turret.turrettype != "sentry" ) )
        return false;
    if ( !isdefined( turret.owner ) || !isplayer( turret.owner ) || !isdefined( turret.owner.team ) || turret.owner.team == self.team )
        return false;
    if ( turret.owner.team != "allies" && turret.owner.team != "axis" )
        return false;
    return isdefined( turret.turret_active ) && turret.turret_active && !( isdefined( turret.dead ) && turret.dead ) && !( isdefined( turret.carried ) && turret.carried );
}

ground_notice_turret( turret )
{
    // Preserve the stock Guardian cone and sentry danger-node marking.
    disabledetouronce( level.outlands_ground_danger );
    self [[ level.outlands_ground_danger ]]( turret );
    self remember_ground_turret( turret );
}

remember_ground_turret( turret )
{
    if ( !self ground_enabled() || !self ground_hostile( turret ) )
        return;
    record = level.outlands_ground_threats[self.team];
    if ( !isdefined( record ) || gettime() - record.seen > 20000 )
    {
        record = spawnstruct();
        record.ready = gettime() + 4000;
        record.next_emp = 0;
    }
    record.entity = turret;
    record.seen = gettime();
    level.outlands_ground_threats[self.team] = record;
}

ground_record()
{
    if ( !self ground_enabled() )
        return undefined;
    record = level.outlands_ground_threats[self.team];
    if ( !isdefined( record ) || gettime() - record.seen > 20000 || gettime() < record.ready || !self ground_hostile( record.entity ) )
        return undefined;
    return record;
}

ground_ammo()
{
    clip = self getweaponammoclip( "emp_grenade_mp" );
    stock = self getweaponammostock( "emp_grenade_mp" );
    if ( stock > clip )
        return stock;
    return clip;
}

ground_emp_throw( origin )
{
    if ( !self ground_enabled() )
    {
        disabledetouronce( level.outlands_ground_emp );
        return self [[ level.outlands_ground_emp ]]( origin );
    }
    record = self ground_record();
    ground = isdefined( record ) && distancesquared( record.entity.origin, origin ) < 16384;
    if ( !ground )
    {
        if ( isdefined( self.bot ) && isdefined( self.bot.threat ) && self ground_hostile( self.bot.threat.entity ) )
            return false;
        disabledetouronce( level.outlands_ground_emp );
        return self [[ level.outlands_ground_emp ]]( origin );
    }
    if ( isdefined( self.outlands_ground_emp_pending ) || gettime() < record.next_emp || self ground_ammo() <= 0 )
        return false;
    request = spawnstruct();
    request.accepted = 1;
    request.confirmed = 0;
    request.record = record;
    request.target = record.entity;
    self.outlands_ground_emp_pending = request;
    if ( !self ground_can_press( request ) )
    {
        self.outlands_ground_emp_pending = undefined;
        return false;
    }
    record.next_emp = gettime() + 6000;
    if ( !isdefined( self.outlands_ground_emp_requests ) )
        self.outlands_ground_emp_requests = 0;
    self.outlands_ground_emp_requests++;
    self.outlands_ground_last_projectiles = 0;
    level.outlands_ground_emp_requests++;
    self thread ground_press_emp( request );
    self thread ground_emp_timeout( request );
    return true;
}

ground_can_press( request )
{
    if ( !self ground_enabled() || !isalive( self ) || !isdefined( self.outlands_ground_emp_pending ) || self.outlands_ground_emp_pending != request )
        return false;
    if ( !isdefined( self.grenadetypesecondary ) || self.grenadetypesecondary != "emp_grenade_mp" || self ground_ammo() <= 0 || self ground_busy() )
        return false;
    return self ground_hostile( request.target ) && distancesquared( self.origin, request.target.origin ) <= 810000 && self botsighttracepassed( request.target );
}

ground_press_emp( request )
{
    self endon( "disconnect" );
    level endon( "game_ended" );
    // Use the real secondary-tactical input; native ThrowGrenade accepts EMP
    // requests without reliably producing an offhand projectile on this runtime.
    for ( i = 0; i < 3; i++ )
    {
        if ( !self ground_can_press( request ) )
        {
            if ( isdefined( self.outlands_ground_emp_pending ) && self.outlands_ground_emp_pending == request )
                self.outlands_ground_emp_pending = undefined;
            return;
        }
        self lookat( request.target.origin + ( 0, 0, 48 ) );
        wait 0.1;
    }
    if ( !self ground_can_press( request ) )
    {
        if ( isdefined( self.outlands_ground_emp_pending ) && self.outlands_ground_emp_pending == request )
            self.outlands_ground_emp_pending = undefined;
        return;
    }
    self.outlands_ground_smoke_owner = request;
    self botbuttonoverride( "+smoke" );
    wait 1;
    self ground_release_smoke( request );
}

ground_release_smoke( request )
{
    if ( !isdefined( self.outlands_ground_smoke_owner ) )
        return;
    if ( isdefined( request ) && self.outlands_ground_smoke_owner != request )
        return;
    self botbuttonoverride( "~smoke" );
    self.outlands_ground_smoke_owner = undefined;
}

ground_death_watch()
{
    self endon( "disconnect" );
    level endon( "game_ended" );
    for (;;)
    {
        self waittill( "death" );
        self ground_release_smoke();
        self.outlands_ground_emp_pending = undefined;
    }
}

ground_end_cleanup()
{
    level waittill( "game_ended" );
    foreach ( player in get_players() )
        if ( isdefined( player ) && isplayer( player ) && player istestclient() )
        {
            player ground_release_smoke();
            player.outlands_ground_emp_pending = undefined;
        }
}

// Confirm a real EMP grenade entity from the native offhand event. Keep ammo
// available during the animation and never manufacture a projectile or hit.
ground_emp_events()
{
    self endon( "disconnect" );
    level endon( "game_ended" );
    for (;;)
    {
        self waittill( "grenade_fire", grenade, weapon );
        request = self.outlands_ground_emp_pending;
        if ( weapon == "emp_grenade_mp" && isdefined( grenade ) && isdefined( request ) && request.accepted )
            self thread ground_confirm_emp( request );
    }
}

ground_confirm_emp( request )
{
    self endon( "death" );
    self endon( "disconnect" );
    level endon( "game_ended" );
    if ( request.confirmed || !isdefined( self.outlands_ground_emp_pending ) || self.outlands_ground_emp_pending != request )
        return;
    request.confirmed = 1;
    self ground_release_smoke( request );
    self.outlands_ground_last_projectiles = 1;
    level.outlands_ground_emp_projectiles++;
    if ( isdefined( request.record ) )
        request.record.next_emp = gettime() + 6000;
    // The normal offhand path owns ammunition consumption.
    if ( isdefined( self.outlands_ground_emp_pending ) && self.outlands_ground_emp_pending == request )
        self.outlands_ground_emp_pending = undefined;
}

ground_emp_timeout( request )
{
    self endon( "death" );
    self endon( "disconnect" );
    level endon( "game_ended" );
    wait 6;
    if ( isdefined( self.outlands_ground_emp_pending ) && self.outlands_ground_emp_pending == request && !request.confirmed )
    {
        self ground_release_smoke( request );
        self.outlands_ground_emp_pending = undefined;
    }
}

ground_equip()
{
    if ( !self ground_enabled() || !isalive( self ) || !isdefined( self ground_record() ) )
        return false;
    if ( level.outlands_ground_emp_index <= 0 || self isitemlocked( level.outlands_ground_emp_index ) || !self [[ level.outlands_ground_allowed ]]( "emp_grenade" ) )
        return false;
    owner = level.outlands_ground_specialists[self.team];
    if ( isdefined( owner ) && isplayer( owner ) && owner istestclient() && isalive( owner ) && isdefined( owner.team ) && owner.team == self.team && owner != self && owner ground_ammo() > 0 )
        return false;
    if ( !isdefined( self.grenadetypesecondary ) )
        return false;
    old = self.grenadetypesecondary;
    if ( old != "flash_grenade_mp" && old != "concussion_grenade_mp" && old != "willy_pete_mp" && old != "emp_grenade_mp" )
        return false;
    if ( self getweaponammoclip( old ) + self getweaponammostock( old ) <= 0 )
        return false;
    // Replace one existing tactical allocation; never add a new equipment slot
    // or replenish the specialist again during this life.
    if ( old != "emp_grenade_mp" )
    {
        self takeweapon( old );
        self setoffhandsecondaryclass( "emp_grenade_mp" );
        self giveweapon( "emp_grenade_mp" );
        self setweaponammoclip( "emp_grenade_mp", 1 );
        self.grenadetypesecondary = "emp_grenade_mp";
        self.grenadetypesecondarycount = 1;
    }
    level.outlands_ground_specialists[self.team] = self;
    return true;
}

watch_ground_support()
{
    level endon( "game_ended" );
    for (;;)
    {
        foreach ( player in get_players() )
        {
            if ( !isdefined( player ) || !isplayer( player ) || !player istestclient() || isdefined( player.outlands_ground_watch ) )
                continue;
            player.outlands_ground_watch = 1;
            player thread ground_emp_events();
            player thread ground_death_watch();
            player thread ground_spawn_watch();
        }
        wait 0.5;
    }
}

ground_spawn_watch()
{
    self endon( "disconnect" );
    level endon( "game_ended" );
    if ( isalive( self ) )
        self thread ground_life();
    for (;;)
    {
        self waittill( "spawned_player" );
        self thread ground_life();
    }
}

ground_life()
{
    self notify( "outlands_ground_life" );
    self endon( "outlands_ground_life" );
    self endon( "disconnect" );
    self endon( "death" );
    level endon( "game_ended" );
    self ground_release_smoke();
    self.outlands_ground_emp_pending = undefined;
    wait 0.5;
    equipped = self ground_equip();
    for (;;)
    {
        wait 0.5;
        record = self ground_record();
        owner = undefined;
        if ( isdefined( record ) )
            owner = level.outlands_ground_specialists[self.team];
        if ( !equipped || !isdefined( record ) || !isdefined( owner ) || owner != self || self ground_ammo() <= 0 || self ground_busy() )
        {
            self cancelgoal( "outlands_ground" );
            continue;
        }
        // No pursuit of players, blind throws, direct damage or aim changes.
        // Stock turret flank nodes and higher-priority native goals win.
        flank = record.entity [[ level.outlands_ground_flank ]]();
        if ( isdefined( flank ) )
            self addgoal( flank, 32, 2, "outlands_ground" );
        else
            self cancelgoal( "outlands_ground" );
        if ( distancesquared( self.origin, record.entity.origin ) <= 810000 && self botsighttracepassed( record.entity ) )
            self ground_emp_throw( record.entity.origin );
    }
}

ground_busy()
{
    if ( self isremotecontrolling() || ( isdefined( self.isplanting ) && self.isplanting ) || ( isdefined( self.isdefusing ) && self.isdefusing ) )
        return true;
    if ( isdefined( self.bot ) && isdefined( self.bot.threat ) && isdefined( self.bot.threat.entity ) && isplayer( self.bot.threat.entity ) && isalive( self.bot.threat.entity ) )
        return true;
    if ( isdefined( level.flags ) )
        foreach ( flag in level.flags )
            if ( isdefined( flag.carrier ) && flag.carrier == self )
                return true;
    return false;
}
