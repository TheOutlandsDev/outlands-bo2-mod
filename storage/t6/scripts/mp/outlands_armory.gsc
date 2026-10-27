// Original opt-in native Armory. Native XP, unlock and class DDL are read-only.
// A bounded base-class editor uses the native pre-loadout spawn wrapper and
// givecustomloadout callback. Advanced attachments/cards stay in stock CAC.
#include common_scripts\utility;

main()
{
    if ( getdvar( "outlands_armory" ) == "" )
        setdvar( "outlands_armory", 0 );
}

init()
{
    if ( !isdedicated() || isdefined( level.outlands_armory_started ) )
        return;
    level.outlands_armory_started = 1;
    level.outlands_armory_records = [];
    level.outlands_armory_pending = undefined;
    level.outlands_armory_hook_ready = 0;
    level.outlands_armory_serial = 0;
    level.outlands_armory_epoch = "a" + randomint( 1000000000 ) + "_" + gettime();
    setdvar( "outlands_armory_response", "" );
    level thread controller();
}

enabled()
{
    return getdvarint( "outlands_armory" ) && isdefined( level.outlands_armory_hook_ready ) && level.outlands_armory_hook_ready;
}

fixture_allowed()
{
    return getdvarint( "outlands_backend_verification" ) && getdvarint( "outlands_verify_armory_editor" ) && getdvar( "net_ip" ) == "127.0.0.1";
}

valid_ref( ref )
{
    if ( !isdefined( ref ) || ref.size < 1 || ref.size > 48 || !issubstr( "abcdefghijklmnopqrstuvwxyz", getsubstr( ref, 0, 1 ) ) )
        return false;
    for ( i = 0; i < ref.size; i++ )
        if ( !issubstr( "abcdefghijklmnopqrstuvwxyz0123456789_", getsubstr( ref, i, i + 1 ) ) )
            return false;
    return true;
}

empty_refs()
{
    return array( "none", "none", "none", "none", "none", "none", "none" );
}

copy_refs( refs )
{
    result = [];
    foreach ( ref in refs )
        result[result.size] = ref;
    return result;
}

join_refs( refs )
{
    text = refs[0];
    for ( i = 1; i < refs.size; i++ )
        text += "," + refs[i];
    return text;
}

build_catalog()
{
    level.outlands_armory_items = [];
    level.outlands_armory_choices = [];
    level.outlands_armory_slots = array( "primary", "secondary", "perk1", "perk2", "perk3", "lethal", "tactical" );
    foreach ( slot in level.outlands_armory_slots )
        level.outlands_armory_choices[slot] = array( "none" );
    table = "mp/statstable.csv";
    for ( index = 1; index < 256; index++ )
    {
        row = tablelookuprownum( table, 0, index );
        if ( row < 0 )
            continue;
        ref = tablelookupcolumnforrow( table, row, 4 );
        native_slot = tablelookupcolumnforrow( table, row, 13 );
        group = tablelookupcolumnforrow( table, row, 2 );
        cost = int( tablelookupcolumnforrow( table, row, 12 ) );
        effects = [];
        if ( group == "specialty" && ( native_slot == "specialty1" || native_slot == "specialty2" || native_slot == "specialty3" ) )
        {
            effects = strtok( ref, "|" );
            valid_effects = effects.size > 0 && effects.size <= 8;
            foreach ( effect in effects )
                if ( !valid_ref( effect ) )
                    valid_effects = false;
            if ( !valid_effects )
                continue;
            // One native perk can grant several effects. Persist a safe item
            // key, charge one point, then register every native effect.
            ref = "perk_" + index;
        }
        if ( !valid_ref( ref ) || cost != 1 || ref == "none" )
            continue;
        slot = "none";
        if ( native_slot == "primary" && ( group == "weapon_smg" || group == "weapon_assault" || group == "weapon_lmg" || group == "weapon_sniper" || group == "weapon_cqb" || group == "weapon_shotgun" ) )
            slot = "primary";
        if ( native_slot == "secondary" && ( group == "weapon_pistol" || group == "weapon_launcher" ) )
            slot = "secondary";
        if ( native_slot == "specialty1" || native_slot == "specialty2" || native_slot == "specialty3" )
            slot = "perk" + getsubstr( native_slot, native_slot.size - 1 );
        // First accepted subset: ordinary throwable grenades. Script equipment
        // such as tactical insertion, C4 and shields needs separate acceptance.
        if ( native_slot == "primarygrenade" && ( ref == "frag_grenade" || ref == "sticky_grenade" ) )
            slot = "lethal";
        if ( native_slot == "specialgrenade" && ( ref == "flash_grenade" || ref == "concussion_grenade" || ref == "emp_grenade" || ref == "willy_pete" ) )
            slot = "tactical";
        if ( slot == "none" || issubstr( ref, "weapon_" ) )
            continue;
        item = spawnstruct();
        item.index = index;
        item.ref = ref;
        item.slot = slot;
        item.label = tablelookupistring( table, 0, index, 3 );
        item.weapon = ref + "_mp";
        item.effects = effects;
        level.outlands_armory_items[ref] = item;
        choices = level.outlands_armory_choices[slot];
        choices[choices.size] = ref;
        level.outlands_armory_choices[slot] = choices;
    }
}

