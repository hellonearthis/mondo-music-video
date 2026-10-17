# Repository updates

**Automatic installation is off by default.** The normal `serve` launcher checks
for updates at startup and, when one is available, the studio displays a notice
with its version and a link to the configured repository. With installation off,
it does not change program files or install packages.

## Enable automatic installation

In **Settings**, turn on **Automatic updates** and save. The choice takes effect
on the next launch. Shut down and start the application normally, then open/refresh its browser tab.
A browser refresh alone does not restart the server or install an update.

A successful update installs the application, advances its checkout, and restarts
the launcher into the new code before serving the UI. Startup checks happen once
per launch; there is no background installation during a production. Models,
ComfyUI/custom nodes, llama.cpp, actor assets and user settings are not replaced
by the updater. Python dependencies may be installed or changed when required
by the new application package.

You can temporarily check without installing, even when the saved setting is on:

```sh
mondo-music-video serve --no-auto-update
```

## Which repository is checked?

The updater follows the current Git branch's configured upstream remote and
branch, including collaborator forks and branches other than `main`. It does
not silently switch everyone to the original author's repository. HTTPS and
GitHub SSH remotes get a usable repository link in the update notice.

Supported installations use an owned Git checkout and a Python virtual
environment, as created by the repository installers. The app locates its source
checkout directly or through installed package metadata. After installing an
update wheel, it retains that source location in private application state.
Wheel-only installations without a known Git checkout need a manual update.

To acquire this updater for the first time, existing older installations must
update normally: stop MMV, pull their tracked branch with `git pull --ff-only`,
and reinstall from the repository using their original install command and
extras. A release that predates the updater cannot bootstrap itself.

## Update transaction

1. Acquire the application's data-directory lock and a checkout-wide runtime
   lease before starting the web server. A second launcher using the same checkout
   must wait until the first app exits, even if it uses another data directory.
2. Fetch the configured upstream branch with a bounded timeout. An offline check
   does not prevent the installed application from starting.
3. If installation is disabled, report availability and the repository link.
4. When enabled, require a clean checkout and a fast-forward update. Local
   changes, untracked work, divergence, a detached branch, an interrupted
   production or a non-virtualenv interpreter prevent automatic installation.
   No local work is stashed, reset or discarded.
5. Stage source snapshots in a temporary directory using Git archives; private
   working-directory files are not copied into the staged source. Build the old
   and new application wheels, and recheck the checkout before installing.
6. Install the new wheel in the current virtualenv, preserving already-installed
   Comfy/MCP extras, then fast-forward Git with ignored-file overwrite protection.
   A remote file colliding with an ignored local asset aborts the merge.
7. Persist the installed revision and restart into the updated application.
   The restarted process skips a redundant check once, avoiding a restart loop.

## Failures and recovery

Network or build-preparation failures leave the existing application untouched
and allow startup to continue. Diagnostics appear in the terminal and update
notice. Package installation details are saved privately in `update-install.log`
inside the application data directory; they are not exposed by the update API.

If installation or the final Git advance fails, the updater attempts to restore
the previous **application package** and stops startup. Pip dependency changes
are not a fully reversible transaction; do not assume every dependency has been
rolled back. Inspect the log and repair the environment with the repository's
installer/original pip install command before starting again. A failed package
recovery also stops startup. Git is never hard-reset to force recovery.

The settings file, secrets, actors, styles, models, runs and private workflow
copies remain in the application data directory. Keep normal backups of that
directory. Updating changes neither publication permissions nor the Git ignore
rules that protect private assets.

## Verification scope

Automated tests use disposable local Git remotes, temporary data and mock package
installation. They cover notification-only mode, settings persistence, current
and alternate upstream branches, clean fast-forward installation, re-exec,
local changes/divergence, ignored asset collisions, interrupted work, offline
checks, preparation/install/recovery failures, source-root discovery and
checkout-wide leases. Chromium checks the default-off switch and repository
notice. They do not install real updates into an operator environment, render
on a GPU, or prove native Windows restart behavior.
