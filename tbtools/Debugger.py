# -*- coding: utf-8 -*-
"""
Pdb debugger class.

Modified from the standard pdb.Pdb class to avoid including readline, so that
the command line completion of other programs which include this isn't
damaged.

In the future, this class will be expanded with improvements over the standard
pdb.

The code in this file is mainly lifted out of cmd.py in Python 2.2, with minor
changes. Licensing should therefore be under the standard Python terms.  For
details on the PSF (Python Software Foundation) standard license, see:

http://www.python.org/2.2.3/license.html

$Id: Debugger.py 1029 2006-01-18 07:33:38Z fperez $"""

#*****************************************************************************
#
# Since this file is essentially a modified copy of the pdb module which is
# part of the standard Python distribution, I assume that the proper procedure
# is to maintain its copyright as belonging to the Python Software Foundation
# (in addition to my own, for all new code).
#
#       Copyright (C) 2001 Python Software Foundation, www.python.org
#       Copyright (C) 2005-2006 Fernando Perez. <fperez@colorado.edu>
#
#  Distributed under the terms of the BSD License.  The full license is in
#  the file COPYING, distributed as part of this software.
#
#*****************************************************************************
__license__ = 'Python'

import sys
import os
import bdb
import pdb
import cmd
import linecache
import readline
import __builtin__

import tbtools
from tbtools import PyColorize, ColorANSI
from tbtools.excolors import ExceptionColors


def _file_lines(fname):
    """Return the contents of a named file as a list of lines.

    This function never raises an IOError exception: if the file can't be
    read, it simply returns an empty list."""

    try:
        outfile = open(fname)
    except IOError:
        return []
    else:
        out = outfile.readlines()
        outfile.close()
        return out


# Python 2.6 defines Restart
try:
    from pdb import Restart
except ImportError:
    # bogus, it won't be raised except when already defined
    class Restart(Exception):
        pass


