# Replydesk: AI email replies

Replydesk reads your inbox, writes a personalized reply to each new email using answers you've saved ahead of time, and lets you review, adjust and send each one from a single dashboard.

- **Login first.** Each person has their own account, and nobody can see another person's mail or answers.
- **Fetches email** from any IMAP mailbox (Gmail, Outlook, Zoho, Yahoo, cPanel hosting and others) and **sends replies** over SMTP, threaded under the original email.
- **Drafts automatically.** New emails get an AI draft in the background. Your own messages and no-reply senders are skipped.
- **Uses your saved answers.** You save common questions and their answers. The AI uses them as the facts but writes each reply fresh for the sender. If an email asks something your answers don't cover, the AI flags it instead of making up an answer.
- **Adjusts with prompts.** Type an instruction ("mention weekend hours"), click one of your saved prompt buttons, or pick one of the three prompts the AI suggests for that email.

---

## Contents

1. [How it works](#1-how-it-works)
2. [Prerequisites](#2-prerequisites)
3. [Backend setup](#3-backend-setup)
4. [Frontend setup](#4-frontend-setup)
5. [Run the app](#5-run-the-app)
6. [First-time walkthrough](#6-first-time-walkthrough)
7. [Connecting a mailbox](#7-connecting-a-mailbox)
8. [Configuration reference](#8-configuration-reference)
9. [API reference](#9-api-reference)
10. [Project structure](#10-project-structure)
11. [Deploying to production](#11-deploying-to-production)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. How it works

```
 Browser (React, :5173)
        │  /api/*  (Vite dev proxy, same-origin session cookie)
        ▼
 FastAPI backend (:8000) ──── SQLite  backend/data/app.db
        │            │
        │            └──── OpenAI API  (writes the drafts)
        ├── IMAP  ─── reads INBOX (read-only, nothing gets marked as read)
        └── SMTP  ─── sends the replies you approve
```

1. You click **Check for new mail**. The backend logs in to your mailbox over IMAP and copies the newest messages it hasn't seen yet.
2. For each new email, a background task sends the AI the email, your saved answers and your profile (name, tone, signature, business details). The AI returns three things: a draft, a note listing anything to check, and three suggested refinement prompts.
3. The email moves to **Ready to review**. You can edit the draft, rewrite it with a prompt, or send it. Sending goes over SMTP with `In-Reply-To` and `References` headers, so the reply lands in the same thread.

> SMTP only *sends* mail. Reading the inbox always uses IMAP, so the app needs both sets of server details.

---

## 2. Prerequisites

| Tool | Version | Check |
|---|---|---|
| Python | 3.12 or newer | `python --version` |
| Node.js | 18 or newer (tested on 24) | `node -v` |
| npm | comes with Node | `npm -v` |
| OpenAI API key | with billing enabled | https://platform.openai.com/api-keys |
| A mailbox with IMAP access | plus an app password (see [section 7](#7-connecting-a-mailbox)) | |

---

## 3. Backend setup

All commands run from the project root.

### 3.1 Create a virtual environment and install packages

**Windows (PowerShell)**
```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

> If PowerShell blocks `Activate.ps1`, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, or use `.venv\Scripts\activate.bat` from Command Prompt.

**macOS / Linux**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

This installs FastAPI, Uvicorn, the OpenAI SDK, bcrypt, cryptography, pydantic, email-validator and python-dotenv.

### 3.2 Create the `.env` file

```powershell
copy .env.example .env      # macOS/Linux: cp .env.example .env
```

Open `backend/.env` and set your key:

```ini
OPENAI_API_KEY=sk-proj-your-key-here
# OPENAI_MODEL=gpt-5.5
# APP_SECRET_KEY=
```

`.env` is in `.gitignore`. **Never commit it, and never paste the key into chats or issues.** If a key gets exposed, revoke it and create a new one.

### 3.3 Start the backend

```bash
uvicorn app.main:app --reload --port 8000
```

On first start the backend creates `backend/data/`, which holds:
- `app.db`: the SQLite database (tables are created automatically)
- `secret.key`: the encryption key for stored mailbox passwords (only created if `APP_SECRET_KEY` is not set)

Check that it's running by opening http://127.0.0.1:8000/api/auth/me. It should return `{"detail":"Not logged in"}`. Interactive API docs are at http://127.0.0.1:8000/docs.

---

## 4. Frontend setup

Open a **second terminal**:

```bash
cd frontend
npm install
```

This installs React 19, React Router and Vite. There's nothing to configure. In development, Vite forwards every `/api/*` request to `http://127.0.0.1:8000` (see `frontend/vite.config.js`), so the browser and the API share one origin and the login cookie just works.

---

## 5. Run the app

You need both servers running at the same time:

| Terminal | Directory | Command |
|---|---|---|
| 1 | `backend` (venv activated) | `uvicorn app.main:app --reload --port 8000` |
| 2 | `frontend` | `npm run dev` |

Then open **http://localhost:5173**.

Other frontend scripts:

| Command | What it does |
|---|---|
| `npm run build` | Production build into `frontend/dist/` |
| `npm run preview` | Serve the production build locally |
| `npm run lint` | Run ESLint |

---

## 6. First-time walkthrough

1. **Create an account.** On the login screen, click *Create an account* and enter your name, email and a password (at least 8 characters).
2. **Connect your mailbox.** Go to **Settings → Mailbox**, click a provider button to fill in the server details, then enter your email address and **app password**. *Connect mailbox* tests both IMAP and SMTP before it saves anything.
3. **Set up how replies sound.** In **Settings → How replies sound**, add your tone (for example "warm, concise"), a short description of you or your business, and your signature.
4. **Add saved answers.** In **Answers**, add the questions people ask you most often and how you answer them. These are the only facts the AI will state, so be specific (prices, timelines, policies, links).
5. **Optional: add reply prompts.** **Prompts** comes with four buttons (More formal, Shorter, Decline politely, Ask for a call). Add your own, such as "Offer 10% off with code THANKS10".
6. **Check for new mail.** On the **Inbox**, click *Check for new mail*. New emails are drafted in the background and show up under **Ready to review**.
7. **Review and send.** Open an email and read the draft. Then:
   - Edit the draft directly in the reply box.
   - Type an instruction and click **Rewrite**, or click a prompt chip. Chips marked ✦ are suggested by the AI for that email.
   - Read any yellow **Check before sending** note. It lists things your answers didn't cover.
   - Click **Send reply**, or **Skip this email**.

---

## 7. Connecting a mailbox

Most providers block your normal password for IMAP/SMTP. Create an **app password** instead:

| Provider | Get an app password | IMAP | SMTP |
|---|---|---|---|
| Gmail / Google Workspace | Turn on 2-Step Verification, then go to https://myaccount.google.com/apppasswords | `imap.gmail.com` : 993 | `smtp.gmail.com` : 465 |
| Outlook / Microsoft 365 | https://account.microsoft.com/security → App passwords | `outlook.office365.com` : 993 | `smtp.office365.com` : 587 |
| Zoho Mail (India) | Zoho Accounts → Security → App passwords | `imap.zoho.in` : 993 | `smtp.zoho.in` : 465 |
| Yahoo | Account security → Generate app password | `imap.mail.yahoo.com` : 993 | `smtp.mail.yahoo.com` : 465 |
| cPanel / custom domain | Your normal mailbox password | `mail.yourdomain.com` : 993 | `mail.yourdomain.com` : 465 |

For Gmail, also make sure IMAP is enabled under Gmail **Settings → Forwarding and POP/IMAP**.

Connection rules the app follows:
- **IMAP:** port `993` uses SSL. Port `143` uses STARTTLS.
- **SMTP:** port `465` uses SSL. Any other port (usually `587`) uses STARTTLS.
- **Each check** reads the newest *N* emails in INBOX. *N* is the **Emails to check each time** setting (25 by default, 200 at most). Emails that are already stored are skipped.
- **Auto-drafting** can be turned off in Settings. Emails then land under **No draft**, and you click *Draft with AI* yourself.

> Some Microsoft 365 organizations turn off password-based IMAP. If you can't create an app password there, ask your admin, or use a different mailbox.

---

## 8. Configuration reference

All settings go in `backend/.env`:

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `OPENAI_API_KEY` | Yes | none | OpenAI key used to write the drafts |
| `OPENAI_MODEL` | No | `gpt-5.5` | Model used for drafts. Use `gpt-5.4-mini` for cheaper, faster drafts |
| `APP_SECRET_KEY` | No | generated into `data/secret.key` | Fernet key that encrypts stored mailbox passwords. Generate one with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |

> **Don't lose the encryption key.** If `data/secret.key` (or `APP_SECRET_KEY`) changes, saved mailbox passwords can't be decrypted, and every user has to re-enter theirs in Settings.

Things you can change in the code:

| What | Where |
|---|---|
| AI instructions (style, fact rules, sign-off) | `SYSTEM_PROMPT` in `backend/app/ai.py` |
| Default prompt buttons for new accounts | `DEFAULT_PRESETS` in `backend/app/main.py` |
| Which senders are never auto-drafted | `AUTOMATED_SENDER` regex in `backend/app/main.py` |
| How long a login lasts | `SESSION_DAYS` in `backend/app/security.py` (default 7) |
| Provider buttons on the Settings page | `PROVIDERS` in `frontend/src/pages/Settings.jsx` |

---

## 9. API reference

Every endpoint except register and login needs the `session` cookie, which is set when you log in. Full interactive docs are at `/docs`.

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/auth/register` | Create an account `{name, email, password}` and log in |
| POST | `/api/auth/login` | Log in `{email, password}` |
| POST | `/api/auth/logout` | End the session |
| GET | `/api/auth/me` | The logged-in user |
| PUT | `/api/profile` | Update `{name, signature, tone, about}` |
| GET / PUT | `/api/mail-account` | Read or save mailbox settings. PUT tests the connection first, and the password is never returned |
| GET / POST | `/api/knowledge` | List or add saved answers `{question, answer}` |
| PUT / DELETE | `/api/knowledge/{id}` | Edit or delete a saved answer |
| GET / POST | `/api/presets` | List or add prompt buttons `{label, text}` |
| DELETE | `/api/presets/{id}` | Delete a prompt button |
| POST | `/api/emails/sync` | Fetch new mail and start auto-drafting. Returns `{fetched, drafting}` |
| GET | `/api/emails?status=` | List emails. Status is one of `new`, `drafting`, `drafted`, `sent`, `ignored` |
| GET | `/api/emails/{id}` | One email with its draft |
| POST | `/api/emails/{id}/draft` | Write a draft `{instruction, revise}`. `revise: true` refines the current draft |
| PUT | `/api/emails/{id}/draft` | Save manual edits `{draft_body}` |
| POST | `/api/emails/{id}/send` | Send the reply `{draft_body}` |
| PATCH | `/api/emails/{id}` | Skip an email or restore it `{status: "ignored" \| "new"}` |
| GET | `/api/stats` | Counts per status, number of saved answers, and whether a mailbox is connected |

---

## 10. Project structure

```
Email_Reply/
├── README.md
├── .gitignore
├── backend/
│   ├── requirements.txt
│   ├── .env.example          # copy to .env
│   ├── .env                  # your secrets (git-ignored)
│   ├── data/                 # created at runtime: app.db, secret.key (git-ignored)
│   └── app/
│       ├── main.py           # FastAPI app and all routes
│       ├── ai.py             # OpenAI drafting: prompt, structured JSON output, errors
│       ├── mail_client.py    # IMAP fetch (read-only), HTML-to-text, SMTP send with threading
│       ├── security.py       # bcrypt passwords, session cookies, password encryption
│       └── db.py             # SQLite schema and connection helper
└── frontend/
    ├── package.json
    ├── vite.config.js        # dev proxy /api -> :8000
    ├── index.html
    └── src/
        ├── main.jsx          # entry point and router
        ├── App.jsx           # login check, protected routes, sidebar layout
        ├── api.js            # fetch wrapper with error handling
        ├── index.css         # all styles (responsive down to phone width)
        └── pages/
            ├── AuthPage.jsx  # login and register
            ├── Inbox.jsx     # dashboard: email list, reading pane, reply editor, prompt chips
            ├── Knowledge.jsx # saved Q&A answers
            ├── Presets.jsx   # reply prompt buttons
            └── Settings.jsx  # mailbox connection and profile
```

**Data model** (SQLite):

| Table | Holds |
|---|---|
| `users` | Accounts, bcrypt password hashes, profile, tone, signature |
| `sessions` | Login tokens with expiry |
| `mail_accounts` | IMAP/SMTP settings and the encrypted mailbox password |
| `knowledge` | Saved questions and answers |
| `prompt_presets` | Prompt buttons |
| `emails` | Fetched emails plus their draft, the AI's note, suggested prompts and status |

---

## 11. Deploying to production

The dev setup is meant for running on your own machine. To host it for other people:

1. **Build the frontend:** `cd frontend && npm run build`, which outputs static files to `frontend/dist/`.
2. **Run the backend without `--reload`:**
   ```bash
   uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
   ```
   Keep one worker. Background drafting runs inside the server process, and SQLite works best with a single writer.
3. **Put a reverse proxy in front** (Nginx or Caddy) on one domain over HTTPS. Serve `frontend/dist/` as static files, with a fallback to `index.html` for client-side routes, and forward `/api/` to `127.0.0.1:8000`. Example Nginx config:
   ```nginx
   server {
       server_name replydesk.example.com;
       root /srv/replydesk/frontend/dist;
       location /api/ { proxy_pass http://127.0.0.1:8000; proxy_set_header Host $host; }
       location / { try_files $uri /index.html; }
   }
   ```
4. **Harden it:**
   - Set `secure=True` in `_set_cookie()` in `backend/app/main.py`, so the cookie is only sent over HTTPS.
   - Set `APP_SECRET_KEY` in the environment instead of relying on `data/secret.key`, and back up `data/`.
   - Add rate limiting on `/api/auth/login`, for example at the proxy.
   - To check mail on a schedule instead of by button, call `POST /api/emails/sync` on a timer for each user, or add a scheduler such as APScheduler.

---

## 12. Troubleshooting

| Symptom | Fix |
|---|---|
| `Could not connect: [AUTHENTICATIONFAILED]` or `Username and Password not accepted` | Use an **app password**, not your normal password. Check that IMAP is enabled in the provider's settings |
| `Could not connect: timed out` or `getaddrinfo failed` | Wrong server name or port, or a firewall or network blocking ports 993, 465 or 587 |
| Drafts fail with "OpenAI API key is missing or invalid" | Check `OPENAI_API_KEY` in `backend/.env`, then restart the backend |
| "Rate limited (or out of credit) on OpenAI" | Add billing or credit at https://platform.openai.com/settings/organization/billing, or wait and try again |
| "AI service error (404)… model" | Your account can't use that model. Set `OPENAI_MODEL` to one it can, such as `gpt-5.4-mini` or `gpt-4.1` |
| An email is stuck on **Drafting** | The backend restarted mid-draft. Open the email and click **Draft with AI** |
| Every request returns 401 after login | Open the app at `http://localhost:5173` rather than `127.0.0.1:8000`, so requests go through the Vite proxy |
| Saved mailbox stopped working after moving servers | `data/secret.key` didn't move with the database. Copy it over, or re-enter the mailbox password in Settings |
| `Activate.ps1 cannot be loaded` | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| Port 8000 or 5173 already in use | Stop the other process, or use `--port 8001` for the backend (and update `vite.config.js`) or `npm run dev -- --port 5174` for the frontend |

To start over with a clean database, stop the backend and delete `backend/data/`. **This deletes all accounts, emails and saved answers.**
