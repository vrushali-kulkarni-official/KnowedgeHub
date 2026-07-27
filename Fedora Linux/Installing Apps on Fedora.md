This is one of the biggest differences between Windows and Linux.

On **Windows**, you usually:

* Go to a website
* Download an `.exe`
* Double-click it

On **Fedora**, there are **many different ways** to install software. As a beginner, it can feel confusing because different developers distribute their software differently.

The good news is that there is a logical order you should follow.

---

# Think of software installation as a pyramid

Always try these methods **from top to bottom**.

```
          Software Store (GUI)
                  │
                  ▼
         dnf package manager
                  │
                  ▼
             Flatpak
                  │
                  ▼
        Official Repository
                  │
                  ▼
         AppImage / tar.gz
                  │
                  ▼
        Build from source (last)
```

The lower you go, the more technical it becomes.

For beginners, you will probably use only the first four methods.

---

# Method 1 — Software Store (Easiest)

This is like Microsoft Store.

Example:

Search

```
Firefox
```

Click

```
Install
```

Done.

---

# Method 2 — DNF (Fedora's Package Manager)

Fedora's package manager is called

```
dnf
```

Think of it as Fedora's equivalent of

```
winget
```

on Windows.

Example

```
sudo dnf install git
```

or

```
sudo dnf install vlc
```

The package is downloaded from Fedora's official repositories.

Advantages

* Safe
* Automatic updates
* Dependency handling
* Easy uninstall

---

## Search first

If you don't know the package name

```
dnf search vscode
```

or

```
dnf search blender
```

Example

```
dnf search docker
```

might show

```
docker
docker-compose
docker-buildx
...
```

Then install

```
sudo dnf install docker
```

---

# Method 3 — Enable RPM Fusion

Many popular applications are **not included in Fedora's default repositories** because of licensing or patent restrictions (for example, multimedia codecs or some third-party software).

One of the first things many Fedora users do is enable **RPM Fusion**.

Once enabled, you can install additional software with normal `dnf` commands.

For example:

```
sudo dnf install vlc
```

works after the required repository is available.

---

# Method 4 — Add an Official Repository

Sometimes the software developer provides their own Fedora repository.

Example

Google Chrome

Google provides its own repository.

You run a command once to add it.

After that

```
sudo dnf install google-chrome-stable
```

works normally.

Why?

Because Fedora now knows where Chrome lives.

---

Example

Docker

Visual Studio Code

Microsoft Edge

Google Chrome

all provide their own repositories.

---

# Method 5 — Flatpak

Many applications are distributed through Flatpak.

Think of Flatpak as

> "An application that brings everything it needs with it."

Advantages

* Works on almost every Linux distribution
* Easy updates
* Very safe
* Doesn't interfere much with the system

Install

```
flatpak install flathub com.discordapp.Discord
```

or

```
flatpak install flathub org.gimp.GIMP
```

---

Update Flatpaks

```
flatpak update
```

---

# Method 6 — Download an RPM Package

Some websites provide

```
something.rpm
```

This is similar to downloading an MSI installer on Windows.

Example

```
google-chrome.rpm
```

Install it

```
sudo dnf install ./google-chrome.rpm
```

Notice the

```
./
```

That means

> install the file in the current folder.

DNF will also install any required dependencies automatically.

---

# Method 7 — AppImage

Some software comes as

```
Application.AppImage
```

Think of it like a portable Windows application.

No installation required.

Steps

Download

```
Application.AppImage
```

Make executable

```
chmod +x Application.AppImage
```

Run

```
./Application.AppImage
```

Done.

---

# Method 8 — Extract a tar.gz Archive

Sometimes you download

```
program.tar.gz
```

This is just a compressed archive.

Extract it

```
tar -xzf program.tar.gz
```

Now you'll have a folder.

Inside might be

```
program
```

or

```
install.sh
```

or

```
README.md
```

Always read

```
README.md
```

because every project can be different.

---

# Method 9 — Build from Source

This is the most advanced method.

You download the source code.

Compile it.

Install it.

Example

```
git clone https://github.com/project/project.git

cd project

mkdir build

cd build

cmake ..

make

sudo make install
```

As a beginner, avoid this unless the project's documentation specifically requires it.

---

# How do you know which method to use?

Suppose you want to install some application.

Go to its official website.

Look for one of these.

## Best

```
Fedora
```

or

```
dnf
```

---

Next best

```
RPM
```

---

Next

```
Flatpak
```

---

Next

```
AppImage
```

---

Next

```
tar.gz
```

---

Worst (for beginners)

```
Source Code
```

---

# Example 1

You want

```
Visual Studio Code
```

Website offers

```
RPM
```

Download

```
code.rpm
```

Install

```
sudo dnf install ./code.rpm
```

Done.

---

# Example 2

You want

```
Discord
```

Use Flatpak

```
flatpak install flathub com.discordapp.Discord
```

---

# Example 3

You want

```
Docker
```

The official website provides a Fedora repository.

Add it once.

Then

```
sudo dnf install docker-ce
```

---

# Example 4

You want

```
Antigravity IDE
```

Imagine the website only provides

```
antigravity.tar.gz
```

Steps

1. Download

2. Extract

```
tar -xzf antigravity.tar.gz
```

3. Read

```
README.md
```

4. Follow the installation instructions (for example, run an installer script or execute the application).

---

# Useful Linux commands you'll use often

Show current folder

```bash
pwd
```

List files

```bash
ls
```

Change folder

```bash
cd folder_name
```

Go up one folder

```bash
cd ..
```

Create folder

```bash
mkdir myfolder
```

Delete file

```bash
rm filename
```

Copy

```bash
cp source destination
```

Move or rename

```bash
mv old new
```

---

# A Beginner's Decision Tree

Whenever you want to install **any** application on Fedora, follow this checklist:

1. **Check the Software Store**.
2. **Search with `dnf`**:

   ```bash
   dnf search <app-name>
   ```
3. **Check if the developer provides a Fedora repository** and follow their installation instructions if they do.
4. **Look for an `.rpm` package** and install it with:

   ```bash
   sudo dnf install ./package-name.rpm
   ```
5. **Look for a Flatpak** version if available.
6. **Use an AppImage** if that's the only option.
7. **Use a `.tar.gz` archive** only if there are no easier options, and follow the included `README.md`.
8. **Build from source** only as a last resort.

---

## My recommendation for you

Since you're new to Fedora and Linux, I suggest these habits:

* **Always prefer `dnf`** when possible. It integrates cleanly with Fedora and keeps software updated.
* **Use Flatpak** when a package isn't available through `dnf` but the developer supports it.
* **Install `.rpm` packages** only from the software's official website or another trusted source.
* **Avoid compiling from source** until you're comfortable with the Linux command line.

If you consistently follow this order, you'll be able to install almost any application on Fedora without unnecessary complexity.