class Pdb(pdb.Pdb):
    """Modified Pdb class, does not load readline."""

    # Ugly hack: we can't call the parent constructor, because it binds
    # readline and breaks tab-completion.  This means we have to COPY the
    # constructor here, and that requires tracking various python versions.

    def __init__(self, color_scheme='NoColor', stdin=None, stdout=None, use_textmate=True):
        bdb.Bdb.__init__(self)
        # don't load readline
        cmd.Cmd.__init__(self, completekey=None, stdin=stdin, stdout=stdout)
        if stdout:
            self.use_rawinput = 0
        self.prompt = 'ipdb> ' # The default prompt is '(Pdb)'
        self.aliases = {}

        # These two lines are part of the py2.4 constructor, let's put them
        # unconditionally here as they won't cause any problems in 2.3.
        self.mainpyfile = ''
        self._wait_for_mainpyfile = 0

        # Read $HOME/.pdbrc and ./.pdbrc
        try:
            self.rcLines = _file_lines(os.path.join(os.environ['HOME'],
                                                    ".pdbrc"))
        except KeyError:
            self.rcLines = []
        self.rcLines.extend(_file_lines(".pdbrc"))

        self.commands = {} # associates a command list to breakpoint numbers
        self.commands_doprompt = {} # for each bp num, tells if the prompt must be disp. after execing the cmd list
        self.commands_silent = {} # for each bp num, tells if the stack trace must be disp. after execing the cmd list
        self.commands_defining = False # True while in the process of defining a command list
        self.commands_bnum = None # The breakpoint number for which we are defining a list

        # Create color table: we copy the default one from the traceback
        # module and add a few attributes needed for debugging
        self.color_scheme_table = ExceptionColors.copy()

        # shorthands
        C = ColorANSI.TermColors
        cst = self.color_scheme_table

        cst['NoColor'].colors.breakpoint_enabled = C.NoColor
        cst['NoColor'].colors.breakpoint_disabled = C.NoColor

        cst['Linux'].colors.breakpoint_enabled = C.LightRed
        cst['Linux'].colors.breakpoint_disabled = C.Red

        cst['LightBG'].colors.breakpoint_enabled = C.LightRed
        cst['LightBG'].colors.breakpoint_disabled = C.Red

        self.set_colors(color_scheme)

        user_names = self.completenames("")
        user_ns = {}
        for name in user_names:
            user_ns[name] = getattr(self, "do_" + name)

        self.user_ns = user_ns

        self.use_textmate = use_textmate
        self.textmate = None

    def set_colors(self, scheme):
        """Shorthand access to the color table scheme selector method."""
        self.color_scheme_table.set_active_scheme(scheme)

    def set_completer_frame(self, frame=None):
        if not self.Completer:
            return

        self.Completer.namespace = self.user_ns
        if frame:
            self.Completer.namespace.update(frame.f_locals)
            self.Completer.namespace.update(frame.f_globals)

        # XXX: I don't really remember why I put this entry here
        # self.Completer.namespace.update(sys._getframe().f_locals)

    def interaction(self, frame, traceback):
        import rlicompleter
        self.Completer = rlicompleter.completer.Completer(self.user_ns)
        
        from pprint import pprint
        def displayhook(object):
            if object is not None:
                pprint(object)
        sys.displayhook = displayhook
        
        self.set_completer_frame(frame)

        # instead of calling pdb.interaction(self, frame, traceback) ::
        self.setup(frame, traceback)
        if hasattr(self, "_private_frame_stack"):
            self.stack = [(f, f.f_lineno) for f in self._private_frame_stack]
            self.curindex = len(self.stack) - 1
            self.curframe = self.stack[-1][0]

        __builtin__._pdb = self

        self.cmdloop()
        self.forget()

    def do_up(self, arg):
        pdb.Pdb.do_up(self, arg)
        self.set_completer_frame(self.curframe)
        self._mate()
    do_u = do_up


    def do_down(self, arg):
        pdb.Pdb.do_down(self, arg)
        self.set_completer_frame(self.curframe)
        self._mate()
    do_d = do_down

    def postcmd(self, stop, line):
        self.set_completer_frame(self.curframe)
        return stop

    def preloop(self):
        # load a new completer, save the old
        self.old_completer = readline.get_completer()
        readline.set_completer(self.Completer.complete)

        # sane defaults
        readline.parse_and_bind("tab: complete")
        readline.parse_and_bind("set show-all-if-ambiguous on")

        self._mate()

    def _mate(self):
        if not self.use_textmate:
            return
        
        try:
            import appscript
        except ImportError:
            self.use_textmate = False
            return
        
        if not self.textmate:
            self.textmate = appscript.app("TextMate.app")
        
        frame, lineno = self.stack[self.curindex]
        filename = self.canonic(frame.f_code.co_filename)
        if path(filename).exists():
            tm_url = "txmt://open?url=file://%s&line=%d&column=2" % (filename, lineno)
            self.textmate.get_url(tm_url.replace(" ", "%20"))
            self.textmate.get_url(tm_url.replace(" ", "%20"))
   
    ##
    # TextMate integration
    ##
    def do_where(self, arg):
        pdb.Pdb.do_where(self, arg)
        self._mate()
    
    def do_next(self, arg):
        pdb.Pdb.do_next(self, arg)
        self._mate()
            

    def postloop(self):
        self.set_completer_frame(None)
        readline.set_completer(self.old_completer)

    def print_stack_trace(self):
        try:
            for frame_lineno in self.stack[:self.curindex+1]:
                self.print_stack_entry(frame_lineno, context=5)
        except KeyboardInterrupt:
            pass


    def print_stack_entry(self, frame_lineno, prompt_prefix='\n-> ', context=3):
        frame, lineno = frame_lineno
        print >>sys.stdout, self.format_stack_entry(frame_lineno, '', context)


    def format_stack_entry(self, frame_lineno, lprefix=': ', context=3):
        import linecache, repr

        ret = ""

        Colors = self.color_scheme_table.active_colors
        ColorsNormal = Colors.Normal
        tpl_link = '%s%%s%s' % (Colors.filenameEm, ColorsNormal)
        tpl_call = 'in %s%%s%s%%s%s' % (Colors.vName, Colors.valEm, ColorsNormal)
        tpl_line = '%%s%s%%s %s%%s' % (Colors.lineno, ColorsNormal)
        tpl_line_em = '%%s%s%%s %s%%s%s' % (Colors.linenoEm, Colors.line,
                                            ColorsNormal)

        frame, lineno = frame_lineno

        return_value = ''
        if '__return__' in frame.f_locals:
            rv = frame.f_locals['__return__']
            #return_value += '->'
            return_value += repr.repr(rv) + '\n'
        ret += return_value

        #s = filename + '(' + `lineno` + ')'
        filename = self.canonic(frame.f_code.co_filename)
        link = tpl_link % filename

        if frame.f_code.co_name:
            func = frame.f_code.co_name
        else:
            func = "<lambda>"

        call = ''
        if func != '?':
            if '__args__' in frame.f_locals:
                args = repr.repr(frame.f_locals['__args__'])
            else:
                args = '()'
            call = tpl_call % (func, args)

        level = '%s %s\n' % (link, call)
        ret += level

        start = lineno - 1 - context//2
        lines = linecache.getlines(filename)
        start = max(start, 0)
        start = min(start, len(lines) - context)
        lines = lines[start : start + context]

        for i in range(len(lines)):
            line = lines[i]
            if start + 1 + i == lineno:
                ret += self.__format_line(tpl_line_em, filename, start + 1 + i, line, arrow = True)
            else:
                ret += self.__format_line(tpl_line, filename, start + 1 + i, line, arrow = False)

        return ret


    def __format_line(self, tpl_line, filename, lineno, line, arrow = False):
        bp_mark = ""
        bp_mark_color = ""

        bp = None
        if lineno in self.get_file_breaks(filename):
            bps = self.get_breaks(filename, lineno)
            bp = bps[-1]

        if bp:
            Colors = self.color_scheme_table.active_colors
            bp_mark = str(bp.number)
            bp_mark_color = Colors.breakpoint_enabled
            if not bp.enabled:
                bp_mark_color = Colors.breakpoint_disabled

        numbers_width = 7
        if arrow:
            # This is the line with the error
            pad = numbers_width - len(str(lineno)) - len(bp_mark)
            if pad >= 3:
                marker = '-'*(pad-3) + '-> '
            elif pad == 2:
                marker = '> '
            elif pad == 1:
                marker = '>'
            else:
                marker = ''
            num = '%s%s' % (marker, str(lineno))
            line = tpl_line % (bp_mark_color + bp_mark, num, line)
        else:
            num = '%*s' % (numbers_width - len(bp_mark), str(lineno))
            line = tpl_line % (bp_mark_color + bp_mark, num, line)

        return line


    def do_list(self, arg):
        self.lastcmd = 'list'
        last = None
        if arg:
            try:
                x = eval(arg, {}, {})
                if type(x) == type(()):
                    first, last = x
                    first = int(first)
                    last = int(last)
                    if last < first:
                        # Assume it's a count
                        last = first + last
                else:
                    first = max(1, int(x) - 5)
            except:
                print '*** Error in argument:', `arg`
                return
        elif self.lineno is None:
            first = max(1, self.curframe.f_lineno - 5)
        else:
            first = self.lineno + 1
        if last is None:
            last = first + 10
        filename = self.curframe.f_code.co_filename
        try:
            Colors = self.color_scheme_table.active_colors
            ColorsNormal = Colors.Normal
            tpl_line = '%%s%s%%s %s%%s' % (Colors.lineno, ColorsNormal)
            tpl_line_em = '%%s%s%%s %s%%s%s' % (Colors.linenoEm, Colors.line, ColorsNormal)
            src = []
            for lineno in range(first, last+1):
                line = linecache.getline(filename, lineno)
                if not line:
                    break

                if lineno == self.curframe.f_lineno:
                    line = self.__format_line(tpl_line_em, filename, lineno, line, arrow = True)
                else:
                    line = self.__format_line(tpl_line, filename, lineno, line, arrow = False)

                src.append(line)
                self.lineno = lineno

            print >>sys.stdout, ''.join(src)

        except KeyboardInterrupt:
            pass

    do_l = do_list
    
    def _runscript(self, filename):
        # The script has to run in __main__ namespace (or imports from
        # __main__ will break).
        #
        # So we clear up the __main__ and set several special variables
        # (this gets rid of pdb's globals and cleans old variables on restarts).
        import __main__
        __main__.__dict__.clear()
        __main__.__dict__.update({"__name__"    : "__main__",
                                  "__file__"    : filename,
                                  "__builtins__": __builtins__,
                                 })

        # When bdb sets tracing, a number of call and line events happens
        # BEFORE debugger even reaches user's code (and the exact sequence of
        # events depends on python version). So we take special measures to
        # avoid stopping before we reach the main script (see user_line and
        # user_call for details).
        self._wait_for_mainpyfile = 1
        self.mainpyfile = self.canonic(filename)
        self._user_requested_quit = 0
        statement = 'execfile( "%s")' % filename
        self.run(statement)


