# -*- coding: utf-8 -*-
"""
ultraTB.py -- Spice up your tracebacks!

* ColorTB
I've always found it a bit hard to visually parse tracebacks in Python.  The
ColorTB class is a solution to that problem.  It colors the different parts of a
traceback in a manner similar to what you would expect from a syntax-highlighting
text editor.

Installation instructions for ColorTB:
    import sys, ultraTB
    sys.excepthook = ultraTB.ColorTB()

* VerboseTB
I've also included a port of Ka-Ping Yee's "cgitb.py" that produces all kinds
of useful info when a traceback occurs.  Ping originally had it spit out HTML
and intended it for CGI programmers, but why should they have all the fun?  I
altered it to spit out colored text to the terminal.  It's a bit overwhelming,
but kind of neat, and maybe useful for long-running programs that you believe
are bug-free.  If a crash *does* occur in that type of program you want details.
Give it a shot--you'll love it or you'll hate it.

Note:

  The Verbose mode prints the variables currently visible where the exception
  happened (shortening their strings if too long). This can potentially be
  very slow, if you happen to have a huge data structure whose string
  representation is complex to compute. Your computer may appear to freeze for
  a while with cpu usage at 100%. If this occurs, you can cancel the traceback
  with Ctrl-C (maybe hitting it more than once).

  If you encounter this kind of situation often, you may want to use the
  Verbose_novars mode instead of the regular Verbose, which avoids formatting
  variables (but otherwise includes the information and context given by
  Verbose).


Installation instructions for ColorTB:
    import sys, ultraTB
    sys.excepthook = ultraTB.VerboseTB()

Note:  Much of the code in this module was lifted verbatim from the standard
library module 'traceback.py' and Ka-Ping Yee's 'cgitb.py'.

* Color schemes
The colors are defined in the class TBTools through the use of the
ColorSchemeTable class. Currently the following exist:

  - NoColor: allows all of this module to be used in any terminal (the color
  escapes are just dummy blank strings).

  - Linux: is meant to look good in a terminal like the Linux console (black
  or very dark background).

  - LightBG: similar to Linux but swaps dark/light colors to be more readable
  in light background terminals.

You can implement other color schemes easily, the syntax is fairly
self-explanatory. Please send back new schemes you develop to the author for
possible inclusion in future releases.

$Id: ultraTB.py 1154 2006-02-11 23:20:05Z fperez $"""

#*****************************************************************************
#       Copyright (C) 2001 Nathaniel Gray <n8gray@caltech.edu>
#       Copyright (C) 2001-2004 Fernando Perez <fperez@colorado.edu>
#
#  Distributed under the terms of the BSD License.  The full license is in
#  the file COPYING, distributed as part of this software.
#*****************************************************************************
__license__ = "BSD"

# Required modules
import sys
import os
import time
import inspect
import keyword
import linecache
import pydoc
import string
import tokenize
import traceback
import types

import tbtools
from excolors import ExceptionColors

# Globals
# amount of space to put line numbers before verbose tracebacks
INDENT_SIZE = 8

#---------------------------------------------------------------------------
# Code begins

# Utility functions
def uniq_stable(elems):
    """uniq_stable(elems) -> list

    Return from an iterable, a list of all the unique elements in the input,
    but maintaining the order in which they first appear.

    A naive solution to this problem which just makes a dictionary with the
    elements as keys fails to respect the stability condition, since
    dictionaries are unsorted by nature.

    Note: All elements in the input must be valid dictionary keys for this
    routine to work, as it internally uses a dictionary for efficiency
    reasons."""

    unique = []
    unique_dict = {}
    for nn in elems:
        if nn not in unique_dict:
            unique.append(nn)
            unique_dict[nn] = None
    return unique

