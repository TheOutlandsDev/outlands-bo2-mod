// Original opt-in Outlands HUD frontend. No client assets, stats or inventory
// writes. Only private client HUD elements and fixed player-command callbacks.
#include common_scripts\utility;

main()
{
    if ( getdvar( "outlands_ui" ) == "" )
        setdvar( "outlands_ui", 0 );
}

init()
{
    if ( !isdedicated() || isdefined( level.outlands_ui_started ) )
        return;
    level.outlands_ui_started = 1;
    level.outlands_ui_owners = [];
    level thread manage();
    level thread chat_commands();
    level thread finish();
}

eligible( player )
{
    if ( !isdefined( player ) || !isplayer( player ) || player istestclient() )
        return false;
    slot = player getentitynumber();
    return slot >= 0 && slot <= 17;
}

// Pure presenters: the same functions are exercised in disposable engine tests.
// An unavailable view contains no earned values. Never present missing as zero.
career_view( record, now, enabled )
{
    view = spawnstruct();
    view.status = "OPERATIONS DISABLED";
    view.ready = 0;
    if ( !enabled )
        return view;
    view.status = "LOADING CAREER";
    if ( !isdefined( record ) || !isdefined( record.restored ) || !record.restored )
        return view;
    view.status = "CAREER UNAVAILABLE";
    if ( !isdefined( record.acknowledged ) || now < record.acknowledged || now - record.acknowledged > 45000 )
        return view;
    if ( !isdefined( record.totals ) || record.totals.size != 3 || !isdefined( record.selected ) )
        return view;
    if ( record.selected != "assault" && record.selected != "objective" && record.selected != "support" )
        return view;
    foreach ( value in record.totals )
        if ( !isdefined( value ) || value < 0 || value > 1000000000 || int( value ) != value )
            return view;
    view.ready = 1;
    view.totals = record.totals;
    view.selected = record.selected;
    view.milestones = 0;
    if ( view.totals[0] >= 25 )
        view.milestones++;
    if ( view.totals[1] >= 3 )
        view.milestones++;
    if ( view.totals[2] >= 3 )
        view.milestones++;
    view.status = "ALL TRACKS PROGRESS TOGETHER";
    if ( view.milestones == 3 )
        view.status = "BROKEN SIGNAL COMPLETE - FIELD REGULAR";
    if ( isdefined( record.command ) && record.command == "select" )
        view.status = "SAVING FOCUS - WAIT FOR CONFIRMATION";
    return view;
}

contract_view( record, now, deadline, enabled, supported )
{
    view = spawnstruct();
    view.ready = 0;
    view.status = "CONTRACTS DISABLED";
    if ( !enabled )
        return view;
    view.status = "TEAM CONTRACTS NOT AVAILABLE HERE";
    if ( !supported )
        return view;
    view.status = "WAITING FOR TEAM CONTRACT";
    if ( !isdefined( record ) )
        return view;
    view.status = "REFRESHING TEAM CONTRACT";
    if ( !isdefined( record.observed ) || now < record.observed || now - record.observed > 5000 || !isdefined( deadline ) || deadline <= now || deadline - now > 300000 )
        return view;
    if ( !isdefined( record.kind ) || ( record.kind != "team_points" && record.kind != "combined_score" && record.kind != "team_eliminations" ) )
        return view;
    if ( !isdefined( record.goal ) || !isdefined( record.progress ) || !isdefined( record.complete ) )
        return view;
    if ( record.goal < 1 || record.goal > 1000000 || int( record.goal ) != record.goal || record.progress < 0 || record.progress > 1000000000 || int( record.progress ) != record.progress || ( record.complete != 0 && record.complete != 1 ) )
        return view;
    if ( record.complete != ( record.progress >= record.goal ) )
        return view;
    view.ready = 1;
    view.kind = record.kind;
    view.goal = record.goal;
    view.progress = record.progress;
    view.seconds = int( ( deadline - now ) / 1000 );
    view.status = "TEAM PROGRESS - CONTRIBUTE PERSONAL SCORE";
    if ( record.complete )
        view.status = "TEAM CONTRACT COMPLETE";
    return view;
}

milestone_goal( total, track )
{
    thresholds = array( 3, 10, 25 );
    if ( track == "assault" )
        thresholds = array( 25, 100, 250 );
    foreach ( threshold in thresholds )
        if ( total < threshold )
            return threshold;
    return thresholds[2];
}

bar_width( value, maximum )
{
    if ( maximum <= 0 || value <= 0 )
        return 0;
    if ( value >= maximum )
        return 330;
    return int( value * 330.0 / maximum );
}

