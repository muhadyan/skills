# Run the old code for the BEFORE take

Run the old code in its own git worktree, on its own ports, next to the new code. The user's checkout is never touched. Uncommitted work stays safe, and a reviewer can keep reading the checkout while you record.

## Pick what runs old

| The change touches | The before take runs |
|---|---|
| frontend only | the old frontend → the same backend as the after take |
| backend only | the old backend on its own port → a second instance of the same frontend, pointed at it (for example `VITE_API_URL=http://localhost:8091/api npx vite --port 5191`) |
| frontend and backend | the old frontend → the old backend |
| database migrations | the old backend on a separate database with the old schema. Record the before take first, and reset between takes. |

The after take runs from the user's checkout. When that checkout has uncommitted work that is not part of the change, run the after code from a second worktree at the change's commit, so the user's unfinished work does not get into the after take.

## Set up the worktree

1. Find the base: `git merge-base HEAD origin/main`, or the commit the user names.
2. `git worktree add --detach <scratch>/before-<repo> <base>` for each repo that runs old.
3. Make it runnable. A fresh worktree is missing:
   - **Untracked config.** Copy the `.env` files and local settings. `git status --ignored --short` in the main checkout lists them.
   - **Dependencies.** Install them (`npm ci`, `uv sync`, `composer install`, `go build`). Or symlink the main checkout's dependency folder when the lockfile is the same: `git diff <base> HEAD -- <lockfile>` prints nothing.
   - **Runtime folders.** Create the git-ignored folders the framework writes to: cache, logs, storage.
   - **Settings.** Flags and settings the old code reads must have the same values as on the after side, or the two takes differ for a reason that is not the change.
4. **Free ports.** `lsof -ti tcp:<port>` prints nothing when the port is free. Give each dev server its own cache folder, because two servers that share one cache break each other. For example, Vite gives `504 (Outdated Optimize Dep)`. Use a separate Vite `cacheDir`, or a separate `.next` folder for Next.js.
5. **Start the old servers.** Send their output to a log file and note each PID. Before you record, curl the old server: it must answer, and must show the old behavior.

Done when the old and the new app both answer on their own ports, and the user's checkout has no changes from you.

## Clean up

Stop each server by its PID or port. Then run `git worktree remove <scratch>/before-<repo>`.

## Last resort: swap files in place

Use this only when the app cannot run from a second folder.

- `git status --porcelain -- <paths>` must print nothing. If it prints files, stop and ask the user to commit them first.
- `git checkout <base> -- <paths>`. The dev server hot-reloads them. Record `before`, then run `git checkout HEAD -- <paths>`.
- Never use `git stash push -- <paths>` here. When there is nothing to stash, the paired `pop` takes someone else's older stash.