def _fixed_getinnerframes(tb, context=1, tb_offset=0):
    import linecache
    LNUM_POS, LINES_POS, INDEX_POS =  (2, 4, 5)

    records  = inspect.getinnerframes(tb, context)

    # If the error is at the console, don't build any context, since it would
    # otherwise produce 5 blank lines printed out (there is no file at the
    # console)
    rec_check = records[tb_offset:]
    try:
        rname = rec_check[0][1]
        if rname == '<ipython console>' or rname.endswith('<string>'):
            return rec_check
    except IndexError:
        pass

    aux = traceback.extract_tb(tb)
    assert len(records) == len(aux)
    for i, (file, lnum, _, _) in zip(range(len(records)), aux):
        maybeStart = lnum-1 - context//2
        start =  max(maybeStart, 0)
        end   = start + context
        lines = linecache.getlines(file)[start:end]
        # pad with empty lines if necessary
        if maybeStart < 0:
            lines = (['\n'] * -maybeStart) + lines
        if len(lines) < context:
            lines += ['\n'] * (context - len(lines))
        buf = list(records[i])
        buf[LNUM_POS] = lnum
        buf[INDEX_POS] = lnum - 1 - start
        buf[LINES_POS] = lines
        records[i] = tuple(buf)
    return records[tb_offset:]

# Helper function -- largely belongs to VerboseTB, but we need the same
# functionality to produce a pseudo verbose TB for SyntaxErrors, so that they
# can be recognized properly by ipython.el's py-traceback-line-re
# (SyntaxErrors have to be treated specially because they have no traceback)
def _formatTracebackLines(lnum, index, lines, Colors, lvals=None):
    # import pdb
    # pdb.set_trace()
    numbers_width = INDENT_SIZE - 1
    res = []
    i = lnum - index
    for line in lines:
        if i == lnum:
            # This is the line with the error
            pad = numbers_width - len(str(i))
            if pad >= 3:
                marker = '-'*(pad-3) + '-> '
            elif pad == 2:
                marker = '> '
            elif pad == 1:
                marker = '>'
            else:
                marker = ''
            num = marker + str(i)
            line = '%s%s%s %s%s' %(Colors.linenoEm, num,
                                   Colors.line, line, Colors.Normal)
        else:
            num = '%*s' % (numbers_width, i)
            line = '%s%s%s %s' %(Colors.lineno, num,
                                 Colors.Normal, line)

        res.append(line)
        if lvals and i == lnum:
            res.append(lvals + '\n')
        i = i + 1
    return res

#---------------------------------------------------------------------------
# Module classes
class TBTools(object):
    """Basic tools used by all traceback printer classes."""

    def __init__(self, color_scheme='LightBG'):
        # Create color table
        self.color_scheme_table = ExceptionColors

        if hasattr(sys.stdout, "isatty") and not sys.stdout.isatty():
            self.set_colors('NoColor')
        else:
            self.set_colors(color_scheme)
        self.old_scheme = color_scheme  # save initial value for toggles

        # NEVER change the order of this list. Put new modes at the end:
        self.valid_modes = ['Plain', 'Context', 'Verbose']
        self.verbose_modes = self.valid_modes[1:3]


    def set_colors(self, *args, **kw):
        """Shorthand access to the color table scheme selector method."""

        self.color_scheme_table.set_active_scheme(*args, **kw)
        # for convenience, set Colors to the active scheme
        self.Colors = self.color_scheme_table.active_colors

    def color_toggle(self):
        """Toggle between the currently active color scheme and NoColor."""

        if self.color_scheme_table.active_scheme_name == 'NoColor':
            self.color_scheme_table.set_active_scheme(self.old_scheme)
            self.Colors = self.color_scheme_table.active_colors
        else:
            self.old_scheme = self.color_scheme_table.active_scheme_name
            self.color_scheme_table.set_active_scheme('NoColor')
            self.Colors = self.color_scheme_table.active_colors

