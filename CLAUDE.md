# CLAUDE.md

## Project: ShadowBoard (test_mcp)

**Description**: Personal virtual boardroom & zero-cost MoE decision engine. A multi-role AI debate system that coordinates DeepSeek, Kimi, and other web AI platforms for collaborative decision-making without API costs.

### Build Commands

```powershell
# Install dependencies
pip install -e .

# Install Playwright browser
playwright install chromium
```

### Test & Quality Commands

```powershell
# Run quality gate (lint + test + perf + compatibility)
.\quality_gate.ps1

# Run tests directly
pytest

# Run with coverage
pytest --cov=src tests/
```

### Entry Points

```powershell
# CLI entry
python main.py

# Web UI
python web_app.py
```

### Project Structure

```
test_mcp/
├── src/                     # Core modules (core/, services/, models/, utils/)
├── tests/                   # Test files
├── docs/                    # Project wiki
├── main.py                  # CLI entry
├── web_app.py               # Gradio web interface
├── pyproject.toml           # Project config
└── requirements.txt         # Dependencies
```

### Key Technologies

- **Automation**: Playwright (Async)
- **Web UI**: Gradio (with Lazy Loading)
- **Async DB**: aiosqlite
- **Async IO**: aiofiles, httpx
- **Testing**: pytest, pytest-asyncio, pytest-mock

### Known Issues

- Requires browser login for AI platforms (DeepSeek, Kimi, etc.)
- Web UI must remain open during AI orchestration
