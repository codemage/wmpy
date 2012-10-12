import argparse
import inspect
import sys

from . import _logging
_logger, _dbg, _info, _warn = _logging.get_logging_shortcuts(__name__)

class ArgSpec(object):
    """ Wrapper around inspect.getargspec that adds some niceties.

        First off, the defaults attribute is a mapping from
        argument name to default value instead of a sequence of
        defaults for the final arguments, and is never None.

        Second, it has a `func` attribute set to the function object
        it was built from.

        Third, it provides make_call_args, to translate a dictionary
        of arguments into an (args, kw) pair usable to call the function.
        This differs from inspect.getcallargs in that it accepts no starting
        positional arguments and will correctly fill varargs from an
        appropriately-named keyword entry mapped to a sequence.  Note that
        this is fragile: a wrapper or substiture function that is semantically
        equivalent in every possible call may use a different *varargs
        name, changing the behavior of this method.  Raises KeyError
        for missing arguments.

        Fourth, it may be called with keyword arguments, and will use
        `self.make_call_args` to convert them and call `func`.  This is
        fragile for the same reason as `make_call_args` itself, but can
        be useful nonetheless.

        Fifth, it contains a 'positionals' attribute that is equal to
        `args` unless the `func` has a *varargs parameter, in which
        case the name of that parameter is appended.
    """
    def __init__(self, func):
        self.func = func
        self.args, self.varargs, self.keywords, defaults = \
            inspect.getargspec(func)
        self.positionals = self.args + \
            ([self.varargs] if self.varargs is not None else [])

        # build a mapping from argument names to their default values, if any:
        if defaults is None:
            self.defaults = {}
        else:
            defaulted_args = self.args[-len(defaults):]
            self.defaults = dict(list(zip(defaulted_args, defaults)))

    def make_call_args(self, arguments):
        args = []
        kw = arguments.copy()
        for arg in self.args:
            if arg in kw:
                args.append(kw.pop(arg))
            elif arg in self.defaults:
                args.append(self.defaults[arg])
            else:
                raise TypeError("missing argument in call to %s(): %s" %
                    (self.func.__name__, arg))
        if self.varargs is not None:
            args.extend(kw.pop(self.varargs))
        if self.keywords is None and len(kw) > 0:
            raise TypeError("unknown arguments %s in call to %s" % 
                (kw, self.func.__name__))
        return args, kw

    def __call__(self, **arguments):
        args, kw = self.make_call_args(arguments)
        _dbg("Calling %s(*%r, **%r)", self.func.__name__,
            args, kw)
        return self.func(*args, **kw)

