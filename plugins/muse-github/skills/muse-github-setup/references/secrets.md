# Repository credentials

## Meta model key

Use repository Actions secret `META_MUSE_CI_API_KEY`. This is a project naming
convention. Preserve the owner's chosen key scope: one Meta key per GitHub owner
or one per repository. Do not copy a key across owners, rotate an existing key,
or change scope without authorization. Keep values out of chat, logs, command
arguments, repository files, and generated settings.

The model step supplies that secret both as `ANTHROPIC_AUTH_TOKEN` for Meta bearer
authentication and as action `anthropic_api_key` for its launch check. The endpoint
is `https://api.meta.ai`, without `/v1`. No Anthropic key or Claude OAuth token is
needed. `classify_inline_comments: 'false'` is mandatory so the optional classifier
does not send this key to Anthropic. Sources:
[Meta configuration](https://dev.meta.ai/docs/coding-agents),
[bearer gateway action recipe](https://code.claude.com/docs/en/llm-gateway-connect#github-actions).

Preserve the model/tier in existing policy. A fresh default is
`muse-spark-1.3-contributor`, whose content may be used for training. A private
repository without an established tier choice requires a specific owner decision;
recommend the standard `muse-spark-1.3` tier. Do not infer consent from a public
repository's choice. Verify current tier terms when that decision is needed:
[Meta pricing/data-use policy](https://dev.meta.ai/docs/pricing-rate-limits).

## Optional secret-manager provisioner

If `repo-secrets` is installed, inspect its actual supported apps and workflow
detection first. A compatible version may provide `muse-ci` and `muse-ci-members`.
Do not assume an older OpenCode detector recognizes the new workflows. Resolve
its executable from the installed skill; run its dry-run/status paths before a
write. Supply the exact owner/repository and prepared workflow root when supported.
Preserve existing secrets unless rotation was requested. A missing mapping is a
request for a non-secret reference, not permission to reuse another owner's key.
A locked vault requires a reader unlock task; do not request the secret itself.

No private plugin is required. If the installed provisioner is incompatible, use
the public fallback and report that limitation. Do not modify another private
skill implicitly during this installation.

## Secure manual fallback

Give the reader a self-contained task block naming the real target URL
`https://github.com/OWNER/REPO/settings/secrets/actions/new`, replacing owner/repo
with verified values. The reader obtains the intended key through
`https://dev.meta.ai/` and adds `META_MUSE_CI_API_KEY` under **Repository secrets**.
The value is entered only in GitHub or an approved local secret-manager flow.

After completion, read back exact secret names through the connected service or
`gh secret list --repo OWNER/REPO --json name` with a resolved executable. Never
read values or dump the environment. If metadata access fails, state that limit
and request only the non-secret presence result. Presence proves neither validity,
model access, account/tier suitability, nor billing. An authorized live workflow
establishes successful authentication separately.

## Membership App and repository token

The dedicated membership App has Organization **Members: Read-only** and no
other permissions. Use its existing installation and credential scope. Creating
an App or broadening repository/organization access requires the corresponding
owner decision; do not add a privileged App to make reviews work.

| Credential | Use |
|---|---|
| `MUSE_CI_MEMBERS_APP_CLIENT_ID` | Membership App identifier, passed only to token minting |
| `MUSE_CI_MEMBERS_APP_PRIVATE_KEY` | Membership App private key, passed only to token minting |
| `MUSE_MEMBERS_TOKEN` | Short-lived minted token, passed only to helper authorization |
| `github.token` | Repository-scoped review comments and optional trusted fix publication |

Do not reuse release or other privileged App keys. Missing membership credentials
or an unverifiable private membership must fail before model use. Read back names,
never key material. Personal-owner repositories are excluded because they have
no organization membership to verify.

Pass the repository token explicitly as action `github_token`; this skips the
Claude GitHub App exchange. Review/follow-up jobs need contents read and PR write;
manual publication additionally needs contents write. No Anthropic App installation
or OIDC permission is needed for this explicit-token path. See
[security](security.md) for capability limits and optional CI metadata permissions.

Installing credentials does not enable workflows. Preserve `MUSE_CI_ENABLED` until
the replacement is ready and activation is authorized; inspect all other consumers
before changing that shared variable.
