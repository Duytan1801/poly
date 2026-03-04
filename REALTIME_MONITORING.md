# Real-Time Trade & Position Monitoring

## 🚀 Overview

The optimized CLI now includes real-time monitoring for HIGH/CRITICAL traders:

1. **Trade Notifications** - Alert on new trades > $5,000
2. **Position Holdings** - Update when PnL changes significantly
3. **Rate-Limited** - Deduplicates notifications with 60s window
4. **Batched Trades** - Groups rapid trades into single notification

---

## 📊 How It Works

### Trade Monitoring

```
Every 20 seconds (configurable):
  For each HIGH/CRITICAL trader:
    1. Fetch recent trades (last 100)
    2. Filter new trades since last check
    3. Filter trades ≥ $5,000
    4. Deduplicate by market (wait 60s per market)
    5. Group rapid trades within 60s window
    6. Send Discord notification to #trades-holding
```

### Position Monitoring

```
Every 5 minutes (configurable):
  For each HIGH/CRITICAL trader:
    1. Fetch current positions
    2. Filter positions ≥ $5,000 value
    3. Calculate total PnL and portfolio value
    4. Check if PnL changed ≥ $5,000 from last check
    5. Send summary to #trades-holding
```

---

## 🎮 Usage

### Basic Usage (Continuous Monitoring)

```bash
# Run indefinitely with default settings
uv run python -m poly.cli_optimized
```

**Default Behavior:**
- Trade polling: Every 20 seconds
- Position polling: Every 5 minutes
- Min trade size: $5,000
- PnL threshold: $5,000
- Deduplication: 60 seconds

### Custom Polling Intervals

```bash
# Check trades every 30s, positions every 10 minutes
uv run python -m poly.cli_optimized \
  --trade-poll-interval 30 \
  --position-poll-interval 600
```

### Testing Mode

```bash
# Short test with minimal wallets
uv run python -m poly.cli_optimized \
  --max-iterations 1 \
  --wallets-per-iteration 3 \
  --max-trades 50 \
  --trade-poll-interval 10 \
  --position-poll-interval 30
```

### Production Mode

```bash
# Run with optimized settings for 24/7 monitoring
uv run python -m poly.cli_optimized \
  --wallets-per-iteration 10 \
  --max-trades 1000 \
  --trade-poll-interval 15 \
  --position-poll-interval 300
```

---

## 📱 Discord Notifications

### Trade Notification Format

```
🎯 LIVE TRADE: 🔴 CRITICAL Risk Trader
Elite Trader executed a new position

Market: Will Bitcoin hit $100k by 2025?
Action: **BUY** YES
Size: **$5,420.00**
Price: **0.65**

Trader Stats:
  WR: 87.3% | Score: 9.1/10

🛰️ Poly Intel | 2 trades
```

### Position Summary Format

```
📊 POSITIONS: 🔴 CRITICAL Risk Trader
Current portfolio holdings with PnL breakdown

Portfolio Summary:
  Total Value: $125,430
  Total PnL: +$42,150
  Trader WR: 87.3% | Score: 9.1/10

1. Will Bitcoin hit $100k?
   YES | 🟢+$8,400
   Value: $32,000 | Size: $25,000 | Price: 0.65

2. Trump 2024 Winner?
   YES | 🟢+$6,200
   Value: $25,000 | Size: $20,000 | Price: 0.70

🛰️ Poly Intel | PnL Change: +$5,250
```

---

## ⚙️ Configuration

### CLI Arguments

| Argument | Description | Default | Range |
|----------|-------------|---------|-------|
| `--trade-poll-interval` | Seconds between trade polls | 20 | 10-300 |
| `--position-poll-interval` | Seconds between position polls | 300 | 60-3600 |
| `--wallets-per-iteration` | Wallets to discover per batch | 10 | 1-50 |
| `--max-trades` | Max trades per wallet to fetch | 100,000 | 100-1,000,000 |

