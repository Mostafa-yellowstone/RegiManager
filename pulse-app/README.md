# RegiManager Pulse (Expo)

Owner CRM mobile app. Production API:

**`https://www.regimanager.com`**

Android package: `com.regimanager.pulse`

> Expo Go is for quick testing only. Play Store installs need a real **EAS Android build** (AAB).

## 1. One-time setup

```bash
cd pulse-app
npm install
npm install -g eas-cli
npx eas login
npx eas init
```

Link or create the EAS project under `mostafaelbigarmiis-team` so `app.json` gets a real `extra.eas.projectId`.

## 2. Google Play Console (required for store upload)

1. Open [Google Play Console](https://play.google.com/console) (one-time **$25** registration).
2. **Create app** → name **RegiManager Pulse**, package `com.regimanager.pulse`.
3. Complete the dashboard checklist (privacy policy, content rating, target audience, etc.) before promoting past internal testing.

## 3. Build a Play Store AAB (Android)

```bash
cd pulse-app
npm run build:android:production
```

Or:

```bash
npx eas build -p android --profile production --no-wait
```

EAS manages the Android upload keystore on first build. When finished, download the **.aab** from the Expo build page, or submit with EAS (below).

### Internal / sideload APK (testers)

```bash
npm run build:android:preview
```

Install the APK from the Expo link (not for Play Store production).

## 4. Upload to Play Store

### Option A — manual

1. Play Console → RegiManager Pulse → **Testing → Internal testing** (or Production)
2. Create a release → upload the **.aab** from EAS
3. Review and roll out

### Option B — EAS Submit (after service account)

1. Create a Google Cloud **service account** JSON key
2. Link it in Play Console → Setup → API access, grant release permission
3. Save the key as `pulse-app/google-service-account.json` (gitignored)
4. Point `eas.json` submit profile at that file, then:

```bash
npm run submit:android:production
# or: npx eas submit -p android --profile production --latest
```

Default submit track is **internal** + **draft** so you can finish listing details in Play Console before going live.

## Store listing icon (important)

Google Play requires the **high-res icon in Play Console** to match the **launcher icon** in the AAB.

Use this exact file for Play Console → Store listing → App icon:

`pulse-app/store-assets/play-store-icon.png`

It is the same asset baked into the production build as the launcher icon.

## 5. iOS

Not configured for store release yet — Android / Play Store only for now.

## Scripts

| Script | Purpose |
|--------|---------|
| `npm run build:android:preview` | Internal APK |
| `npm run build:android:production` | Play Store AAB |
| `npm run submit:android:production` | Upload latest AAB via EAS |
