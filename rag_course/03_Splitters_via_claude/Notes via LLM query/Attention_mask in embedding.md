When working with **embeddings in RAG systems**, the `attention_mask` is often passed alongside the tokenized text to the embedding model. It tells the transformer **which tokens are real content and which tokens are just padding**.

---

# Why do we need `attention_mask`?

Transformer models require inputs in batches to have the same length.

Suppose you have two sentences:

```text
Doc 1: "I love AI"
Doc 2: "Artificial Intelligence is changing the world"
```

After tokenization:

```python
Doc 1 = [101, 1045, 2293, 9932, 102]
Doc 2 = [101, 7976, 4454, 2003, 2559, 1996, 2088, 102]
```

Lengths:

```text
Doc 1 = 5 tokens
Doc 2 = 8 tokens
```

To create a batch, the shorter sentence must be padded:

```python
Doc 1 = [101, 1045, 2293, 9932, 102,   0,   0,   0]
Doc 2 = [101, 7976, 4454, 2003, 2559, 1996, 2088, 102]
```

where:

```text
0 = PAD token
```

Now both sequences have length 8.

---

# The problem

Without an attention mask, the transformer would think:

```text
0
0
0
```

are actual words.

The model would attend to them and produce incorrect embeddings.

---

# Solution: Attention Mask

The tokenizer creates:

```python
attention_mask =
[
 [1,1,1,1,1,0,0,0],
 [1,1,1,1,1,1,1,1]
]
```

Meaning:

```text
1 = Real token
0 = Ignore token
```

---

# Example using HuggingFace

```python
from transformers import AutoTokenizer

tokenizer = AutoTokenizer.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")

encoded = tokenizer(
    ["I love AI", "Artificial Intelligence is changing the world"],
    padding=True,
    truncation=True,
    return_tensors="pt",
)

print(encoded)
```

Output:

```python
{
    "input_ids": tensor([
        [101, 1045, 2293, 9932, 102, 0, 0, 0],
        [101, 7976, 4454, 2003, 2559, 1996, 2088, 102],
    ]),
    "attention_mask": tensor([[1, 1, 1, 1, 1, 0, 0, 0], [1, 1, 1, 1, 1, 1, 1, 1]]),
}
```

---

# How attention_mask is used inside Self-Attention

Recall the transformer attention formula:

[
Attention(Q,K,V) = Softmax\left(\frac{QK^T}{\sqrt{d}}\right)V
]

Before the softmax is applied, positions where:

```text
attention_mask = 0
```

are assigned a very large negative value:

```python
-10000
```

or

```python
-inf
```

So:

```python
softmax(-inf) = 0
```

The model completely ignores those tokens.

---

# Why is this important for embeddings?

In RAG, we often generate embeddings like:

```python
embeddings = model(**encoded)
```

The output contains one vector per token:

```text
Token 1 -> 384 dimensions
Token 2 -> 384 dimensions
...
```

To get a single document embedding, we perform pooling.

For example:

```python
sentence_embedding = mean_pooling(token_embeddings, attention_mask)
```

---

# Why pooling needs attention_mask

Imagine:

```text
Real tokens = 5
Padding tokens = 3
```

Token embeddings:

```text
Token1 = [1,2]
Token2 = [2,3]
Token3 = [3,4]
Token4 = [4,5]
Token5 = [5,6]

PAD1 = [0,0]
PAD2 = [0,0]
PAD3 = [0,0]
```

If you average all 8 vectors:

```text
(1+2+3+4+5)/8 = 1.875
```

Wrong.

You should average only the 5 real tokens:

```text
(1+2+3+4+5)/5 = 3
```

Correct.

The attention mask tells the pooling function:

```text
Ignore PAD tokens
```

---

# Mean Pooling Code from Sentence Transformers

You may have seen code like:

```python
token_embeddings = model_output[0]

input_mask_expanded = (
    attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
)

sentence_embedding = torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(
    input_mask_expanded.sum(1), min=1e-9
)
```

What happens?

### Step 1

Mask:

```text
[1,1,1,1,1,0,0,0]
```

becomes

```text
[
 [1,1,1,...],
 [1,1,1,...],
 [1,1,1,...],
 [1,1,1,...],
 [1,1,1,...],
 [0,0,0,...],
 [0,0,0,...],
 [0,0,0,...]
]
```

matching embedding dimensions.

---

### Step 2

Multiply:

```python
token_embeddings * mask
```

Padding embeddings become:

```text
[0,0,0,...]
```

---

### Step 3

Sum only real token embeddings.

---

### Step 4

Divide by number of real tokens.

Not by total sequence length.

---

# In Real-World RAG Pipelines

When you use:

```python
SentenceTransformer("all-MiniLM-L6-v2")
```

the library automatically:

1. Tokenizes text
2. Creates attention masks
3. Runs transformer
4. Applies masked mean pooling
5. Returns final embeddings

You normally never see the attention mask.

---

# Production Example

When embedding a chunk:

```python
chunk = "Transformers use self-attention..."
```

Internally:

```python
tokens = tokenizer(chunk)
attention_mask = [1, 1, 1, 1, 1, ...]
```

For a shorter chunk:

```python
chunk = "Hello world"
```

Internally:

```python
input_ids =
[101, 7592, 2088, 102, 0, 0, 0, ...]

attention_mask =
[1,1,1,1,0,0,0,...]
```

The mask ensures:

* Transformer ignores padding
* Pooling ignores padding
* Final embedding represents only the actual text

---

### Simple mental model

Think of `attention_mask` as a **"valid token marker"**:

```text
1 = This word exists, use it
0 = This is padding, ignore it
```

In embedding models used in RAG (MiniLM, MPNet, BGE, E5, GTE, etc.), the attention mask is crucial because both the transformer layer and the pooling layer rely on it to ensure the final embedding represents only the real text and not the padding added for batching.
