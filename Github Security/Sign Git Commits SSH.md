Yes. Since you're using **Fedora + GitHub + SSH keys already**, I recommend **SSH commit signing** rather than GPG for your setup. GitHub supports GPG, SSH, and S/MIME signatures; GitHub describes SSH signing as the simpler option, and SSH signing requires Git 2.34+. ([GitHub Docs][1])

## 1. What does "signing a commit" mean?

Normally:

```text
You → git commit → Commit
```

Anyone can configure Git with someone else's:

```text
user.name
user.email
```

So the name on a commit alone isn't cryptographic proof that the person created it.

With signing:

```text
You
 │
 │ private SSH signing key
 ▼
git commit
 │
 ▼
Signed commit
 │
 ▼
GitHub
 │
 ▼
✓ Verified
```

GitHub can cryptographically verify that the commit was signed by the private key corresponding to a public signing key registered with your GitHub account. ([GitHub Docs][2])

---

# 2. SSH signing vs SSH authentication

This is important.

Your SSH key can be used for:

### Authentication

```text
SSH key → authenticate to GitHub → git push/pull
```

### Signing

```text
SSH key → cryptographically sign commit → GitHub verifies commit
```

They are related but **not the same operation**.

GitHub allows an SSH key to be used for both authentication and signing, but if you want the same key to serve both purposes, GitHub requires you to upload it twice: once as an authentication key and once as a signing key. ([GitHub Docs][3])

For a security-hardened setup, I recommend:

```text
Authentication key
    ↓
~/.ssh/githubAlienKey

Signing key
    ↓
~/.ssh/github_signing_key
```

That gives you separation of duties.

---

# 3. First check your Git version

On Fedora:

```bash
git --version
```

You want:

```text
git version 2.34+
```

SSH commit signing was introduced in Git 2.34. ([GitHub Docs][1])

Also check OpenSSH:

```bash
ssh -V
```

---

# 4. Create a dedicated SSH signing key

I recommend creating a **separate Ed25519 key specifically for signing**.

Run:

```bash
ssh-keygen -t ed25519 -C "git-commit-signing" -f ~/.ssh/github_commit_signing
```

You'll get:

```text
~/.ssh/github_commit_signing
~/.ssh/github_commit_signing.pub
```

The important distinction:

```text
github_commit_signing
        ↑
PRIVATE KEY
DO NOT SHARE

github_commit_signing.pub
        ↑
PUBLIC KEY
Can be uploaded to GitHub
```

When asked for a passphrase, **use a strong passphrase**.

---

# 5. Add the signing key to ssh-agent

Start the agent:

```bash
eval "$(ssh-agent -s)"
```

Add the private key:

```bash
ssh-add ~/.ssh/github_commit_signing
```

Check:

```bash
ssh-add -l
```

You should see your key.

---

# 6. Add the public key to GitHub

This part is slightly different from adding an SSH authentication key.

Copy the public key:

```bash
cat ~/.ssh/github_commit_signing.pub
```

You'll get something like:

```text
ssh-ed25519 AAAAC3... git-commit-signing
```

Copy the **entire line**.

Then go to:

