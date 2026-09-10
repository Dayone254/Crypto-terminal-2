/**
 * Cross-platform build wrapper.
 *
 * Preloads scripts/node22-readlink-fix.js (which repairs Node 22's `fs.readlink`
 * behaviour on volumes where it wrongly reports EISDIR for regular files) before
 * invoking `next build`, so plain `npm run build` works.
 *
 * The shim is passed as a `--require` argv element rather than via NODE_OPTIONS,
 * because NODE_OPTIONS cannot carry a quoted path that contains spaces.
 */
"use strict";

const path = require("path");
const { spawnSync } = require("child_process");

const shim = path.join(__dirname, "node22-readlink-fix.js");
const nextBin = require.resolve("next/dist/bin/next");

const result = spawnSync(
    process.execPath,
    ["--require", shim, nextBin, "build"],
    { stdio: "inherit" }
);

process.exit(result.status === null ? 1 : result.status);
