# The Long War for Secrets

**A complete, honest history of cryptography — from a leather strap in ancient Sparta to the post-quantum lattice schemes safeguarding your HTTPS connection.**

---

## How to read this

Every era below is the same five-beat pattern. **The previous method had a flaw** → **someone discovered a way to break it** → **an inventor built something new** → **here is how it works** → **and here's what will eventually break it too**. Cryptography is an arms race. The story has no final chapter.

---

## The timeline at a glance

| Era | Year | Method |
|---|---|---|
| 01 | ~700 BC | Scytale (Sparta) |
| 02 | ~50 BC | Caesar cipher (Rome) |
| 03 | ~850 AD | Frequency analysis (Baghdad) |
| 04 | 1467 / 1553 | Polyalphabetic ciphers (Italy) |
| 05 | 16th–19th c. | Black chambers, Kasiski (Europe) |
| 06 | 1917 → 1940s | One-time pad, Enigma |
| 07 | 1975 → 2001 | DES, then AES (block ciphers) |
| 08 | 1976 – 1985 | Diffie–Hellman, RSA, ECC (public-key) |
| 09 | 1989 – 2012 | MD5 → SHA-1 → SHA-2 → SHA-3 (hashing) |
| 10 | 1991 – today | PGP, TLS, SSH, Signal (real-world systems) |
| 11 | 1976 – today | bcrypt → scrypt → Argon2 (password hashing) |
| 12 | 1994 – today | Shor's algorithm & post-quantum cryptography |

---

## Era 01 — The First Whisper  ·  Ancient Sparta, c. 700 BC

A Spartan general needs to send an order across enemy territory without a messenger being able to read it if he is captured. He takes a wooden rod of a particular diameter, wraps a long, narrow strip of leather around it in a tight spiral, and writes his message across the coil — left to right, top to bottom, one letter on each wrap. He unwraps the strip. The letters, now scattered along a strip of meaningless-looking leather, are handed to a runner. The receiver, who owns a rod of the **same diameter**, re-wraps it and reads the message.

**Problem it solved.** Couriers get captured. Plain messages on paper, parchment, or clay can be read by anyone who holds them. Armies, tax collectors, lovers, and conspirators all needed a way to send a written message that a literate, motivated third party could not read.

**How it works.** A strip is a long single-row tape. The rod wraps it into N parallel rows. Write horizontally and you get N rows of plaintext; unwrap and the letters scatter into one long ribbon in a different order. To recover, the receiver needs a rod of the right diameter so the number of rows matches. Plaintext "ATTACK AT DAWN" on a 5-row rod becomes "AKWANTATTACKDAWN" on the unwrapped strip.

**The flaw.** Once a codebreaker guesses the diameter (he just tries rods), the message falls. Worse, the letters of the plaintext remain in the ciphertext; an analyst who guesses the row count can unscramble. The scytale taught cryptography its first lesson — **obscure-by-shape is not the same as obscure-by-math**.

Around the same time, Hebrew scribes used a different idea: the **Atbash**, in which the first letter of the alphabet maps to the last, the second to the second-to-last, and so on. It is a *substitution cipher*: letters are replaced with other letters, unlike the scytale, which merely permutes them. Atbash is the ancestor of an idea that will dominate cryptography for two thousand years.

---

## Era 02 — Caesar & the Shift  ·  Roman Republic, c. 50 BC

Julius Caesar writes letters to Cicero and to his generals. He does not trust the couriers. So he takes every letter of his message and shifts it three places down the Latin alphabet. *A* becomes *D*, *B* becomes *E*, and *X* wraps around to *A*. The recipient shifts back. The order is fixed. The key — "three" — is shared out of band, before the war, in person, in a tent.

**How it works.** For each plaintext letter at position *p*, the ciphertext is `c = (p + k) mod 26`. Decrypt: `p = (c − k) mod 26`. The *Caesar cipher* is a **monoalphabetic substitution**: every letter is replaced by exactly one other letter, determined by a single shared key `k`. With k = 3, "ATTACK AT DAWN" → "DWWDFN DW GDZQ".

**The flaw.** Only 25 possible keys. A determined attacker can try them all by hand in a few minutes. Worse, even without trying keys, the substitution table is rigid: every *E* in the plaintext becomes the same letter in the ciphertext. This is the property that a 9th-century scholar will learn to exploit.

**The three lessons.** *One*: a key is necessary — without a shared secret, the cipher is worthless. *Two*: a small key space is death — if you can enumerate all keys, the enemy can too. *Three*: structure in the plaintext bleeds through to the ciphertext. Every weakness the Romans had, the Arabs would see.