### Hardcoded Constants

**In `trade_monitor.py`:**
```python
self.min_trade_size = 5000  # $5,000 minimum for notifications
self.deduplication_window = 60  # 60 seconds wait for same market
```

**In `position_monitor.py`:**
```python
self.pnl_change_threshold = 5000  # $5,000 PnL change to notify
self.position_size_min = 5000  # $5,000 minimum position to include
```

---

## 📈 Performance Impact

### API Usage

**Trade Monitoring:**
- Requests: ~0.5 req/s (10 wallets × 1 req / 20s)
- Within 200 req/10s limit (well within limits)

**Position Monitoring:**
- Requests: ~0.033 req/s (10 wallets × 1 req / 300s)
- Minimal impact on API limits

### Discord Rate Limiting

- Limit: ~50 messages per minute per channel
- Expected: 2-5 notifications per minute (trades) + occasional position updates
- With deduplication: < 3 messages per minute

### Memory Usage

- Trade tracking: ~5KB per wallet (timestamps, batches)
- Position tracking: ~20KB per wallet (positions, PnL history)
- Total: ~25KB × 500 wallets = ~12.5MB (negligible)

---

## 🔄 Monitoring Workflow

### Startup

```
1. System boots up
2. Discord bot initializes (if available)
3. Trade monitor starts background task
4. Position monitor starts background task
5. Discovery loop starts main task
6. All three run concurrently
```

### Continuous Operation

```
Discovery Loop:
  - Discover new wallets from on-chain events
  - Analyze and score traders
  - Add HIGH/CRITICAL to monitoring
  - Sleep 2 seconds between iterations

Trade Monitor (Background):
  - Sleep for poll_interval (20s)
  - Check for new trades on monitored wallets
  - Filter significant trades (≥ $5,000)
  - Deduplicate and batch trades
  - Send Discord notifications
  - Repeat

Position Monitor (Background):
  - Sleep for poll_interval (300s)
  - Fetch positions for monitored wallets
  - Calculate PnL changes
  - Notify if significant change (≥ $5,000)
  - Repeat
```

### Shutdown

```
1. User presses Ctrl+C
2. All tasks receive Cancel signal
3. Graceful shutdown - send remaining notifications
4. Close Discord client
5. Close GraphQL client
6. Clean exit
```

---

## 🛡️ Error Handling

### Discord Bot Issues

- If Discord bot unavailable: System runs in analysis-only mode
- Trade/position monitoring paused (no notifications)
- Discovery loop continues normally

### API Failures

- Trade fetch fails: Log error, retry in next interval
- Position fetch fails: Log error, retry in next interval
- No data loss - state preserved between intervals

### Deduplication Protection

- Same market notified twice within 60s window: Second notification muted
- Prevents notification spam from rapid trading
- Tracked per wallet per market

---

## 📊 Notification Examples

### Scenario 1: Single Large Trade

```
Trader: 0x1234... (CRITICAL - 9.5/10)
Place: BUY $7,500 on "Will Bitcoin hit $100k?"
Result: Immediate notification to #trades-holding
Next check: Same market muted for 60s
```

### Scenario 2: Rapid Trading (Burst)

```
Trader: 0x5678... (HIGH - 8.2/10)
Time T+0s: BUY $5,200 on Market A
Time T+10s: BUY $6,100 on Market A
Time T+20s: BUY $5,800 on Market A
Time T+40s: Window expires
Result: Single notification: "3 trades total: $17,100 BUY Market A"
```

### Scenario 3: Position PnL Change

```
Trader: 0xabcd... (CRITICAL - 9.1/10)
Positions: 5 open markets, total value $125,000
Last PnL: +$40,000 → Current PnL: +$48,500
Change: +$8,500 (exceeds $5,000 threshold)
Result: Position summary sent to #trades-holding
```

---

## 🧪 Testing

### Test Trade Monitoring

