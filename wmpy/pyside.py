from .PySide import QtCore, QtDeclarative, QtGui

from ._collection import WatchableList
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
        for key, val in dct.items():
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
        for key, val in list(dct.items()):
            if isinstance(val, Property):
                val._fixup_single(name, dct, key)
         
        if 'HasProperties' in globals():
            bases = tuple(
                base for base in bases if base is not HasProperties)
        return super(PropertyMeta, mcls).__new__(mcls, name, bases, dct)

class HasProperties(qt.core.Object, metaclass=PropertyMeta):
    pass

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

class ListModel(WatchableList, HasProperties, qt.core.AbstractListModel):
    def __init__(self, parent=None, *args, **kw):
        qt.core.AbstractListModel.__init__(self, parent, *args, **kw)
        WatchableList.__init__(self)
        self.setRoleNames({0: 'value'})
        self.add_listener_gen('update', self.update_gen)
        self.add_listener_gen('insert', self.insert_gen)
        self.add_listener_gen('del', self.delete_gen)

    def update_gen(self, _also_self, _eventname, idx, new_value):
        if isinstance(idx, slice):
            start, stop, step = idx.indices(len(self))
            if step != 1:
                raise ValueError("Can't update non-contiguous slices")

        else:
            start = idx
            stop = idx+1

        yield
        self.dataChanged.emit(
            self.index(start, 0),
            self.index(stop-1, 0))

    def insert_gen(self, _also_self, _eventname, idx, values):
        self.beginInsertRows(qt.core.ModelIndex(), idx, idx+len(values)-1)
        result_kw = yield
        self.endInsertRows()
        if 'exc_info' in result_kw:
            self.beginResetModel()
            self.endResetModel()
        self.lengthChanged.emit()

    def delete_gen(self, _also_self, _eventname, idx):
        if isinstance(idx, slice):
            start, stop, step = idx.indices(len(self))
            if step != 1:
                raise ValueError("Can't del non-contiguous slices")
        else:
            start = idx
            stop = idx+1

        self.beginRemoveRows(qt.core.ModelIndex(), start, stop-1)
        result_kw = yield
        self.endRemoveRows()
        if 'exc_info' in result_kw:
            self.reset()
        self.lengthChanged.emit()

    @qt.core.Slot(result=int)
    def rowCount(self, parent=qt.core.ModelIndex()):
        return len(self)

    length, lengthChanged = Property(int, rowCount)

    def _prep(self, val):
        return val

    def data(self, index, role=0):
        if role != 0 or index.column() != 0 or index.parent().isValid():
            return None
        index = index.row()
        try:
            return self._prep(self[index])
        except Exception:
            _warn("Exception in %s.data()", self, exc_info=True)
            return None

    @qt.core.Slot()
    def reset(self):
        self.beginResetModel()
        self.endResetModel()

    @qt.core.Slot(int, result="QVariant")
    def get(self, row):
        try:
            return self.data(self.index(row))
        except Exception:
            _warn("Exception in %s.get()", self, exc_info=True)
            return None

    @qt.core.Slot(int, "QVariant")
    def insert(self, row, item):
        if isinstance(item, list):
            self[row:row] = item
        else:
            self[row:row] = [item]

    @qt.core.Slot("QVariant")
    def append(self, item):
        super(ListModel, self).append(item)

    @qt.core.Slot(int)
    def remove(self, row):
        del self[row]

class ListBase(HasProperties, qt.core.AbstractListModel):
    # this is a hack designed to work on top of
    # _collections.ManyToManyCollection for imgview
    # when that is refactored to use the WatchableList-style interface we can
    # make this a simple mix of the MMList/MMSet and ListModel above
    def __init__(self, parent=None, *args, **kw):
        qt.core.AbstractListModel.__init__(self, parent, *args, **kw)
        self.setRoleNames({0: 'value'})
        self._reset()

    def _reset(self):
        self._items = []

    def _prep(self, val):
        return val

    def __getitem__(self, idx):
        return self._items[idx]

    def changed(self, *_args):
        # TODO: make this smarter
        self.beginResetModel()
        self._reset()
        self.lengthChanged.emit()
        self.endResetModel()

    @qt.core.Slot(result=int)
    def rowCount(self, parent=qt.core.ModelIndex()):
        try:
            return len(self._items)
        except Exception:
            self._warn("failed in rowCount", exc_info=True)
            return 0

    length, lengthChanged = Property(int, rowCount)

    @qt.core.Slot(int, result="QVariant")
    def get(self, row):
        try:
            return self._prep(self._items[row])
        except Exception:
            self._warn("failed in get()", exc_info=True)
            return None

    def data(self, index, role=0):
        return self.get(index.row())
