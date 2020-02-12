from sympy import (Integer, Rational, Float, Function, Symbol,
    Add, Mul, Pow, Abs, S, N, sign, srepr, simplify, sympify, 
    var, sin, cos, exp, log, symbols, preorder_traversal)
from SIMDExprTree import ExprTree
import re, sys

# For debugging purposes, Part 1:
# Basic arithmetic operations
def ConstSIMD_check(a):
    return Float(a, 34)
def AbsSIMD_check(a):
    return Abs(a)
def nrpyAbsSIMD_check(a):
    return Abs(a)
def AddSIMD_check(a, b):
    return a + b
def SubSIMD_check(a, b):
    return a - b
def MulSIMD_check(a, b):
    return a * b
def FusedMulAddSIMD_check(a, b, c):
    return a*b + c
def FusedMulSubSIMD_check(a, b, c):
    return a*b - c
def DivSIMD_check(a, b):
    return a / b
def signSIMD_check(a):
    return sign(a)

# For debugging purposes, Part 2:
# Transcendental operations
def PowSIMD_check(a, b):
    return a**b
def SqrtSIMD_check(a):
    return a**(Rational(1, 2))
def CbrtSIMD_check(a):
    return a**(Rational(1, 3))
def ExpSIMD_check(a):
    return exp(a)
def LogSIMD_check(a):
    return log(a)
def SinSIMD_check(a):
    return sin(a)
def CosSIMD_check(a):
    return cos(a)

