# How to Upload GameOptimizerPro to GitHub

Step-by-step guide for first-time GitHub upload.

---

## Step 1 — Create the Repository

1. Go to [github.com/new](https://github.com/new)
2. Fill in:
   - **Repository name:** `GameOptimizerPro`
   - **Description:** `Windows & Gaming Optimizer — GPU Auto-Tuner, Tweaks, BIOS Guide`
   - **Visibility:** Public *(so others can find and use it)*
   - ✅ Check **"Add a README file"** — uncheck this, we have our own
   - Leave everything else default
3. Click **"Create repository"**

---

## Step 2 — Install Git

If you don't have Git installed:

1. Download from [git-scm.com/download/win](https://git-scm.com/download/win)
2. Run the installer with default settings
3. Open **Git Bash** (right-click on Desktop → "Git Bash Here")

---

## Step 3 — Upload the Files

Open **Git Bash** and run these commands one by one:

```bash
# 1. Go to your GameOptimizerPro folder
cd "C:/Tools/GameOptimizerPro"

# 2. Initialize a git repository
git init

# 3. Connect to your GitHub repository
git remote add origin https://github.com/FloDePin/GameOptimizerPro-v2.1.1.git

# 4. Stage all files
git add .

# 5. Create the first commit
git commit -m "Initial release: GameOptimizerPro v2.0"

# 6. Rename branch to main (GitHub standard)
git branch -M main

# 7. Push to GitHub
git push -u origin main
```

GitHub will ask for your username and password.
> **Note:** Use a **Personal Access Token** as the password, not your GitHub password.
> Create one at: Settings → Developer settings → Personal access tokens → Generate new token
> Required scopes: `repo`

---

## Step 4 — Create a Release

1. On your repository page, click **"Releases"** (right sidebar)
2. Click **"Create a new release"**
3. Fill in:
   - **Tag:** `v2.0`
   - **Release title:** `GameOptimizerPro v2.0`
   - **Description:** Copy from `CHANGELOG.md` — the `[2.0]` section
4. Under **"Attach binaries"** — drag and drop your `GameOptimizerPro_v2.0_final.zip`
5. Click **"Publish release"**

---

## Step 5 — Add a .gitignore (optional but recommended)

Create a file called `.gitignore` in your project folder with this content:

```
# Python
__pycache__/
*.pyc
*.pyo
*.pyd

# GameOptimizerPro runtime data
logs/
profiles/*.json
assets/

# Windows
Thumbs.db
desktop.ini
```

Then run:
```bash
git add .gitignore
git commit -m "Add .gitignore"
git push
```

---

## Updating Later

When you make changes and want to push them:

```bash
cd "C:/Tools/GameOptimizerPro"
git add .
git commit -m "Describe what you changed"
git push
```

For a new release, repeat Step 4 with the new version tag (e.g. `v2.1`).

---

## Repository URL

Your project will be live at:
**https://github.com/FloDePin/GameOptimizerPro-v2.1.1**
