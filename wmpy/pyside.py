from PySide import QtCore, QtDeclarative, QtGui

from . import _logging
_logger, _dbg, _info, _warn = _logging.get_logging_shortcuts(__name__)

class Shortcut(object):
    def __init__(self, module, prefix):
        self.module = module
        self.prefix = prefix

    def __getattr__(self, name):
        try:
            return getattr(self.module, self.prefix+name)
        except AttributeError:
            return getattr(self.module, name)

class Shortcuts(object):
    core = Shortcut(QtCore, 'Q')
    quick = Shortcut(QtDeclarative, 'QDeclarative')
    gui = Shortcut(QtGui, 'Q')
        
qt = Shortcuts()

class Property(object):
    """ Bundles a PySide property and its NOTIFY signal.

        Use like so:
        >>> class Example(HasProperties, qt.core.Object):
        ...     def get_val(self):
        ...         return self._val
        ...     def set_val(self, newv):
        ...         self._val = newv
        ...     def show(self):
        ...         print self.val
        ...     val, val_changed = Property(int, get_val, set_val)
        >>> obj = Example()
        >>> obj.val_changed.connect(obj.show)
        True
        >>> obj.val = 42
        42

    """

    def _fixup_single(self, typename, dct, qname):
        for key, val in dct.iteritems():
            if val is self:
                self.name = key
            elif val is self._signal:
                self.signal = key

        if self.name is None or self.signal is None:
            raise TypeError('must use x, x_changed = Property(...) idiom')

        _dbg("fixing up %s.%s", typename, self.name)
        dct[self.name] = self.qtproperty
        del self._signal

    def __iter__(self):
        return iter((self, self._signal))

    def __init__(self, type_, getter, setter=None):
        self.name = None
        self.signal = None
        self._signal = qt.core.Signal(lambda self: None)
        def wrap_getter(instance):
            try:
                return getter(instance)
            except Exception:
                _warn("failed to get %s", self.name, exc_info=True)
                return type_()
        if setter is None:
            self.qtproperty = qt.core.Property(type_,
                getter,
                notify=self._signal)
        else:
            def wrap_setter(instance, val):
                setter(instance, val)
                getattr(instance, self.signal).emit()
            self.qtproperty = qt.core.Property(type_,
                getter,
                wrap_setter,
                notify=self._signal)
        self._getter = getter
        self._setter = setter

class PropertyMeta(type(qt.core.QObject)):
    def __new__(mcls, name, bases, dct):
        props = {}
        qtprops = {}
        for key, val in dct.items():
            if isinstance(val, Property):
                val._fixup_single(name, dct, key)
         
        if 'HasProperties' in globals():
            bases = tuple(
                base for base in bases if base is not HasProperties)
        return super(PropertyMeta, mcls).__new__(mcls, name, bases, dct)

class HasProperties(qt.core.Object):
    __metaclass__ = PropertyMeta

class SimpleProperty(Property):

    """ Builds one of the above that reads and writes to a simple
        attribute on the object.

        This uses getattr and setattr so it will also work fine to
        delegate to a regular Python @property.
    """
    def __init__(self, type_, name):
        def getter(self):
            try:
                return getattr(self, name)
            except:
                _warn("getter for %s failed", name, exc_info=True)
                return type_()
        def setter(self, val):
            try:
                setattr(self, name, val)
            except:
                _warn("setter for %s failed", name, exc_info=True)
        Property.__init__(self, type_, getter, setter)

class ListBase(HasProperties, qt.core.AbstractListModel):
    def __init__(self, parent=None, *args, **kw):
        qt.core.AbstractListModel.__init__(self, parent, *args, **kw)
        self.setRoleNames({0: 'value'})
        self._reset()

    def _reset(self):
        self._items = []

    def _prep(self, val):
        return val

    def changed(self):
        # TODO: make this smarter
        self.beginResetModel.emit()
        self._reset()
        self.lengthChanged.emit()
        self.endResetModel.emit()

    @qt.core.Slot(result=int)
    def rowCount(self, parent=qt.core.ModelIndex()):
        try:
            return len(self._items)
        except Exception:
            self._warn("failed in rowCount", exc_info=True)
            return 0

    length, lengthChanged = Property(int, rowCount)

    @qt.core.Slot(int, result=qt.core.Object)
    def data(self, index, role=0):
        if isinstance(index, qt.core.ModelIndex):
            index = index.row()
        return self._prep(self._items[index])

