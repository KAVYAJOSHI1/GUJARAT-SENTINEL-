const { Config } = require("@remotion/cli/config");

Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
Config.setChromiumOpenGlRenderer("angle");

// This host already has a real Chrome install — point Remotion at it
// directly instead of trying to download its own headless shell.
if (process.env.SENTINEL_CHROME_PATH) {
  Config.setBrowserExecutable(process.env.SENTINEL_CHROME_PATH);
}
