# Publishing to GitHub and verifying the links

## 1. Before you commit
```bash
cd super-investing-research-agent
python3 -m pytest                      # should pass
git init                               # skip if already a repo
git add .
git status                             # read this list carefully
```
Confirm that **`.env` is NOT listed**. Only `.env.example` should appear. Also check:
```bash
git ls-files | grep -E "\.env$" || echo "OK: no .env tracked"
git grep -nE "AIza|sk-ant-" || echo "OK: no keys in tracked files"
```

## 2. Decide about the research pack
`research_pack/*` is git-ignored by default. If the assignment allows publishing the documents and you want
reviewers to be able to re-run everything, delete the last two lines of `.gitignore`.
Otherwise keep them out and say in your submission where the pack comes from.

## 3. Generate the real deliverables first
```bash
python3 run_experiments.py SRVCABLE --pack research_pack --reference-date 2026-09-23
python3 app.py SRVCABLE --pack research_pack --reference-date 2026-09-23
```
Then fill in `logs/test_log.md` Part B from what you observed.

## 4. Commit and push
Create an empty repository on github.com (no README, no .gitignore), then:
```bash
git add .
git commit -m "Research agent for SRVCABLE assignment"
git branch -M main
git remote add origin https://github.com/<your-username>/super-investing-research-agent.git
git push -u origin main
```

## 5. Verify the submitted links work
1. Open the repo URL in a **private/incognito window**. If it asks you to sign in, the repo is private; make it public
   (Settings → General → Danger Zone → Change visibility) or follow the assignment's sharing rules.
2. Click `README.md`, `system_prompt.md`, `output/SRVCABLE_research_brief.md`, `logs/test_log.md`. Each should render.
3. Do a clean-clone test:
   ```bash
   cd /tmp && git clone https://github.com/<your-username>/super-investing-research-agent.git && cd super-investing-research-agent
   python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
   python3 -m pytest
   ```
   (Tests that need the real pack will be skipped if you did not publish it.)
4. Copy the exact URL of the brief file from the browser address bar for the assignment form.