---

## Era 03 — Al-Kindi Breaks the Silence  ·  Abbasid Baghdad, c. 850 AD

In the House of Wisdom, the great library of Baghdad, al-Kindī is studying the Quran. He is not a codebreaker by trade. But he notices something almost embarrassing in its simplicity: in any long Arabic text, certain letters appear far more often than others. *Alif* dominates. *Yāʾ* is rare. He realizes this fact is not a curiosity of holy text — it is a property of *every* language. And if a cipher maps each plaintext letter to one fixed ciphertext letter, then the pattern of frequencies in the ciphertext must, with very few exceptions, mirror the frequencies of the original language. He does not need to know the key. He just counts, and matches the most common ciphertext symbol to the most common letter of the language.

He writes the technique down in *A Manuscript on Deciphering Cryptographic Messages* — the birth of **cryptanalysis** as a discipline.

**What it broke.** Every monoalphabetic substitution, forever. The Caesar cipher, Atbash, the dozen random-substitution alphabets that medieval courts had used, the cryptograms of the early Renaissance — all were vulnerable to a single mathematical insight.

**The lesson for cipher designers.** If a pattern exists in the plaintext, hide it. Al-Kindī's paper forces every cipher maker to ask one question: *does the ciphertext look like the plaintext in any statistical way?* The whole rest of the story is an attempt to make the answer **no**.

For a long moment, the codebreakers have won. There is no good monoalphabetic cipher left in the world. The code makers need a new idea. It will take six hundred years.

---

## Era 04 — Alberti, Vigenère & the Long Calm  ·  Renaissance Italy, 1467 / 1553

Leon Battista Alberti, a Renaissance architect of the facade of Santa Maria Novella, publishes a short treatise called *De componendis cifris*. In it, he describes a physical disk: two concentric copper circles, the outer engraved with the plaintext alphabet, the inner with a shifted alphabet, the whole rotating on a pin. To encode a letter, you find the plaintext on the outer ring, look across to the inner ring, and write down whatever the inner ring shows. Then — and this is the new idea — *you rotate the inner ring*, and the substitution for the next letter is different.

Eighty-six years later, Giovan Battista Bellaso refines Alberti's disk into a practical scheme. Take a keyword — say, `LEMON`. Repeat it across the top of your message. The first letter of the message is shifted by `L`, the second by `E`, the third by `M`, and so on, cycling through the keyword. The same plaintext letter, in the same message, now maps to different ciphertext letters depending on where it falls in the key cycle. Frequency analysis, al-Kindī's great weapon, sees a flattened distribution. For the next three hundred years, this cipher — published under the wrong name as the **Vigenère cipher** — is called *le chiffre indéchiffrable*: the indecipherable cipher.

**How it works.** `cᵢ = (pᵢ + k[i mod m]) mod 26` where `m` is the key length. For the key `LEMON` over `ATTACKATDAWN`:

```
      A  T  T  A  C  K  A  T  D  A  W  N
key:  L  E  M  O  N  L  E  M  O  N  L  E
cipher:L  X  F  O  P  V  E  F  R  N  H  R
```

Two T's, one at position 1, one at position 7. Different keys → different ciphertext: T→X, T→F.

**The flaw.** The key is short and it repeats. A 5-letter keyword means every 5th letter is shifted by the same amount. A codebreaker just has to find the cycle length — by spotting repeated bigrams in the ciphertext. That is what Charles Babbage in 1854 and Friedrich Kasiski in 1863 independently figured out. Once you know the key length, you split the ciphertext into that many Caesar ciphers and frequency-analyse each one. *Le chiffre indéchiffrable* lasted about 300 years in practice, then fell in a single afternoon's math.

> "A cipher is breakable if its key is shorter than its message." — the implicit lesson of every era so far.

The natural next idea: make the key *as long as the message*, and *never repeat it*. If the key is truly random, as long as the message, and used only once, the cipher is — provably, mathematically — unbreakable. It is called the **one-time pad**, and it is the only cipher in history that is perfectly secure.

---

## Era 05 — Black Chambers & the Return of Frequency  ·  Europe, 16th–19th c.

While the cipher makers strut, the cipher breakers build institutions. Every major European power runs a *black chamber* — a state office whose entire job is to open other people's mail, copy the ciphertext, seal it back up, and crack it overnight. The French *Cabinet Noir* systematically reads Habsburg correspondence. The Habsburgs read the French. Both sides keep inventing new ciphers. Both sides keep getting cracked.

