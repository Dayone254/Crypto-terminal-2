/**
 * Node 22 `fs.readlink` workaround.
 *
 * On this machine, Node 22.23.2 returns EISDIR from fs.readlink() for paths that
 * lstat confirms are *regular files* — but only on the F: volume (on C: it
 * correctly returns EINVAL). Next.js's webpack module resolver calls readlink
 * during the production build, so the build aborts with:
 *
 *   Error: EISDIR: illegal operation on a directory, readlink '..._app.js'
 *
 * This shim restores the documented behaviour: readlink on a non-symlink must
 * fail with EINVAL, not EISDIR. Load it before anything else, e.g.
 *
 *   NODE_OPTIONS="--require ./scripts/node22-readlink-fix.js" npm run build
 *
 * It is a no-op on healthy platforms (the original is called through).
 */
"use strict";

const fs = require("fs");

function makeEinval(p) {
    const err = new Error(`EINVAL: invalid argument, readlink '${p}'`);
    err.code = "EINVAL";
    err.errno = -22;
    err.syscall = "readlink";
    err.path = p;
    return err;
}

function shouldRedirect(p) {
    try {
        return !fs.lstatSync(p).isSymbolicLink();
    } catch {
        // Let the original implementation surface ENOENT etc.
        return false;
    }
}

const originalReadlinkSync = fs.readlinkSync.bind(fs);
fs.readlinkSync = function (p, ...rest) {
    if (shouldRedirect(p)) throw makeEinval(p);
    return originalReadlinkSync(p, ...rest);
};

const originalReadlink = fs.readlink.bind(fs);
fs.readlink = function (p, options, callback) {
    let cb = callback;
    let opts = options;
    if (typeof options === "function") {
        cb = options;
        opts = undefined;
    }
    if (shouldRedirect(p)) {
        const err = makeEinval(p);
        if (typeof cb === "function") return process.nextTick(cb, err);
        throw err;
    }
    return opts === undefined ? originalReadlink(p, cb) : originalReadlink(p, opts, cb);
};

const originalPromises = fs.promises && fs.promises.readlink;
if (originalPromises) {
    fs.promises.readlink = async function (p, ...rest) {
        if (shouldRedirect(p)) throw makeEinval(p);
        return originalPromises.call(fs.promises, p, ...rest);
    };
}
