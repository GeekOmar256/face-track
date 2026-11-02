# BioAttendance web app (Firebase)

A small admin + student web app, hosted on Firebase, that talks to the same
Firestore project the Pi syncs to. No build step - plain HTML/CSS/JS,
deployed as static files via Firebase Hosting.

- **Admin**: sign in with email/password, view/edit/remove students,
  pre-register a new student, remotely start/stop an attendance session,
  view session history.
- **Student**: enter a Student ID, see their own attendance stats. No
  password - see the security note below before relying on this for
  anything sensitive.

It never writes attendance data directly. Every admin action creates a
document in the `commands` collection; the Pi (running
`app/web/firebase_command_worker.py`) picks it up, does the real work
locally, and marks it done/error. This keeps the Pi as the single source
of truth and avoids the web app and the Pi fighting over the same records.

## 1. Create the Firebase project (if you haven't already)

1. [Firebase Console](https://console.firebase.google.com) -> Add project.
2. Enable **Firestore** (Build -> Firestore Database -> Create database).
3. Enable **Authentication** -> Sign-in method -> **Email/Password**.
4. Project settings -> General -> "Your apps" -> add a **Web app**. Copy
   the config object it gives you into `public/firebase-config.js`
   (replacing the placeholder values). These are public identifiers, safe
   to commit.
5. Project settings -> Service accounts -> Generate new private key. This
   is the file the **Pi** needs at `data/firebase_credentials.json` (see
   the main `README.md`). Never put this file here in `webapp/` or commit
   it anywhere.

## 2. Create the first admin account

The web app has no sign-up flow by design - admins are provisioned
manually so a stranger can't just register themselves as one.

1. Firebase Console -> Authentication -> Users -> Add user. Set an email
   and password for yourself.
2. Copy that user's **UID** from the Users list.
3. Firestore Database -> Start collection -> collection ID `admins` ->
   document ID = that UID -> any field (e.g. `role: "admin"`) -> Save.

Repeat step 3 for each additional admin. There's no limit, but each one
needs an Authentication user *and* a matching `admins/{uid}` doc - having
only one or the other won't grant access.

## 3. Deploy

```bash
npm install -g firebase-tools   # one-time
firebase login
cd webapp
firebase use --add                     # pick your project, call it "default"
firebase deploy --only hosting,firestore:rules
```

Firebase Hosting gives you a URL like `https://YOUR-PROJECT.web.app`. Open
it, go to `/admin.html` and sign in with the account from step 2.

## 4. Point the Pi at the same project

On the Pi, `app/firebase_sync.py` needs the **service account** JSON
(step 1.5 above) at `data/firebase_credentials.json`. Once that's in
place and the app is restarted, `app/web/firebase_command_worker.py`
starts listening for commands from this web app automatically - see the
"Firebase sync" section of the main `README.md`.

## Security notes - read before relying on this for anything sensitive

- **Students have no password.** By design (per project requirements),
  a student identifies themselves with just their Student ID. Firestore
  rules (`firestore.rules`) can't cryptographically verify that, so
  anyone who knows or guesses a valid Student ID can view that student's
  name and attendance records. To limit the damage: the `student_stats`
  collection is the *only* thing a signed-out visitor can read, it's
  per-student only (never RFID UIDs, fingerprint slots, or other
  students' data), and `list` is disabled on it so the whole roster can't
  be scraped in one query - only one known ID at a time. If this ever
  needs to be tightened, add a PIN or a real account per student; nothing
  else in the architecture would need to change.
- **Admin accounts are provisioned manually**, not self-service. That's
  intentional - don't add a sign-up form without also rethinking the
  `admins` collection's write rule (currently `false` from the client, on
  purpose).
- The `commands` collection accumulates over time (nothing deletes old
  ones). Harmless for a school-sized deployment; if it grows large,
  add a scheduled Cloud Function to prune `status != 'pending'` docs
  older than a few days.