class ParserGenerator(object):
    """ A configurable decorator that builds ArgumentParser instances
        from function signatures.  These parsers are stored as 'parser'
        attributes on the functions, but should primarily be used by calling
        'func.parse_and_call(argv, **extra_args)'; this is set up to use the
        generated parser to build appropriate arguments for a call to the
        function.

        By default, all parameters will be represented as positional arguments
        of the same name, will be required iff they have no defaults, and
        result in string values being passed.

        If the decorator is provided with keyword arguments, they should be
        set to dictionaries of keyword arguments for parser.add_argument
        calls.  By default, arguments specified this way are --long options;
        they may include a 'name' or 'names' keyword to provide other names.
        If a nargs keyword is present (even if None), a positional argument is
        made instead.  Argument settings defined this way override the
        automatic defaults for wrapped-function parameters of the same names;
        keys with no matching names are passed as keyword parameters.  (If a
        name is not an arg name, and the function does not accept a **kw-style
        argument, an error is raised from gen_parser.)
        
        Decorator keywords may also be set to any other value, in which case
        the generated flag will be a --long flag whose presence will result in
        the named parameter being set to that value; the parameter should have
        a default setting for when the flag is absent.
    """

    def __init__(self, ignored_args = (), **common_options):
        """ ignored_args should be a sequence of argument names; these are not
            added to the parser as arguments by default; they must be passed as
            keyword arguments to the built `parse_and_call`.
        
            common_options provides argparse overrides by name; any arg with
            a matching name in any generated parser will default to using
            those settings instead of just being a positional.
        """
        self.ignored_args = ignored_args
        self.common_options = self._fix_argparse_dicts(common_options)

    @staticmethod
    def build_parser(argspec, arguments):
        """ May be overridden to customize how the parser instance
            is build before adding arguments.

            Accepts an ArgSpec instance and an arguments dictionary
            as is provided when a ParserGenerator is used as a decorator.
        """
        fname = argspec.func.__name__
        if fname.startswith('do_'):
            fname = fname[3:]

        parser_args = arguments.pop('parser_args', {})
        parser_args.setdefault('prog', '%s %s' % (sys.argv[0], fname))
        if argspec.func.__doc__ is not None:
            parser_args.setdefault('description', argspec.func.__doc__)
        return argparse.ArgumentParser(**parser_args)

    @staticmethod
    def _fix_argparse_dicts(arguments):
        return {
            name: (info if isinstance(info, dict)
                   else dict(action='store_const', const=info))
            for name, info in arguments.items() }

    def __call__(self, ignore=None, **arguments):
        """ This actually implements the decorator. """
        func = None
        if inspect.isfunction(ignore):
            # left off the parens?
            func = ignore
            ignore = []
        elif ignore is None:
            ignore = []

        ignore += self.ignored_args
        if func is None:
            return lambda func: self._make_parser(func, ignore, arguments)
        else:
            return self._make_parser(func, ignore, arguments)

    def _add_arg(self, argspec, parser, flag, info):
        assert (
            # we can only pass in things in the arg list, unless
            # the function takes a **kw:
            flag in argspec.positionals
            or argspec.keywords is not None), \
            "%s not in args %s" % (flag, argspec.positionals)
        
        for k, v in self.common_options.get(flag, {}).items():
            info.setdefault(k, v)

        if flag in argspec.defaults:
            info.setdefault('default', argspec.defaults[flag])

        if 'nargs' in info:
            argnames = [flag]
        else:
            argnames = ['-%s' % char for char in info.pop('short', [])]
            argnames.append('--%s' % flag)
            info.setdefault('required',
                flag in argspec.args and flag not in argspec.defaults)

        _dbg("  add arg: %s %s", argnames, info)
        argspec.func.args[flag] = parser.add_argument(*argnames, **info)

    def _make_parser(self, func, ignore, arguments):
        _dbg("make action for %s, ignore=%r, arguments=%r",
            func.__name__, ignore, arguments)

        # canonicalize non-dict keywords from decorator into store_const:
        arguments = self._fix_argparse_dicts(arguments)

        argspec = ArgSpec(func)

        func.args = {}
        func.required_args = set()
        func.unparsed_args = set()
        for arg in argspec.positionals:
            if arg in ignore:
                if arg not in arguments:
                    func.unparsed_args.add(arg)
                if arg not in argspec.defaults:
                    func.required_args.add(arg)
                continue # don't default these to anything

            if arg in self.common_options:
                _dbg("%s: defaulting %s to common arg",
                    func.__name__, arg)
                arguments[arg] = self.common_options[arg]
            elif arg not in arguments:
                _dbg("%s: defaulting %s to positional",
                    func.__name__, arg)
                if arg == argspec.varargs:
                    nargs = '*'
                elif arg in argspec.defaults:
                    nargs = '?'
                else:
                    nargs = None
                arguments[arg] = {'nargs': nargs}
        
        # now that we have the arguments dict all filled in,
        # build a parser out of it
        parser = self.build_parser(argspec, arguments)

        # add positional arguments from the function signature in order first,
        # stripping them out of the arguments dict as we go
        for arg in argspec.positionals:
            if arg in arguments:
                self._add_arg(argspec, parser,
                    arg, arguments.pop(arg))

        # the rest ought to be **kw params, for which don't care about ordering
        for flag, info in arguments.items():
            self._add_arg(argspec, parser, flag, info)

        # we have a parser, build parse_and_call
        def parse_and_call(argv, **other_args):
            options = vars(parser.parse_args(argv))
            options.update(other_args)
            return argspec(**options)

        # okay, that's everything; set attach our fine work to the function
        # and return it.
        # (We don't wrap the function so that it is still possible to call it
        # with the original signature instead of an argv.)
        func.parser = parser
        func.parse_and_call = parse_and_call
        func.call_with_options = argspec
        return func

