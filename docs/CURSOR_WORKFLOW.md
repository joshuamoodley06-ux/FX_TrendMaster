# Cursor Workflow

## Open this repo

Open the root folder in Cursor:

```text
FX_TrendMaster/
```

Not a random old zip extraction folder. Not OneDrive chaos if avoidable.

## Recommended Cursor usage

Work one module at a time:

```text
electron/src/main.tsx
backend/main.py
processor/core/ledger_resolver.py
```

Do not ask Cursor to rewrite the entire project in one go unless you enjoy watching software invent mythology.

## GitHub flow

```text
1. Edit in Cursor
2. Run/test locally or on VPS
3. Commit in GitHub Desktop
4. Push to private GitHub repo
```

## Never commit

```text
.env
*.db
node_modules/
dist/
build/
logs/
```