can_customize( player )
{
    mode = getdvar( "g_gametype" );
    if ( mode != "tdm" && mode != "dm" && mode != "conf" && mode != "ctf" && mode != "dem" && mode != "dom" && mode != "koth" && mode != "hq" )
        return false;
    index = int( tablelookup( "mp/statstable.csv", 4, "feature_cac", 0 ) );
    return index > 0 && !player isitemlocked( index ) && !getgametypesetting( "disableCAC" ) && !getgametypesetting( "disableClassSelection" );
}

allocation( player )
{
    maximum = 10;
    for ( i = 1; i <= 3; i++ )
    {
        index = int( tablelookup( "mp/statstable.csv", 4, "feature_allocation_slot_" + i, 0 ) );
        if ( index <= 0 || player isitemlocked( index ) )
            maximum--;
    }
    configured = getgametypesetting( "maxAllocation" );
    if ( configured < maximum )
        maximum = configured;
    return maximum;
}

item_unlocked( player, ref, slot )
{
    if ( ref == "none" )
        return true;
    item = level.outlands_armory_items[ref];
    if ( !isdefined( item ) || item.slot != slot || player isitemlocked( item.index ) || maps\mp\gametypes\_class::is_item_excluded( item.index ) )
        return false;
    if ( issubstr( slot, "perk" ) && !level.perksenabled )
        return false;
    if ( ref == "peacekeeper" && !getdvarint( "tu6_enableDLCWeapons" ) )
        return false;
    return true;
}

validate_refs( player, refs )
{
    result = spawnstruct();
    result.valid = 0;
    result.points = 0;
    result.reason = "CLASS UNAVAILABLE";
    if ( !isdefined( refs ) || refs.size != 7 )
        return result;
    if ( !can_customize( player ) )
    {
        result.reason = "CREATE-A-CLASS LOCKED OR MODE UNSUPPORTED";
        return result;
    }
    for ( i = 0; i < 7; i++ )
    {
        if ( !valid_ref( refs[i] ) || !item_unlocked( player, refs[i], level.outlands_armory_slots[i] ) )
        {
            result.reason = "ITEM LOCKED OR RESTRICTED";
            return result;
        }
        if ( refs[i] != "none" )
            result.points++;
    }
    if ( result.points > allocation( player ) )
    {
        result.reason = "PICK-10 LIMIT EXCEEDED";
        return result;
    }
    result.valid = 1;
    result.reason = "BASE CLASS / NO ATTACHMENTS OR WILDCARDS";
    return result;
}