In 1854, Charles Babbage, the irascible Englishman who almost invented the computer, works out how to break Vigenère. He does not publish. In 1863, Friedrich Kasiski, a retired Prussian infantry officer, publishes the same idea in a thin book, *Die Geheimschriften und die Dechiffrir-Kunst*. The method is now called the **Kasiski examination**: look for repeated sequences in the ciphertext, measure the distances between them, take the greatest common divisor of those distances, and that is almost certainly the key length. From then on, the Vigenère family of ciphers is finished for serious use.

**The real lesson of this era.** Frequency analysis works against *any* cipher that has a repeating structure. Polyalphabetic substitution defeats it only as long as the key is long enough that the cycle does not become visible. The "long calm" from 1553 to 1854 was a 300-year illusion. Code makers who rely on obscurity of method, rather than obscurity of key, will lose.

---

## Era 06 — One-Time Pad & the Mechanical Storm  ·  1917 → 1940s

In 1917, two men independently invent the same cipher. Gilbert Vernam, an engineer at AT&T, proposes a system in which a teleprinter message is XORed character-by-character with a key tape. Joseph Mauborgne, a U.S. Army captain, realizes the same scheme and adds the rule that breaks everything else: the key tape must be *truly random*, *as long as the message*, and *never reused*. This is the **one-time pad (OTP)**. Claude Shannon will later prove, in 1949, that the OTP is information-theoretically secure: even an attacker with infinite compute cannot distinguish a real OTP ciphertext from random noise, because the ciphertext carries literally zero information about the message. It is the only perfectly secret cipher in existence.

It is also, in practice, a logistical nightmare. You and your recipient must somehow share a key as long as every message you will ever send, in advance, over a secure channel. For a spy in 1943, this means a tiny book of random numbers, memorized page by page, that must last a lifetime. The moment you reuse a key — and every spy agency on earth has, at some point, out of laziness or shortage — the cipher is broken. Soviet intelligence famously reused OTP keys in the 1940s and 1950s. American cryptanalysts, in a project called *VENONA*, exploited the reuse to read Moscow's cables for years. The moral: the one-time pad is mathematically perfect and operationally treacherous.

**How OTP works.** Each plaintext bit `pᵢ` is XORed with a random key bit `kᵢ` to produce ciphertext `cᵢ = pᵢ ⊕ kᵢ`. Decryption: `pᵢ = cᵢ ⊕ kᵢ`. Because every key bit is independent and equiprobable, every plaintext bit is equally likely.

```
plaintext  : 0 1 1 0 0 0 1 1   ("SOS" in 8-bit ASCII, simplified)
key (rand) : 1 0 1 1 0 1 0 0
XOR        : 1 1 0 1 0 1 1 1   ← ciphertext
```

### Enigma, and the breaking of it

While the theorists chase the perfect cipher, the field armies of the world adopt something far more practical: rotor machines. The most famous is the **Enigma**, patented by the German engineer Arthur Scherbius in 1918, deployed by the German military from the late 1920s. An Enigma machine has a keyboard, a lampboard, a plugboard at the front, and three (later four) rotors inside, each of which is a wired substitution that ticks forward like an odometer after every keypress. Critically, after each keypress, the rightmost rotor advances one position, so the next keypress is encrypted by a *different* set of substitutions. The total number of possible machine configurations is astronomical — about 10²³ in the wartime four-rotor setup, more than the number of stars in the Milky Way.

It is, however, not a one-time pad. The rotors are mechanical, the substitution repeats every 26⁴ ≈ 460,000 keystrokes, and crucially, *a letter can never encrypt to itself* — a constraint that turns out to be the very crack the Polish mathematician Marian Rejewski finds in 1932. By 1938, the Poles can read much German military traffic. When the Germans add new rotors and a more complex plugboard in 1939, the Poles hand their work to the British and the French. At Bletchley Park, Alan Turing and Gordon Welchman build on it: the *bombe*, an electromechanical device that chews through Enigma configurations at industrial speed, helped by sloppy operator habits and predictable message openings ("Heil Hitler", weather reports). By 1942, the Allies are reading a substantial fraction of German naval and army traffic. Historians estimate the work at Bletchley Park shortened the war by 2–4 years.

**The flaw that killed Enigma.** Structure, not key length. Enigma had a 26⁴ × huge-plugboard keyspace — far larger than any brute force. The Allies did not brute force it. They exploited *structural properties*: the no-letter-encrypts-to-itself rule, the regularity of the rotor stepping, and — most painfully for the Germans — the operational mistakes of their own operators. Cryptography is not a math contest; it is a system, and humans are always the weakest part.

