const { execFileSync } = require("node:child_process");
const { realpathSync } = require("node:fs");

const identityKey = "CARTWHEEL_BUILD_SOURCE_SHA";
if (Object.prototype.hasOwnProperty.call(process.env, identityKey)) {
  throw new Error(`${identityKey} must come from the fixture Git checkout`);
}

// Use fixed Git arguments and discard Git environment overrides supplied by a caller.
const gitEnv = { ...process.env };
for (const key of Object.keys(gitEnv)) {
  if (key.startsWith("GIT_")) delete gitEnv[key];
}

function git(...args) {
  return execFileSync("git", args, {
    cwd: __dirname,
    env: gitEnv,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  }).trim();
}

if (realpathSync(git("rev-parse", "--show-toplevel")) !== realpathSync(__dirname)) {
  throw new Error("Cartwheel must build from its standalone fixture Git checkout");
}
if (git("status", "--porcelain=v1", "--untracked-files=all") !== "") {
  throw new Error("Cartwheel build requires a clean Git checkout");
}
const sourceSha = git("rev-parse", "--verify", "HEAD");
if (!/^[0-9a-f]{40}$/.test(sourceSha)) {
  throw new Error("Cartwheel build requires a full Git HEAD SHA");
}

module.exports = {
  env: { [identityKey]: sourceSha },
};
