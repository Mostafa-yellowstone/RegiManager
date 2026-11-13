// The repo is public, so google-services.json stays out of git. EAS builds get it from the
// GOOGLE_SERVICES_JSON file variable; local builds use the copy in this folder.
module.exports = ({ config }) => ({
  ...config,
  android: {
    ...config.android,
    googleServicesFile: process.env.GOOGLE_SERVICES_JSON ?? './google-services.json',
  },
});