parse_action( text )
{
    if ( text == "!outlands" )
        return "toggle";
    if ( text == "!outlands career" )
        return "career";
    if ( text == "!outlands contracts" )
        return "contracts";
    if ( text == "!outlands close" )
        return "close";
    if ( text == "!outlands focus" )
        return "focus";
    return "none";
}

chat_commands()
{
    level endon( "game_ended" );
    for (;;)
    {
        level waittill( "say", text, player, hidden, team_chat );
        if ( !eligible( player ) || !isdefined( text ) || !isdefined( team_chat ) || team_chat )
            continue;
        // Native chat can prefix a control byte. Hidden /!outlands is accepted
        // without forwarding the private command to the chat/model worker.
        if ( text.size > 1 && getsubstr( text, 0, 1 ) != "!" )
            text = getsubstr( text, 1 );
        action = parse_action( text );
        if ( action != "none" )
            dispatch( player, action );
    }
}

bind_commands( player )
{
    player endon( "disconnect" );
    level endon( "game_ended" );
    player notifyonplayercommand( "outlands_ui_toggle", "outlands" );
    player notifyonplayercommand( "outlands_ui_next", "outlands_next" );
    player notifyonplayercommand( "outlands_ui_focus", "outlands_focus" );
    player notifyonplayercommand( "outlands_ui_close", "outlands_close" );
    player thread listen( "outlands_ui_toggle", "toggle" );
    player thread listen( "outlands_ui_next", "next" );
    player thread listen( "outlands_ui_focus", "focus" );
    player thread listen( "outlands_ui_close", "close" );
    player thread close_on( "spawned_player" );
    player thread close_on( "death" );
    player waittill( "disconnect" );
}

listen( event, action )
{
    self endon( "disconnect" );
    level endon( "game_ended" );
    for (;;)
    {
        self waittill( event );
        dispatch( self, action );
    }
}

close_on( event )
{
    self endon( "disconnect" );
    level endon( "game_ended" );
    for (;;)
    {
        self waittill( event );
        slot = self getentitynumber();
        state = level.outlands_ui_owners[slot];
        if ( isdefined( state ) && state.owner == self )
            destroy_hud( state );
    }
}

dispatch( player, action )
{
    if ( !eligible( player ) || !getdvarint( "outlands_ui" ) )
        return false;
    if ( action != "toggle" && action != "next" && action != "focus" && action != "close" && action != "career" && action != "contracts" )
        return false;
    slot = player getentitynumber();
    state = level.outlands_ui_owners[slot];
    if ( isdefined( state ) && state.owner != player )
    {
        destroy_hud( state );
        state = undefined;
    }
    if ( isdefined( state ) && gettime() - state.last_action < 250 )
        return false;
    if ( action == "close" || ( action == "toggle" && isdefined( state ) && state.open ) )
    {
        if ( isdefined( state ) )
            destroy_hud( state );
        return true;
    }
    if ( !isdefined( state ) || !state.open )
    {
        if ( action == "next" || action == "focus" )
            return false;
        state = create_hud( player );
        level.outlands_ui_owners[slot] = state;
    }
    state.last_action = gettime();
    state.deadline = gettime() + 40000;
    if ( action == "career" || action == "contracts" )
        state.page = action;
    if ( action == "next" )
    {
        state.page = "career";
        if ( state.previous_page == "career" )
            state.page = "contracts";
    }
    if ( action == "focus" && state.page == "career" )
    {
        record = operation_record( player );
        view = career_view( record, gettime(), getdvarint( "outlands_operations" ) );
        if ( view.ready )
        {
            track = "assault";
            if ( view.selected == "assault" )
                track = "objective";
            if ( view.selected == "objective" )
                track = "support";
            queue = getfunction( "scripts/mp/outlands_operations", "queue_command" );
            if ( isdefined( queue ) && [[ queue ]]( player, "select", track ) )
            {
                state.saving_until = gettime() + 25000;
                state.save_started = gettime();
                state.save_session = record.session;
                state.requested_track = track;
            }
        }
    }
    state.previous_page = state.page;
    refresh_view( state );
    return true;
}

operation_record( player )
{
    same = getfunction( "scripts/mp/outlands_operations", "same_human" );
    if ( !isdefined( same ) || !isdefined( level.outlands_operations_records ) )
        return undefined;
    record = level.outlands_operations_records[player getentitynumber()];
    if ( ![[ same ]]( record ) || record.player != player )
        return undefined;
    return record;
}