#---------------------------------------------------------------------------
class ListTB(TBTools):
    """Print traceback information from a traceback list, with optional color.

    Calling: requires 3 arguments:
      (etype, evalue, elist)
    as would be obtained by:
      etype, evalue, tb = sys.exc_info()
      if tb:
        elist = traceback.extract_tb(tb)
      else:
        elist = None

    It can thus be used by programs which need to process the traceback before
    printing (such as console replacements based on the code module from the
    standard library).
    """

    def __init__(self, color_scheme='NoColor'):
        TBTools.__init__(self, color_scheme=color_scheme)

    def __call__(self, etype, value, elist):
        print >>sys.stderr, self.text(etype, value, elist)

    def text(self, etype, value, elist, context=5):
        """Return a color formatted string with the traceback info."""

        Colors = self.Colors
        out_string = []
        if elist:
            out_string.append('Traceback %s(most recent call last)%s:' % \
                                (Colors.normalEm, Colors.Normal) + '\n')
            out_string.extend(self._format_list(elist))
        else:
            out_string.append('%s%s%s\n' % (Colors.topline, '-'*60, Colors.Normal))
        lines = self._format_exception_only(etype, value)
        for line in lines[:-1]:
            out_string.append(" "+line)
        out_string.append(lines[-1])
        return ''.join(out_string)

    def _format_list(self, extracted_list):
        """Format a list of traceback entry tuples for printing.

        Given a list of tuples as returned by extract_tb() or
        extract_stack(), return a list of strings ready for printing.
        Each string in the resulting list corresponds to the item with the
        same index in the argument list.  Each string ends in a newline;
        the strings may contain internal newlines as well, for those items
        whose source text line is not None.

        Lifted almost verbatim from traceback.py
        """

        Colors = self.Colors
        list = []
        for filename, lineno, name, line in extracted_list[:-1]:
            item = '  File %s"%s"%s, line %s%d%s, in %s%s%s\n' % \
                    (Colors.filename, filename, Colors.Normal,
                     Colors.lineno, lineno, Colors.Normal,
                     Colors.name, name, Colors.Normal)
            if line:
                item = item + '    %s\n' % line.strip()
            list.append(item)
        # Emphasize the last entry
        filename, lineno, name, line = extracted_list[-1]
        item = '%s  File %s"%s"%s, line %s%d%s, in %s%s%s%s\n' % \
                (Colors.normalEm,
                 Colors.filenameEm, filename, Colors.normalEm,
                 Colors.linenoEm, lineno, Colors.normalEm,
                 Colors.nameEm, name, Colors.normalEm,
                 Colors.Normal)
        if line:
            item = item + '%s    %s%s\n' % (Colors.line, line.strip(),
                                            Colors.Normal)
        list.append(item)
        return list

    def _format_exception_only(self, etype, value):
        """Format the exception part of a traceback.

        The arguments are the exception type and value such as given by
        sys.exc_info()[:2]. The return value is a list of strings, each ending
        in a newline.  Normally, the list contains a single string; however,
        for SyntaxError exceptions, it contains several lines that (when
        printed) display detailed information about where the syntax error
        occurred.  The message indicating which exception occurred is the
        always last string in the list.

        Also lifted nearly verbatim from traceback.py
        """

        Colors = self.Colors
        list = []
        if not issubclass(etype, str):
            stype = Colors.excName + etype.__name__ + Colors.Normal
        else:
            stype = etype  # String exceptions don't get special coloring
        if value is None:
            list.append( str(stype) + '\n')
        else:
            if etype is SyntaxError:
                try:
                    msg, (filename, lineno, offset, line) = value
                except:
                    pass
                else:
                    #print 'filename is', filename  # dbg
                    if not filename: filename = "<string>"
                    list.append('%s  File %s"%s"%s, line %s%d%s\n' % \
                            (Colors.normalEm,
                             Colors.filenameEm, filename, Colors.normalEm,
                             Colors.linenoEm, lineno, Colors.Normal  ))
                    if line is not None:
                        i = 0
                        while i < len(line) and line[i].isspace():
                            i = i+1
                        list.append('%s    %s%s\n' % (Colors.line,
                                                      line.strip(),
                                                      Colors.Normal))
                        if offset is not None:
                            s = '    '
                            for c in line[i:offset-1]:
                                if c.isspace():
                                    s = s + c
                                else:
                                    s = s + ' '
                            list.append('%s%s^%s\n' % (Colors.caret, s,
                                                       Colors.Normal) )
                        value = msg
            s = self._some_str(value)
            if s:
                list.append('%s%s:%s %s' % (str(stype), Colors.excName,
                                              Colors.Normal, s))
            else:
                list.append('%s' % str(stype))
        return list

    def _some_str(self, value):
        # Lifted from traceback.py
        try:
            return str(value)
        except:
            return '<unprintable %s object>' % type(value).__name__