controller()
{
    level endon( "game_ended" );
    wait 1;
    build_catalog();
    cursor = 0;
    for (;;)
    {
        if ( getdvarint( "outlands_armory" ) && !level.outlands_armory_hook_ready && isdefined( level.spawnplayer ) )
        {
            if ( isdefined( level.givecustomloadout ) )
                setdvar( "outlands_armory_hook_conflict", 1 );
            else
            {
                level.outlands_armory_stock_spawn = level.spawnplayer;
                level.spawnplayer = ::spawn_wrapper;
                level.givecustomloadout = ::grant_callback;
                level.outlands_armory_hook_ready = 1;
                println( "Outlands Armory native hooks ready" );
            }
        }
        if ( !enabled() )
        {
            foreach ( record in level.outlands_armory_records )
                if ( isdefined( record ) )
                    cancel_record( record, "ARMORY DISABLED" );
            level.outlands_armory_pending = undefined;
            setdvar( "outlands_armory_response", "" );
            wait 0.1;
            continue;
        }
        foreach ( player in get_players() )
        {
            if ( !eligible( player ) )
                continue;
            slot = player getentitynumber();
            if ( slot < 0 || slot > 17 )
                continue;
            old = level.outlands_armory_records[slot];
            if ( !same_record( old ) || old.player != player )
            {
                record = new_record( player );
                level.outlands_armory_records[slot] = record;
                player thread lifecycle( record );
            }
        }
        consume_response();
        if ( isdefined( level.outlands_armory_pending ) && gettime() - level.outlands_armory_pending.sent > 2000 )
        {
            record = level.outlands_armory_pending.record;
            record.command = "none";
            record.armed = 0;
            record.queued = undefined;
            record.status = "NOT CONFIRMED / REOPEN OR EQUIP AGAIN";
            record.restored = 0;
            record.retry_after = gettime() + 2000;
            level.outlands_armory_pending = undefined;
        }
        if ( !isdefined( level.outlands_armory_pending ) )
        {
            for ( attempts = 0; attempts < 18; attempts++ )
            {
                cursor = ( cursor + 1 ) % 18;
                record = level.outlands_armory_records[cursor];
                if ( !same_record( record ) || record.fixture )
                    continue;
                if ( record.command == "none" && !record.restored && gettime() >= record.retry_after )
                    record.command = "hello";
                if ( record.command != "none" )
                {
                    emit_request( record );
                    break;
                }
            }
        }
        wait 0.025;
    }
}

new_record( player )
{
    record = spawnstruct();
    level.outlands_armory_serial++;
    record.player = player;
    record.slot = player getentitynumber();
    record.guid = "" + player.guid;
    record.session = level.outlands_armory_epoch + "_" + record.slot + "_" + level.outlands_armory_serial;
    record.spawn = 0;
    record.sequence = 0;
    record.revision = 0;
    record.restored = 0;
    record.fixture = 0;
    record.armed = 0;
    record.in_spawn = 0;
    record.command = "none";
    record.draft = empty_refs();
    record.saved = empty_refs();
    record.queued = undefined;
    record.active = undefined;
    record.active_revision = 0;
    record.transition = 0;
    record.status = "LOADING SAVED CLASS";
    record.retry_after = gettime();
    return record;
}

same_record( record )
{
    if ( !isdefined( record ) || !isdefined( record.player ) || !isplayer( record.player ) || ( record.player getentitynumber() ) != record.slot )
        return false;
    if ( record.fixture )
        return fixture_allowed() && record.player istestclient();
    if ( !eligible( record.player ) || "" + record.player.guid != record.guid )
        return false;
    return true;
}

record_for( player )
{
    if ( !isdefined( level.outlands_armory_records ) || !isdefined( player ) || !isplayer( player ) )
        return undefined;
    record = level.outlands_armory_records[player getentitynumber()];
    if ( !same_record( record ) || record.player != player )
        return undefined;
    return record;
}

cancel_record( record, status )
{
    if ( isdefined( level.outlands_armory_pending ) && level.outlands_armory_pending.record == record )
    {
        level.outlands_armory_pending = undefined;
        setdvar( "outlands_armory_response", "" );
    }
    record.queued = undefined;
    record.active = undefined;
    record.armed = 0;
    record.transition = 0;
    record.status = status;
    if ( record.command != "hello" )
        record.command = "cancel";
}

lifecycle( record )
{
    self endon( "disconnect" );
    level endon( "game_ended" );
    self thread cancel_on( record, "changed_class" );
    self thread cancel_on( record, "joined_team" );
    self thread cancel_on( record, "joined_spectators" );
    self waittill( "disconnect" );
}

