"""Tests for SecurePythonREPL."""

import pytest
from deepscroll.repl import SecurePythonREPL, REPLResult


class TestSecurePythonREPL:
    """Test SecurePythonREPL functionality."""

    @pytest.fixture
    def repl(self) -> SecurePythonREPL:
        """Create a REPL instance."""
        return SecurePythonREPL()

    def test_execute_simple(self, repl: SecurePythonREPL) -> None:
        """Test simple code execution."""
        result = repl.execute("x = 1 + 1")

        assert result.success is True
        assert repl.get_variable("x") == 2

    def test_execute_with_print(self, repl: SecurePythonREPL) -> None:
        """Test code with print output."""
        result = repl.execute('print("Hello, World!")')

        assert result.success is True
        assert "Hello, World!" in (result.output or "")

    def test_execute_multiple_lines(self, repl: SecurePythonREPL) -> None:
        """Test multi-line code execution."""
        code = """
def add(a, b):
    return a + b

result = add(2, 3)
"""
        result = repl.execute(code)

        assert result.success is True
        assert repl.get_variable("result") == 5

    def test_execute_list_operations(self, repl: SecurePythonREPL) -> None:
        """Test list operations."""
        code = """
numbers = [1, 2, 3, 4, 5]
doubled = [x * 2 for x in numbers]
total = sum(doubled)
"""
        result = repl.execute(code)

        assert result.success is True
        assert repl.get_variable("total") == 30

    def test_forbidden_open(self, repl: SecurePythonREPL) -> None:
        """Test that open() is forbidden."""
        result = repl.execute('f = open("test.txt", "r")')

        assert result.success is False
        assert "Forbidden" in (result.error or "")

    def test_forbidden_eval(self, repl: SecurePythonREPL) -> None:
        """Test that eval() is forbidden."""
        result = repl.execute('eval("1+1")')

        assert result.success is False
        assert "Forbidden" in (result.error or "")

    def test_forbidden_exec(self, repl: SecurePythonREPL) -> None:
        """Test that exec() is forbidden."""
        result = repl.execute('exec("x = 1")')

        assert result.success is False
        assert "Forbidden" in (result.error or "")

    def test_forbidden_import(self, repl: SecurePythonREPL) -> None:
        """Test that __import__ is forbidden."""
        result = repl.execute('__import__("os")')

        assert result.success is False
        assert "Forbidden" in (result.error or "")

    def test_allowed_regex(self, repl: SecurePythonREPL) -> None:
        """Test that regex is allowed."""
        code = """
matches = re.findall(r'\\d+', 'abc123def456')
"""
        result = repl.execute(code)

        assert result.success is True
        assert repl.get_variable("matches") == ["123", "456"]

    def test_allowed_json(self, repl: SecurePythonREPL) -> None:
        """Test that json is allowed."""
        code = """
data = json.loads('{"key": "value"}')
output = json.dumps(data)
"""
        result = repl.execute(code)

        assert result.success is True
        assert repl.get_variable("data") == {"key": "value"}

    def test_allowed_math(self, repl: SecurePythonREPL) -> None:
        """Test that math is allowed."""
        code = """
result = math.sqrt(16) + math.pi
"""
        result = repl.execute(code)

        assert result.success is True
        import math

        assert repl.get_variable("result") == math.sqrt(16) + math.pi

    def test_allowed_collections(self, repl: SecurePythonREPL) -> None:
        """Test that collections are allowed."""
        code = """
counter = collections.Counter(['a', 'b', 'a', 'c', 'a'])
"""
        result = repl.execute(code)

        assert result.success is True
        counter = repl.get_variable("counter")
        assert counter["a"] == 3

    def test_set_variable(self, repl: SecurePythonREPL) -> None:
        """Test setting variables from outside."""
        repl.set_variable("external_data", [1, 2, 3])

        result = repl.execute("total = sum(external_data)")

        assert result.success is True
        assert repl.get_variable("total") == 6

    def test_set_variable_private_forbidden(self, repl: SecurePythonREPL) -> None:
        """Test that private variables cannot be set."""
        with pytest.raises(ValueError):
            repl.set_variable("_private", "value")

    def test_get_nonexistent_variable(self, repl: SecurePythonREPL) -> None:
        """Test getting a nonexistent variable."""
        assert repl.get_variable("nonexistent") is None

    def test_reset(self, repl: SecurePythonREPL) -> None:
        """Test REPL reset."""
        repl.execute("x = 42")
        assert repl.get_variable("x") == 42

        repl.reset()

        assert repl.get_variable("x") is None

    def test_syntax_error(self, repl: SecurePythonREPL) -> None:
        """Test handling of syntax errors."""
        result = repl.execute("def broken(")

        assert result.success is False
        assert "Syntax" in (result.error or "") or "error" in (result.error or "").lower()

    def test_runtime_error(self, repl: SecurePythonREPL) -> None:
        """Test handling of runtime errors."""
        result = repl.execute("x = 1 / 0")

        assert result.success is False
        assert "ZeroDivision" in (result.error or "")

    def test_execute_expression(self, repl: SecurePythonREPL) -> None:
        """Test expression evaluation."""
        repl.set_variable("x", 10)

        result = repl.execute_expression("x * 2")

        assert result.success is True
        assert result.return_value == 20

    def test_output_truncation(self) -> None:
        """Test that large output is truncated."""
        repl = SecurePythonREPL(max_output_size=100)

        result = repl.execute('print("x" * 500)')

        assert result.success is True
        assert len(result.output or "") <= 150  # Some overhead for truncation message

    def test_persistent_state(self, repl: SecurePythonREPL) -> None:
        """Test that state persists across executions."""
        repl.execute("counter = 0")
        repl.execute("counter += 1")
        repl.execute("counter += 1")

        assert repl.get_variable("counter") == 2

    def test_function_definition_and_call(self, repl: SecurePythonREPL) -> None:
        """Test defining and calling functions."""
        repl.execute("""
def greet(name):
    return f"Hello, {name}!"
""")
        repl.execute('message = greet("World")')

        assert repl.get_variable("message") == "Hello, World!"

    def test_list_comprehension(self, repl: SecurePythonREPL) -> None:
        """Test list comprehensions work."""
        result = repl.execute("squares = [x**2 for x in range(5)]")

        assert result.success is True
        assert repl.get_variable("squares") == [0, 1, 4, 9, 16]

    def test_dict_operations(self, repl: SecurePythonREPL) -> None:
        """Test dictionary operations."""
        code = """
data = {"a": 1, "b": 2}
data["c"] = 3
keys = list(data.keys())
"""
        result = repl.execute(code)

        assert result.success is True
        assert repl.get_variable("keys") == ["a", "b", "c"]


class TestREPLResult:
    """Test REPLResult dataclass."""

    def test_success_result(self) -> None:
        """Test creating a success result."""
        result = REPLResult(success=True, output="Hello")

        assert result.success is True
        assert result.output == "Hello"
        assert result.error is None

    def test_error_result(self) -> None:
        """Test creating an error result."""
        result = REPLResult(success=False, error="Something went wrong")

        assert result.success is False
        assert result.error == "Something went wrong"
