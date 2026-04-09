# Recovery Guide (after hermes update)

If `hermes update` breaks things or you need to `git reset --hard`, just recreate the symlinks. All actual code lives in `waifu-sprites/` — hermes-agent only points to it.

---

## Step 1: Recreate symlinks

```bash
cd ~/.hermes/hermes-agent
ln -sf /path/to/waifu-sprites/src/waifu_hook.py waifu_hook.py
ln -sf /path/to/waifu-sprites/src/waifu.py waifu.py
```

## Step 2: Verify

```bash
cd ~/.hermes/hermes-agent && python3 -c "import waifu_hook; print(waifu_hook.WAIFU_URL)"
# Should print: http://<wsl2-host-ip>:8000/state
```

## Step 3: Launch

```bash
cd ~/.hermes/hermes-agent && python3 waifu.py
```

That's it. No code to recreate — it's all in `waifu-sprites/`.

---

## If waifu-sprites repo is also broken

```bash
cd /path/to/waifu-sprites
git status
git checkout -- .    # restore tracked files
# or
git pull             # get latest
```

Then re-do Step 1 above.

---

## Server startup

On Windows, start the servers manually or create bat files pointing to your `waifu-sprites/` directory:

```bat
:: TTS server
cd /d C:\path\to\waifu-sprites
python tts_server.py

:: Sprite server (separate terminal)
cd /d C:\path\to\waifu-sprites
node server.js
```