cancel_on( record, event )
{
    self endon( "disconnect" );
    level endon( "game_ended" );
    for (;;)
    {
        self waittill( event );
        cancel_record( record, "STOCK CLASS / OUTLANDS QUEUE CANCELLED" );
    }
}

request( player, kind )
{
    record = record_for( player );
    if ( !enabled() || !eligible( player ) || !isdefined( record ) || !record.restored || record.command != "none" || ( kind != "save" && kind != "equip" ) )
        return false;
    refs = record.draft;
    if ( kind == "equip" )
        refs = record.saved;
    view = validate_refs( player, refs );
    if ( !view.valid )
    {
        record.status = view.reason;
        return false;
    }
    record.requested = copy_refs( refs );
    record.command = kind;
    record.status = "SAVING / WAIT FOR SERVER CONFIRMATION";
    return true;
}

emit_request( record )
{
    record.sequence++;
    refs = empty_refs();
    if ( record.command == "save" || record.command == "equip" )
        refs = record.requested;
    if ( record.command == "claim" )
        refs = record.queued;
    if ( record.command == "applied" || record.command == "failed" )
        refs = record.last_claim;
    if ( !isdefined( refs ) || refs.size != 7 )
    {
        record.command = "none";
        return;
    }
    groups = [];
    unlocked = "";
    for ( i = 0; i < 7; i++ )
    {
        group = "none";
        bit = "0";
        item = level.outlands_armory_items[refs[i]];
        if ( isdefined( item ) )
        {
            group = item.slot;
            if ( item_unlocked( record.player, refs[i], level.outlands_armory_slots[i] ) )
                bit = "1";
        }
        groups[i] = group;
        unlocked += bit;
    }
    pending = spawnstruct();
    pending.record = record;
    pending.id = record.session + "_" + record.sequence;
    pending.kind = record.command;
    pending.sent = gettime();
    pending.spawn = record.spawn;
    pending.refs = copy_refs( refs );
    pending.revision = record.revision;
    level.outlands_armory_pending = pending;
    setdvar( "outlands_armory_response", "" );
    customize = 0;
    if ( can_customize( record.player ) )
        customize = 1;
    println( "OUTLANDS_ARMORY_V3|" + record.session + "|" + record.sequence + "|" + record.command + "|" + record.slot + "|" + record.guid + "|" + level.outlands_armory_epoch + "|" + record.spawn + "|" + allocation( record.player ) + "|" + gettime() + "|" + join_refs( refs ) + "|" + join_refs( groups ) + "|" + unlocked + "|" + customize + "|" + record.revision + "|base1" );
}

uint_text( text )
{
    if ( text.size < 1 || text.size > 10 )
        return false;
    for ( i = 0; i < text.size; i++ )
        if ( !issubstr( "0123456789", getsubstr( text, i, i + 1 ) ) )
            return false;
    return int( text ) >= 0 && "" + int( text ) == text;
}

