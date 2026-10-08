if {![package vsatisfies [package provide Tcl] 9.0]} return
package ifneeded tk 9.1.0 [list load [file normalize [file join $dir .. libtcl9tk9.1.dylib]]]
package ifneeded Tk 9.1.0 [list package require -exact tk 9.1.0]