By 1945, both sides have learned the same lesson. Polyalphabetic ciphers are not enough. The key has to be long, the system has to be mathematically analyzable, and the operators have to use it correctly. The next era, the era of the computer, will finally give the cipher makers what they need: ciphers whose security rests on the difficulty of a well-studied math problem.

---

## Era 07 — DES, AES & the Block Cipher  ·  1973 → 2001

After the war, cryptography is a military secret. The U.S. National Security Agency treats it as classified ordnance. That changes in 1972, when the National Bureau of Standards — now NIST — puts out a public call for a national cipher standard. IBM submits a design based on work by the German-born cryptographer Horst Feistel. The result is adopted in 1977 as the **Data Encryption Standard (DES)**, the first civilian, publicly scrutinized, mass-deployed block cipher.

**What a block cipher is.** A block cipher encrypts a fixed-size chunk of data — say, 64 bits in DES, 128 bits in AES — under a fixed key. It must be a *permutation*: every possible input maps to a unique output, and decryption is the reverse permutation. The trick is to design a permutation that is so tangled that, without the key, the permutation looks random, while with the key, it is fast to compute forward and backward. DES uses a 56-bit key. AES uses 128, 192, or 256.

**How DES/AES works — the Feistel pattern.** Split the block into two halves, L and R. For 16 rounds (DES) or 10–14 rounds (AES): the new right half is the old left half XORed with a *round function* `F` applied to the old right half and a subkey derived from the main key. Then swap. After all rounds, swap once more. Because the operation is invertible, you can run it backwards with the same subkeys in reverse order.

```
L₀ →  L₁ = R₀  →  L₂ = R₁  →  …
R₀ →  R₁ = L₀ ⊕ F(R₀, k₁)
        →  R₂ = L₁ ⊕ F(R₁, k₂)
        →  …
```

**The flaw that killed DES.** 56 bits is not enough. By the 1990s, a 56-bit key is brute-forceable. The EFF's "Deep Crack" machine, built in 1998 for $250,000, tests 9×10¹⁰ keys per second and finds a DES key in about 56 hours.

### AES — the Rijndael cipher (2001)

Fifteen submissions are whittled down to five finalists, then to one. The winner is **Rijndael**, designed by two Belgian cryptographers, Joan Daemen and Vincent Rijmen. It is adopted as the **Advanced Encryption Standard (AES)** in 2001. AES operates on 128-bit blocks with 128-, 192-, or 256-bit keys, using 10, 12, or 14 rounds of a substitution–permutation network. Each round: *SubBytes* (a fixed non-linear S-box), *ShiftRows* (a permutation), *MixColumns* (a linear mixing in GF(2⁸)), and *AddRoundKey* (XOR with the round key). After more than two decades and uncountable cryptanalyses, the best known attack on full AES-128 still requires roughly 2¹²⁶ operations — close to brute force. AES is, today, the workhorse of symmetric encryption on the planet. Your TLS connection, your Wi-Fi, your disk encryption, your VPN, your SSH session, your Bitcoin wallet's seed storage — almost all of them use AES under the hood.

**Modes of operation.** A block cipher encrypts a single block at a time. To encrypt a long message, you need a *mode of operation*. Naive modes (ECB) leak patterns. Modern modes (CBC, CTR, GCM) chain blocks together with an initialization vector and, in the case of **GCM** (Galois/Counter Mode), also provide authentication — meaning the receiver can tell whether the ciphertext was tampered with. GCM is what TLS 1.3 actually uses.

---

## Era 08 — Public-Key & the Impossible Key Exchange  ·  1976 – 1985

Throughout all of the previous eras, every cipher has the same fatal structural flaw: **both sides must share the same secret key, before any communication can happen**. To send a message to someone, you must first meet them in person, or send a trusted courier, or use some pre-existing secure channel. The more people you want to talk to, the more keys you must distribute, the more chances there are to fail. By 1970, the number of symmetric keys required to connect a network of *n* people is roughly *n*² — a million people need a billion keys, and every one of them must be delivered by hand. This is the **key distribution problem**, and it is, in some sense, the original sin of cryptography.

In 1976, two American cryptographers, Whitfield Diffie and Martin Hellman, propose a radical idea. What if a key is split in two — a *public* half and a *private* half? The public half is published in the phone book. The private half never leaves your pocket. Anyone in the world can use your public key to encrypt a message to you, and only you, with your private key, can decrypt it. Mathematically, the two halves are related, but deriving the private half from the public half is computationally infeasible. The paper is called *New Directions in Cryptography*, and it is the most important paper in the field since al-Kindī's manuscript a thousand years earlier. (A British cryptographer named James Ellis at GCHQ had the same idea in 1969, and Clifford Cocks at GCHQ discovered RSA itself in 1973 — but it was all classified, and the public discovery changed the world anyway.)