#----------------------------------------------------------------------------
class VerboseTB(TBTools):
    """A port of Ka-Ping Yee's cgitb.py module that outputs color text instead
    of HTML.  Requires inspect and pydoc.  Crazy, man.

    Modified version which optionally strips the topmost entries from the
    traceback, to be used with alternate interpreters (because their own code
    would appear in the traceback)."""

    def __init__(self, color_scheme='Linux', tb_offset=0, long_header=0,
                 include_vars=1):
        """Specify traceback offset, headers and color scheme.

        Define how many frames to drop from the tracebacks. Calling it with
        tb_offset=1 allows use of this handler in interpreters which will have
        their own code at the top of the traceback (VerboseTB will first
        remove that frame before printing the traceback info)."""
        TBTools.__init__(self, color_scheme=color_scheme)
        self.tb_offset = tb_offset
        self.long_header = long_header
        self.include_vars = include_vars

    def text(self, etype, evalue, tb, context=5):
        """Return a nice text document describing the traceback."""

        # a str instance has once been passed as etype ...
        if isinstance(etype, (type, types.ClassType)):
            etype = etype.__name__

        # some locals
        Colors        = self.Colors   # just a shorthand + quicker name lookup
        ColorsNormal  = Colors.Normal  # used a lot
        indent        = ' '*INDENT_SIZE
        exc           = '%s%s%s' % (Colors.excName, str(etype), ColorsNormal)
        em_normal     = '%s\n%s%s' % (Colors.valEm, indent, ColorsNormal)
        undefined     = '%sundefined%s' % (Colors.em, ColorsNormal)

        # some internal-use functions
        def text_repr(value):
            """Hopefully pretty robust repr equivalent."""
            # this is pretty horrible but should always return *something*
            try:
                return pydoc.text.repr(value)
            except KeyboardInterrupt:
                raise
            except:
                try:
                    return repr(value)
                except KeyboardInterrupt:
                    raise
                except:
                    try:
                        # all still in an except block so we catch
                        # getattr raising
                        name = getattr(value, '__name__', None)
                        if name:
                            # ick, recursion
                            return text_repr(name)
                        klass = getattr(value, '__class__', None)
                        if klass:
                            return '%s instance' % text_repr(klass)
                    except KeyboardInterrupt:
                        raise
                    except:
                        return 'UNRECOVERABLE REPR FAILURE'
        def eqrepr(value, repr=text_repr): return '=%s' % repr(value)
        def nullrepr(value, repr=text_repr): return ''

        # meat of the code begins

        if self.long_header:
            # Header with the exception type, python version, and date
            pyver = 'Python ' + string.split(sys.version)[0] + ': ' + sys.executable
            date = time.ctime(time.time())

            head = '%s%s%s\n%s%s%s\n%s' % (Colors.topline, '-'*75, ColorsNormal,
                                           exc, ' '*(75-len(str(etype))-len(pyver)),
                                           pyver, string.rjust(date, 75) )
            head += "\nA problem occured executing Python code.  Here is the sequence of function"\
                    "\ncalls leading up to the error, with the most recent (innermost) call last."
        else:
            # Simplified header
            head = '%s%s%s\n%s%s' % (Colors.topline, '-'*75, ColorsNormal, exc,
                                     string.rjust('Traceback (most recent call last)',
                                                  75 - len(str(etype)) ) )
        frames = []
        # Flush cache before calling inspect.  This helps alleviate some of the
        # problems with python 2.3's inspect.py.
        linecache.checkcache()
        # Drop topmost frames if requested
        try:
            # Try the default getinnerframes and Alex's: Alex's fixes some
            # problems, but it generates empty tracebacks for console errors
            # (5 blanks lines) where none should be returned.
            #records = inspect.getinnerframes(tb, context)[self.tb_offset:]
            #print 'python records:', records # dbg
            records = _fixed_getinnerframes(tb, context, self.tb_offset)
            #print 'alex   records:', records # dbg
        except:

            # FIXME: I've been getting many crash reports from python 2.3
            # users, traceable to inspect.py.  If I can find a small test-case
            # to reproduce this, I should either write a better workaround or
            # file a bug report against inspect (if that's the real problem).
            # So far, I haven't been able to find an isolated example to
            # reproduce the problem.
            traceback.print_exc(file=sys.stderr)
            return ''

        # build some color string templates outside these nested loops
        tpl_link       = '%s%%s%s' % (Colors.filenameEm, ColorsNormal)
        tpl_call       = 'in %s%%s%s%%s%s' % (Colors.vName, Colors.valEm,
                                              ColorsNormal)
        tpl_call_fail  = 'in %s%%s%s(***failed resolving arguments***)%s' % \
                         (Colors.vName, Colors.valEm, ColorsNormal)
        tpl_local_var  = '%s%%s%s' % (Colors.vName, ColorsNormal)
        tpl_global_var = '%sglobal%s %s%%s%s' % (Colors.em, ColorsNormal,
                                                 Colors.vName, ColorsNormal)
        tpl_name_val   = '%%s %s= %%s%s' % (Colors.valEm, ColorsNormal)
        tpl_line       = '%s%%s%s %%s' % (Colors.lineno, ColorsNormal)
        tpl_line_em    = '%s%%s%s %%s%s' % (Colors.linenoEm, Colors.line,
                                            ColorsNormal)

        # now, loop over all records printing context and info
        abspath = os.path.abspath
        for frame, file, lnum, func, lines, index in records:
            #print '*** record:', file, lnum, func, lines, index  # dbg
            try:
                file = file and abspath(file) or '?'
            except OSError:
                # if file is '<console>' or something not in the filesystem,
                # the abspath call will throw an OSError.  Just ignore it and
                # keep the original file string.
                pass
            link = tpl_link % file
            try:
                args, varargs, varkw, locals = inspect.getargvalues(frame)
            except:
                # This can happen due to a bug in python2.3.  We should be
                # able to remove this try/except when 2.4 becomes a
                # requirement.  Bug details at http://python.org/sf/1005466
                traceback.print_exc(file=sys.stderr)

            if func == '?':
                call = ''
            else:
                # Decide whether to include variable details or not
                var_repr = self.include_vars and eqrepr or nullrepr
                try:
                    call = tpl_call % (func, inspect.formatargvalues(args,
                                                varargs, varkw,
                                                locals, formatvalue=var_repr))
                except KeyError:
                    # Very odd crash from inspect.formatargvalues().  The
                    # scenario under which it appeared was a call to
                    # view(array, scale) in NumTut.view.view(), where scale had
                    # been defined as a scalar (it should be a tuple). Somehow
                    # inspect messes up resolving the argument list of view()
                    # and barfs out. At some point I should dig into this one
                    # and file a bug report about it.
                    traceback.print_exc(file=sys.stderr)
                    call = tpl_call_fail % func

            # Initialize a list of names on the current line, which the
            # tokenizer below will populate.
            names = []

            def tokeneater(token_type, token, start, end, line):
                """Stateful tokeneater which builds dotted names.

                The list of names it appends to (from the enclosing scope) can
                contain repeated composite names.  This is unavoidable, since
                there is no way to disambguate partial dotted structures until
                the full list is known.  The caller is responsible for pruning
                the final list of duplicates before using it."""

                # build composite names
                if token == '.':
                    try:
                        names[-1] += '.'
                        # store state so the next token is added for x.y.z names
                        tokeneater.name_cont = True
                        return
                    except IndexError:
                        pass
                if token_type == tokenize.NAME and token not in keyword.kwlist:
                    if tokeneater.name_cont:
                        # Dotted names
                        names[-1] += token
                        tokeneater.name_cont = False
                    else:
                        # Regular new names.  We append everything, the caller
                        # will be responsible for pruning the list later.  It's
                        # very tricky to try to prune as we go, b/c composite
                        # names can fool us.  The pruning at the end is easy
                        # to do (or the caller can print a list with repeated
                        # names if so desired.
                        names.append(token)
                elif token_type == tokenize.NEWLINE:
                    raise IndexError
            # we need to store a bit of state in the tokenizer to build
            # dotted names
            tokeneater.name_cont = False

            def linereader(file=file, lnum=[lnum], getline=linecache.getline):
                line = getline(file, lnum[0])
                lnum[0] += 1
                return line

            # Build the list of names on this line of code where the exception
            # occurred.
            try:
                # This builds the names list in-place by capturing it from the
                # enclosing scope.
                tokenize.tokenize(linereader, tokeneater)
            except IndexError:
                # signals exit of tokenizer
                pass
            except tokenize.TokenError, msg:
                _m = ("An unexpected error occurred while tokenizing input\n"
                      "The following traceback may be corrupted or invalid\n"
                      "The error message is: %s\n" % msg)
                print >>sys.stderr, _m

            # prune names list of duplicates, but keep the right order
            unique_names = uniq_stable(names)

            # Start loop over vars
            lvals = []
            if self.include_vars:
                for name_full in unique_names:
                    name_base = name_full.split('.', 1)[0]
                    if name_base in frame.f_code.co_varnames:
                        if locals.has_key(name_base):
                            try:
                                value = repr(eval(name_full, locals))
                            except:
                                value = undefined
                        else:
                            value = undefined
                        name = tpl_local_var % name_full
                    else:
                        if frame.f_globals.has_key(name_base):
                            try:
                                value = repr(eval(name_full, frame.f_globals))
                            except:
                                value = undefined
                        else:
                            value = undefined
                        name = tpl_global_var % name_full
                    lvals.append(tpl_name_val % (name, value))
            if lvals:
                lvals = '%s%s' % (indent, em_normal.join(lvals))
            else:
                lvals = ''

            level = '%s %s\n' % (link, call)

            if index is None:
                frames.append(level)
            else:
                frames.append('%s%s' % (level, ''.join(
                    _formatTracebackLines(lnum, index, lines, self.Colors, lvals))))

        # Get (safely) a string form of the exception info
        try:
            etype_str, evalue_str = map(str, (etype, evalue))
        except:
            # User exception is improperly defined.
            etype, evalue = str, sys.exc_info()[:2]
            etype_str, evalue_str = map(str, (etype, evalue))
        # ... and format it
        exception = ['%s%s%s: %s' % (Colors.excName, etype_str,
                                     ColorsNormal, evalue_str)]
        if type(evalue) is types.InstanceType:
            try:
                names = [w for w in dir(evalue) if isinstance(w, basestring)]
            except:
                # Every now and then, an object with funny inernals blows up
                # when dir() is called on it.  We do the best we can to report
                # the problem and continue
                _m = '%sException reporting error (object with broken dir())%s:'
                exception.append(_m % (Colors.excName, ColorsNormal))
                etype_str, evalue_str = map(str, sys.exc_info()[:2])
                exception.append('%s%s%s: %s' % (Colors.excName, etype_str,
                                     ColorsNormal, evalue_str))
                names = []
            for name in names:
                value = text_repr(getattr(evalue, name))
                exception.append('\n%s%s = %s' % (indent, name, value))
        # return all our info assembled as a single string
        return '%s\n\n%s\n%s' % (head, '\n'.join(frames), ''.join(exception[0]) )

    def handler(self, info=None):
        (etype, evalue, tb) = info or sys.exc_info()
        self.tb = tb
        print >>sys.stderr, self.text(etype, evalue, tb)

    # Changed so an instance can just be called as VerboseTB_inst() and print
    # out the right info on its own.
    def __call__(self, etype=None, evalue=None, tb=None):
        """This hook can replace sys.excepthook (for Python 2.1 or higher)."""
        if tb is None:
            self.handler()
        else:
            self.handler((etype, evalue, tb))