```bash
# Run for 2 iterations with short intervals
uv run python -m poly.cli_optimized \
  --max-iterations 2 \
  --wallets-per-iteration 5 \
  --max-trades 100 \
  --trade-poll-interval 10
```

### Test Position Monitoring

```bash
# Run for 3 iterations to catch position checks
uv run python -m poly.cli_optimized \
  --max-iterations 3 \
  --wallets-per-iteration 5 \
  --max-trades 100 \
  --position-poll-interval 20
```

### Test Full Monitoring

```bash
# Run in background for 10 minutes
timeout 600 uv run python -m poly.cli_optimized \
  --wallets-per-iteration 10 \
  --max-trades 500 \
  --trade-poll-interval 15 \
  --position-poll-interval 60
```

---

## 🐛 Troubleshooting

### No Trade Notifications

**Problem:** Not receiving trade notifications

**Solutions:**
1. Verify Discord bot is running (check console for "⚠️ Discord bot not configured")
2. Wait for first discovery cycle to find HIGH/CRITICAL traders
3. Ensure traders have made trades ≥ $5,000
4. Check trade log level: `export POLY_LOG_LEVEL=DEBUG`

### No Position Updates

**Problem:** Not receiving position summaries

**Solutions:**
1. Ensure monitored traders have open positions ≥ $5,000
2. Wait for PnL to change ≥ $5,000 (first update may take time)
3. Check position polling not too frequent (default: 5 min)
4. Verify API returning correct position data

### Too Many Notifications

**Problem:** Getting spammed with notifications

**Solutions:**
1. Increase `--trade-poll-interval` to 30 or 60 seconds
2. Increase deduplication window in code (currently 60s)
3. Increase PnL threshold in code (currently $5,000)
4. Lower `--wallets-per-iteration` to reduce monitored trader count

---

## 📈 Performance Tips

### Reduce API Usage

```bash
# Increase polling intervals
--trade-poll-interval 30      # Check trades every 30s
--position-poll-interval 600  # Check positions every 10 min
```

### Reduce Discord Spam

```bash
# Increase deduplication window
# Edit trade_monitor.py line 23:
self.deduplication_window = 120  # 120 seconds instead of 60

# Increase PnL threshold
# Edit position_monitor.py line 23:
self.pnl_change_threshold = 10000  # $10,000 instead of $5,000
```

### Monitor Fewer Wallets

```bash
# Reduce discovery rate
--wallets-per-iteration 5  # Discover 5 wallets per batch
```

---

## 🚀 Production Deployment

### Systemd Service

```ini
[Unit]
Description=Polymarket Intel Monitor
After=network.target

[Service]
Type=simple
User=poly
WorkingDirectory=/home/poly/poly
Environment="PATH=/home/poly/.local/bin:/usr/bin:/bin"
ExecStart=/home/poly/.local/bin/uv run python -m poly.cli_optimized
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### Screen/Tmux

```bash
# Start new session
screen -S poly-monitor

# Run in background
uv run python -m poly.cli_optimized

# Detach: Ctrl+A, D
# Reattach: screen -r poly-monitor
```

### Docker Compose

```yaml
version: '3.8'
services:
  poly-monitor:
    build: .
    command: python -m poly.cli_optimized
    env_file: .env
    restart: unless-stopped
```

---

## 📝 Summary

The real-time monitoring system provides:

✅ **Trade Notifications** - Alert on significant trades (> $5,000)
✅ **Position Updates** - Update when PnL changes (> $5,000)
✅ **Smart Deduplication** - Prevent notification spam (60s window)
✅ **Batched Alerts** - Group rapid trades for clarity
✅ **Rate-Limited** - Respect API and Discord limits
✅ **Production Ready** - Robust error handling and graceful shutdown

**Next Steps:**
1. Test with small iteration count
2. Monitor Discord output for 10-15 minutes
3. Adjust intervals based on activity
4. Run continuously in production

**Status:** ✅ READY FOR PRODUCTION
