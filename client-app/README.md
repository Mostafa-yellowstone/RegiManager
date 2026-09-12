# RegiManager Client Wallet (Expo)

Cross-platform **iOS + Android** wallet for end clients. Talks to production at:

**`https://www.regimanager.com`**

## 1. Install on Android (recommended: installable APK)

### A. One-time setup on your PC

```bash
cd client-app
npm install
npm install -g eas-cli
npx eas login
npx eas build:configure
```

### B. Build an APK you can sideload

```bash
npx eas build -p android --profile preview
```

When the build finishes, open the link Expo gives you → download the **.apk** → copy it to the phone → open the file → Allow install from that source → Install.

That installs **RegiManager Wallet** as a real Android app (not Expo Go).

### C. Faster day-to-day testing (Expo Go)

1. Install **Expo Go** from the Play Store.
2. On your PC:

```bash
cd client-app
npx expo start
```

3. Scan the QR code with Expo Go (same Wi‑Fi), or press `a` if an emulator is running.

> Expo Go is fine for UI testing. For a normal “install the app” experience for clients, use the **APK** path above.

---

## 2. Production API URL

Already set to:

```bash
EXPO_PUBLIC_API_BASE_URL=https://www.regimanager.com
```

in `.env` and as the app default. Restart Expo (`npx expo start -c`) after changing env.

---

## 3. Make login work on the live site

The phone app calls `https://www.regimanager.com/api/client/...`.

That API must be **deployed** on the server (this repo’s client wallet backend + migration `0184`). Until deploy, login returns **404**.

After deploy:

1. Run migration on production: `python manage.py migrate`
2. In CRM → client profile → **Client App Access** → set 4–8 digit PIN → enable
3. Give the client: **portal code** + phone/email + PIN
4. Sign in from the app

---

## 4. Sign-in fields

| Field | Value |
|-------|--------|
| Agency portal code | `Organization.portal_token` |
| Phone or email | Client phone / email on file |
| PIN | Staff-set PIN |

API docs: [`docs/CLIENT_APP_API.md`](../docs/CLIENT_APP_API.md)

---

## 5. Documents / ID cards

Files download with the session token, then open via the Android share sheet (PDF/image viewers).

---

## Local Django override (optional)

```bash
EXPO_PUBLIC_API_BASE_URL=http://192.168.x.x:8000
```

Use your PC LAN IP for a physical phone talking to local Django.