consume_response()
{
    value = getdvar( "outlands_armory_response" );
    if ( value == "" )
        return;
    setdvar( "outlands_armory_response", "" );
    pending = level.outlands_armory_pending;
    fields = strtok( value, "|" );
    if ( !isdefined( pending ) || fields.size != 5 || fields[0] != pending.id || fields[1] != "" + pending.record.slot || !uint_text( fields[3] ) || gettime() - pending.sent > 2000 || !same_record( pending.record ) || pending.record.command != pending.kind )
        return;
    refs = strtok( fields[4], "," );
    if ( refs.size != 7 )
        return;
    foreach ( ref in refs )
        if ( !valid_ref( ref ) )
            return;
    record = pending.record;
    status = fields[2];
    revision = int( fields[3] );
    if ( status == "saved" && pending.kind == "hello" && revision > 0 )
    {
        record.saved = copy_refs( refs );
        record.draft = copy_refs( refs );
        record.revision = revision;
        record.restored = 1;
        record.status = "SAVED CLASS LOADED / EQUIP TO QUEUE";
    }
    else if ( status == "empty" && pending.kind == "hello" && revision == 0 )
    {
        record.restored = 1;
        record.status = "NEW BASE CLASS / CHOOSE ITEMS THEN SAVE";
    }
    else if ( status == "queued" && ( pending.kind == "save" || pending.kind == "equip" ) && join_refs( refs ) == join_refs( pending.refs ) && ( ( pending.kind == "save" && revision == pending.revision + 1 ) || ( pending.kind == "equip" && revision == pending.revision ) ) )
    {
        record.revision = revision;
        record.saved = copy_refs( refs );
        record.status = "SAVED / QUEUED FOR YOUR NEXT RESPAWN";
        if ( record.spawn == pending.spawn )
        {
            record.queued = copy_refs( refs );
            record.queued_spawn = record.spawn;
        }
        else
            record.status = "SAVED / RESPAWN PASSED / EQUIP AGAIN";
    }
    else if ( status == "armed" && pending.kind == "claim" && revision == pending.revision && join_refs( refs ) == join_refs( pending.refs ) && record.spawn == pending.spawn && record.in_spawn )
    {
        record.armed = 1;
        record.transition = 1;
        record.last_claim = copy_refs( refs );
    }
    else if ( status == "cancelled" && pending.kind == "cancel" )
        record.status = "OUTLANDS CLASS CANCELLED / STOCK CLASS ACTIVE";
    else if ( status == "applied" && pending.kind == "applied" )
        record.status = "OUTLANDS CLASS EQUIPPED / NATIVE XP UNCHANGED";
    else
    {
        record.armed = 0;
        record.transition = 0;
        record.queued = undefined;
        record.status = "REQUEST REJECTED / REOPEN OR RETRY";
        if ( status == "rejected" )
            record.restored = 0;
    }
    record.command = "none";
    level.outlands_armory_pending = undefined;
}

spawn_wrapper()
{
    self endon( "disconnect" );
    level endon( "game_ended" );
    record = record_for( self );
    if ( enabled() && isdefined( record ) )
    {
        record.spawn++;
        record.in_spawn = 1;
        record.armed = 0;
        record.transition = 0;
        if ( isdefined( record.queued ) )
        {
            view = validate_refs( self, record.queued );
            if ( record.spawn == record.queued_spawn + 1 && view.valid && record.command == "none" )
            {
                if ( record.fixture && fixture_allowed() )
                {
                    record.armed = 1;
                    record.transition = 1;
                    record.last_claim = copy_refs( record.queued );
                }
                else
                {
                    record.command = "claim";
                    until = gettime() + 2500;
                    while ( !record.armed && gettime() < until && same_record( record ) && record.command == "claim" && enabled() )
                        wait 0.025;
                }
            }
            if ( !record.armed )
            {
                record.queued = undefined;
                record.status = "NOT EQUIPPED / STOCK CLASS RETAINED";
                if ( isdefined( record.active ) )
                {
                    previous_view = validate_refs( self, record.active );
                    if ( previous_view.valid )
                    {
                        record.last_claim = copy_refs( record.active );
                        record.armed = 1;
                        record.transition = 0;
                    }
                }
            }
        }
        else if ( isdefined( record.active ) )
        {
            active_view = validate_refs( self, record.active );
            if ( active_view.valid )
            {
                record.last_claim = copy_refs( record.active );
                record.armed = 1;
            }
            else
            {
                record.active = undefined;
                record.status = "ACTIVE CLASS LOCKED / STOCK CLASS USED";
            }
        }
    }
    self [[ level.outlands_armory_stock_spawn ]]();
    if ( isdefined( record ) )
    {
        record.in_spawn = 0;
        record.armed = 0;
    }
}

