# Static-analysis triage

**Date:** 13 November 2026. **Input:** `bandit.json`, generated at `2026-11-13T16:06:00Z`; 46 low-severity results, zero medium/high results, no scanner errors. One rule-specific suppression is present for ONVIF's protocol-required SHA-1 digest. This is a static review of the supplied scanner results and their call sites, not a penetration test or security certification.

## Disposition

**44 results are not actionable as the claimed security issue in the inspected product paths. The two privileged CLI helper launches led to an implemented installation-ownership correction; privileged acceptance remains pending.** The new typed-settings and preview-worker modules have no results in this report; their callers do not add shell execution, insecure XML parsing, hardcoded credentials or security-sensitive use of ordinary randomness.

The root `SECURITY.md` and `docs/security.md` define a trusted-LAN appliance with protected installation metadata, dedicated service processes, and trusted administrator control of camera destinations. No scoped `SECURITY.md` was found. Those deployment statements are assumptions to enforce, not evidence that a particular installed host has correct permissions.

| Rule/category | Count | Static disposition |
|---|---:|---|
| B404: subprocess imports | 8 | Imports alone are not a vulnerability; corresponding execution sites were reviewed below. |
| B603: subprocess arguments | 15 | 13 not actionable for command injection; 2 helper launches have an implemented ownership correction with privileged acceptance pending. Calls use argument lists without a shell. Camera URLs are constrained to RTSP/RTSPS; API log times/counts are validated; plugin probe names come from the installed GStreamer registry. |
| B607: executable resolved through PATH | 7 | No remotely controlled PATH or executable name was found in these paths. This remains a deployment trust assumption; using an explicit trusted PATH/absolute executables is reasonable hardening, especially for privileged CLI use. |
| B101: assertions | 7 | Database/server initialization and renderer pipeline invariants, not authentication, authorization or input-validation gates. Removing them under optimized Python does not establish a security-control bypass. |
| B105/B106: password-like constants | 6 | Export omission (`None`), transient empty ciphertext/password initialization followed by authenticated encryption, or the WS-Security PasswordDigest namespace URI. None is a hardcoded application login secret. |
| B311: ordinary randomness | 2 | Random/weighted camera rotation order, not session tokens, key material or credential nonces. Security tokens and the new keyed cache fingerprint use `secrets`. |
| B405: ElementTree import | 1 | Standard ElementTree constructs outbound SOAP elements, serializes them and supplies types/errors. Untrusted inbound bytes are parsed exclusively through `SafeET.fromstring(..., forbid_dtd=True, forbid_entities=True, forbid_external=True)` after response-size checks (`services/onvif.py:75–82,138–169`). |

## Privileged helper boundary: implemented correction, acceptance pending

The original two review items remain separate scanner inputs: **input 9, `cli.py:653` (update)** and **input 10, `cli.py:664` (uninstall)**. Both invoke an installed helper, adding `sudo` when appropriate. The original staging copy used `rsync -a` and retained the checkout owner's UID/GID. An initial trusted source owner should not retain authority to modify a future installed privileged helper.

The final helper was inspected read-only. `installer/lib.sh:14–22` now uses `rsync --safe-links --chown=root:root --chmod=u=rwX,go=rX,ug-s,-t`. This gives staged files/directories root ownership, preserves necessary executable/traverse access, removes group/other write and setuid/setgid/sticky bits, and omits links escaping the copied source tree. The top-level staged directory is explicitly 0755. `install-local.sh` explicitly sets the dedicated prefix and release container to root-owned 0755. `cw_assert_prefix_ancestors` requires existing ancestors to be real, root-owned directories without group/other write; it is checked early and immediately before staging. These controls address the identified source-owner persistence mechanism for ordinary installed paths. Initial source and custom interpreter trust remain prerequisites.

**Privileged verification remains pending.** `test_installed_source_does_not_retain_checkout_owner_or_writable_modes` exercises source UID/GID 12345, writable and special-bit modes, unsafe external links and excluded virtual environments, then checks root ownership and normalized installed modes while preserving the source. It requires root and rsync and is explicitly skipped in this environment. The positive ancestor-policy case uses simulated metadata because this workspace remaps even system-directory owners; the writable-parent rejection exercises real filesystem metadata. The root review reports the focused installer outcomes separately. No privileged program or new test was run by this read-only reviewer.

The related release-container path check is also implemented. `install-local.sh:205–210` validates ancestors, locks the dedicated prefix as root-owned 0755, calls `cw_assert_release_directory`, and only then creates/normalizes `releases`. `installer/lib.sh:66–70` rejects a symlink or non-directory release container, including a dangling symlink. Two real-filesystem regression cases exercise symlink/file rejection and preserve an outside sentinel. The root reviewer reports **21 focused installer-release tests passed and one root/rsync case skipped**. These are reported test outcomes, not a privileged execution performed by this static reviewer. No unresolved source correction remains from the specific ownership mechanism assessed here; privileged installation/upgrade verification remains required.

The two per-input statuses are retained as **`needs_review` for privileged acceptance**, with review ranks 1 and 2, rather than being represented as two still-unimplemented ownership fixes. The static correction is present; this report does not claim that the corresponding privileged transfer or appliance upgrade has passed.

## Existing limits and practical follow-up

The legacy OMX backend and the FFmpeg fallback pass resolved stream URLs as process arguments. This is an existing local credential-exposure boundary, separate from shell-command injection; `docs/security.md` now explicitly identifies both cases. Protect local process-inspection access; argv-list use does not remove this local exposure. Complete URI-token encryption remains separate roadmap work.

