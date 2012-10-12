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

    def __bool__(self):
        raise ValueError("use &, |, and ~ for logic in tag expressions")

class Tag(Expr):
    def __init__(self, name):
        self.name = name

    def evaluate(self, image, tags):
        return self.name in tags

    def sort_tag(self):
        return self.name

    def __str__(self):
        return self.name

    def __repr__(self):
        return "Tag(%r)" % self.name

class BinaryExpr(Expr):
    def __init__(self, lhs, rhs):
        self.lhs = lhs
        self.rhs = rhs

    def evaluate(self, image, tags):
        return self._evaluate(self.lhs.evaluate(image, tags), self.rhs.evaluate(image, tags), image, tags)

    def __str__(self):
        return "(%s) %s (%s)" % (self.lhs, self.OP, self.rhs)

    def __repr__(self):
        return "%s(%r, %r)" % (type(self).__name__, self.lhs, self.rhs)


class UnaryExpr(Expr):
    def __init__(self, operand):
        self.operand = operand

    def evaluate(self, image, tags):
        return self._evaluate(self.operand.evaluate(image, tags), image, tags)

class And(BinaryExpr):
    OP = '&'
    def _evaluate(self, lhs_result, rhs_result, _image, _tags):
        if isinstance(lhs_result, str) and rhs_result:
            return lhs_result
        return lhs_result and rhs_result

    def sort_tag(self):
        return self.lhs.sort_tag() or self.rhs.sort_tag()

class Or(BinaryExpr):
    OP = '|'
    def _evaluate(self, lhs_result, rhs_result, _image, _tags):
        return bool(lhs_result or rhs_result)

    def sort_tag(self):
        return None

class Not(UnaryExpr):
    def _evaluate(self, operand_result, _image, _tags):
        return not operand_result

    def sort_tag(self):
        return None

    def __str__(self):
        return "~(%s)" % self.operand

    def __repr__(self):
        return "Not(%r)" % self.operand

class Untagged(Expr):
    def evaluate(self, image, tags):
        return len(tags) == 0

    def sort_tag(self):
        return None

    def __str__(self):
        return "untagged"

    def __repr__(self):
        return "Untagged()"

