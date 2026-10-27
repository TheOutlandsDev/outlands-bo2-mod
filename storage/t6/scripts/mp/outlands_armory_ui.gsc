// Original bounded native base-class editor. No forced binds or input capture.
#include common_scripts\utility;

init()
{
    if ( !isdedicated() || isdefined( level.outlands_armory_ui_started ) )
        return;
    level.outlands_armory_ui_started = 1;
    level.outlands_armory_ui_owners = [];
    level thread manage_editor();
    level thread chat_editor();
    level thread end_editor();
}

parse_action( text )
{
    if ( text == "!outlands armory" )
        return "toggle";
    if ( text == "!outlands up" )
        return "up";
    if ( text == "!outlands down" )
        return "down";
    if ( text == "!outlands left" )
        return "prev";
    if ( text == "!outlands right" )
        return "next";
    if ( text == "!outlands save" )
        return "save";
    if ( text == "!outlands equip" )
        return "equip";
    if ( text == "!outlands stock" )
        return "stock";
    if ( text == "!outlands close" )
        return "close";
    return "none";
}

chat_editor()
{
    level endon( "game_ended" );
    for (;;)
    {
        level waittill( "say", text, player, hidden, team_chat );
        if ( !scripts\mp\outlands_ui::eligible( player ) || !isdefined( text ) || !isdefined( team_chat ) || team_chat )
            continue;
        if ( text.size > 1 && getsubstr( text, 0, 1 ) != "!" )
            text = getsubstr( text, 1 );
        action = parse_action( text );
        if ( action != "none" )
            dispatch( player, action );
    }
}

bind_editor( player )
{
    player endon( "disconnect" );
    level endon( "game_ended" );
    actions = array( "up", "down", "prev", "next", "save", "equip", "stock", "close" );
    player notifyonplayercommand( "outlands_armory_toggle", "outlands_armory" );
    player thread listen_editor( "toggle" );
    foreach ( action in actions )
    {
        player notifyonplayercommand( "outlands_armory_" + action, "outlands_armory_" + action );
        player thread listen_editor( action );
    }
    player thread close_editor_on( "death" );
    player thread close_editor_on( "spawned_player" );
    player waittill( "disconnect" );
}

listen_editor( action )
{
    self endon( "disconnect" );
    level endon( "game_ended" );
    for (;;)
    {
        self waittill( "outlands_armory_" + action );
        dispatch( self, action );
    }
}

close_editor_on( event )
{
    self endon( "disconnect" );
    level endon( "game_ended" );
    for (;;)
    {
        self waittill( event );
        state = level.outlands_armory_ui_owners[self getentitynumber()];
        if ( isdefined( state ) && state.owner == self )
            scripts\mp\outlands_ui::destroy_hud( state );
    }
}

dispatch( player, action )
{
    if ( !scripts\mp\outlands_ui::eligible( player ) || !scripts\mp\outlands_armory::enabled() )
        return false;
    slot = player getentitynumber();
    state = level.outlands_armory_ui_owners[slot];
    if ( isdefined( state ) && state.owner != player )
    {
        scripts\mp\outlands_ui::destroy_hud( state );
        state = undefined;
    }
    if ( isdefined( state ) && gettime() - state.last_action < 250 )
        return false;
    if ( action == "close" || ( action == "toggle" && isdefined( state ) && state.open ) )
    {
        if ( isdefined( state ) )
            scripts\mp\outlands_ui::destroy_hud( state );
        return true;
    }
    if ( !isdefined( state ) || !state.open )
    {
        if ( action != "toggle" && action != "stock" )
            return false;
        if ( isdefined( level.outlands_ui_owners ) )
        {
            career = level.outlands_ui_owners[slot];
            if ( isdefined( career ) )
                scripts\mp\outlands_ui::destroy_hud( career );
        }
        state = create_editor( player );
        level.outlands_armory_ui_owners[slot] = state;
    }
    state.last_action = gettime();
    state.deadline = gettime() + 40000;
    record = scripts\mp\outlands_armory::record_for( player );
    if ( !isdefined( record ) )
        return false;
    if ( action == "up" )
        state.row = ( state.row + 6 ) % 7;
    if ( action == "down" )
        state.row = ( state.row + 1 ) % 7;
    if ( action == "prev" || action == "next" )
    {
        direction = 1;
        if ( action == "prev" )
            direction = -1;
        cycle_item( record, state.row, direction );
    }
    if ( action == "save" || action == "equip" )
        scripts\mp\outlands_armory::request( player, action );
    if ( action == "stock" )
        scripts\mp\outlands_armory::cancel_record( record, "STOCK CLASS ON NEXT RESPAWN" );
    draw_editor( state, record );
    return true;
}

cycle_item( record, row, direction )
{
    if ( !record.restored || row < 0 || row >= 7 || ( direction != 1 && direction != -1 ) )
        return false;
    slot = level.outlands_armory_slots[row];
    choices = level.outlands_armory_choices[slot];
    current = 0;
    for ( i = 0; i < choices.size; i++ )
        if ( choices[i] == record.draft[row] )
            current = i;
    for ( step = 1; step <= choices.size; step++ )
    {
        index = ( current + direction * step + choices.size * 2 ) % choices.size;
        if ( scripts\mp\outlands_armory::item_unlocked( record.player, choices[index], slot ) )
        {
            record.draft[row] = choices[index];
            record.status = "DRAFT ONLY / SAVE TO QUEUE NEXT RESPAWN";
            return true;
        }
    }
    return false;
}

