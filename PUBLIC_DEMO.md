# SPYDR public browser sandbox
The repository now includes a **public Vercel-friendly sandbox** at the repository root, alongside the original local Python backend under `agentcompany/` and `web/`.

The public sandbox allows visitors to create goals, author manual strategies, approve or reject them, enter deliverables, view browser-local history, change a hypothetical budget, export their data, or reset their workspace. It seeds a clearly marked sample plan.

**Limitations:** No hosted model inference, cloud database, authenticated users, shared workspace, tamper-resistant audits, or external actions. All data is stored in the visitor's browser localStorage. Clearing browser storage deletes work. Do not enter confidential information or API keys.

**Vercel:** Import this GitHub repository, set Root Directory to the repository root and framework preset **Other**, and deploy production from `main`. No environment variables are required for this sandbox. A full public AI application requires separate PostgreSQL persistence, proper user authentication, scoped authorizations, protected provider keys, abuse throttles, and spending controls. Vercel Hobby plan is for noncommercial use; check plan terms before commercial operation.
