import sys
import ultraTB
import Debugger
import bdb

defaultTB = ultraTB.AutoFormattedTB(mode="Context", color_scheme="LightBG")
defaultPDB = Debugger.Pdb(color_scheme="LightBG")

# convenience
set_trace = Debugger.set_trace

# replacement excepthook
# usage: sys.excepthook = tbtools.excepthook


def excepthook(etype, value, tb):
    if etype is bdb.BdbQuit:
        return
        
    defaultTB(etype, value, tb)

    if tb and not sys.stdout.closed and \
            hasattr(sys.stdout, "isatty") and \
            sys.stdout.isatty() and \
            etype.__name__ != "DistributionNotFound":
        Debugger.post_mortem(tb)
