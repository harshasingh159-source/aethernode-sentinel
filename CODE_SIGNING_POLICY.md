# Code signing policy

**Status:** AetherNode has applied for free code signing for open-source projects from
[SignPath Foundation](https://signpath.org). Until that is approved, releases are **not code-signed**:
check downloads against the SHA-256 published with each release.

When signing is active, every signed release carries this attribution:

> Free code signing provided by [SignPath.io](https://about.signpath.io), certificate by [SignPath Foundation](https://signpath.org)

## What gets signed

- Only `AetherNode.exe` from this repository's GitHub Releases.
- It is built by GitHub Actions ([`.github/workflows/release.yml`](.github/workflows/release.yml)) directly from the
  public source of a tagged commit. Nothing is built or signed on a personal computer.
- The build runs the test suite and refuses to continue if the release tag doesn't match the version in
  `aethernode/__init__.py`.
- File metadata is fixed: product name **AetherNode** and product version equal to the release version
  (see [`packaging/make_version_info.py`](packaging/make_version_info.py)).
- The .exe bundles third-party open-source components (Python, FastAPI, Scapy, …), listed with their
  licenses in `THIRD_PARTY_NOTICES.txt`. They are packaged unmodified inside the single .exe; no
  third-party binary is signed on its own.

## Team roles

| Role | Members |
|---|---|
| Committers and reviewers | [harshasingh159-source](https://github.com/harshasingh159-source) |
| Approvers | [harshasingh159-source](https://github.com/harshasingh159-source) |

- Committers write and merge code to `main`. Changes from anyone else arrive as pull requests and are
  reviewed by a committer before merging.
- Every signing request is approved manually by an approver, for that release only.
- All team members use multi-factor authentication for GitHub and for SignPath.

## Privacy

This program will not transfer any information to other networked systems unless specifically requested by
the user or the person installing or operating it. See [Privacy](README.md#privacy) for exactly what
network traffic it creates on your local network.

## Reporting problems

If you believe a signed AetherNode release is malicious or was not built from this repository, open an
issue at <https://github.com/harshasingh159-source/aethernode-sentinel/issues> or contact SignPath Foundation
at support@signpath.io.