### Diffie–Hellman key exchange (1976)

Diffie and Hellman's original paper gives a way for two strangers to *agree on a shared secret over an insecure channel*, without having met before. The protocol is built on a *one-way function* in modular arithmetic:

**How it works.** Alice and Bob agree on a public prime *p* and a public base *g*. Alice picks a secret *a*, sends Bob `A = gᵃ mod p`. Bob picks a secret *b*, sends Alice `B = gᵇ mod p`. Alice computes `Bᵃ mod p = gᵃᵇ mod p`. Bob computes `Aᵇ mod p = gᵃᵇ mod p`. They now share a secret `gᵃᵇ mod p`. An eavesdropper sees `gᵃ` and `gᵇ`, but computing *a* from `gᵃ mod p` — the **discrete logarithm problem** — is believed to be intractable for large enough *p*.

```
public:   p = 23, g = 5
Alice:   a = 6  →  A = 5⁶  mod 23 = 8
Bob:     b = 15 →  B = 5¹⁵ mod 23 = 19
exchange over the wire: A=8, B=19
shared:  Alice: 19⁶  mod 23 = 2
         Bob:    8¹⁵ mod 23 = 2     ✓ same secret
```

**What it solved.** For the first time in history, two strangers who have never met can agree on a secret that no eavesdropper can derive from the public exchange. This is the foundation of every modern internet handshake. It does not require a courier. It does not require a pre-shared key. It just requires a math problem that is hard to reverse.

### RSA (1977)

A year after Diffie–Hellman, three MIT researchers — Ron Rivest, Adi Shamir, and Leonard Adleman — publish the first practical public-key *encryption* and *digital signature* scheme. The trick is the same modular arithmetic, but with a different one-way function: multiplication is easy, factoring is hard.

**How RSA works.** Choose two large random primes *p* and *q*. Compute *n = p·q*. Choose *e* coprime to *(p−1)(q−1)*. Compute *d* such that *e·d ≡ 1 (mod (p−1)(q−1))*. The **public key** is *(n, e)*. The **private key** is *d*. To encrypt a message *m*: `c = mᵉ mod n`. To decrypt: `m = cᵈ mod n`. To sign: `s = mᵈ mod n`; anyone can verify with `sᵉ mod n = m`. The entire security of RSA rests on the fact that multiplying *p* and *q* is trivial, but recovering them from *n* — **integer factorization** — is not.

| Public key (share with the world) | Private key (never share) |
|---|---|
| n = p · q (a 2048-bit number) | d such that e·d ≡ 1 (mod (p−1)(q−1)) |
| e = 65537 (often) | (equivalently: the prime factors p, q) |

**The flaw that will eventually threaten RSA.** No one has ever proven that factoring 2048-bit numbers is fundamentally intractable. The best known classical algorithm, the *General Number Field Sieve*, is sub-exponential but still infeasible. In 1994, Peter Shor shows that a sufficiently large quantum computer could factor in polynomial time. The moment a cryptographically relevant quantum computer exists, every RSA key ever recorded is breakable. This is why NIST has been running the post-quantum competition since 2016.

### Elliptic-curve cryptography (1985)

Independently proposed by Neal Koblitz and Victor Miller in 1985, **ECC** replaces the integer multiplication / factoring one-way function with arithmetic on a carefully chosen elliptic curve over a finite field. The discrete log problem on an elliptic curve is believed to be much harder than ordinary discrete log: a 256-bit elliptic-curve key offers roughly the security of a 3072-bit RSA key. That efficiency advantage matters in small devices — smart cards, phones, IoT sensors, Apple's Secure Enclave, the Bitcoin and Ethereum signature algorithms. Today, ECDSA and ECDH are the workhorses of public-key on the consumer internet. Curve25519, designed by Daniel Bernstein in 2005, is the modern default — used by SSH, Signal, Tor, WhatsApp, and TLS 1.3.

**What this whole era gave us.** Three new primitives, all built on the same trick — a math problem that is easy in one direction and hard in the other:

- **Public-key encryption** (RSA, ECIES): encrypt with the public key, only the private-key holder can decrypt.
- **Digital signatures** (RSA-PSS, ECDSA, Ed25519): sign with the private key, anyone can verify with the public key. This is what gives software updates, code commits, and TLS certificates their authenticity.
- **Key agreement** (Diffie–Hellman, ECDH): two parties derive a shared secret over an insecure channel, then use it as a symmetric key for AES.