#----------------------------------------------------------------------------
class FormattedTB(VerboseTB, ListTB):
    """Subclass ListTB but allow calling with a traceback.

    It can thus be used as a sys.excepthook for Python > 2.1.

    Also adds 'Context' and 'Verbose' modes, not available in ListTB.

    Allows a tb_offset to be specified. This is useful for situations where
    one needs to remove a number of topmost frames from the traceback (such as
    occurs with python programs that themselves execute other python code,
    like Python shells).  """

    def __init__(self, mode='Plain', color_scheme='Linux',
                 tb_offset=0, long_header=0, include_vars=0):

        VerboseTB.__init__(self, color_scheme, tb_offset, long_header,
                           include_vars=include_vars)
        self.set_mode(mode)

    def _extract_tb(self, tb):
        if tb:
            return traceback.extract_tb(tb)
        else:
            return None

    def text(self, etype, value, tb, context=5, mode=None):
        """Return formatted traceback.

        If the optional mode parameter is given, it overrides the current
        mode."""

        if mode is None:
            mode = self.mode
        if mode in self.verbose_modes and tb and tb.tb_next:
            # verbose modes need a full traceback
            return VerboseTB.text(self, etype, value, tb, context=5)
        else:
            # We must check the source cache because otherwise we can print
            # out-of-date source code.
            linecache.checkcache()
            # Now we can extract and format the exception
            elist = self._extract_tb(tb)
            if len(elist) > self.tb_offset:
                del elist[:self.tb_offset]
            return ListTB.text(self, etype, value, elist)

    def set_mode(self, mode=None):
        """Switch to the desired mode.

        If mode is not specified, cycles through the available modes."""

        if not mode:
            new_idx = ( self.valid_modes.index(self.mode) + 1 ) % \
                      len(self.valid_modes)
            self.mode = self.valid_modes[new_idx]
        elif mode not in self.valid_modes:
            raise ValueError, 'Unrecognized mode in FormattedTB: <'+mode+'>\n'\
                  'Valid modes: '+str(self.valid_modes)
        else:
            self.mode = mode
        # include variable details only in 'Verbose' mode
        self.include_vars = (self.mode == self.valid_modes[2])

    # some convenient shorcuts
    def plain(self):
        self.set_mode(self.valid_modes[0])

    def context(self):
        self.set_mode(self.valid_modes[1])

    def verbose(self):
        self.set_mode(self.valid_modes[2])


