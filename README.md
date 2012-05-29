wmpy
====

Walter Mundt's Python bits and pieces.

This contains various bits of Python code I have written on my own
time and find handy.

Contents:

- `nat_sort_key` can be used for `key=` in `sort` or `sorted`, and sorts strings with embedded numbers in a way that attempts to make sense.
- `io_pipe` is a `with` context manager to set up an `os.pipe` r/w pair wrapped in unbuffered `io`-module file objects, that is closed on exit from the block.
- `WatchedThread` is a Thread subclass that tries to make it easier to gracefully handle uncaught exceptions in thread targets, dying messily by default and offering easy ways to re-raise exceptions across the thread boundary.
- `ArgSpec` is a wrapper around `inspect.getargspec` that provides a defaults dict instead of a defaults list, and can invoke the inspected function from a dict containing all the arguments to pass (INCLUDING a sequence keyed by the name of the `*varargs`).  This is not always a great idea, but it's handy for:
- `ParserGenerator` instances are decorators that automatically build `argparse.ArgumentParser` instances based on a function's signature, and attach them to the function as `parser` attributes.  They also tack on a bunch of info about said arguments, and a `parse_and_call` method that takes an argv and calls the decorated function if the argv parses successfully.  One can pass keyword arguments to the decorator in order to customize the syntax, add help text, or do anything else an argparse `add_argument` can do.

Tests and examples are currently missing, since I'm using this stuff mostly in other code I haven't gotten into a publishable state yet.  Feel free to use it if it is useful, but YMMV.

wmpy is Copyright (c) 2012 Walter Mundt.
It is available under an MIT license; see the LICENSE file for details.
