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

- `DATA_DIR`: Path to directory with speedtest JSON files (default: `/data`); Note: This applies only to
- `REFRESH_INTERVAL_SECONDS`: Data cache TTL (default: `3600`)

You can adjust the application port in `.streamlit/config.toml`. Note that this will also apply to the container build and therefore requires adjustments of your `docker-compose.yaml`.

### Directory Structure

```
app/
├── app.py              # Main application
├── charts.py           # Chart generation (Altair)
├── components.py       # Reusable UI components
└── data_loader.py      # Data loading & caching
```

### Code Quality

This project uses **pre-commit hooks** to ensure code quality:

- **Black**: Automatic code formatting
- **Ruff**: Linting and code quality checks

The hooks run automatically on every commit. To manually check before committing:

```bash
uv run ruff check app/
uv run black --check app/
```

To auto-fix issues:

```bash
uv run ruff check --fix app/
uv run black app/
```

## Contribute

Feel free to file a PR if you think you have found a critical bug or want to add a feature. It will help tremendously if you keep the scope of your PR limited to one feature. I maintain this repo voluntarily, so my free time is limited.
