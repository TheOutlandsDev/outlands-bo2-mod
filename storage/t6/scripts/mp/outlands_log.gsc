// Original structured-log boundary helper. Engine println emits its final newline
// separately; include both boundaries in the same payload to avoid joined records.
emit( text )
{
    println( "\n" + text + "\n" );
}
