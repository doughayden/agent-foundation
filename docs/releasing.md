# Release a Version

Cut releases with release-please, promote them to production, and ship hotfixes.

## How Releases Work

`.github/workflows/release.yml` runs [release-please](https://github.com/googleapis/release-please) on every push to `main`, using a token from a GitHub App you create once ([One-Time Setup](#one-time-setup-github-app)).

- **The release pull request:** release-please keeps one pull request open, titled like `chore(main): release X.Y.Z`. It shows the next version and the changelog entries the release will add, and release-please updates it on every push to `main`. The open pull request takes the place of an `[Unreleased]` changelog section: to see what the next release contains, open it.
- **The version:** release-please reads the [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) titles merged since the last release. A `fix` bumps the patch version, a `feat` the minor version, and a breaking change the major version. Before 1.0.0, a breaking change bumps the minor version instead (`bump-minor-pre-major` in `release-please-config.json`).
- **Merging it:** release-please tags `vX.Y.Z` on the squash commit and publishes a GitHub Release with the same notes. The `v*` tag deploys nothing.
- **The release commit deploys like any merge:** it changes `pyproject.toml` and `uv.lock`, so it runs the normal merge pipeline (dev in dev-only mode, dev and stage in production mode). That merge run makes the release promotable to prod.
- **`uv.lock`:** release-please bumps `version` in `pyproject.toml` but not the project's own entry in `uv.lock`, which would fail `uv sync --locked`. An `extra-files` TOML entry in `release-please-config.json` bumps that one version line in the same commit, the workaround from [release-please#2561](https://github.com/googleapis/release-please/issues/2561). Once [release-please#2693](https://github.com/googleapis/release-please/pull/2693) ships, the Python strategy does this itself and the entry can go.

Configuration lives in `release-please-config.json` (release type, changelog sections, `uv.lock` entry) and `.release-please-manifest.json` (the last released version).

## One-Time Setup (GitHub App)

release-please needs a GitHub App token instead of the default `GITHUB_TOKEN`: a pull request opened or updated with `GITHUB_TOKEN` starts no workflow runs, so the release pull request's required checks never report and it can never merge ([release-please-action: Other Actions on Release Please PRs](https://github.com/googleapis/release-please-action#other-actions-on-release-please-prs)). An App token is short-lived and not tied to a person.

Register the App, then store its Client ID and private key, following [create-github-app-token: Usage](https://github.com/actions/create-github-app-token#usage). The template needs these settings:

1. **Repository permissions:** Contents, Issues and Pull requests, all Read and write. Metadata sets itself to Read-only. Leave every other permission at No access.
2. **Webhook:** uncheck Active. The App only mints tokens.
3. **Installation:** choose "Only on this account", create the App, then open Install App and install it on this repository only. Registering the App is not enough: the token request fails until the App is installed.
4. **Variable and secret:** store the Client ID (it starts with `Iv`; the numeric App ID is a different value) and a generated private key under the names `release.yml` reads:
   ```bash
   gh variable set RELEASE_APP_CLIENT_ID --body "<client-id>"
   gh secret set RELEASE_APP_PRIVATE_KEY < <downloaded-key>.pem
   ```
   Delete the downloaded `.pem` file afterwards. GitHub generates a new key whenever you need one.
5. **Immutable releases:** enable them in Settings → General → Releases, or run:
   ```bash
   gh api -X PUT repos/<owner>/<repo>/immutable-releases
   ```

> [!NOTE]
> Without `RELEASE_APP_CLIENT_ID`, the release job is skipped. A fork without the App sees no failed runs and gets no releases, so it cuts them by hand: [Release Without the App](#release-without-the-app).

### Release Without the App

Promotion only needs a `vX.Y.Z` tag on a commit whose merge run deployed stage, so a release can be cut by hand:

1. In a pull request, set `version` in `pyproject.toml` and `.release-please-manifest.json`, run `uv lock`, and add the version's entries to `CHANGELOG.md`. Keeping the manifest current lets release-please continue from this version if you install the App later. The change to `pyproject.toml` and `uv.lock` makes the merge run deploy, so the merge commit becomes promotable
2. Merge it, then tag the merge commit and push the tag. The `v*` tag deploys nothing:
   ```bash
   git fetch origin main
   git tag -a vX.Y.Z <merge-commit> -m "Release vX.Y.Z"
   git push origin vX.Y.Z
   ```
3. In production mode, promote it with the same steps as a release-please release ([Promote to Production](#promote-to-production-production-mode))

## Cut a Release

1. Open the release pull request (label `autorelease: pending`) and review the version and changelog entries
2. Wait for its required checks, then squash-merge it. The release pull request is generated, so skip editing its title or body: release-please rewrites both on the next push to `main`
3. The `Release` workflow run on the merge commit tags `vX.Y.Z`, publishes the GitHub Release, and relabels the pull request `autorelease: tagged`

A merge produces:

- **Tag:** `vX.Y.Z` on the squash commit
- **GitHub Release:** immutable, with the version's changelog entries as its notes
- **Changelog:** the new version's entries at the top of `CHANGELOG.md`, and the version in `pyproject.toml`, `uv.lock` and `.release-please-manifest.json`

In dev-only mode, that is the whole release: the merge run deploys the release commit to dev like any other merge.

## Promote to Production (Production Mode)

> [!IMPORTANT]
> The approval gate needs reviewers: set `prod_apply_reviewer_users` or `prod_apply_reviewer_teams` in `terraform/bootstrap/prod/terraform.tfvars` and apply the prod bootstrap root. See [Protection Strategies](references/protection-strategies.md#environment-protection-automated).

A production release is two tags on one commit: `vX.Y.Z`, which release-please creates when the release pull request merges, and `prod-vX.Y.Z`, which promotes that commit to prod.

1. Wait for the release commit's merge run to pass `Apply Stage`, `Smoke Stage` and `Judge Eval`. A promotion pushed earlier fails `Require Stage Success` and needs a re-run once stage is green
2. Promote it with a second tag on the same commit (repository admin). Push each promotion tag on its own, since GitHub starts no workflow when more than three tags arrive in one push:
   ```bash
   git fetch --tags
   git tag -a prod-vX.Y.Z 'vX.Y.Z^{commit}' -m "Promote vX.Y.Z to prod"
   git push origin prod-vX.Y.Z
   ```
   The push starts the prod jobs, and fails at metadata extraction unless the tag has the form `prod-vX.Y.Z` and `vX.Y.Z` marks the same commit. Only commits that contain the `prod-v*` pipeline can be promoted; for an older build, use a Cloud Run traffic split ([Rollback](#rollback)).
3. Monitor the workflow: Actions tab → CI/CD Pipeline
4. **Approved reviewer:** Actions → prod-apply job → Review deployments → Approve
5. Verify the production deployment

## Hotfixes and Rollback

### Hotfix

No GCP access needed. Ship the fix as a new patch release:

1. Revert or fix on a branch and open a pull request:
   ```bash
   git checkout -b hotfix/revert-bad-change
   git revert --no-edit <bad-commit>
   git commit --amend -m "fix: revert <bad change>"
   git push origin hotfix/revert-bad-change
   gh pr create --title "fix: revert <bad change>"
   ```
   Retitle the revert commit: `git revert` and the GitHub Revert button both title it `Revert "..."`, which is not a Conventional Commit, so release-please skips it and the fix never releases. A one-commit pull request squash-merges under the commit's title, not the pull request's
2. Merge it after approval. release-please updates the release pull request: a patch version, or a minor version if `feat` commits are already waiting on `main`
3. Merge the release pull request ([Cut a Release](#cut-a-release))
4. In production mode, promote the new version ([Promote to Production](#promote-to-production-production-mode))

### Rollback

Cloud Run traffic split, instant, requires GCP access:

```bash
# List revisions
gcloud run revisions list --service=<service> --region=<region>

# Route all traffic to the previous revision
gcloud run services update-traffic <service> \
  --to-revisions=<previous-revision>=100 \
  --region=<region>
```

Follow up with a hotfix release. The rollback decision tree is in [Troubleshooting](troubleshooting.md#rollback-strategies).

## Changelog and Commit Types

release-please writes one changelog entry per commit on `main`, using its title. You squash-merge, so that is the squash commit title: the PR title by default, or the only commit's title when the pull request has one commit, and whatever the person merging types last. That final title decides the entry, its section and the version bump.

| Commit type | Changelog section |
|---|---|
| `feat` | Added |
| `perf`, `ci`, `test` | Changed |
| `revert` | Removed |
| `fix` | Fixed |
| Any other type (`build`, `docs`, `chore`, `refactor`, `style`) | Not listed |

The mapping is `changelog-sections` in `release-please-config.json`; a type it does not list gets no entry. Documentation ships with the change it describes, so that change's entry covers it. When every commit since the last release is unlisted, release-please opens no release pull request.

- **Dependency bumps:** Dependabot titles them `build(deps)`, so they are unlisted. When a bump changes what ships, like an ADK upgrade or a security fix, retitle it `fix(deps): ...` in the squash merge dialog so it gets an entry and a release

- **Breaking changes:** a `!` after the type or scope (`feat!:`, `feat(api)!:`) or a `BREAKING CHANGE:` footer adds the change to a breaking-changes section at the top of the version's notes, with the footer text as the description. Put the migration steps in that footer
- **Correct a merged entry:** edit the merged pull request's body and add a `BEGIN_COMMIT_OVERRIDE` block with the replacement commit messages, then re-run the latest `Release` workflow run (Actions tab) to rebuild the release pull request. This also fixes a release pull request whose `CHANGELOG.md` fails a spelling or whitespace hook because of a typo in a merged title ([release-please: How can I fix release notes?](https://github.com/googleapis/release-please#how-can-i-fix-release-notes))
- **Choose the version:** a `Release-As: X.Y.Z` footer on a commit merged to `main` makes the next release that version

> [!NOTE]
> release-please only adds entries for new versions. Entries for releases before it took over stay as they were written.

## Immutable Releases

With immutable releases on, a published release's tag cannot be moved or deleted while the release exists. To remove a release and its tag, delete the release first: the tag stays behind, and can then be deleted on its own.

> [!CAUTION]
> Deleting a release permanently discards its notes and assets. Once the tag is gone too, a promotion tag for that version fails `Extract Build Metadata`, since it needs the release tag.

```bash
gh release delete vX.Y.Z --yes
gh api -X DELETE repos/<owner>/<repo>/git/refs/tags/vX.Y.Z
```

---

← [Back to Documentation](README.md)