The pattern, from now on, is always the same: *use public-key to establish trust and agree on a key, then switch to fast symmetric crypto (AES) for the actual data*. Public-key is for the handshake. Symmetric-key is for the conversation.

---

## Era 09 — Hashing & the Fingerprint  ·  1989 – 2012

Encryption keeps a secret. But sometimes you do not need a secret. You need a *fingerprint*. You have a file. You want to know, later, whether it is the same file. You want to be sure a software update has not been tampered with in transit. You want to store passwords without actually keeping them. You want a unique, fixed-size handle for an arbitrarily large blob of data, with the property that no two different blobs share the same handle. That is a **cryptographic hash function**. It is not encryption — there is no key, no decryption, no secret. It is a one-way function from "any length" to "fixed length" with three unforgiving properties: *preimage resistance* (given a hash, you cannot find the input), *second-preimage resistance* (given an input, you cannot find a different input with the same hash), and *collision resistance* (you cannot find any two inputs with the same hash).

**How a hash works.** Pad the input to a multiple of the block size, then process it block by block through a *compression function*. Each new block's output depends on the previous block's output (the *chain*), so a change in any bit of the input eventually propagates everywhere. Final output: a fixed-size digest (160 bits for SHA-1, 256 bits for SHA-256, 512 for SHA-512, arbitrary for SHA-3/Keccak).

```
"Hello"           →  185f8db3 2271f6f7...
"Hello."          →  2c8e9b70 ...   (one byte in, completely different hash out — the avalanche effect)
```

**The flaw that killed MD5 and SHA-1.** MD5 (Rivest, 1991) was the workhorse of the 1990s. SHA-1 (NSA, 1995) replaced it for serious use. In 2004, Wang et al. produce the first practical SHA-1 collision. By 2017, Google's SHAttered project produces a chosen-prefix collision for the full SHA-1, two PDF files with the same SHA-1 hash but visibly different content. Today, MD5 and SHA-1 are considered broken; SHA-2 (especially SHA-256) and SHA-3 (Keccak) are the modern defaults.

**What hashes are for.**
- **Integrity** — the SHA-256 checksum on a downloaded file, the SHA-256 reference in a software update manifest.
- **Signatures** — instead of signing a 1 GB document, sign its 256-bit hash.
- **Commitment schemes** — publish a hash now, reveal the input later. Anyone can verify the reveal matches the commitment.
- **Data structures** — Merkle trees (used in git, IPFS, Bitcoin, certificate transparency logs) hash children to parents, all the way up to a single root hash that authenticates an enormous set.
- **Password storage** — but not plain hashing. See Era 11.

---

## Era 10 — The Real World: TLS, SSH, Signal  ·  1991 – today

By 1990, all the building blocks are in place. RSA, DES, SHA, Diffie–Hellman. Now the question becomes: how do you actually use them? Almost no one in the world — outside a few thousand cryptographers and engineers — wants to call a math library every time they read their email. The 1990s and 2000s are the era where cryptography gets *packaged*: turned into protocols, libraries, and products that ordinary software and ordinary people can use without thinking about the math.

### PGP and the email problem (1991)

In 1991, Phil Zimmermann, a privacy activist in Boulder, Colorado, releases **Pretty Good Privacy (PGP)** — the first time strong public-key encryption is available to ordinary civilians. PGP lets you encrypt email with RSA, sign it with a hash, and distribute your public key through a "web of trust" — your friends sign your key, their friends sign theirs, and you trust a key if enough people you trust have signed it. The U.S. government investigates Zimmermann for three years for "exporting munitions" (strong crypto was, at the time, classified as a weapon). He is never charged. PGP becomes the spiritual ancestor of every end-to-end encrypted messaging system we use today.

### SSL and TLS — the lock in your browser (1994–2018)

In 1994, Taher Elgamal at Netscape designs **SSL 2.0** to protect the world's first commercial web browser. SSL 1.0 was never released. SSL 3.0 (1996) is the first widely-deployed version. In 1999, the IETF standardizes the protocol under a new name: **TLS 1.0**. TLS 1.1 (2006), TLS 1.2 (2008) follow. The current standard, **TLS 1.3** (RFC 8446, 2018), is a near-total rewrite: only authenticated encryption (AEAD, e.g. AES-GCM or ChaCha20-Poly1305), no CBC mode, no MD5, no SHA-1, no static RSA key exchange, no renegotiation, and a one-and-a-half-round-trip handshake that is both faster and simpler than its predecessors.