class SyntaxTB(ListTB):
    """Extension which holds some state: the last exception value"""

    def __init__(self, mode='Plain', color_scheme='NoColor'):
        ListTB.__init__(self, color_scheme=color_scheme)
        self.last_syntax_error = None
        self.mode = mode

    def __call__(self, etype, value, elist):
        self.last_syntax_error = value
        ListTB.__call__(self, etype, value, elist)

    def _extract_tb(self, tb):
        if tb:
            return traceback.extract_tb(tb)
        else:
            return None

    def text(self, etype, value, tb, context=5, mode=None):
        if not mode:
            mode = self.mode

        # We must check the source cache because otherwise we can print
        # out-of-date source code.
        linecache.checkcache()
        if mode in self.verbose_modes:
            Colors = self.Colors
            ColorsNormal = Colors.Normal
            # Simplified header
            exc = '%s%s%s' % (Colors.excName, etype.__name__, ColorsNormal)
            tpl_link = '%s%%s%s' % (Colors.filenameEm, ColorsNormal)
            head = '%s%s%s\n%s%s' % (Colors.topline, '-'*75, ColorsNormal, exc,
                                     string.rjust('Source of error (context)',
                                                  75 - len(str(etype))))

            filename = value.filename
            lineno = value.lineno
            
            # SyntaxError in non-python sources
            # bail out
            if lineno is None:
                elist = self._extract_tb(tb)
                return ListTB.text(self, etype, value, elist)

            context = context/2

            lines = linecache.getlines(value.filename)
            lines = lines[(lineno-1)-context:(lineno-1)+context]

            while len(lines) <> context*2 + 1:
                lines.append("\n")

            index = context

            try:
                filename = filename and os.path.abspath(filename) or '?'
            except OSError:
                # if file is '<console>' or something not in the filesystem,
                # the abspath call will throw an OSError.  Just ignore it and
                # keep the original file string.
                pass
            link = tpl_link % filename

            sourcelines = [link + "\n"]
            sourcelines += _formatTracebackLines(lineno, index, lines, Colors)

            etype_str, evalue_str = "SyntaxError", value.msg
            exception = '%s%s%s: %s' % (Colors.excName, etype_str,
                                        ColorsNormal, evalue_str)

            return '%s\n\n%s\n%s' % (head, ''.join(sourcelines), exception)
        else:
            # Now we can extract and format the exception
            elist = self._extract_tb(tb)
            return ListTB.text(self, etype, value, elist)

    def clear_err_state(self):
        """Return the current error state and clear it"""
        e = self.last_syntax_error
        self.last_syntax_error = None
        return e

