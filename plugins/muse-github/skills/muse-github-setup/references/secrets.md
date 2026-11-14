# Repository credentials

## Meta model key

Use the repository Actions secret `META_MUSE_CI_API_KEY`. It identifies the
provider, model family, and CI use without colliding with unrelated Meta keys.
This is a project convention, not an assertion that Meta requires that name.
The cookbook uses `MODEL_API_KEY`; the customized provider references
`{env:META_MUSE_CI_API_KEY}` instead. Keep those two names aligned.

Use the key scope the owner chose: one Meta API key per GitHub owner, shared
by its repositories, or a dedicated key per repository. Store it in the
owner's secret manager. Never copy a key across owners or invent a scope the
owner did not choose. GitHub secret names may be reused across repositories because each
repository has its own secret scope. Distinct names within one repository would
be needed for separate CI environments; this template has one Muse CI key.

If the optional private skill `repo-secrets` is installed, inspect its supported
apps before delegating. Its Muse interface is:

```text
scripts/repo_secrets set --repo OWNER/REPO --app muse-ci --workflow-root WORKTREE
scripts/repo_secrets status --repo OWNER/REPO --app muse-ci --workflow-root WORKTREE
scripts/repo_secrets set --repo OWNER/REPO --app muse-ci --workflow-root WORKTREE --dry-run
```

Run the `--dry-run` form first: it shows whether a 1Password mapping exists
(`missing — will prompt`) without reading or writing any secret.

Resolve `scripts/repo_secrets` relative to that installed skill. Replace
`OWNER/REPO` with the verified GitHub name and `WORKTREE` with the setup
worktree's absolute root. The private provisioner detects the action on this
worktree even before the workflow exists on the default branch. Its mapping is
keyed by GitHub owner, like its other apps. An absent mapping is a request for
the non-secret reference, not permission to reuse another owner's key.
Existing secrets are preserved unless rotation is explicitly requested.

An older private skill without Muse support is unavailable for this integration.
Recommend updating it separately when appropriate and use the public fallback.
Never automatically author another private skill during an installation.

## Public fallback

Give the user a self-contained task block with the **actual target URL**
`https://github.com/OWNER/REPO/settings/secrets/actions/new`. Explain that they
create a repository-specific Meta API key at `https://dev.meta.ai/`, then add
`META_MUSE_CI_API_KEY` under **Repository secrets**, with its value entered only
in GitHub or an approved local secret-manager flow. Replace the owner/repo
placeholders before delivery. The user supplies the key through that secure
surface, never this conversation.

Wait for their completion report. Then use `gh secret list --repo OWNER/REPO
--json name` to verify the exact name exists. If access prevents that read,
report the limitation and request the non-secret presence result from the user.
Do not claim verification merely because the user said they finished. Do not
print values, run a broad environment dump, or place a key in command arguments.

Secret metadata proves only that a name is present. Correct account, model
access, billing, tier, and key validity are established by a later authorized
workflow run. The contributor model's data-use policy is a separate owner
decision; a low price is not evidence of private-code suitability.

## GitHub membership App

The helper checks `GET /orgs/ORG/members/USER` with `MUSE_MEMBERS_TOKEN`. The
repository `GITHUB_TOKEN` cannot prove private membership: GitHub answers a
non-member requester with a redirect, which the helper refuses. Each workflow
therefore mints `MUSE_MEMBERS_TOKEN` in its first credential step from a
dedicated organization GitHub App:

| Setting | Value |
|---|---|
| App name | `muse-ci-members-ORG` |
| Permissions | Organization permission **Members: Read-only**; nothing else |
| Webhook | Inactive |
| Installable on | Only this account (the organization) |
| Repository secrets | `MUSE_CI_MEMBERS_APP_CLIENT_ID`, `MUSE_CI_MEMBERS_APP_PRIVATE_KEY` |

Do not reuse a release or other privileged App: its key would reach the
authorization step with far more than membership read. The minted token lasts
about an hour and is revoked when the job ends. If the private `repo-secrets`
skill supports `--app muse-ci-members`, use it after the setup PR merges (its
detection reads the default branch). Otherwise hand the owner the two secret
names and verify presence with `gh secret list`. Never request the key in chat.
Personal-account repositories are out of scope: the workflows skip them, and
personal accounts have no organization membership to check.

Sources: [Meta cookbook](https://github.com/meta-models/meta-model-cookbook/tree/c5a9882b4c7f3900e9c93122249d37317c8abff4/03_use_cases/11_github_repo_agent),
[Meta pricing and tier policy](https://dev.meta.ai/docs/pricing-rate-limits),
[GitHub membership API](https://docs.github.com/en/rest/orgs/members#check-organization-membership-for-a-user).
