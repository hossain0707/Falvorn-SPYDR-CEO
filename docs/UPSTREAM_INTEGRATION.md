# Relationship to Paperclip

The reel describes a CEO-led AI organization. Its description closely matches
[Paperclip](https://github.com/paperclipai/paperclip), a mature, MIT-licensed agent
management application. However, the reel did **not** expose a direct GitHub
URL, so the exact repository shown has not been independently authenticated.

This project is a **clean-room, focused implementation** of the general idea,
not a copied or modified upstream Paperclip source tree. No upstream Paperclip
files are included. The original Paperclip tree is large, changes rapidly,
and was not locally cloned in this environment.

## Why keep it separate?

- The backend runs from Python 3.13 standard library plus an OpenAI-compatible API.
- Standalone operation requires no Postgres, Redis, JavaScript server, npm install,
  or hosted SaaS.
- It offers a bounded, human-initiated text deliverable workflow with a clear
  budget estimate and a SHA-256 audit chain.
- It cannot claim feature parity or superiority to the entire Paperclip project:
  Paperclip already supports rich orchestration, plugins, and budgets.

## If you want a true Paperclip fork later

1. Create a **fork** of `paperclipai/paperclip` in GitHub (not an empty repo).
2. Review the MIT license and retain its original copyright notice.
3. Compare these enhancements against the current Paperclip architecture.
4. Decide whether to integrate this app as an isolated service or port features
   into the Paperclip control plane.
5. Test the changes in the upstream framework before any publish or deployment.

Never rename the upstream code as wholly proprietary, remove the original MIT
notice, or imply that this standalone project is the official Paperclip app.
