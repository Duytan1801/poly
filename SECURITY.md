# Security Guide 🔐

## Environment Variables & Secrets

### Important Security Practices

**✅ DO:**
- Use `.env` files for local development
- Add `.env` to `.gitignore` (already done)
- Use `.env.example` as a template (safe to commit)
- Set environment variables in production (CI/CD, cloud platforms)

**❌ DO NOT:**
- Hardcode tokens or API keys in source code
- Commit `.env` files to git
- Share tokens in chat, emails, or documentation
- Push secrets to GitHub (even private repos)

---

## Setup Instructions

### 1. Local Development

The `.env` file is already created with your tokens:
```bash
# File: .env (already exists, ignored by git)
DISCORD_BOT_TOKEN=your_discord_bot_token_here
ALCHEMY_API_KEY=your_alchemy_api_key_here
```

The code automatically loads from `.env` using `python-dotenv`.

### 2. Production Deployment

Set environment variables on your platform:

**Heroku:**
```bash
heroku config:set DISCORD_BOT_TOKEN=your_token_here
heroku config:set ALCHEMY_API_KEY=your_key_here
```

**Railway:**
```bash
railway variables set DISCORD_BOT_TOKEN=your_token_here
railway variables set ALCHEMY_API_KEY=your_key_here
```

**Docker:**
```bash
docker run -e DISCORD_BOT_TOKEN=your_token_here \
           -e ALCHEMY_API_KEY=your_key_here \
           your-image
```

**Systemd:**
```ini
# /etc/systemd/system/poly.service
[Service]
Environment="DISCORD_BOT_TOKEN=your_token_here"
Environment="ALCHEMY_API_KEY=your_key_here"
```

---

## What's Protected

### Files Ignored by Git

`.gitignore` includes:
```
.env
*.pyc
__pycache__/
.data/
*.log
node_modules/
```

### Files Safe to Commit

- `.env.example` - Template without real values
- `*.py` - Source code
- `*.md` - Documentation
- `test_*.py` - Test files
- `.gitignore` - Git ignore rules

---

## If You Accidentally Commit a Secret

### Immediate Steps:

1. **Rotate the token immediately:**
   - Discord: Go to Developer Portal → Bot → Reset Token
   - Alchemy: Go to Dashboard → API Keys → Regenerate

2. **Remove from git history:**
   ```bash
   # Remove file from entire git history
   git filter-branch --force --index-filter \
     'git rm --cached --ignore-unmatch .env' \
     --prune-empty --tag-name-filter cat -- --all

   # Force push (if already pushed)
   git push origin --force --all
   ```

3. **Verify `.env` is in `.gitignore:**
   ```bash
   grep ".env" .gitignore
   ```

---

## Security Checklist

Before pushing to GitHub:

- [ ] `.env` is in `.gitignore`
- [ ] `.env` file exists locally (not in git)
- [ ] `.env.example` exists (template for others)
- [ ] No hardcoded tokens in source code
- [ ] No tokens in commit messages or comments
- [ ] No tokens in screenshots or documentation

---

## Token Permissions

### Discord Bot Token

Your bot token has permissions to:
- Send messages to specific channels
- Read message history
- Use embeds and formatting

**Required permissions:** Send Messages, Embed Links

**Channel:** The bot sends to channel ID `1478038183873740972`

### Alchemy API Key

Used for:
- Wallet clustering analysis
- Transaction history lookups
- On-chain data queries

**Rate limits:** Check your plan at alchemy.com

---

## Monitoring & Rotation

### When to Rotate Tokens:

- ✅ Token accidentally exposed
- ✅ Security incident
- ✅ Team member leaves
- ✅ Regular security rotation (quarterly)

### How to Rotate Discord Token:

1. Go to: https://discord.com/developers/applications
2. Select your application
3. Navigate to "Bot" section
4. Click "Reset Token"
5. Copy new token to `.env`
6. Restart your application

### How to Rotate Alchemy Key:

1. Go to: https://dashboard.alchemy.com/
2. Navigate to your app
3. Go to "API Keys"
4. Click "Regenerate Key"
5. Copy new key to `.env`
6. Restart your application

---

## Best Practices Summary

1. **Never commit secrets** - Use `.env` files
2. **Use `.gitignore`** - Prevent accidental commits
3. **Rotate regularly** - Quarterly token rotation
4. **Monitor usage** - Check for suspicious activity
5. **Least privilege** - Only necessary permissions
6. **Audit access** - Review who has tokens
7. **Backup `.env`** - Keep a secure backup (not in git)
8. **Document** - Use `.env.example` for setup

---

## Support

If you suspect a security issue:

1. Rotate tokens immediately
2. Review git history for exposure
3. Check API usage logs
4. Contact platform support if needed

---

**Remember:** Security is everyone's responsibility. When in doubt, rotate the token!