The new worker pool improves concurrency control but does not sandbox multimedia libraries or eliminate credential-bearing arguments in the existing fallback. Its limits remain per API process, with uncapped identical HTTP waiters and shutdown dependent on the underlying media operation finishing or being terminated by the service manager.

The executable PATH, privileged installed-file ownership transfer, OS package binaries and multimedia-library vulnerabilities were not dynamically verified by this reviewer. Pinning a trusted service PATH and replacing internal assertions with explicit runtime checks can improve operational clarity, but the low scanner categories alone do not justify a broad refactor or claim a demonstrated exploit.

## Per-result record

The following table preserves the scanner's input order and duplicate-looking rules. `NA` means **not_actionable for the scanner's material claim in the inspected code path**, not a guarantee that the component has no other weaknesses. `Review` means **needs_review for privileged acceptance of the implemented ownership correction**, as detailed above. No findings were discarded.

| Input | Rule | Source location | Verdict / rationale |
|---:|---|---|---|
| 1 | B404 | `api/routes_logs.py:5` | NA — import; execution reviewed |
| 2 | B603 | `api/routes_logs.py:32` | NA — bounded/fixed argv; no shell interpretation |
| 3 | B404 | `cli.py:6` | NA — import; execution reviewed |
| 4 | B607 | `cli.py:99` | NA — operator/service PATH boundary; deployment hardening noted |
| 5 | B603 | `cli.py:99` | NA — bounded/fixed argv; no shell interpretation |
| 6 | B607 | `cli.py:413` | NA — operator/service PATH boundary; deployment hardening noted |
| 7 | B603 | `cli.py:413` | NA — bounded/fixed argv; no shell interpretation |
| 8 | B603 | `cli.py:606` | NA — bounded/fixed argv; no shell interpretation |
| 9 | B603 | `cli.py:653` | Review — ownership correction implemented; root verification pending; rank 1 |
| 10 | B603 | `cli.py:664` | Review — ownership correction implemented; root verification pending; rank 2 |
| 11 | B101 | `db.py:55` | NA — internal lifecycle invariant |
| 12 | B101 | `db.py:63` | NA — internal lifecycle invariant |
| 13 | B311 | `renderer/controller.py:332` | NA — camera selection order, not security randomness |
| 14 | B311 | `renderer/controller.py:334` | NA — camera selection order, not security randomness |
| 15 | B101 | `renderer/gstreamer.py:442` | NA — internal lifecycle invariant |
| 16 | B101 | `renderer/gstreamer.py:534` | NA — internal lifecycle invariant |
| 17 | B101 | `renderer/gstreamer.py:581` | NA — internal lifecycle invariant |
| 18 | B101 | `renderer/gstreamer.py:1561` | NA — internal lifecycle invariant |
| 19 | B404 | `renderer/omxplayer.py:9` | NA — import; execution reviewed |
| 20 | B603 | `renderer/omxplayer.py:138` | NA — bounded/fixed argv; no shell interpretation |
| 21 | B607 | `renderer/omxplayer.py:266` | NA — operator/service PATH boundary; deployment hardening noted |
| 22 | B603 | `renderer/omxplayer.py:266` | NA — bounded/fixed argv; no shell interpretation |
| 23 | B607 | `renderer/omxplayer.py:360` | NA — operator/service PATH boundary; deployment hardening noted |
| 24 | B603 | `renderer/omxplayer.py:360` | NA — bounded/fixed argv; no shell interpretation |
| 25 | B101 | `renderer/rpc.py:97` | NA — internal lifecycle invariant |
| 26 | B105 | `services/backup.py:56` | NA — omission/initialization/protocol identifier, not a login secret |
| 27 | B106 | `services/backup.py:306` | NA — transient initialization before encryption |
| 28 | B106 | `services/cameras.py:50` | NA — transient initialization before encryption |
| 29 | B106 | `services/cameras.py:177` | NA — transient initialization before encryption |
| 30 | B105 | `services/cameras.py:180` | NA — omission/initialization/protocol identifier, not a login secret |
| 31 | B404 | `services/capabilities.py:7` | NA — import; execution reviewed |
| 32 | B603 | `services/capabilities.py:28` | NA — bounded/fixed argv; no shell interpretation |
| 33 | B607 | `services/capabilities.py:115` | NA — operator/service PATH boundary; deployment hardening noted |
| 34 | B603 | `services/capabilities.py:115` | NA — bounded/fixed argv; no shell interpretation |
| 35 | B404 | `services/decoder_policy.py:8` | NA — import; execution reviewed |
| 36 | B603 | `services/decoder_policy.py:70` | NA — bounded/fixed argv; no shell interpretation |
| 37 | B404 | `services/diagnostics.py:9` | NA — import; execution reviewed |
| 38 | B607 | `services/diagnostics.py:131` | NA — operator/service PATH boundary; deployment hardening noted |
| 39 | B603 | `services/diagnostics.py:131` | NA — bounded/fixed argv; no shell interpretation |
| 40 | B405 | `services/onvif.py:16` | NA — hardened parser handles inbound XML |
| 41 | B105 | `services/onvif.py:38` | NA — omission/initialization/protocol identifier, not a login secret |
| 42 | B404 | `services/renderer_config.py:5` | NA — import; execution reviewed |
| 43 | B607 | `services/renderer_config.py:40` | NA — operator/service PATH boundary; deployment hardening noted |
| 44 | B603 | `services/renderer_config.py:40` | NA — bounded/fixed argv; no shell interpretation |
| 45 | B404 | `services/stream_probe.py:4` | NA — import; execution reviewed |
| 46 | B603 | `services/stream_probe.py:107` | NA — bounded/fixed argv; no shell interpretation |