grant_callback()
{
    record = record_for( self );
    if ( !enabled() || !isdefined( record ) || !record.in_spawn || !record.armed )
        return undefined;
    view = validate_refs( self, record.last_claim );
    if ( !view.valid )
    {
        record.armed = 0;
        record.queued = undefined;
        record.active = undefined;
        record.status = "UNLOCKS CHANGED / EQUIPMENT NOT CONFIRMED";
        if ( !record.fixture && record.transition && record.command == "none" )
            record.command = "failed";
        return undefined;
    }
    refs = copy_refs( record.last_claim );
    record.armed = 0;
    record.queued = undefined;
    record.active = copy_refs( refs );
    if ( record.transition )
        record.active_revision = record.revision;
    weapon = grant_base( self, refs );
    record.applied_spawn = record.spawn;
    if ( record.fixture )
        record.fixture_grants++;
    record.status = "EQUIPPED / VERIFYING NATIVE INVENTORY";
    record.player thread verify_grant( record, refs, record.transition, record.active_revision );
    return weapon;
}

grant_base( player, refs )
{
    player takeallweapons();
    player giveweapon( "knife_mp" );
    player.specialty = [];
    for ( i = 2; i <= 4; i++ )
        if ( refs[i] != "none" )
            foreach ( effect in level.outlands_armory_items[refs[i]].effects )
                player.specialty[player.specialty.size] = effect;
    player maps\mp\gametypes\_class::register_perks();
    spawn_weapon = "knife_held_mp";
    count = 0;
    for ( i = 1; i >= 0; i-- )
    {
        if ( refs[i] == "none" )
            continue;
        item = level.outlands_armory_items[refs[i]];
        player giveweapon( item.weapon );
        if ( player hasperk( "specialty_extraammo" ) )
            player givemaxammo( item.weapon );
        spawn_weapon = item.weapon;
        count++;
    }
    if ( count < 2 )
        player giveweapon( "knife_held_mp" );
    player.primaryloadoutweapon = "";
    player.secondaryloadoutweapon = "";
    if ( refs[0] != "none" )
        player.primaryloadoutweapon = level.outlands_armory_items[refs[0]].weapon;
    if ( refs[1] != "none" )
        player.secondaryloadoutweapon = level.outlands_armory_items[refs[1]].weapon;
    player.primaryloadoutaltweapon = "";
    player.secondaryloadoutaltweapon = "";
    player.pers["primaryWeapon"] = refs[0];
    player.spawnweapon = spawn_weapon;
    player.pers["spawnWeapon"] = spawn_weapon;
    player setspawnweapon( spawn_weapon );
    player.grenadetypeprimary = "frag_grenade_mp";
    player.grenadetypeprimarycount = 0;
    player.grenadetypesecondary = "flash_grenade_mp";
    player.grenadetypesecondarycount = 0;
    if ( refs[5] != "none" )
    {
        item = level.outlands_armory_items[refs[5]];
        player.grenadetypeprimary = item.weapon;
        player.grenadetypeprimarycount = 1;
    }
    if ( refs[6] != "none" )
    {
        item = level.outlands_armory_items[refs[6]];
        player.grenadetypesecondary = item.weapon;
        player.grenadetypesecondarycount = 1;
    }
    player giveweapon( player.grenadetypeprimary );
    player setweaponammoclip( player.grenadetypeprimary, player.grenadetypeprimarycount );
    player switchtooffhand( player.grenadetypeprimary );
    player setoffhandsecondaryclass( player.grenadetypesecondary );
    player giveweapon( player.grenadetypesecondary );
    player setweaponammoclip( player.grenadetypesecondary, player.grenadetypesecondarycount );
    // Record actual spawned equipment through the same native observation API
    // as stock CAC. This does not set progression, unlock flags or class DDL.
    streaks = array( 0, 0, 0 );
    for ( i = 0; i < 3; i++ )
        if ( level.loadoutkillstreaksenabled && isdefined( player.killstreak[i] ) && isdefined( level.killstreakindices[player.killstreak[i]] ) )
            streaks[i] = level.killstreakindices[player.killstreak[i]];
    player recordloadoutperksandkillstreaks( player.primaryloadoutweapon, player.secondaryloadoutweapon, player.grenadetypeprimary, player.grenadetypesecondary, streaks[0], streaks[1], streaks[2] );
    return spawn_weapon;
}

