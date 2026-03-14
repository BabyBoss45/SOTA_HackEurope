# Testing Patterns

**Analysis Date:** 2026-03-14

## Test Framework

**Runner:**
- Python: pytest
- TypeScript/Node: No test framework configured (package.json shows `test: "echo \"Error: no test specified\"..."`)

**Assertion Library:**
- Python: pytest assertions (built-in `assert` statements)
- TypeScript: Not applicable (no test setup)

**Run Commands:**
```bash
# Python agents tests
pytest                       # Run all tests
pytest agents/tests/         # Run agent tests specifically
pytest -m unit               # Run only unit tests (marked with @pytest.mark.unit)
pytest -m integration        # Run integration tests (marked with @pytest.mark.integration)
pytest -xvs                  # Verbose output with immediate failure stop
```

## Test File Organization

**Location:**
- Python: `agents/tests/` directory, separate from source
- TypeScript: No tests present; convention would be co-located with `.test.tsx` or `__tests__` folders

**Naming:**
- Python: `test_*.py` or `*_test.py`
- Examples: `test_sdk_wallet.py`, `test_task_memory.py`, `test_fun_activity_agent.py`

**Structure:**
```
agents/
├── src/                      # Source code
│   ├── butler/
│   ├── shared/
│   └── [agent_name]/
├── tests/                    # Test directory
│   ├── conftest.py          # Shared fixtures and configuration
│   ├── test_*.py            # Test modules
│   └── [subdirs]/           # Organized by feature
└── test_sota_sdk.py         # Standalone integration tests
```

## Test Structure

**Suite Organization (pytest pattern):**
```python
# agents/tests/test_sdk_wallet.py
import pytest

pytestmark = pytest.mark.unit

class TestKeyValidation:
    """Group related tests in a class"""

    def test_rejects_short_key(self):
        """Test case: describe behavior"""
        from sota_sdk.chain.wallet import AgentWallet
        with pytest.raises(ValueError):
            AgentWallet("deadbeef")

    def test_accepts_base58_key(self, mock_cluster, mock_client):
        """Test case: uses fixtures"""
        # test code

class TestKeySecurity:
    """Another group of tests"""

    def test_key_not_in_error_messages(self):
        """Assertion example"""
        assert TEST_KEY_BASE58 not in str(exc_info.value)
```

**Patterns:**
- **Setup:** Use pytest fixtures for common setup (not setUp methods)
- **Teardown:** Use pytest fixture cleanup with `yield` or cleanup code after yield
- **Assertion:** Standard Python `assert` statements
- **Markers:** `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.slow` for filtering

**Fixture Teardown Example from `conftest.py`:**
```python
@pytest_asyncio.fixture
async def hub_server():
    """Start an isolated hub FastAPI app on a random port, yield HubContext."""
    # ... setup code ...
    yield ctx

    # Cleanup
    server.should_exit = True
    await asyncio.sleep(0.1)
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass
```

## Mocking

**Framework:** `unittest.mock` (Python standard library)
- `MagicMock` for synchronous mocks
- `AsyncMock` for async function mocks
- `patch` decorator for replacing imports

**Patterns (from `conftest.py`):**
```python
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

# Basic mock
@pytest.fixture
def mock_wallet():
    """MagicMock mimicking AgentWallet."""
    wallet = MagicMock()
    wallet.address = "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU"
    wallet.sign_message.return_value = "3fGh" + "ab" * 32
    wallet.build_and_send.return_value = "5wHG" + "cc" * 32
    return wallet

# Async mock
@pytest.fixture
def mock_ws_client():
    """AsyncMock mimicking MarketplaceClient."""
    client = AsyncMock()
    client.send = AsyncMock()
    type(client).connected = PropertyMock(return_value=False)
    return client

# Patch decorator
@patch("sota_sdk.chain.wallet.Client")
@patch("sota_sdk.chain.wallet.get_cluster")
def test_accepts_base58_key(self, mock_cluster, mock_client):
    mock_cluster.return_value = MagicMock(rpc_url="https://api.devnet.solana.com")
    mock_client.return_value = MagicMock()
    # test code
```

**What to Mock:**
- External services (Solana RPC, OpenAI, database)
- Network calls (requests, WebSocket connections)
- File system operations
- System time/clock functions

**What NOT to Mock:**
- Business logic functions (test actual behavior)
- Data transformation functions
- Validation logic

## Fixtures and Factories

**Test Data (Factory Fixtures from `conftest.py`):**
```python
@pytest.fixture
def make_job():
    """Factory fixture: make_job(**overrides) → Job with sensible defaults."""
    def _make(**overrides) -> Job:
        defaults = {
            "id": str(uuid.uuid4()),
            "description": "Test job",
            "tags": ["test"],
            "budget_usdc": 10.0,
            "deadline_ts": int(time.time()) + 3600,
            "poster": "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU",
        }
        defaults.update(overrides)
        return Job(**defaults)
    return _make

# Usage in tests:
def test_bid_on_job(make_job):
    job = make_job(budget_usdc=50.0)  # Override budget
    # test code
```

