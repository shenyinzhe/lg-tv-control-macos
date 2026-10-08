# Security

The app controls a paired TV on a trusted local network. The webOS client uses TLS but accepts self-signed TV certificates without verifying the peer's identity. Network attackers on the LAN may impersonate a TV. Do not expose TV control ports to the internet, and do not use this app on an untrusted network.

Pairing credentials live in `~/Library/Application Support/LGTVControl/pairing.sqlite` with owner-only permissions. They are not stored in Keychain. Configuration and logs should also be considered private. No credential files are part of this repository or build artifacts.

Do not post exploitable vulnerabilities or private logs in public issues. Until a private reporting channel is enabled by the repository maintainer, use the hosting platform's private vulnerability-reporting feature if available. No response-time commitment is currently offered.

Release maintainers must review bundled dependencies, include their licenses and notices, sign and notarize public binaries where appropriate, and test on supported hardware. Local builds are ad-hoc signed and are not notarized.