inventory_matches( player, refs )
{
    for ( i = 0; i < 2; i++ )
        if ( refs[i] != "none" && !player hasweapon( level.outlands_armory_items[refs[i]].weapon ) )
            return false;
    expected_perks = 0;
    for ( i = 2; i <= 4; i++ )
    {
        if ( refs[i] == "none" )
            continue;
        foreach ( effect in level.outlands_armory_items[refs[i]].effects )
        {
            expected_perks++;
            if ( level.perksenabled && !player hasperk( effect ) )
                return false;
        }
    }
    if ( player.specialty.size != expected_perks )
        return false;
    if ( player.grenadetypeprimarycount != ( refs[5] != "none" ) || player.grenadetypesecondarycount != ( refs[6] != "none" ) )
        return false;
    if ( player getweaponammoclip( player.grenadetypeprimary ) != player.grenadetypeprimarycount || player getweaponammoclip( player.grenadetypesecondary ) != player.grenadetypesecondarycount )
        return false;
    foreach ( weapon in player getweaponslist() )
        if ( weapon != "knife_mp" && weapon != "knife_held_mp" && weapon != player.primaryloadoutweapon && weapon != player.secondaryloadoutweapon && weapon != player.grenadetypeprimary && weapon != player.grenadetypesecondary && !maps\mp\killstreaks\_killstreaks::iskillstreakweapon( weapon ) )
            return false;
    return true;
}

verify_grant( record, refs, transition, revision )
{
    self endon( "disconnect" );
    self waittill( "spawned_player" );
    if ( !same_record( record ) || !enabled() )
        return;
    matched = inventory_matches( self, refs );
    record.status = "EQUIPMENT NOT CONFIRMED / SELECT STOCK CLASS";
    if ( matched )
        record.status = "OUTLANDS CLASS EQUIPPED";
    else
        record.active = undefined;
    if ( !record.fixture && transition && record.command == "none" && record.revision == revision )
    {
        record.command = "failed";
        if ( matched )
            record.command = "applied";
    }
    if ( record.fixture )
        record.fixture_matched = matched;
}

valid_slot( index )
{
    return isdefined( index ) && int( index ) == index && index >= 0 && index < 5;
}

eligible( player )
{
    if ( !isdefined( player ) || !isplayer( player ) || player istestclient() )
        return false;
    if ( !isdefined( player.guid ) || !scripts\mp\outlands_operations::valid_guid( "" + player.guid ) )
        return false;
    return isdefined( player.pers["team"] ) && ( player.pers["team"] == "allies" || player.pers["team"] == "axis" || player.pers["team"] == "free" );
}

inspect_native_slot( player, index )
{
    result = spawnstruct();
    result.ready = 0;
    result.native_valid = 0;
    result.index = -1;
    if ( !isdefined( player ) || !isplayer( player ) || !valid_slot( index ) )
        return result;
    // Native validity is separate from authoritative human unlock acceptance.
    // Do not infer earned attachment/perk ownership from this flag alone.
    if ( !player classisvalid( index ) )
        return result;
    result.index = index;
    result.native_valid = 1;
    result.primary = player getloadoutweapon( index, "primary" );
    result.secondary = player getloadoutweapon( index, "secondary" );
    result.perks = player getloadoutperks( index );
    result.ready = isdefined( result.primary ) && isdefined( result.secondary ) && isdefined( result.perks );
    return result;
}

stage_native_reference( player, index )
{
    // Private all-bot probe only. This is a native slot-selection feasibility
    // experiment, not the custom-class equip adapter used by a live player.
    if ( !getdvarint( "outlands_backend_verification" ) || getdvar( "net_ip" ) != "127.0.0.1" || !isdefined( player ) || !isplayer( player ) || !player istestclient() )
        return false;
    view = inspect_native_slot( player, index );
    if ( !view.ready || player.sessionstate != "playing" || !isalive( player ) || !isdefined( game["state"] ) || game["state"] != "playing" )
        return false;
    // Stock menuclass also sets these fields but can regrant weapons in its
    // grace-period path. Stage the reference only; stock spawning owns grants.
    selected = "CLASS_CUSTOM" + ( index + 1 );
    player.pers["class"] = selected;
    player.class = selected;
    player.pers["weapon"] = undefined;
    player.pers["changed_class"] = 1;
    return true;
}