manage()
{
    level endon( "game_ended" );
    for (;;)
    {
        foreach ( player in get_players() )
        {
            if ( !eligible( player ) )
                continue;
            if ( !isdefined( player.outlands_ui_bound ) )
            {
                player.outlands_ui_bound = 1;
                player thread bind_commands( player );
            }
        }
        for ( slot = 0; slot <= 17; slot++ )
        {
            state = level.outlands_ui_owners[slot];
            if ( !isdefined( state ) || !state.open )
                continue;
            if ( !getdvarint( "outlands_ui" ) || !eligible( state.owner ) || ( state.owner getentitynumber() ) != slot || gettime() >= state.deadline )
                destroy_hud( state );
            else
                refresh_view( state );
        }
        wait 0.5;
    }
}

refresh_view( state )
{
    record = operation_record( state.owner );
    career = career_view( record, gettime(), getdvarint( "outlands_operations" ) );
    team = "none";
    if ( isdefined( state.owner.pers["team"] ) )
        team = state.owner.pers["team"];
    contract = undefined;
    supported = ( team == "allies" || team == "axis" ) && getdvar( "g_gametype" ) != "dm";
    if ( supported && isdefined( level.outlands_contracts_records ) )
        contract = level.outlands_contracts_records[team];
    deadline = undefined;
    if ( isdefined( level.outlands_contracts_deadline ) && isdefined( level.outlands_contracts_active ) && level.outlands_contracts_active )
        deadline = level.outlands_contracts_deadline;
    task = contract_view( contract, gettime(), deadline, getdvarint( "outlands_contracts" ), supported );
    // Once submitted, keep showing the last acknowledged focus until the same
    // session's worker response arrives. Expiry never pretends the save worked.
    if ( career.ready && isdefined( state.save_session ) && isdefined( record ) )
    {
        if ( record.session != state.save_session )
        {
            career.status = "SESSION CHANGED - REOPEN CAREER";
            state.save_session = undefined;
        }
        else if ( record.acknowledged > state.save_started && career.selected == state.requested_track )
            state.save_session = undefined;
        else if ( state.saving_until > gettime() )
            career.status = "SAVING FOCUS - WAIT FOR CONFIRMATION";
        else
            career.status = "FOCUS NOT CONFIRMED - RETRY WHEN READY";
    }
    draw_view( state, career, task );
}

ui_element( state, x, y, sort )
{
    hud = newclienthudelem( state.owner );
    hud.horzalign = "center";
    hud.vertalign = "middle";
    hud.alignx = "left";
    hud.aligny = "top";
    hud.x = x;
    hud.y = y;
    hud.sort = sort;
    hud.alpha = 1;
    hud.foreground = true;
    hud.hidewheninmenu = true;
    hud.archived = false;
    state.elements[state.elements.size] = hud;
    return hud;
}

ui_panel( state, x, y, width, height, color, sort )
{
    hud = ui_element( state, x, y, sort );
    hud.color = color;
    hud.alpha = 0.96;
    hud setshader( "white", width, height );
    return hud;
}

ui_label( state, x, y, size, caption, color )
{
    hud = ui_element( state, x, y, 102 );
    hud.font = "default";
    hud.fontscale = size;
    hud.color = color;
    ui_text( hud, caption );
    return hud;
}

ui_text( hud, value )
{
    if ( !isdefined( hud.outlands_text ) || hud.outlands_text != value )
    {
        hud settext( value );
        hud.outlands_text = value;
    }
}

create_hud( player )
{
    state = spawnstruct();
    state.owner = player;
    state.elements = [];
    state.open = 1;
    state.page = "career";
    state.previous_page = "career";
    state.last_action = -1000;
    state.saving_until = 0;
    state.deadline = gettime() + 40000;
    amber = ( 0.95, 0.57, 0.20 );
    white = ( 0.94, 0.94, 0.91 );
    soft = ( 0.70, 0.72, 0.73 );
    state.background = ui_panel( state, -305, -175, 610, 350, ( 0.06, 0.075, 0.085 ), 100 );
    state.rail = ui_panel( state, -305, -175, 610, 3, amber, 101 );
    state.heading = ui_label( state, -285, -160, 1.8, "OUTLANDS / OPERATIONS", white );
    state.divider = ui_panel( state, -285, -126, 570, 1, ( 0.24, 0.26, 0.27 ), 101 );
    state.selector = ui_panel( state, -285, -105, 145, 29, amber, 101 );
    state.career_label = ui_label( state, -275, -101, 1.4, "CAREER", white );
    state.contract_label = ui_label( state, -275, -61, 1.4, "CONTRACTS", white );
    state.motto = ui_label( state, -282, 28, 1.0, "CLASSIC COMBAT", soft );
    state.motto_second = ui_label( state, -282, 45, 1.0, "A DEEPER CAREER", soft );
    state.title = ui_label( state, -115, -103, 1.7, "BROKEN SIGNAL", white );
    state.subtitle = ui_label( state, -115, -76, 1.0, "Next milestones / Personal contributions", soft );
    state.rows = [];
    for ( i = 0; i < 3; i++ )
    {
        row = spawnstruct();
        row.name = ui_label( state, -115, -45 + i * 48, 1.1, "", soft );
        row.value = ui_label( state, 105, -45 + i * 48, 1.2, "", white );
        row.goal = ui_label( state, 193, -45 + i * 48, 1.0, "", soft );
        row.empty = ui_label( state, 105, -45 + i * 48, 1.2, "--", soft );
        row.bar = ui_panel( state, -115, -22 + i * 48, 330, 3, amber, 102 );
        state.rows[state.rows.size] = row;
    }
    state.detail = ui_label( state, -115, 111, 1.0, "", amber );
    state.status = ui_label( state, -285, 142, 0.85, "", soft );
    state.footer = ui_label( state, -285, 157, 0.85, "F6 MENU / F7 PAGE / F8 FOCUS / F9 CLOSE (optional bindings)", soft );
    return state;
}