# Simplified interface
def run(statement, globals=None, locals=None):
    tbtools.defaultPDB.run(statement, globals, locals)

def runeval(expression, globals=None, locals=None):
    return tbtools.defaultPDB.runeval(expression, globals, locals)

def runctx(statement, globals, locals):
    # B/W compatibility
    run(statement, globals, locals)

def runcall(*args, **kwds):
    return tbtools.defaultPDB.runcall(*args, **kwds)

def set_trace():
    try:
        tbtools.defaultPDB.set_trace(sys._getframe().f_back)
    except bdb.BdbQuit:
        pass

# Post-Mortem interface

def post_mortem(t):
    p = tbtools.defaultPDB
    p.reset()
    p._private_frame_stack = [t.tb_frame]
    while t.tb_next is not None:
        t = t.tb_next
        p._private_frame_stack.append(t.tb_frame)
    p.interaction(t.tb_frame, t)

def pm():
    post_mortem(sys.last_traceback)


def main():
    if not sys.argv[1:]:
        print "usage: ipdb.py scriptfile [arg] ..."
        sys.exit(2)

    mainpyfile =  sys.argv[1]     # Get script filename
    if not os.path.exists(mainpyfile):
        print 'Error:', mainpyfile, 'does not exist'
        sys.exit(1)

    del sys.argv[0]         # Hide "pdb.py" from argument list

    # Replace pdb's dir with script's dir in front of module search path.
    sys.path[0] = os.path.dirname(mainpyfile)

    # Note on saving/restoring sys.argv: it's a good idea when sys.argv was
    # modified by the script being debugged. It's a bad idea when it was
    # changed by the user from the command line. The best approach would be to
    # have a "restart" command which would allow explicit specification of
    # command line arguments.
    pdb = tbtools.defaultPDB
    while 1:
        try:
            pdb._runscript(mainpyfile)
            if pdb._user_requested_quit:
                break
            print "The program finished and will be restarted"
        except Restart:
            # Restart is defined by pdb in Python 2.6
            print "Restarting", mainpyfile, "with arguments"
            print "\t" + " ".join(sys.argv[1:])
        except SystemExit:
            # In most cases SystemExit does not warrant a post-mortem session.
            print "The program exited via sys.exit(). Exit status: ",
            tbtools.ultraTB.print_exc()
            # print sys.exc_info()[1]
        except bdb.BdbQuit:
            # requested quit
            break
        except:
            etype, value, tb = sys.exc_info()
            tbtools.defaultTB(etype, value, tb)
            print "Uncaught exception. Entering post mortem debugging"
            print "Running 'cont' or 'step' will restart the program"
            post_mortem(tb)
            print "Post mortem debugger finished. The "+mainpyfile+" will be restarted"


# When invoked as main program, invoke the debugger on a script
if __name__=='__main__':
    main()