#----------------------------------------------------------------------------
class AutoFormattedTB(SyntaxTB, FormattedTB):
    """A traceback printer which can be called on the fly.

    It will find out about exceptions by itself.

    A brief example:

    AutoTB = AutoFormattedTB(mode = 'Verbose', color_scheme='Linux')
    try:
      ...
    except:
      AutoTB()  # or AutoTB(out=logfile) where logfile is an open file object
    """
    def __init__(self, mode='Plain', color_scheme='Linux',
                 tb_offset=0, long_header=0, include_vars=0):

        SyntaxTB.__init__(self, mode, color_scheme)
        FormattedTB.__init__(self, mode, color_scheme,
                             tb_offset, long_header, include_vars)

    def __call__(self, etype=None, evalue=None, tb=None,
                 out=None, tb_offset=None):
        """Print out a formatted exception traceback.

        Optional arguments:
          - out: an open file-like object to direct output to.

          - tb_offset: the number of frames to skip over in the stack, on a
          per-call basis (this overrides temporarily the instance's tb_offset
          given at initialization time.  """

        # set proper handler
        if etype is SyntaxError:
            handler = SyntaxTB
        else:
            handler = FormattedTB

        if out is None:
            out = sys.stderr
        if tb_offset is not None:
            tb_offset, self.tb_offset = self.tb_offset, tb_offset
            print >>out, handler.text(self, etype, evalue, tb)
            self.tb_offset = tb_offset
        else:
            print >>out, handler.text(self, etype, evalue, tb)

    def text(self, etype=None, value=None, tb=None, context=5, mode=None):
        if etype is None:
            etype, value, tb = sys.exc_info()

        if etype is SyntaxError:
            handler = SyntaxTB
        else:
            handler = FormattedTB

        self.tb = tb
        return handler.text(self, etype, value, tb, context=5, mode=mode)

