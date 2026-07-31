On Fedora 44 GNOME, GitHub authentication over SSH consists of four steps:

1. Create an SSH key pair.
2. Add the private key to the SSH agent.
3. Add the public key to GitHub.
4. Test the connection.

I'll explain what each step is doing so you understand it, not just copy commands.

---

# Step 1: Check if you already have SSH keys

Open Terminal and run:

```bash
ls -la ~/.ssh
```

You might see something like:

```text
authorized_keys
config
id_ed25519
id_ed25519.pub
known_hosts
```

### Meaning

* `id_ed25519` → Private key (SECRET)
* `id_ed25519.pub` → Public key (safe to share)
* `known_hosts` → Servers you've connected to
* `config` → SSH configuration

If you don't have `id_ed25519`, create one.

---

# Step 2: Generate a new SSH key pair

GitHub recommends **Ed25519**.

Run:

```bash
ssh-keygen -t ed25519 -C "your_email@example.com"
```

Example:

```bash
ssh-keygen -t ed25519 -C "bhargav@example.com"
```

You will see:

```text
Generating public/private ed25519 key pair.
Enter file in which to save the key:
```

Press **Enter**

It will save as

```
~/.ssh/id_ed25519
```

unless you want another filename.

---

## If you have multiple GitHub accounts

Instead of the default name, use different names.

Example:

Personal

```text
~/.ssh/github_personal
```

Work

```text
~/.ssh/github_work
```

This makes managing multiple accounts much easier.

---

Next you'll see:

```text
Enter passphrase (empty for no passphrase):
```

Use a strong passphrase.

Example:

```text
CorrectHorseBatteryStaple2026!
```

Then confirm it.

---

The output will look similar to

```text
Your identification has been saved in:

~/.ssh/id_ed25519

Your public key has been saved in:

~/.ssh/id_ed25519.pub
```

---

# Step 3: Understand what was created

Private key

```
~/.ssh/id_ed25519
```

This file proves your identity.

Never share it.

Never upload it.

Never email it.

---

Public key

```
~/.ssh/id_ed25519.pub
```

This is safe to share.

GitHub stores this.

---

# Step 4: Start the SSH Agent

The SSH Agent remembers your decrypted private key so you don't enter the passphrase every time.

Start it:

```bash
eval "$(ssh-agent -s)"
```

Example output

```text
Agent pid 4382
```

---

# Step 5: Add your private key

If using the default name:

```bash
ssh-add ~/.ssh/id_ed25519
```

If using a custom name:

```bash
ssh-add ~/.ssh/github_personal
```

You'll be asked for your passphrase once.

---

# Step 6: Verify the key is loaded

```bash
ssh-add -l
```

Example:

```text
256 SHA256:abcd1234... github_personal (ED25519)
```

---

# Step 7: Copy the public key

Display it:

```bash
cat ~/.ssh/id_ed25519.pub
```

or

```bash
cat ~/.ssh/github_personal.pub
```

It looks like

```text
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIM........ bhargav@example.com
```

Copy the entire line.

---

# Step 8: Add it to GitHub

1. Sign in to GitHub.
2. Click your profile picture.
3. **Settings**
4. **SSH and GPG keys**
5. **New SSH Key**
6. Give it a title like:

```
Fedora Workstation
```

7. Paste the public key.
8. Save.

---

# Step 9: Test the connection

Run

```bash
ssh -T git@github.com
```

First time you'll see

```text
The authenticity of host 'github.com' can't be established.
```

Answer

```text
yes
```

Then

```text
Hi your_username! You've successfully authenticated.
```

That means everything works.

---

# Step 10: Configure Git

Set your identity for commits.

Globally:

```bash
git config --global user.name "Your Name"
git config --global user.email "your_email@example.com"
```

Verify:

```bash
git config --global --list
```

---

# Multiple GitHub Accounts (Recommended)

If you use two GitHub accounts, create two keys.

Example:

```text
~/.ssh/github_personal
~/.ssh/github_personal.pub

~/.ssh/github_work
~/.ssh/github_work.pub
```

Create an SSH config file:

```bash
nano ~/.ssh/config
```

Example:

```text
Host github-personal
    HostName github.com
    User git
    IdentityFile ~/.ssh/github_personal
    IdentitiesOnly yes

Host github-work
    HostName github.com
    User git
    IdentityFile ~/.ssh/github_work
    IdentitiesOnly yes
```

Clone repositories using the host alias:

Personal:

```bash
git clone git@github-personal:username/repository.git
```

Work:

```bash
git clone git@github-work:company/repository.git
```

This keeps each GitHub account using its own SSH key.

---

# Useful SSH Commands

| Command                                        | Purpose                        |
| ---------------------------------------------- | ------------------------------ |
| `ssh-keygen -t ed25519 -C "email@example.com"` | Generate a new key pair        |
| `ls ~/.ssh`                                    | List SSH files                 |
| `eval "$(ssh-agent -s)"`                       | Start the SSH agent            |
| `ssh-add ~/.ssh/id_ed25519`                    | Add a private key to the agent |
| `ssh-add -l`                                   | List loaded keys               |
| `cat ~/.ssh/id_ed25519.pub`                    | Show the public key            |
| `ssh -T git@github.com`                        | Test GitHub authentication     |
| `ssh -vT git@github.com`                       | Verbose troubleshooting        |
| `ssh-add -D`                                   | Remove all keys from the agent |

## How the authentication actually works

When you connect to GitHub over SSH:

1. Your computer says, "I want to connect."
2. GitHub sends a random cryptographic challenge.
3. Your **private key** signs that challenge.
4. GitHub verifies the signature using the **public key** you uploaded.
5. If the signature matches, GitHub knows you own the private key and grants access.

At no point is your private key sent over the network, which is why SSH authentication is both secure and convenient once it's set up.

Since you mentioned earlier that you use **multiple GitHub accounts**, I recommend creating **a separate ED25519 key for each account** (for example, `github_personal` and `github_work`) instead of using the default `id_ed25519`. This avoids conflicts and makes it easy to switch between accounts.

