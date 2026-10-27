// Original Outlands native handoff for the host's weighted map director.
// No map command is executed here: stock match-end map_rotate owns transition.
init()
{
    if ( !isdedicated() || !getdvarint( "outlands_rotation" ) || !getdvarint( "outlands_rotation_host" ) || isdefined( level.outlands_rotation_started ) )
        return;
    level.outlands_rotation_started = 1;
    level thread prepare_next_map();
}

contains_value( values, wanted )
{
    foreach ( value in values )
        if ( value == wanted )
            return true;
    return false;
}

prepare_next_map()
{
    level endon( "game_ended" );
    wait 3;
    nonce = "r" + randomint( 1000000000 ) + "_" + gettime();
    maps = strtok( getdvar( "outlands_rotation_maps" ), "," );
    modes = strtok( getdvar( "outlands_rotation_modes" ), "," );
    setdvar( "outlands_rotation_plan", "" );
    for ( attempt = 0; attempt < 60; attempt++ )
    {
        if ( !getdvarint( "outlands_rotation" ) )
            return;
        println( "OUTLANDS_ROTATION_V1|" + nonce + "|" + getdvar( "mapname" ) + "|" + getdvar( "g_gametype" ) );
        wait 2;
        fields = strtok( getdvar( "outlands_rotation_plan" ), "|" );
        if ( fields.size != 3 || fields[0] != nonce || !contains_value( maps, fields[1] ) || !contains_value( modes, fields[2] ) )
            continue;
        entry = "gametype " + fields[2] + " execgts outlands_" + fields[2] + ".cfg map " + fields[1];
        setdvar( "sv_maprotationcurrent", entry );
        if ( getdvar( "sv_maprotationcurrent" ) == entry )
        {
            println( "OUTLANDS_ROTATION_ACK_V1|" + nonce + "|" + fields[1] + "|" + fields[2] );
            return;
        }
    }
    println( "Outlands rotation: next-map handoff unavailable; static fallback retained." );
}