draw_view( state, career, task )
{
    amber = ( 0.95, 0.57, 0.20 );
    white = ( 0.94, 0.94, 0.91 );
    state.selector.y = -105;
    state.career_label.color = ( 0.06, 0.075, 0.085 );
    state.contract_label.color = white;
    view = career;
    names = array( "ASSAULT", "OBJECTIVE", "SUPPORT" );
    if ( state.page == "contracts" )
    {
        state.selector.y = -65;
        state.career_label.color = white;
        state.contract_label.color = ( 0.06, 0.075, 0.085 );
        ui_text( state.title, "TEAM CONTRACT" );
        ui_text( state.subtitle, "Shared match progress / Current team only" );
        names = array( "TEAM PROGRESS", "SECONDS REMAINING", "" );
        view = task;
    }
    else
    {
        ui_text( state.title, "BROKEN SIGNAL" );
        ui_text( state.subtitle, "Next milestones / Personal contributions" );
    }
    for ( i = 0; i < 3; i++ )
    {
        row = state.rows[i];
        ui_text( row.name, names[i] );
        row.name.color = white;
        row.value.alpha = 0;
        row.goal.alpha = 0;
        row.empty.alpha = 1;
        row.bar.alpha = 0;
        if ( state.page == "contracts" && i == 2 )
        {
            row.empty.alpha = 0;
            continue;
        }
        if ( !view.ready )
            continue;
        value = 0;
        target = 1;
        if ( state.page == "career" )
        {
            value = career.totals[i];
            track = tolower( names[i] );
            target = milestone_goal( value, track );
            if ( career.selected == track )
                row.name.color = amber;
        }
        else if ( i == 0 )
        {
            value = task.progress;
            target = task.goal;
        }
        else
            value = task.seconds;
        row.empty.alpha = 0;
        row.value.alpha = 1;
        row.value setvalue( value );
        if ( state.page == "career" || i == 0 )
        {
            row.goal.alpha = 1;
            row.goal setvalue( target );
            width = bar_width( value, target );
            if ( width > 0 )
            {
                row.bar.alpha = 1;
                row.bar setshader( "white", width, 3 );
            }
        }
    }
    detail = "CAREER DATA UNAVAILABLE";
    if ( state.page == "career" && career.ready )
    {
        detail = "FOCUS: ASSAULT";
        if ( career.selected == "objective" )
            detail = "FOCUS: OBJECTIVE";
        if ( career.selected == "support" )
            detail = "FOCUS: SUPPORT";
    }
    if ( state.page == "contracts" )
    {
        detail = "CONTRACT DATA UNAVAILABLE";
        if ( task.ready )
        {
            detail = "TEAM MATCH POINTS";
            if ( task.kind == "combined_score" )
                detail = "COMBINED SCOREBOARD SCORE";
            if ( task.kind == "team_eliminations" )
                detail = "TEAM ELIMINATIONS";
        }
    }
    ui_text( state.detail, detail );
    ui_text( state.status, view.status );
}

destroy_hud( state )
{
    if ( !isdefined( state ) )
        return;
    foreach ( hud in state.elements )
        if ( isdefined( hud ) )
            hud destroy();
    state.elements = [];
    state.open = 0;
}

finish()
{
    level waittill( "game_ended" );
    for ( slot = 0; slot <= 17; slot++ )
        if ( isdefined( level.outlands_ui_owners[slot] ) )
            destroy_hud( level.outlands_ui_owners[slot] );
}
