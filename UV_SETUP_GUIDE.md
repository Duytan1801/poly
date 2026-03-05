# UV Setup Guide - Polymarket Unified Insider Detection

Quick setup guide for using `uv` package manager with the unified insider detection system.

## Prerequisites

1. **Install UV**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

2. **Install Python 3.14** (with free-threading support)
```bash
# UV will automatically download Python 3.14 when needed
uv python install 3.14
```

## Quick Start

### 1. Clone and Setup

```bash
cd /path/to/poly
uv sync
```

This will:
- Create a virtual environment
- Install Python 3.14
- Install all dependencies
- Set up the project

### 2. Run the Unified System

```bash
# Run with free-threading enabled
uv run python -X gil=0 src/poly/unified_insider_detector.py
```

Or use the CLI command:

```bash
uv run poly-unified
```

### 3. Use in Your Code

```bash
# Activate the virtual environment
source .venv/bin/activate  # Linux/Mac
# or
.venv\Scripts\activate  # Windows

# Run your script with free-threading
python -X gil=0 your_script.py
```

## Installation Options

### Minimal (Unified System Only)

```bash
uv sync
```

Installs only:
- httpx
- pandas
- numpy
- polars
- msgpack
- python-dotenv

Perfect for the unified system!

### With Development Tools

```bash
uv sync --extra dev
```

Adds:
- pytest
- pytest-asyncio
- pytest-cov
- black
- ruff
- mypy

### With Legacy System

```bash
uv sync --extra legacy
```

Adds all legacy dependencies:
- numba, perpetual, pyarrow, etc.

### Full Installation

```bash
uv sync --extra full
```

Installs everything (unified + legacy + dev tools)

## Usage Examples

### Example 1: Quick Scan

```python
# your_script.py
from poly.unified_insider_detector import quick_scan

results = quick_scan(limit=100, mode="fast")
print(f"Found {len(results)} traders")
```

Run:
```bash
uv run python -X gil=0 your_script.py
```

### Example 2: Find Insiders

```python
# find_insiders.py
from poly.unified_insider_detector import find_insiders

insiders = find_insiders(limit=100, threshold=5.0)
for trader in insiders:
    print(f"{trader['address']}: Risk {trader['risk_score']:.1f}")
```

Run:
```bash
uv run python -X gil=0 find_insiders.py
```

### Example 3: Custom Analysis

```python
# analyze.py
from poly.unified_insider_detector import UnifiedInsiderDetector

detector = UnifiedInsiderDetector()
results = detector.analyze_top_traders(limit=50, mode="hybrid")
high_risk = detector.filter_high_risk(results, threshold=6.0)

print(f"High-risk traders: {len(high_risk)}")
detector.close()
```

Run:
```bash
uv run python -X gil=0 analyze.py
```

## UV Commands

### Sync Dependencies

```bash
uv sync                    # Install/update dependencies
uv sync --frozen           # Use exact versions from lockfile
uv sync --no-dev           # Skip dev dependencies
```

### Add Dependencies

```bash
uv add httpx              # Add new dependency
uv add --dev pytest       # Add dev dependency
uv add --optional legacy numba  # Add to optional group
```

### Remove Dependencies

```bash
uv remove package-name
```

### Run Commands

```bash
uv run python script.py           # Run Python script
uv run poly-unified               # Run CLI command
uv run pytest                     # Run tests
```

### Python Management

```bash
uv python list                    # List available Python versions
uv python install 3.14            # Install Python 3.14
uv python pin 3.14                # Pin project to Python 3.14
```

### Lock File

```bash
uv lock                           # Generate/update uv.lock
uv lock --upgrade                 # Upgrade all dependencies
uv lock --upgrade-package httpx   # Upgrade specific package
```

## Project Structure

```
poly/
├── pyproject.toml              # Project configuration
├── uv.lock                     # Dependency lockfile (auto-generated)
├── .venv/                      # Virtual environment (auto-created)
├── src/poly/
│   └── unified_insider_detector.py  # Main system
├── UNIFIED_SYSTEM_README.md    # Usage guide
└── UV_SETUP_GUIDE.md          # This file
```

## Configuration

The `pyproject.toml` is configured for:

- **Python 3.14** minimum requirement
- **Minimal dependencies** for unified system
- **Optional groups** for legacy and dev tools
- **CLI commands** for easy access

## Performance Tips

### 1. Enable Free-Threading

Always run with `-X gil=0` for maximum performance:

```bash
uv run python -X gil=0 script.py
```

### 2. Use UV's Fast Resolver

UV's dependency resolver is 10-100x faster than pip:

```bash
time uv sync  # Seconds
time pip install -e .  # Minutes
```

### 3. Parallel Installation

UV installs packages in parallel automatically:

```bash
uv sync  # Installs multiple packages simultaneously
```

## Troubleshooting

### "Python 3.14 not found"

```bash
uv python install 3.14
uv sync
```

### "Package conflicts"

```bash
uv lock --upgrade
uv sync --frozen
```

### "Virtual environment issues"

```bash
rm -rf .venv
uv sync
```

### "Import errors"

Make sure you're in the virtual environment:

```bash
source .venv/bin/activate
python -c "import poly.unified_insider_detector"
```

Or use `uv run`:

```bash
uv run python -c "import poly.unified_insider_detector"
```

## Comparison: UV vs PIP

| Feature | UV | PIP |
|---------|----|----|
| Dependency Resolution | 10-100x faster | Slow |
| Parallel Installation | Yes | No |
| Lockfile | Yes (uv.lock) | No (manual) |
| Python Management | Built-in | Separate tool |
| Virtual Env | Auto-created | Manual |
| Disk Cache | Yes | Limited |

## CI/CD Integration

### GitHub Actions

```yaml
name: Test
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v1
      - run: uv sync
      - run: uv run pytest
```

### Docker

```dockerfile
FROM python:3.14-slim
WORKDIR /app
COPY . .
RUN pip install uv
RUN uv sync --frozen
CMD ["uv", "run", "python", "-X", "gil=0", "src/poly/unified_insider_detector.py"]
```

## Migration from PIP

If you have an existing `requirements.txt`:

```bash
# Convert to pyproject.toml
uv add $(cat requirements.txt)

# Or import directly
uv pip compile requirements.txt -o requirements.lock
uv sync
```

## Best Practices

1. **Always use `uv sync`** instead of `pip install`
2. **Commit `uv.lock`** to version control
3. **Use `--frozen`** in CI/CD for reproducible builds
4. **Pin Python version** with `uv python pin 3.14`
5. **Use optional groups** for different use cases

## Resources

- UV Documentation: https://docs.astral.sh/uv/
- Python 3.14 Free-Threading: https://docs.python.org/3.14/whatsnew/3.14.html
- Project README: `UNIFIED_SYSTEM_README.md`

## Quick Reference

```bash
# Setup
uv sync                                    # Install dependencies
uv python install 3.14                     # Install Python 3.14

# Run
uv run python -X gil=0 script.py          # Run with free-threading
uv run poly-unified                        # Run CLI

# Manage
uv add package                             # Add dependency
uv remove package                          # Remove dependency
uv lock --upgrade                          # Update lockfile

# Test
uv run pytest                              # Run tests
uv run black .                             # Format code
uv run ruff check .                        # Lint code
```

## Support

For issues:
1. Check UV docs: https://docs.astral.sh/uv/
2. Check project README: `UNIFIED_SYSTEM_README.md`
3. Verify Python 3.14: `uv run python --version`
4. Check dependencies: `uv tree`