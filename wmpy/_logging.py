from __future__ import absolute_import

import inspect
import logging
import types
import sys

def _patched_findCaller(_logger):
    for frame in inspect.stack():
        if 'logging' not in frame[1]:
            return frame[1:4]
    return None
logging.Logger.findCaller = _patched_findCaller

def get_logging_shortcuts(name):
    """ Returns a logger, along with bound versions of its debug, warning,
        and error methods.
    """
    logger = logging.getLogger(name)
    return logger, logger.debug, logger.info, logger.warning

class _InstanceLoggerAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        instance_desc = self.extra.replace('%', '%%')

        return '%s: %s' % (instance_desc, msg), kwargs

class _InstanceLoggerDescriptor(object):
    """ Property descriptor providing both class and instance-level loggers.

        This is the magic behind InstanceLoggingMixin, below.
    """
    __slots__ = ('num_created')
    CLASS_LOGGER_KEY = '_class_logger'
    INSTANCE_LOGGER_KEY = '_instance_logger'

    def __init__(self):
        self.num_created = 0

    def _get_class_logger(self, cls):
        # check vars on classes so as not to catch superclasses' loggers:
        if self.CLASS_LOGGER_KEY in vars(cls):
            return vars(cls)[self.CLASS_LOGGER_KEY]
        
        module = sys.modules[cls.__module__]
        parent_logger = getattr(module, '_logger',
            logging.getLogger(cls.__module__))
        class_desc = getattr(cls, '_logging_desc', cls.__name__)
        if isinstance(class_desc, property):
            # instance descriptions set via property, have to default this:
            class_desc = cls.__name__

        cls_logger = parent_logger.getChild(class_desc)
        setattr(cls, self.CLASS_LOGGER_KEY, cls_logger)
        return cls_logger

    def _get_instance_logger(self, instance, cls):
        if hasattr(instance, self.INSTANCE_LOGGER_KEY):
            return getattr(instance, self.INSTANCE_LOGGER_KEY)

        parent_logger = self._get_class_logger(cls)
        class_desc = getattr(cls, '_logging_desc', None)
        instance_desc = getattr(cls, '_logging_desc', class_desc)
        if instance_desc is not class_desc:
            instance_desc = '<%s>' % instance_desc
        else:
            instance_desc = '@%x' % id(instance)
        instance_desc += '.%d' % (self.num_created,)
        self.num_created += 1
        
        instance_logger = _InstanceLoggerAdapter(parent_logger, instance_desc)
        setattr(instance, self.INSTANCE_LOGGER_KEY, instance_logger)
        return instance_logger

    def __get__(self, instance, owner):
        if instance is None:
            return self._get_class_logger(owner)
        else:
            return self._get_instance_logger(instance, owner)

class automethod(object):
    """ Decorator that returns a method which, if set on a class, will be
        called as either or a class or instance method depending on the
        type of access.
    """
    __slots__ = ('func',)
    def __init__(self, func):
        self.func = func
    
    def __get__(self, instance, owner):
        if instance is None:
            return types.MethodType(self.func, owner, type(owner))
        else:
            return types.MethodType(self.func, instance, owner)

class InstanceLoggingMixin(object):
    """ Makes a _logger property available that can be used to log in either
        a class or instance context, as well as _dbg, _warn, and _error
        shortcut methods with the came capability.

        Sub may set a '_logging_desc' attribute at either the class or instance
        level to control the name of their loggers.  Instance loggers are
        actually LoggerAdapters on top of their class loggers; this is so that
        the logging module doesn't try to remember the logger settings for
        every instance.  If the module in which a class is defined has a
        '_logger' set, it is the parent of class loggers; otherwise the parent
        is named after the module.

        If `_logging_desc` is a @property, the class name will be used for the
        class-level logger and the returned property values will be used for
        instance logger names.

        This class is not entirely thread-safe; classes or instances that may
        be used on multiple threads should try to ensure that at least one
        self._logger access happens at some well-defined "first time".
    """
    _logger = _InstanceLoggerDescriptor()

    # __slots__ = (_logger.INSTANCE_LOGGER_KEY)
    # ^ can't have slots on any base of a class also derived from many C
    # extension types

    @automethod
    def _dbg(self_or_cls, *arg, **kw):  # pylint: disable=E0213
        self_or_cls._logger.debug(*arg, **kw)

    @automethod
    def _info(self_or_cls, *arg, **kw):  # pylint: disable=E0213
        self_or_cls._logger.info(*arg, **kw)

    @automethod
    def _warn(self_or_cls, *arg, **kw):  # pylint: disable=E0213
        self_or_cls._logger.warning(*arg, **kw)

    @automethod
    def _error(self_or_cls, *arg, **kw):  # pylint: disable=E0213
        self_or_cls._logger.error(*arg, **kw)

class LogBufferMixin(object):
    """ Mixin for unittest.TestCase classes.
    
        Arranges to log to the current sys.stdout during test cases,
        which allows logging output to be picked up by the unittest
        framework output capturing mechanism if test output buffering
        is in effect.
    """
    def setUp(self):
        super(LogBufferMixin, self).setUp()
        handler = logging.StreamHandler(sys.stdout)
        logging.getLogger().addHandler(handler)
        self.addCleanup(logging.getLogger().removeHandler, handler)