The story of every padlock in your browser is: *TLS_ECDHE_ECDSA_WITH_AES_256_GCM_SHA384*. Read that as English: "Use elliptic-curve Diffie–Hellman (with new keys every session) to agree on a key. Authenticate the server with an elliptic-curve signature. Encrypt everything with AES-256 in GCM mode. Hash the handshake with SHA-384." It is the same five-beat structure, every connection, billions of times a day.

### SSH (1995)

Tatu Ylönen, a researcher at Helsinki University of Technology, gets tired of having his password sniffed on the university's network. In 1995, he writes **SSH** (Secure Shell), a protocol that replaces telnet and rsh with an encrypted, authenticated remote-login session. SSH-1 is soon broken. SSH-2 (1996, RFCs 4251–4254) is the current version, and every Unix sysadmin on earth has used it ten thousand times. The default key exchange today is Curve25519 ECDH, the default signature is Ed25519, the default cipher is ChaCha20-Poly1305 or AES-GCM.

### Signal Protocol — the messenger era (2013)

By the early 2010s, the unsolved problem is messaging. PGP works for email between two technical users who already trust each other's keys. But what about group chats, disappearing messages, conversation history that needs to survive lost phones, and the fact that most users cannot tell a phishing email from a real one? In 2013, Moxie Marlinspike and Trevor Perrin publish the **Signal Protocol**, which combines three ideas: the **Double Ratchet** (every message uses a fresh key derived from the previous one — the X3DH key agreement + a per-message symmetric ratchet), **forward secrecy** (compromising today's key does not reveal yesterday's messages), and **post-compromise security** (the protocol heals itself after a key leak). Signal, WhatsApp, Google Messages, Facebook Messenger's secret conversations, and Skype all now use the Signal Protocol — roughly two billion people.

### WireGuard (2017) and modern VPNs

Most VPNs of the 2010s are based on IPsec or OpenVPN, both decades old, both notoriously complex, both with sprawling codebases measured in hundreds of thousands of lines. In 2017, Jason Donenfeld releases **WireGuard**: ~4,000 lines of code, modern cryptography only (Curve25519 for key agreement, ChaCha20-Poly1305 for encryption, BLAKE2 for hashing, HKDF for key derivation), no cipher negotiation, no certificate hierarchies, no mode confusion. WireGuard is now in the Linux kernel. The lesson, again: simpler is more secure.

---

## Era 11 — Passwords Done Right  ·  1976 – today

If you remember only one thing from the whole story, let it be this. **Never store passwords in plaintext. Never hash passwords with a fast hash. Never, ever, hash a password with SHA-1 or SHA-256 alone.** The reason is not subtle. A fast hash is designed to be fast. A modern rig can compute billions of MD5 hashes per second. If your database leaks and the passwords are hashed with a fast hash, the attacker can try the entire English dictionary, the entire RockYou list, every password ever leaked from any other site, in hours. The fix is to use a hash function that is *deliberately slow* and *deliberately memory-hungry*, and to add a unique random salt to every password so two users with the same password do not get the same hash.

**The password-hashing ladder.**
- **Unix crypt (1976)** — Robert Morris's original DES-based `crypt()`. 4096 hashes per second per core. Broken.
- **MD5 / SHA-1 (1990s)** — better than nothing, but far too fast. Billions of guesses per second on a GPU. Considered broken since the 2000s.
- **bcrypt (1999)** — Provos and Mazières at OpenBSD. Adaptive cost factor, blowfish-based, intentionally slow. Tunable: as hardware gets faster, you raise the cost. Still in wide use.
- **scrypt (2009)** — Colin Percival adds a memory-hard component: the function cannot be parallelized cheaply on a GPU or ASIC because it requires a large working set of memory. Slower per hash, but the attacker cannot just throw more silicon at it.
- **Argon2 (2015)** — winner of the Password Hashing Competition. Three variants: Argon2d (data-dependent, max memory hardness), Argon2i (data-independent, side-channel resistant), Argon2id (hybrid, recommended). Tunable for time cost, memory cost, and parallelism. Current best practice.

> "If you can guess a user's password by brute force in under a second, you have not hashed it — you have merely obfuscated it." — modern security lore

---

## Era 12 — The Quantum Cliff & What Comes After  ·  1994 – today