**Dynamic Agent Class Factory:**
```python
@pytest.fixture
def make_agent_class():
    """Factory: make_agent_class(name, tags, execute_fn) → SOTAAgent subclass."""
    def _make(
        name: str = "test-agent",
        tags: Optional[list[str]] = None,
        execute_fn=None,
    ) -> type:
        async def default_execute(self, job):
            return {"success": True, "result": "done"}

        attrs = {
            "name": name,
            "tags": tags or ["test"],
        }
        if execute_fn:
            attrs["execute"] = execute_fn
        else:
            attrs["execute"] = default_execute

        cls = type(f"Dynamic_{name.replace('-','_')}", (SOTAAgent,), attrs)
        return cls
    return _make
```

**Location:**
- Shared fixtures: `agents/tests/conftest.py`
- Test-specific factories: Defined in test file using `@pytest.fixture`
- Factory pattern: Callable fixtures that return create functions, not data

## Coverage

**Requirements:** Not enforced (no coverage config in repository)

**View Coverage:**
```bash
pytest --cov=agents/src --cov-report=html  # Generate HTML coverage report
pytest --cov=agents/src --cov-report=term  # Terminal report
```

## Test Types

**Unit Tests:**
- Marked with `@pytest.mark.unit`
- Test single functions/classes in isolation
- Mock all external dependencies
- Examples: `test_sdk_wallet.py`, `test_task_memory.py`
- No network, file system, or database access

**Example from `test_sdk_wallet.py`:**
```python
pytestmark = pytest.mark.unit

class TestKeyValidation:
    def test_rejects_short_key(self):
        from sota_sdk.chain.wallet import AgentWallet
        with pytest.raises(ValueError):
            AgentWallet("deadbeef")
```

**Integration Tests:**
- Marked with `@pytest.mark.integration`
- Test multiple components working together
- May start test servers (FastAPI app in `conftest.py`)
- Async test patterns

**Example fixture that starts a test hub server:**
```python
@pytest_asyncio.fixture
async def hub_server():
    """Start an isolated hub FastAPI app on a random port, yield HubContext."""
    # Sets up a full test server with registry, bidding engine, router
    # Returns HubContext with URLs and internal objects
    # Runs full WebSocket protocol for agent connections
```

**E2E Tests:**
- Not currently implemented
- Would test full workflows from user input to job completion
- Would require deployed services

## Common Patterns

**Async Testing:**
```python
import pytest_asyncio

@pytest_asyncio.fixture
async def async_resource():
    """Async fixture for async setup/teardown."""
    # async setup
    yield resource
    # async cleanup

@pytest.mark.asyncio
async def test_async_operation(async_resource):
    """Test function marked as async."""
    result = await some_async_function()
    assert result.success
```

**Error Testing:**
```python
def test_validation_error():
    from sota_sdk.chain.wallet import AgentWallet

    with pytest.raises(ValueError) as exc_info:
        AgentWallet("invalid_key")

    assert "expected message" in str(exc_info.value)
```

**Parametrized Tests:**
```python
@pytest.mark.parametrize("input,expected", [
    ("test1", "result1"),
    ("test2", "result2"),
])
def test_multiple_cases(input, expected):
    assert process(input) == expected
```

**Module Import Workaround (from `test_task_memory.py`):**
```python
# For testing modules that import heavy dependencies (solana, openai),
# use importlib.util.spec_from_file_location to load directly
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(name, filepath)
mod = importlib.util.module_from_spec(spec)
sys.modules[name] = mod
spec.loader.exec_module(mod)
```

## Test Markers and Configuration

**Custom Markers (from `conftest.py`):**
```python
def pytest_configure(config):
    config.addinivalue_line("markers", "unit: unit tests (no network)")
    config.addinivalue_line("markers", "integration: integration tests (need ports)")
    config.addinivalue_line("markers", "slow: slow tests (>10s)")
```

**Helper Functions:**
```python
# Port allocation for test servers
def free_port() -> int:
    """Bind to port 0 and return the OS-assigned port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]

# Async polling for eventual consistency
async def wait_for(predicate, timeout: float = 5.0, interval: float = 0.05):
    """Async poll helper — raises TimeoutError if predicate never becomes truthy."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if asyncio.iscoroutine(result):
            result = await result
        if result:
            return result
        await asyncio.sleep(interval)
    raise TimeoutError(f"Predicate did not become truthy within {timeout}s")
```

## Existing Test Files

**Key test modules:**
- `agents/tests/test_sdk_wallet.py` - AgentWallet Solana integration tests (unit)
- `agents/tests/test_task_memory.py` - Adaptive Task Memory system tests (unit, fully mocked)
- `agents/tests/test_sdk_config.py` - Configuration tests
- `agents/tests/test_sdk_server.py` - Server/API tests
- `agents/tests/test_fun_activity_agent.py` - Agent-specific tests
- `agents/tests/test_e2e_agents.py` - End-to-end agent workflow tests
- `agents/tests/test_hub_connector_paid.py` - Hub connector integration tests
- `agents/test_sota_sdk.py` - Standalone SDK integration tests

**Test count:** ~15+ test files with 100+ test cases across agents

---

*Testing analysis: 2026-03-14*
