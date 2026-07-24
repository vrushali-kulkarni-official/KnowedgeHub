
### What is GloVe-100? (Very Simple Explanation)

Imagine every word is converted into a list of numbers so that a computer can understand its meaning.

For example:

```python
"cat"  -> [0.21, -0.54, 0.89, ..., 0.12]
"dog"  -> [0.19, -0.50, 0.85, ..., 0.15]
"car"  -> [-0.72, 0.31, -0.44, ..., 0.67]
```

The list of numbers is called an **embedding vector**.

**GloVe-100** means:

* **GloVe** = Global Vectors for Word Representation (a word embedding algorithm created at Stanford in 2014) ([Stanford NLP Group][1])
* **100** = each word is represented by **100 numbers (100 dimensions)**. ([sparknlp.org][2])

So:

```python
"king" -> [100 numbers]
"queen" -> [100 numbers]
"apple" -> [100 numbers]
```

---

## Why do we need this?

Computers don't understand words.

For a computer:

```python
"cat"
```

is just text.

We need to convert words into numbers before using Machine Learning or Deep Learning.

Bad way:

```python
cat = 1
dog = 2
car = 3
```

This tells the computer nothing about meaning.

It would think:

```python
dog > cat
```

which is nonsense.

---

## What GloVe does

GloVe learns word meanings from huge amounts of text.

It notices things like:

```text
cat appears near:
  pet
  animal
  kitten

dog appears near:
  pet
  animal
  puppy

car appears near:
  engine
  road
  vehicle
```

Because "cat" and "dog" appear in similar contexts, their vectors become similar. ([Stanford NLP Group][1])

---

## Example

Suppose (simplified):

```python
cat = [0.8, 0.2, 0.9]
dog = [0.7, 0.3, 0.8]
car = [-0.5, 0.9, -0.3]
```

Notice:

```python
cat ≈ dog
```

but

```python
cat ≠ car
```

The computer can now understand that:

```text
cat and dog are related
cat and car are not
```

---

## Why 100 Dimensions?

Think of dimensions as features.

A 2D vector:

```python
[0.5, 0.8]
```

can store very little information.

A 100D vector:

```python
[0.5, 0.8, -0.3, 0.2, ..., 0.9]
```

can store much more meaning. ([pythonandml.github.io][3])

Common GloVe sizes are:

| Model     | Dimensions |
| --------- | ---------- |
| GloVe-50  | 50         |
| GloVe-100 | 100        |
| GloVe-200 | 200        |
| GloVe-300 | 300        |

([pythonandml.github.io][3])

Higher dimensions:

* More expressive
* Better quality
* More memory
* Slower

---

## Real Example

A GloVe-100 vector might look like:

```python
king =
[0.504, -0.221, 0.456, ... 100 values]
```

```python
queen =
[0.498, -0.215, 0.463, ... 100 values]
```

These vectors end up close together because the words have similar meanings. ([Stanford NLP Group][1])

---

## In a RAG Pipeline

You normally **do not use GloVe for documents anymore**.

Modern RAG uses:

* OpenAI embeddings
* BGE embeddings
* E5 embeddings
* Nomic embeddings
* Gemini embeddings

because they create embeddings for entire sentences and paragraphs.

GloVe creates embeddings only for individual words. ([Stanford NLP Group][1])

Example:

```python
"cat"      -> vector
"dog"      -> vector
```

But not directly:

```python
"How do I train a dog?"
```

You would have to combine word vectors yourself.

Modern embedding models directly produce:

```python
Sentence
   ↓
768/1024/1536 dimensional vector
```

which works much better for RAG.

---

## Simple Analogy

Imagine every word is a person on a map.

```text
Cat      Dog
  ●------●





Car                     Plane
 ●----------------------●
```

Words with similar meanings stand close together.

GloVe-100 is simply a way of deciding the coordinates of each word using **100 coordinates instead of just 2**. ([Stanford NLP Group][1])

### One-line definition

**GloVe-100 is a pre-trained word embedding model where every word is represented by a vector of 100 numbers, allowing computers to measure semantic similarity between words.** ([Wolfram Resource System][4])

[1]: https://nlp.stanford.edu/projects/glove/?utm_source=chatgpt.com "GloVe: Global Vectors for Word Representation"
[2]: https://sparknlp.org/2020/01/22/glove_100d.html?utm_source=chatgpt.com "Glove Embeddings 6B 100 | glove_100d | Spark NLP 2.4.0"
[3]: https://pythonandml.github.io/dlbook/content/word_embeddings/glove.html?utm_source=chatgpt.com "4.2.2 GloVe — Oddly Satisfying Deep Learning"
[4]: https://resources.wolframcloud.com/NeuralNetRepository/resources/GloVe-100-Dimensional-Word-Vectors-Trained-on-Wikipedia-and-Gigaword-5-Data/?utm_source=chatgpt.com "GloVe 100-Dimensional Word Vectors - Wolfram Neural Net Repository"
