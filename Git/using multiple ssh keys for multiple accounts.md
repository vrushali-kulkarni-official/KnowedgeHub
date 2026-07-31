The error is happening because **GitHub is authenticating you as the wrong account**.

Your output proves it:

```bash
ssh -T git@github.com
Hi VBCreators!
```

But the repository belongs to:

```
vrushali-kulkarni-official/KnowedgeHub
```

So when you do:

```bash
git push
```

GitHub receives the request from the **VBCreators** account, which doesn't have permission to push to the **vrushali-kulkarni-official** repository.

---

# Step 1. Check which SSH key Git is actually using

Run:

```bash
ssh -vT git@github.com
```

Look for lines like:

```text
Offering public key: ~/.ssh/id_ed25519
Offering public key: ~/.ssh/github_vrushali
```

Eventually you'll see something like:

```text
Authenticated to github.com
Hi VBCreators!
```

That tells us which key GitHub accepted.

---

# Step 2. Check your remote

Run:

```bash
git remote -v
```

You will probably see

```text
origin git@github.com:vrushali-kulkarni-official/KnowedgeHub.git
```

The URL is correct.

The problem is **which SSH identity** is being used.

---

# Step 3. Use SSH host aliases (recommended)

When using multiple GitHub accounts, don't connect to `github.com` directly.

Instead create aliases.

Open:

```bash
nano ~/.ssh/config
```

Example:

```text
Host github-work
    HostName github.com
    User git
    IdentityFile ~/.ssh/github_work
    IdentitiesOnly yes

Host github-vrushali
    HostName github.com
    User git
    IdentityFile ~/.ssh/github_vrushali
    IdentitiesOnly yes
```

Replace the filenames with your actual private key names.

For example you might have

```bash
ls ~/.ssh
```

showing

```
github_work
github_work.pub

github_vrushali
github_vrushali.pub
```

---

# Step 4. Test each account

Work account

```bash
ssh -T git@github-work
```

Should print

```text
Hi VBCreators!
```

Personal account

```bash
ssh -T git@github-vrushali
```

Should print

```text
Hi vrushali-kulkarni-official!
```

If it still says

```
Hi VBCreators!
```

then the wrong key is configured.

---

# Step 5. Change the repository remote

Instead of

```text
git@github.com:vrushali-kulkarni-official/KnowedgeHub.git
```

use

```text
git@github-vrushali:vrushali-kulkarni-official/KnowedgeHub.git
```

Run

```bash
git remote set-url origin git@github-vrushali:vrushali-kulkarni-official/KnowedgeHub.git
```

Now

```bash
git push
```

will always use the correct key.

---

# Step 6. Verify

```bash
git remote -v
```

Should show

```text
origin  git@github-vrushali:vrushali-kulkarni-official/KnowedgeHub.git
```

---

# Step 7. Configure Git identity (optional but recommended)

Inside that repository:

```bash
git config user.name
git config user.email
```

If they're wrong:

```bash
git config user.name "Vrushali Kulkarni"
git config user.email "vrushali.kulkarni.official@gmail.com"
```

This affects commit authorship only—it does **not** control authentication.

---

## I need two outputs from you

Please paste the output of:

```bash
ls -l ~/.ssh
```

and

```bash
cat ~/.ssh/config
```

(if it exists)

Also run:

```bash
git remote -v
```

With those three outputs, I can tell you exactly what to change.

