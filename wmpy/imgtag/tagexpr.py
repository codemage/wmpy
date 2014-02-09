import math
import operator
import random

from .. import nat_sort_key
from .. import _logging

_logger, _dbg, _info, _warn = _logging.get_logging_shortcuts(__name__)

class Expr(object):
    def __and__(self, other):
        return And(self, other)

    def __or__(self, other):
        return Or(self, other)

    def __neg__(self):
        return Not(self)

    def __invert__(self):
        return Not(self)

    def __add__(self, other):
        return Or(self, other)

    def __sub__(self, other):
        return And(self, Not(other))

    def _subset(self, op, operand):
        try:
            factor = op(1.0, operand)
        except TypeError:
            return NotImplemented
        return RandomSubset(self, factor)

    def __mul__(self, factor):
        return self._subset(operator.mul, factor)

    def __div__(self, divisor):
        return self._subset(operator.truediv, divisor)

    __truediv__ = __div__

    def __bool__(self):
        raise ValueError("use &, |, and ~ for logic in tag expressions")

    def preprocess(self, all_images):
        pass

    def filter(self, all_images):
        self.preprocess(all_images)
        for image in all_images:
            if self.evaluate(image):
                yield image

    def sort_images(self, tags, images):
        _dbg("Sorting %d images from %s by name", len(images), self)
        images.sort(key=lambda image: nat_sort_key(image.name))

class Tag(Expr):
    def __init__(self, name):
        self.name = name

    def evaluate(self, image):
        return self.name in set(image.tags)

    def sort_images(self, tags, images):
        _dbg("Sorting %d images by tag %s", len(images), self.name)
        indices = {}
        all_tagged_images = tags[self.name].image_list
        for i, image in enumerate(all_tagged_images):
            indices[id(image)] = i
        images.sort(key=lambda image: indices[id(image)])

    def __str__(self):
        return self.name

    def __repr__(self):
        return "Tag(%r)" % self.name

class BinaryExpr(Expr):
    def __init__(self, lhs, rhs):
        self.lhs = lhs
        self.rhs = rhs

    def evaluate(self, image):
        return self._evaluate(self.lhs.evaluate(image), self.rhs.evaluate(image), image)

    def preprocess(self, all_images):
        self.lhs.preprocess(all_images)
        self.rhs.preprocess(all_images)

    def __str__(self):
        return "(%s) %s (%s)" % (self.lhs, self.OP, self.rhs)

    def __repr__(self):
        return "%s(%r, %r)" % (type(self).__name__, self.lhs, self.rhs)


class UnaryExpr(Expr):
    def __init__(self, operand):
        self.operand = operand

    def preprocess(self, all_images):
        self.operand.preprocess(all_images)

    def evaluate(self, image):
        return self._evaluate(self.operand.evaluate(image), image)

    def __repr__(self):
        return "%s(%r)" % (type(self).__name__, self.operand)

class And(BinaryExpr):
    OP = '&'
    def _evaluate(self, lhs_result, rhs_result, _image):
        return lhs_result and rhs_result

    def sort_images(self, tags, images):
        self.lhs.sort_images(tags, images)

class RandomSubset(Expr):
    def __init__(self, expr, factor=1.0):
        self.expr = expr
        self.factor = float(factor)
        self._selected = None

    def __mul__(self, factor):
        try:
            return RandomSubset(self.expr, self.factor * factor)
        except TypeError:
            return NotImplemented

    def __div__(self, divisor):
        try:
            return RandomSubset(self.expr, self.factor / divisor)
        except TypeError:
            return NotImplemented

    __truediv__ = __div__

    def preprocess(self, all_images):
        expr_images = list(self.expr.filter(all_images))
        num_returned = math.ceil(len(expr_images)*min(self.factor, 1.0))
        sampled = random.sample(expr_images, num_returned)
        self._selected = set(id(image) for image in sampled)
        _info("Selected %s/%s images matching '%s'",
            num_returned, len(expr_images), self.expr)

    def evaluate(self, image):
        return id(image) in self._selected

    def __str__(self):
        return "(%s)*%s" % (self.expr, self.factor)

    def __repr__(self):
        return "RandomSubset(%r, %r)" % (self.expr, self.factor)

class Or(BinaryExpr):
    OP = '|'
    def _evaluate(self, lhs_result, rhs_result, _image):
        return bool(lhs_result or rhs_result)

class Not(UnaryExpr):
    def _evaluate(self, operand_result, _image):
        return not operand_result

    def __str__(self):
        return "~(%s)" % self.operand

class Untagged(Expr):
    def evaluate(self, image):
        return len(image.tags) == 0

    def __str__(self):
        return "untagged"

    def __repr__(self):
        return "Untagged()"

class Shuffled(UnaryExpr):
    def _evaluate(self, operand_result, _image):
        return operand_result

    def sort_images(self, tags, images):
        _dbg("Shuffling %d images from '%s'", len(images), self.operand)
        random.shuffle(images)

    def __str__(self):
        return "shuffle(%s)" % (self.operand,)

    def __repr__(self):
        return "Shuffled(%r)" % (self.operand,)

tagexpr_builtins = {'shuffle': Shuffled}

