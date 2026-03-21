# The Moon Ecosystem — Deploy Guide

## Prerequisites

- Python 3.12.3+
- Node v22.14.0+ (for MCP tools)
- LibreOffice v25.8.5.2 (for document export)
- mmdc v11.12.0 (for Mermaid diagrams)

## Initial Setup

```bash
# 1. Clone and enter directory
cd "/home/johnathan/Área de trabalho/The Moon"

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
# Edit .env with your real API keys

# 4. Validate environment
python3 moon_sync.py --health

# 5. Run test suite
python3 -m pytest tests/ --tb=no -q
```

## Production Deployment

### Option 1: Manual Daemon Start

```bash
# Validate environment
python3 moon_sync.py --health

# Start daemon in foreground
python3 moon_sync.py --serve
```

### Option 2: Systemd Service (Recommended)

```bash
# 1. Copy service file to systemd
sudo cp the-moon.service /etc/systemd/system/the-moon.service

# 2. Update user and paths in the service file if needed
sudo nano /etc/systemd/system/the-moon.service

# 3. Enable and start service
sudo systemctl daemon-reload
sudo systemctl enable the-moon.service
sudo systemctl start the-moon.service

# 4. Check status
sudo systemctl status the-moon.service
sudo journalctl -u the-moon.service -f  # follow logs
```

## Environment Validation

```bash
# Check system health
python3 moon_sync.py --health

# Schedule a task
python3 moon_sync.py --schedule "sports_analytics:report:brasileirao:3"

# Run tests
python3 -m pytest tests/ --tb=short
```

## Service Management

```bash
# Start
sudo systemctl start the-moon.service

# Stop
sudo systemctl stop the-moon.service

# Restart
sudo systemctl restart the-moon.service

# View logs
sudo journalctl -u the-moon.service -f

# Check status
sudo systemctl status the-moon.service
```

## Troubleshooting

### Common Issues

1. **Missing API Keys**: Verify all required keys in `.env` are set
2. **Permission Errors**: Ensure the user running the service has access to the project directory
3. **Python Dependencies**: Make sure virtual environment is activated or packages installed globally

### Health Checks

The daemon performs periodic health checks and reports status via:
- Internal heartbeat logs (every 60s)
- `moon_sync.py --health` command
- Observable metrics via MoonObserver

## Production Best Practices

1. **Security**:
   - Never commit `.env` files to Git
   - Use least-privilege principle for service user
   - Regularly rotate API keys

2. **Monitoring**:
   - Monitor systemd service status
   - Check application logs regularly
   - Set up alerts for failed tasks

3. **Backups**:
   - Back up `data/` directory regularly
   - Version control for code changes
   - Document environment variables securely

## Updating

```bash
# 1. Pull latest changes
git pull origin main

# 2. Update dependencies if needed
pip install -r requirements.txt

# 3. Restart service
sudo systemctl restart the-moon.service
```