In 1994, a mathematician at Bell Labs named Peter Shor publishes an algorithm that, if run on a sufficiently powerful quantum computer, would factor large integers in polynomial time. It would also solve the discrete logarithm problem. In one paper, Shor's algorithm makes RSA, Diffie–Hellman, DSA, ECDH, and ECDSA all breakable at once. In 1996, Lov Grover publishes a separate quantum algorithm that gives a quadratic speedup on brute-force search, effectively halving the security of symmetric ciphers and hashes. AES-256, against Grover, is roughly AES-128 against classical brute force — still safe. AES-128, against Grover, is roughly AES-64 — too weak.

No one has built a cryptographically relevant quantum computer yet. The current record is factoring small numbers like 21 on a few hundred noisy qubits. The estimates for breaking a real 2048-bit RSA key range from "a few decades away" to "never, due to fundamental physical limits." But cryptography must plan in decades, not in years. An adversary can record today's TLS traffic, store it, and decrypt it later when a quantum computer exists. This is the **harvest now, decrypt later** attack, and it is the reason NIST has been running a post-quantum competition since 2016.

**The post-quantum winners (2022/2024 standards).**
- **CRYSTALS-Kyber** (now ML-KEM) — key encapsulation, based on the hardness of *learning-with-errors* in module lattices. Replaces Diffie–Hellman in TLS 1.3.
- **CRYSTALS-Dilithium** (now ML-DSA) — digital signatures, same lattice family. Replaces RSA / ECDSA in most contexts.
- **FALCON** — another lattice signature, smaller signatures than Dilithium. Useful when size matters (DNSSEC, blockchain).
- **SPHINCS+** (now SLH-DSA) — signature based only on the security of hash functions. Larger and slower than lattice schemes, but the security argument is older and more conservative. The conservative fallback.

None of these schemes depend on factoring or discrete logs. They depend on hard problems in lattices, hash-function preimages, and error-correcting codes — for which no polynomial-time quantum algorithm is known. As of 2024, NIST has standardized ML-KEM, ML-DSA, and SLH-DSA. TLS 1.3 has draft hybrid key-exchange mechanisms (X25519 + ML-KEM-768) so that a connection is secure if *either* the classical or the post-quantum component holds.

**The deeper frontier.** Post-quantum cryptography is one branch of a much larger frontier:
- **Zero-knowledge proofs** — prove you know a secret without revealing it. ZK-SNARKs (used in Zcash) and ZK-STARKs (used in StarkNet) are the headline constructions.
- **Fully homomorphic encryption (FHE)** — compute on encrypted data without ever decrypting it. A cloud can run your queries on your encrypted medical record and return an encrypted result, learning nothing. Practical FHE arrived around 2009 (Craig Gentry's breakthrough) and is now used in production.
- **Secure multi-party computation (MPC)** — multiple parties jointly compute a function of their secrets without revealing them to each other.
- **Threshold cryptography** — split a private key into N shares, require any M of them to sign. Used in cryptocurrency custody and root keys of major certificate authorities.
- **Quantum key distribution (QKD)** — use the laws of physics to detect eavesdropping on the key exchange. Beautiful in theory, practically limited.

---

## The Pattern That Never Ends

If you step back from 3,000 years of struggle, you see a single rhythm, repeating. Almost every cryptographic advance is the same five beats:

1. **An era of confident use.** The new cipher is "unbreakable." (Caesar, Vigenère, DES, MD5 — all said it.)
2. **The slow discovery of a flaw.** Frequency analysis, key-cycle recovery, brute force, collision attacks, quantum algorithms.
3. **The cipher falls.** Publicly, sometimes embarrassingly, almost always in retrospect.
4. **A new primitive is invented.** Driven by a hard math problem (factoring, discrete log, lattices) or by a better construction (Feistel, sponge, ratchet).
5. **New code makers trust it.** Until the cycle repeats.

Cryptography is not a destination. It is a discipline. The day you stop worrying about a cipher is the day someone, somewhere, is writing the paper that will break it. The ciphers in your browser today — AES-256, ChaCha20-Poly1305, X25519, ML-KEM, SHA-256, Ed25519, Argon2id — are the best we have ever had. They are also, by definition, the next thing an attacker will study. The long war is not over. It is, if anything, accelerating.

> "The only system that is truly secure is one that is powered off." — Gene Spafford, often quoted by his students

---

## A note on sources

The technical content is drawn from standard references: Kahn's *The Codebreakers*; Singh's *The Code Book*; the NIST FIPS 197 (AES) and FIPS 202 (SHA-3) publications; the TLS 1.3 RFC (8446); Bernstein's Curve25519 paper; the Signal Protocol documentation; and the NIST Post-Quantum Cryptography project pages. Where dates are contested in the literature (Vigenère, RSA, public-key priority between GCHQ and the open community), the conventional public-history dates are used; the classified priority is noted in passing.
