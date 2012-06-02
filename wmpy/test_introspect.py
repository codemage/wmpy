""" unit tests for wmio._introspect """
import shlex
import sys
import unittest

from . import _introspect as i

class ArgSpecTests(unittest.TestCase):
    def assertSpecMatches(self, func,
        args, varargs, keywords, positionals,
        **defaults):

        spec = i.ArgSpec(func)
        self.assertEqual(args, spec.args)
        self.assertEqual(varargs, spec.varargs)
        self.assertEqual(keywords, spec.keywords)
        self.assertEqual(positionals, spec.positionals)
        self.assertEqual(defaults, spec.defaults)
        return spec

    def testSpec(self):
        va = ['a']; vab = ['a', 'b']
        self.assertSpecMatches(lambda: None, [], None, None, [])
        self.assertSpecMatches(lambda a: None, va, None, None, va)
        self.assertSpecMatches(lambda a=42: None, va, None, None, va, a=42)
        self.assertSpecMatches(lambda a, b: None, vab, None, None, vab)
        self.assertSpecMatches(lambda a, *b: None, va, 'b', None, vab)
        self.assertSpecMatches(lambda a, **b: None, va, None, 'b', va)
        self.assertSpecMatches(lambda *a, **b: None, [], 'a', 'b', va)

    def assertCallArgsMatch(self, func, expected_args, expected_kw,
                            **arguments):
        args, kw = i.ArgSpec(func).make_call_args(arguments)
        self.assertEqual(expected_args, args)
        self.assertEqual(expected_kw, kw)

    def testMakeCallArgs(self):
        with self.assertRaisesRegexp(TypeError, 'unknown'):
            i.ArgSpec(lambda: None).make_call_args({'a': 42})
        with self.assertRaisesRegexp(TypeError, 'missing'):
            i.ArgSpec(lambda a: None).make_call_args({})
        self.assertCallArgsMatch(lambda a: None, [42], {}, a=42)
        self.assertCallArgsMatch(lambda a=5: None, [5], {})
        self.assertCallArgsMatch(lambda a=42: None, [42], {}, a=42)
        self.assertCallArgsMatch(lambda *a: None, [5,42], {}, a=[5,42])
        self.assertCallArgsMatch(
            lambda a, *b, **c: None,
            [5, 14, 42], {'z': 'q'},
            a=5, b=[14,42], z='q')

import logging
logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)

class ParserGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.gen = i.ParserGenerator(['ignored'],
            common1=dict(action='append', type=float),
            common2=42,
            )
        self.expected_call = None
        def do_stuff(ignored, a, common1=None, common2=5, **b):
            """docstring"""
            self.assertEqual(self.expected_call,
                (ignored, a, common1, common2, b))
            self.expected_call = None
        self.argspec = i.ArgSpec(do_stuff)

    def testBuildParser(self):
        parser = self.gen.build_parser(self.argspec, {})
        self.assertEqual(parser.description, 'docstring')
        self.assertEqual(parser.prog, sys.argv[0] + ' stuff')

    def assertCallMatches(self, cmd, *expected_call):
        self.expected_call = expected_call
        args = shlex.split(cmd)
        self.argspec.func.parse_and_call(args, ignored=expected_call[0])
        self.assertEqual(self.expected_call, None)

    def testDecoratorDefault(self):
        func = self.gen(self.argspec.func)
        self.assertIs(func, self.argspec.func)
        self.assertTrue(hasattr(func, 'parser'))
        self.assertTrue(hasattr(func, 'parse_and_call'))
        self.assertTrue(hasattr(func, 'call_with_options'))
        
        self.assertCallMatches('first', 1, 'first', [], 5, {})
        self.assertCallMatches('a --common2', 2, 'a', [], 42, {})
        self.assertCallMatches('b --common1=1 --common1=2 --common1=3',
            3, 'b', [1,2,3], 5, {})

    # TODO: test passing the generator extra configuration