# Input: SymPy expression.
# Return value: SymPy expression containing all needed SIMD compiler intrinsics
# Complication: SIMD functions require numerical constants to be stored in SIMD arrays
# Resolution: This function extends lists "SIMD_const_varnms" and "SIMD_const_values",
#             which store the name of each constant SIMD array (e.g., _Integer_1) and
#             the value of each variable (e.g., 1.0).
def expr_convert_to_SIMD_intrins(expr, SIMD_const_varnms, SIMD_const_values, SIMD_const_suffix="", debug="False"):

    # Declare all variables, so we can eval them in the next (AddSIMD & MulSIMD) step
    for item in preorder_traversal(expr):
        for arg in item.args:
            if isinstance(arg, Symbol):
                var(str(arg))

    expr_orig = expr
    tree = ExprTree(expr)

    AbsSIMD  = Function("AbsSIMD")
    AddSIMD  = Function("AddSIMD")
    SubSIMD  = Function("SubSIMD")
    MulSIMD  = Function("MulSIMD")
    FusedMulAddSIMD = Function("FusedMulAddSIMD")
    FusedMulSubSIMD = Function("FusedMulSubSIMD")
    DivSIMD  = Function("DivSIMD")
    SignSIMD = Function("SignSIMD")

    PowSIMD  = Function("PowSIMD")
    SqrtSIMD = Function("SqrtSIMD")
    CbrtSIMD = Function("CbrtSIMD")
    ExpSIMD  = Function("ExpSIMD")
    LogSIMD  = Function("LogSIMD")
    SinSIMD  = Function("SinSIMD")
    CosSIMD  = Function("CosSIMD")

    # Step 1: Replace transcendental, power, and division functions with SIMD equivalents
    #         Note that due to how SymPy expresses rational numbers, the following does not
    #         affect fractional expressions of integers
    for subtree in tree.preorder(tree.root):
        func = subtree.expr.func
        args = subtree.expr.args
        if   func == Abs:
            subtree.expr = AbsSIMD(args[0])
        elif func == exp:
            subtree.expr = ExpSIMD(args[0])
        elif func == log:
            subtree.expr = LogSIMD(args[0])
        elif func == sin:
            subtree.expr = SinSIMD(args[0])
        elif func == cos:
            subtree.expr = CosSIMD(args[0])
        elif func == sign:
            subtree.expr = SignSIMD(args[0])
    expr = tree.reconstruct()

    # Fun little recursive function for constructing integer powers:
    def IntegerPowSIMD(a, n):
        if   n == 2:
            return MulSIMD(a, a)
        elif n > 2:
            return MulSIMD(IntegerPowSIMD(a, n - 1), a)
        elif n <= -2:
            return DivSIMD(1, IntegerPowSIMD(a, -n))
        elif n == -1:
            return DivSIMD(1, a)

    for subtree in tree.preorder(tree.root):
        func = subtree.expr.func
        args = subtree.expr.args
        if func == Pow:
            if   args[1] == 0.5:
                subtree.expr = SqrtSIMD(args[0])
                subtree.children.pop(1) # Remove 0.5
            elif args[1] == -0.5:
                subtree.expr = DivSIMD(1, SqrtSIMD(args[0]))
                tree.build(subtree, clear=True)
            elif args[1] == Rational(1, 3):
                subtree.expr = CbrtSIMD(args[0])
                subtree.children.pop(1) # Remove -0.5
            elif args[1] == int(args[1]):
                subtree.expr = IntegerPowSIMD(*args)
                tree.build(subtree, clear=True)
            else:
                subtree.expr = PowSIMD(*args)
    expr = tree.reconstruct()

    # Step 2: Replace all rational numbers (expressed as Rational(a,b))
    #         and integers with the new functions RationalTMP and
    #         IntegerTMP, where Rational(a,b) -> RationalTMP(a,b)
    #         and Integer(a) -> IntegerTMP(a)
    RationalTMP = Function("RationalTMP")
    IntegerTMP = Function("IntegerTMP")
    
    for subtree in tree.postorder(tree.root):
        if isinstance(subtree.expr, Integer):
            subtree.expr = IntegerTMP(subtree.expr)
            tree.build(subtree, clear=True)
        elif isinstance(subtree.expr, Rational):
            args = subtree.expr.p, subtree.expr.q
            subtree.expr = RationalTMP(*args)
            tree.build(subtree, clear=True)
    expr = tree.reconstruct(evaluate=True)
    # We must evaluate the expression, otherwise nested multiplications
    # will arise that conflict with the following replacements in Step 3.

    # Step 3: The pattern Mul(-1,Rational(a,b)) is often seen. Replace with Rational(-a,b).
    for subtree in tree.preorder(tree.root):
        func = subtree.expr.func
        args = subtree.children
        if func == Mul:
            index = -1 # Index of -1
            for i, arg in enumerate(args):
                if arg.expr == IntegerTMP(-1): index = i
            if index != -1:
                for arg in args:
                    if arg.expr.func == RationalTMP:
                        subtree.children.pop(index) # Remove -1
                        arg.children[0].expr *= -1
                        break
    expr = tree.reconstruct()

    # Step 4: SIMD multiplication and addition compiler intrinsics read in
    #         only two arguments at once, where SymPy's Mul() and Add()
    #         operators can read an arbitrary number of arguments.
    #         Here, we split e.g., Mul(a,b,c,d) into
    #         MulSIMD(a,MulSIMD(b,MulSIMD(c,d))),
    #         To accomplish this easily, we construct a string
    #         'MulSIMD(A,MulSIMD(B,...', where MulSIMD(a,b) is some user-
    #         defined function that takes in only two arguments, and then
    #         evaluate the string using the eval() function.
    # Implementation detail: If we did not perform Step 2 above, the eval
    #         function would automatically evaluate all Rational expressions
    #         as though they were input as integers: e.g., 1/2 evaluates to 0.
    #         This is undesirable, so we instead define new, temporary
    #         functions IntegerTMP and RationalTMP that are undisturbed by
    #         the eval()
    for subtree in tree.preorder(tree.root):
        func = subtree.expr.func
        args = subtree.expr.args
        if (func == Mul or func == Add):
            func = MulSIMD if func == Mul else AddSIMD
            subexpr = func(*args[-2:])
            for arg in args[:-2]:
                subexpr = func(arg, subexpr, evaluate=False)
            subtree.expr = subexpr
            tree.build(subtree, clear=True)
    expr = tree.reconstruct()

    # Step 5: Simplification patterns:
    # Step 5a: Replace the pattern Mul(Div(1,b),a) or Mul(a,Div(1,b)) with Div(a,b):
    for subtree in tree.preorder(tree.root):
        func = subtree.expr.func
        args = subtree.expr.args
        if   func == MulSIMD and args[0].func == DivSIMD and args[1].func == IntegerTMP:
            subtree.expr = DivSIMD(args[1], args[0].args[1])
            tree.build(subtree, clear=True)
        elif func == MulSIMD and args[1].func == DivSIMD and args[0].func == IntegerTMP:
            subtree.expr = DivSIMD(args[0], args[1].args[1])
            tree.build(subtree, clear=True)
    expr = tree.reconstruct()

    # Step 5: Subtraction intrinsics. SymPy replaces all a-b with a + (-b) = Add(a,Mul(-1,b))
    #         Here, we replace
    #         a) AddSIMD(a,MulSIMD(-1,b)),
    #         b) AddSIMD(a,MulSIMD(b,-1)),
    #         c) AddSIMD(MulSIMD(-1,b),a), and
    #         d) AddSIMD(MulSIMD(b,-1),a)
    #         with SubSIMD(a,b)
    for subtree in tree.preorder(tree.root):
        func = subtree.expr.func
        args = subtree.expr.args
        if   func == AddSIMD and args[0].func == MulSIMD and \
                args[0].args[0] == IntegerTMP(-1):
            subtree.expr = SubSIMD(args[1], args[0].args[1])
            tree.build(subtree, clear=True)
        elif func == AddSIMD and args[0].func == MulSIMD and \
                args[0].args[1] == IntegerTMP(-1):
            subtree.expr = SubSIMD(args[1], args[0].args[0])
            tree.build(subtree, clear=True)
        elif func == AddSIMD and args[1].func == MulSIMD and \
                args[1].args[0] == IntegerTMP(-1):
            subtree.expr = SubSIMD(args[0], args[1].args[1])
            tree.build(subtree, clear=True)
        elif func == AddSIMD and args[1].func == MulSIMD and \
                args[1].args[1] == IntegerTMP(-1):
            subtree.expr = SubSIMD(args[0], args[1].args[0])
            tree.build(subtree, clear=True)
    expr = tree.reconstruct()

    # Step 6: Now that all multiplication and addition functions only take two
    #         arguments, we can now easily define fused-multiply-add functions,
    #         where AddSIMD(a,MulSIMD(b,c)) = b*c + a = FusedMulAddSIMD(b,c,a),
    #         or    AddSIMD(MulSIMD(b,c),a) = b*c + a = FusedMulAddSIMD(b,c,a).
    # Fused multiply add (FMA3) is standard on Intel CPUs with the AVX2
    #         instruction set, starting with Haswell processors in 2013:
    #         https://en.wikipedia.org/wiki/Haswell_(microarchitecture)
    for subtree in tree.preorder(tree.root):
        func = subtree.expr.func
        args = subtree.expr.args
        if   func == AddSIMD and args[0].func == MulSIMD:
            subtree.expr = FusedMulAddSIMD(*args[0].args, args[1])
            tree.build(subtree, clear=True)
        elif func == AddSIMD and args[1].func == MulSIMD:
            subtree.expr = FusedMulAddSIMD(*args[1].args, args[0])
            tree.build(subtree, clear=True)
        elif func == SubSIMD and args[0].func == MulSIMD:
            subtree.expr = FusedMulSubSIMD(*args[0].args, args[1])
            tree.build(subtree, clear=True)
    expr = tree.reconstruct()

    # Step 7a: Set all variable names and corresponding values.
    for item in preorder_traversal(expr):
        if item.func == RationalTMP:
            # Set variable name
            if item.args[0] * item.args[1] < 0:
                SIMD_const_varnms.extend(["_Rational_m" + str(abs(item.args[0])) + "_" + str(abs(item.args[1])) + SIMD_const_suffix])
            elif item.args[0] > 0 and item.args[1] > 0:
                SIMD_const_varnms.extend(["_Rational_" + str(item.args[0]) + "_" + str(item.args[1]) + SIMD_const_suffix])
            else:
                # E.g., doesn't make sense to have -1/-3. SymPy should have simplified this.
                print("Found a weird Rational(a, b) expression, where a < 0 and b < 0. Report to SymPy devels.")
                print("Specifically, found that a = " + str(item.args[0]) + " and b = " + str(item.args[1]))
                sys.exit(1)
            # Set variable value, to 34 digits of precision
            SIMD_const_values.extend([str(N(Float(item.args[0], 34)/Float(item.args[1], 34), 34))])
        elif item.func == IntegerTMP:
            # Set variable name
            if item.args[0] < 0:
                SIMD_const_varnms.extend(["_Integer_m" + str(-item.args[0]) + SIMD_const_suffix])
            else:
                SIMD_const_varnms.extend(["_Integer_" + str(item.args[0]) + SIMD_const_suffix])
            # Set variable value, to 34 digits of precision
            SIMD_const_values.extend([str((Float(item.args[0], 34)))])

    # Step 7b: Replace all integers and rationals with the appropriate variable names:
    for item in preorder_traversal(expr):
        tempitem = item
        if item.func == RationalTMP:
            if item.args[0] * item.args[1] < 0:
                tempitem = var("_Rational_m" + str(abs(item.args[0])) + "_" + str(abs(item.args[1])) + SIMD_const_suffix)
            elif item.args[0] > 0 and item.args[1] > 0:
                tempitem = var("_Rational_" + str(item.args[0]) + "_" + str(item.args[1]) + SIMD_const_suffix)
            else:
                # E.g., doesn't make sense to have -1/-3. SymPy should have simplified this.
                print("Found a weird Rational(a, b) expression, where a < 0 and b < 0. Report to SymPy devels.")
                print("Specifically, found that a = " + str(item.args[0]) + " and b = " + str(item.args[1]))
                sys.exit(1)
        elif item.func == IntegerTMP:
            if item.args[0] < 0:
                tempitem = var("_Integer_m" + str(-item.args[0]) + SIMD_const_suffix)
            else:
                tempitem = var("_Integer_" + str(item.args[0]) + SIMD_const_suffix)
        if item != tempitem: expr = expr.subs(item, tempitem)

    def lookup_name_output_idx(name, list_of_names):
        for i in range(len(list_of_names)):
            if list_of_names[i] == name:
                return i
        print("I SHOULDN'T BE HERE!", name, list_of_names)
        sys.exit(1)

    if debug == "True":
        expr_check = expr
        if "SIMD" in str(expr):
            expr_check = eval(str(expr).replace("SIMD", "SIMD_check"))

        for item in preorder_traversal(expr_check):
            tempitem = item
            if item.is_Symbol and str(item)[0] == "_":
                if str(item)[:9] == "_Integer_" or str(item)[:10] == "_Rational_":
                    tempitem = SIMD_const_values[lookup_name_output_idx(str(item), SIMD_const_varnms)]
            if item != tempitem: expr_check = expr_check.subs(item, tempitem)

        expr_diff = expr_check - expr_orig
        # Some variables do not want to cancel in SymPy ~0.7.4. The eval(str(srepr())) below normalizes the expression.
        expr_diff = eval(str(srepr(expr_diff)))
        for item in preorder_traversal(expr_diff):
            if item.func == Float:
                if abs(item - Integer(item)) < 1.0e-14:
                    expr_diff = expr_diff.xreplace({item:Integer(item)})

        # Only simplify if expr_diff != 0:
        if expr_diff != 0:
            simp_expr_diff = simplify(expr_diff)
            if simp_expr_diff != 0:
                print("Warning: found possible diff", (simp_expr_diff))
    return(expr)
