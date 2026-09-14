# RegiManager Client Wallet (Expo)

Cross-platform **iOS + Android** wallet for end clients. Talks to production at:

**`https://www.regimanager.com`**

Bundle ID / package: `com.regimanager.clientwallet`

## 1. One-time setup

```bash
cd client-app
npm install
npm install -g eas-cli
npx eas login
```

---

## 2. Install on iPhone (EAS cloud build)

You are on Windows, so iOS builds run in **Expo’s cloud** (no Mac/Xcode required for the build itself).

### A. Apple requirements

You need an **Apple Developer Program** account ($99/year):

1. [developer.apple.com](https://developer.apple.com) → enroll
2. Have access to create certificates / profiles for `com.regimanager.clientwallet`

On the **first** iOS build, EAS will ask to log into Apple and can generate credentials for you (recommended).

### B. Build an installable iOS app (internal / TestFlight-style)

```bash
cd client-app
npx eas build -p ios --profile preview
```

Or:

```bash
npm run build:ios:preview
```

When the build finishes:

1. Open the Expo build page link
2. Install via the QR code / link on the iPhone (internal distribution), **or**
3. For App Store / TestFlight: use production profile + submit (below)

### C. Production / TestFlight / App Store

```bash
npx eas build -p ios --profile production
npx eas submit -p ios --profile production
```

Fill in App Store Connect app details first (create the app with bundle ID `com.regimanager.clientwallet`).

### D. Faster day-to-day testing (Expo Go on iPhone)

1. Install **Expo Go** from the App Store  
2. On your PC:

```bash
cd client-app
npx expo start
```

3. Scan the QR code with the Camera app / Expo Go (same Wi‑Fi)

> Expo Go is for quick UI tests. Clients should install a real **EAS build**, not Expo Go.

---

## 3. Install on Android (APK)

```bash
cd client-app
npx eas build -p android --profile preview
```

Download the **.apk** from the Expo link → install on the phone.

---

## 4. Build both platforms

```bash
npx eas build -p all --profile preview
```

---

## 5. Production API URL

Already set to:

```bash
EXPO_PUBLIC_API_BASE_URL=https://www.regimanager.com
```

in `.env` and as the app default. Restart Expo (`npx expo start -c`) after changing env.

---

## 6. Make login work on the live site

The phone app calls `https://www.regimanager.com/api/client/...`.

After deploy:

1. Run migrations on production: `python manage.py migrate`
2. In CRM → client profile → **Client App Access** → set PIN → enable
3. Give the client: **Client App Portal No.** + phone/email + PIN
4. Sign in from the app

| Field | Value |
|-------|--------|
| Client App Portal No. | Short 6-digit org code (`Organization.client_app_portal_no`) |
| Phone or email | Client phone / email on file |
| PIN | Staff-set PIN |

API docs: [`docs/CLIENT_APP_API.md`](../docs/CLIENT_APP_API.md)

---

## Local Django override (optional)

```bash
EXPO_PUBLIC_API_BASE_URL=http://192.168.x.x:8000
```

Use your PC LAN IP for a physical phone talking to local Django.