create_editor( player )
{
    state = spawnstruct();
    state.owner = player;
    record = scripts\mp\outlands_armory::record_for( player );
    state.session = "none";
    if ( isdefined( record ) )
        state.session = record.session;
    state.elements = [];
    state.row = 0;
    state.open = 1;
    state.last_action = -1000;
    state.deadline = gettime() + 40000;
    amber = ( 0.95, 0.57, 0.20 );
    white = ( 0.94, 0.94, 0.91 );
    soft = ( 0.70, 0.72, 0.73 );
    scripts\mp\outlands_ui::ui_panel( state, -305, -175, 610, 350, ( 0.06, 0.075, 0.085 ), 100 );
    scripts\mp\outlands_ui::ui_panel( state, -305, -175, 610, 3, amber, 101 );
    scripts\mp\outlands_ui::ui_label( state, -285, -160, 1.8, "OUTLANDS / ARMORY", white );
    scripts\mp\outlands_ui::ui_label( state, -285, -131, 0.9, "BASE CLASS / NATIVE UNLOCKS / ONE SAVED SLOT", soft );
    state.selector = scripts\mp\outlands_ui::ui_panel( state, -285, -105, 570, 26, ( 0.19, 0.15, 0.10 ), 101 );
    state.labels = [];
    state.values = [];
    names = array( "PRIMARY", "SECONDARY", "PERK 1", "PERK 2", "PERK 3", "LETHAL", "TACTICAL" );
    for ( i = 0; i < 7; i++ )
    {
        state.labels[i] = scripts\mp\outlands_ui::ui_label( state, -275, -101 + i * 29, 1.1, names[i], soft );
        state.values[i] = scripts\mp\outlands_ui::ui_label( state, -90, -101 + i * 29, 1.15, "NONE", white );
    }
    state.points = scripts\mp\outlands_ui::ui_label( state, 210, -155, 1.4, "", amber );
    scripts\mp\outlands_ui::ui_label( state, 240, -155, 1.4, "/", soft );
    state.limit = scripts\mp\outlands_ui::ui_label( state, 260, -155, 1.4, "", soft );
    state.status = scripts\mp\outlands_ui::ui_label( state, -285, 113, 0.85, "LOADING SAVED CLASS", soft );
    scripts\mp\outlands_ui::ui_label( state, -285, 133, 0.8, "F6 ROW / F7-F8 CHANGE / F9 SAVE / F11 EQUIP (optional binds)", soft );
    scripts\mp\outlands_ui::ui_label( state, -285, 151, 0.8, "F5 CLOSE / Stock CAC retains attachments, wildcards and special equipment", soft );
    return state;
}

draw_editor( state, record )
{
    if ( !isdefined( record ) )
        return;
    state.selector.y = -105 + state.row * 29;
    for ( i = 0; i < 7; i++ )
    {
        state.labels[i].color = ( 0.70, 0.72, 0.73 );
        if ( i == state.row )
            state.labels[i].color = ( 0.95, 0.57, 0.20 );
        ref = record.draft[i];
        item = level.outlands_armory_items[ref];
        if ( !isdefined( state.values[i].outlands_ref ) || state.values[i].outlands_ref != ref )
        {
            if ( isdefined( item ) )
                state.values[i] settext( item.label );
            else
                state.values[i] settext( "NONE" );
            state.values[i].outlands_ref = ref;
        }
    }
    view = scripts\mp\outlands_armory::validate_refs( record.player, record.draft );
    state.points setvalue( view.points );
    state.limit setvalue( scripts\mp\outlands_armory::allocation( record.player ) );
    scripts\mp\outlands_ui::ui_text( state.status, record.status );
}

manage_editor()
{
    level endon( "game_ended" );
    for (;;)
    {
        foreach ( player in get_players() )
            if ( scripts\mp\outlands_ui::eligible( player ) && !isdefined( player.outlands_armory_bound ) )
            {
                player.outlands_armory_bound = 1;
                player thread bind_editor( player );
            }
        for ( slot = 0; slot <= 17; slot++ )
        {
            state = level.outlands_armory_ui_owners[slot];
            if ( !isdefined( state ) || !state.open )
                continue;
            record = scripts\mp\outlands_armory::record_for( state.owner );
            if ( !scripts\mp\outlands_armory::enabled() || !scripts\mp\outlands_ui::eligible( state.owner ) || ( state.owner getentitynumber() ) != slot || gettime() >= state.deadline || !isdefined( record ) || record.session != state.session )
                scripts\mp\outlands_ui::destroy_hud( state );
            else
                draw_editor( state, scripts\mp\outlands_armory::record_for( state.owner ) );
        }
        wait 0.25;
    }
}

end_editor()
{
    level waittill( "game_ended" );
    foreach ( state in level.outlands_armory_ui_owners )
        if ( isdefined( state ) )
            scripts\mp\outlands_ui::destroy_hud( state );
}