#---------------------------------------------------------------------------
# A simple class to preserve Nathan's original functionality.
class ColorTB(FormattedTB):
    """Shorthand to initialize a FormattedTB in Linux colors mode."""
    def __init__(self, color_scheme='Linux'):
        FormattedTB.__init__(self, color_scheme=color_scheme)


def print_exc(limit=None, file=None):
    if file is None:
        file = sys.stderr
    try:
        etype, value, tb = sys.exc_info()
        tbtools.defaultTB(etype, value, tb, out=file)
    finally:
        etype = value = tb = None

#----------------------------------------------------------------------------
# module testing (minimal)
if __name__ == "__main__":
    def spam(c, (d, e)):
        x = c + d
        y = c * d
        foo(x, y)

    def foo(a, b, bar=1):
        eggs(a, b + bar)

    def eggs(f, g, z=globals()):
        h = f + g
        i = f - g
        return h / i

    print ''
    print '*** Before ***'
    try:
        print spam(1, (2, 3))
    except:
        traceback.print_exc()
    print ''

    handler = ColorTB()
    print '*** ColorTB ***'
    try:
        print spam(1, (2, 3))
    except:
        apply(handler, sys.exc_info() )
    print ''

    handler = VerboseTB()
    print '*** VerboseTB ***'
    try:
        print spam(1, (2, 3))
    except:
        apply(handler, sys.exc_info() )
    print ''
