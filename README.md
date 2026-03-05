# Netzbremse Dashboard

This project complements the [Netzbremse Measurement Project](https://github.com/AKVorrat/netzbremse-measurement), which periodically tests your internet speed through different routes to collect data on Telekom's peering. With this dashboard you can neatly visualize the data, identify trends, and track the performance of your connection across time.

In principle, this app runs in a separate container and only maps the output directory of netzbremse-measurement as its input, therefore sharing only a volume. Besides,
the two containers run completely independently, however, locally, without a running measurement container, this app won't have any data.

## Deployment

Find an almost ready-to-be-used `docker-compose.yml` file in the repo. The only adjustment you will have to make is to change the data directory. You have two options:

1. Map the container directory `/data` to the same docker volume (name) that your netzbremse-measurement container uses.
2. Map the container directory `/data` to a host directory that your netzbremse-measurement container json files are saved in.

You can also build the image yourself:

```bash
docker compose build
```

or use my prebuilt image: `ghcr.io/lwndp/netzbremse-dashboard:latest`

## Security 

> ⚠️ Important: This a development project. It is not hardened to be published to the internet without any safety precautions, such as authentication or reverse-proxy. Please be careful and know what you are doing when deploying this on a public server.

## Development

### Requirements

- Python 3.12
- uv
- Docker

### Quick Start

**Using Docker (recommended):**
```bash
docker compose up --build
```

Dashboard available at `http://localhost:8501`

**Local development:**

Install dependencies:
```bash
uv sync
```

Install pre-commit hooks (runs code quality checks on every commit):
```bash
pre-commit install
```

Set environment variables in a `.env` file. To get started:
```bash
cp .env.example .env
```
**Note:** DATA_DIR should contain the raw output of the measurement app, i.e. json files.

Run the app (without Docker):
```bash
uv run streamlit run app/app.py
```

#### Configuration

- `DATA_DIR`: Path to directory with speedtest JSON files (default: `/data`).
- `REFRESH_INTERVAL_SECONDS`: Auto-refresh interval in seconds and data cache TTL (default: `3600`). Must be a positive integer; invalid values fall back to `3600`.
- `DEFAULT_METRIC`: Default KPI key for the dropdown (default: `download`). Valid keys: `download`, `upload`, `latency`, `jitter`, `downLoadedLatency`, `downLoadedJitter`, `upLoadedLatency`, `upLoadedJitter`.

You can adjust the application port in `.streamlit/config.toml`. Note that this will also apply to the container build and therefore requires adjustments of your `docker-compose.yaml`.

### Directory Structure

```
app/
├── app.py              # Main application
├── charts.py           # Chart generation (Altair)
├── components.py       # Reusable UI components
└── data_loader.py      # Data loading & caching
tests/
├── conftest.py         # Pytest fixtures (Streamlit stub)
├── test_charts.py      # Unit tests for charts.py
└── test_data_loader.py # Unit tests for data_loader.py
```

### Common tasks

A `Makefile` is provided for the most common development tasks:

| Command       | Description                                    |
| ------------- | ---------------------------------------------- |
| `make test`   | Run the unit test suite                        |
| `make lint`   | Check code style and quality (non-destructive) |
| `make format` | Auto-format code with Black and isort          |

### Tests

The test suite covers the core data loading and chart logic without requiring a running Streamlit server.

```bash
make test
# or: uv run pytest tests/ -v
```

Pre-commit hooks run tests automatically on every commit that touches `app/` or `tests/`.

### Code Quality

Pre-commit hooks enforce code quality on every commit:

- **Ruff**: Linting
- **Black**: Formatting
- **isort**: Import ordering
- **pytest**: Unit tests (only when `app/` or `tests/` files are staged)

Check manually before committing:

```bash
make lint
```

Auto-fix formatting issues:

```bash
make format
```

## Contribute

Feel free to file a PR if you think you have found a critical bug or want to add a feature. It will help tremendously if you keep the scope of your PR limited to one feature. I maintain this repo voluntarily, so my free time is limited.