[GitHub SSH and GPG keys settings](https://github.com/settings/keys?utm_source=chatgpt.com)

Choose:

```text
New SSH key
```

For **Title**, use something descriptive:

```text
Fedora - Git Commit Signing
```

For **Key type**, select:

```text
Signing Key
```

Then paste:

```text
ssh-ed25519 AAAAC3... git-commit-signing
```

GitHub officially supports SSH keys for commit signing. ([GitHub Docs][3])

---

# 7. Tell Git to use SSH for signing

Run:

```bash
git config --global gpg.format ssh
```

This tells Git:

> When I say "sign", use SSH signatures instead of GPG.

Now configure the signing key:

```bash
git config --global user.signingkey ~/.ssh/github_commit_signing.pub
```

GitHub's current documentation uses exactly this approach for SSH signing. ([GitHub Docs][4])

---

# 8. Make Git sign every commit automatically

This is the part I **strongly recommend** for your security-hardening setup.

Run:

```bash
git config --global commit.gpgsign true
```

Now:

```bash
git commit -m "feat: add authentication"
```

automatically becomes a signed commit.

You don't need:

```bash
git commit -S -m "..."
```

every time.

GitHub documents `commit.gpgsign true` as the configuration for automatically signing commits. ([GitHub Docs][2])

---

# 9. Verify your Git configuration

Run:

```bash
git config --global --get gpg.format
```

Expected:

```text
ssh
```

Then:

```bash
git config --global --get user.signingkey
```

Expected:

```text
/home/YOUR_USERNAME/.ssh/github_commit_signing.pub
```

And:

```bash
git config --global --get commit.gpgsign
```

Expected:

```text
true
```

You can see all relevant configuration with:

```bash
git config --global --list --show-origin | grep -E 'user\.|gpg|sign'
```

---

# 10. Create a test signed commit

Go into your repository:

```bash
cd /path/to/your/project
```

Make a small change:

```bash
echo "# Commit signing test" >> signing-test.md
```

Stage it:

```bash
git add signing-test.md
```

Commit:

```bash
git commit -m "test: verify commit signing"
```

Because you enabled:

```bash
git config --global commit.gpgsign true
```

Git should automatically sign it.

---

# 11. Verify the signature locally

Run:

```bash
git log --show-signature -1
```

You should see information about the SSH signature.

You can also inspect the commit:

```bash
git show --show-signature --stat HEAD
```

And:

```bash
git verify-commit HEAD
```

If everything is configured correctly, Git should report a valid signature.

---

# 12. Push the commit

```bash
git push
```

Then open the repository on GitHub.

Go to:

```text
Repository
   ↓
Commits
   ↓
Your commit
```

You should see:

```text
✓ Verified
```

GitHub marks a commit **Verified** when it successfully validates its GPG, SSH, or S/MIME signature. ([GitHub Docs][1])

---

# 13. Very important: your Git email must match GitHub

Signing the commit is only one part.

Check:

```bash
git config --global user.name
git config --global user.email
```

For example:

```text
Bhargav Zantye
bhargav@example.com
```

The email used as your Git committer identity should be an email associated with your GitHub account.

Check your GitHub email settings here:

[GitHub email settings](https://github.com/settings/emails?utm_source=chatgpt.com)

This is important for GitHub to associate the commit with your account. GitHub's documentation specifically notes that the signing key and committer identity need to line up appropriately for verification. ([GitHub Docs][4])

---

# 14. Your recommended setup

Because you've been working toward a hardened Git/GitHub workflow, I'd structure your machine like this:

```text
                         FEDORA
                           │
              ┌────────────┴────────────┐
              │                         │
       SSH Authentication          SSH Commit Signing
              │                         │
              ▼                         ▼
   ~/.ssh/githubAlienKey      ~/.ssh/github_commit_signing
              │                         │
              ▼                         ▼
         GitHub SSH                 GitHub
        authentication          Signing Key
              │                         │
              ▼                         ▼
       git pull / push             git commit
                                        │
                                        ▼
                                  Cryptographic
                                    signature
                                        │
                                        ▼
                                   ✓ Verified
```

That's much better than relying only on:

```text
user.name
user.email
```

---

# 15. Since you have multiple GitHub accounts

This is particularly important in **your setup**.

You have multiple GitHub identities, so I would **not blindly use one global signing key for everything**.

For example:

```text
VBCreators
    │
    ├── SSH authentication
    │      ~/.ssh/githubAlienKey
    │
    └── SSH signing
           ~/.ssh/vbcreators_commit_signing


Vrushali account
    │
    ├── SSH authentication
    │      ~/.ssh/vbalien_github_vrushali
    │
    └── SSH signing
           ~/.ssh/vrushali_commit_signing
```

Then configure the signing key **per repository**:

```bash
git config user.signingkey ~/.ssh/vbcreators_commit_signing.pub
```

instead of:

```bash
git config --global user.signingkey ...
```

This is safer when the same Fedora installation is used for multiple GitHub accounts.

---

# 16. You can also sign only one commit

If you haven't enabled automatic signing, you can manually sign a commit:

```bash
git commit -S -m "feat: add authentication"
```

GitHub documents `-S` as the explicit commit-signing option. ([GitHub Docs][2])

But for your security-oriented workflow, I recommend:

```bash
git config --global commit.gpgsign true
```

so you don't accidentally forget.

---

# 17. Signing ≠ sign-off

Don't confuse:

```bash
git commit -S
```

with:

```bash
git commit -s
```

They are completely different.

### `-S`

Cryptographically signs the commit:

```text
-S
 ↓
SSH/GPG signature
 ↓
GitHub Verified
```

### `-s`

Adds a Developer Certificate of Origin sign-off:

```text
Signed-off-by: Bhargav Zantye <...>
```

It is **not** a cryptographic signature.

GitHub explicitly distinguishes commit signing from commit sign-off. ([GitHub Docs][1])

---

# 18. Your complete recommended commands

For your Fedora machine, the basic SSH-signing setup is:

```bash
# Check Git
git --version

# Create dedicated signing key
ssh-keygen -t ed25519 \
  -C "git-commit-signing" \
  -f ~/.ssh/github_commit_signing

# Start ssh-agent
eval "$(ssh-agent -s)"

# Load signing key
ssh-add ~/.ssh/github_commit_signing

# Display public key
cat ~/.ssh/github_commit_signing.pub

# Tell Git to use SSH signatures
git config --global gpg.format ssh

# Configure signing key
git config --global user.signingkey ~/.ssh/github_commit_signing.pub

# Automatically sign every commit
git config --global commit.gpgsign true

# Verify configuration
git config --global --get gpg.format
git config --global --get user.signingkey
git config --global --get commit.gpgsign
```

Then add:

```text
~/.ssh/github_commit_signing.pub
```

to GitHub as a **Signing Key**.

---

## What I recommend we do next

Since you're building a **production-grade Git/GitHub security setup**, don't stop at just signing commits. The ideal chain for your project is:

```text
Developer
   │
   ├── SSH authentication
   │
   ├── Signed commits
   │
   ├── pre-commit
   │     ├── Gitleaks
   │     ├── private-key detection
   │     └── code hygiene
   │
   ├── commit-msg
   │     └── Conventional Commits
   │
   ├── pre-push
   │     ├── tests
   │     └── security checks
   │
   └── GitHub Actions
         ├── verify signatures
         ├── secret scanning
         ├── SAST
         ├── dependency scanning
         ├── container scanning
         └── tests
```

GitHub can also enforce signed commits on protected branches, so eventually you can make it impossible for unsigned commits to enter your important branches. ([GitHub Docs][1])

[GitHub's official commit-signing documentation](https://docs.github.com/en/authentication/managing-commit-signature-verification/signing-commits?apiVersion=2022-11-28&utm_source=chatgpt.com) is the best reference to keep alongside your setup.

[1]: https://docs.github.com/en/authentication/managing-commit-signature-verification/about-commit-signature-verification?apiVersion=2022-11-28&utm_source=chatgpt.com "About commit signature verification - GitHub Docs"
[2]: https://docs.github.com/en/authentication/managing-commit-signature-verification/signing-commits?apiVersion=2022-11-28&utm_source=chatgpt.com "Signing commits - GitHub Docs"
[3]: https://docs.github.com/en/authentication/connecting-to-github-with-ssh/adding-a-new-ssh-key-to-your-github-account?tool=cli&utm_source=chatgpt.com "Adding a new SSH key to your GitHub account - GitHub Docs"
[4]: https://docs.github.com/en/authentication/managing-commit-signature-verification/telling-git-about-your-signing-key?platform=linux&utm_source=chatgpt.com "Telling Git about your signing key - GitHub Docs"
