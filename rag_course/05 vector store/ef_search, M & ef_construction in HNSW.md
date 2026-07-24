If you understand **just three HNSW parameters**, you understand about **90% of HNSW tuning**:

1. **M** → *How many roads each city has*
2. **ef_construction** → *How carefully those roads are built*
3. **ef_search** → *How many roads you explore while searching*

Let's build this from first principles.

---

# First, remember how HNSW works

Imagine your vectors are cities.

Instead of comparing your query against **every city** (brute force), HNSW builds a graph.

Example:

```
        A -------- B
       / \        / \
      C---D------E---F
          |      |
          G------H
```

Every city (vector) connects to nearby cities.

When searching, you don't visit every city.

Instead, you "walk" through the graph.

```
Query
  ↓
A → D → G → H

Found nearest vector.
```

The graph quality determines how quickly you find the answer.

---

# The three parameters

These parameters affect different stages.

| Parameter       | Used During    | Can Change Later? |
| --------------- | -------------- | ----------------- |
| M               | Index building | ❌ No              |
| ef_construction | Index building | ❌ No              |
| ef_search       | Query/search   | ✅ Yes             |

Think of it like constructing a highway system.

```
Construction phase
    |
    |---- M
    |
    |---- ef_construction
    |
Index Finished
    |
Searching
    |
    |---- ef_search
```

---

# 1. M (Maximum Connections)

This is the easiest parameter.

## What does it mean?

Every vector connects to nearby vectors.

M decides

> **How many neighbors each vector is allowed to keep.**

Suppose M = 2

```
       A
      / \
     B   C
```

Only two roads.

---

Now M = 5

```
        A
      / | \
     B  C  D
    /   |   \
   E    F    G
```

Much denser graph.

---

## Real-world analogy

Imagine Google Maps.

### Small M

Every city has only

* 2 roads

```
A ----- B ----- C
```

Finding another city can require lots of turns.

---

### Large M

Every city has many roads.

```
      B
     /
A---C---D
|\  |  /|
| \ | / |
E---F---G
```

Many shortcuts exist.

Finding destinations becomes easier.

---

## Advantages of larger M

Higher M means

✅ More possible routes

✅ Better graph

✅ Better recall

---

## Disadvantages

More memory.

Suppose

```
1 million vectors
```

M = 16

Each vector stores 16 neighbors.

```
1,000,000 × 16
```

neighbor links.

---

Now M = 64

```
1,000,000 × 64
```

Four times more links.

Much more RAM.

---

## Summary

Higher M

```
Better recall
Higher memory
Longer build
```

Lower M

```
Less memory
Faster build
Lower recall
```

Typical production values are often around **16** by default, with **32–64** used when very high recall or higher-dimensional embeddings justify the additional memory. ([AI/TLDR][1])

---

# 2. ef_construction

This parameter is used **only while building the graph**.

This is where many beginners get confused.

M decides

> How many neighbors to KEEP.

ef_construction decides

> How many neighbors to CONSIDER before choosing those M neighbors.

---

Imagine inserting a new vector.

```
New vector X
```

Suppose

```
M = 4
```

Eventually X can only keep

```
4 neighbors
```

Question:

How do we decide which four?

---

Suppose nearby vectors are

```
A
B
C
D
E
F
G
H
I
```

---

## Small ef_construction

Suppose

```
ef_construction = 4
```

Algorithm only looks at

```
A
B
C
D
```

Chooses

```
A
B
C
D
```

Done.

Maybe E was actually closer.

Too late.

---

## Large ef_construction

Suppose

```
ef_construction = 200
```

Algorithm explores

```
A
B
C
D
E
F
G
...
200 candidates
```

Now it can choose the truly best neighbors.

Graph quality improves.

---

Think of hiring employees.

Small search:

```
Interview 5 people

Hire best one
```

Large search:

```
Interview 500 people

Hire best one
```

Better employee.

Same idea.

---

## Important point

After the graph is built

```
ef_construction disappears.
```

It is never used again.

Changing it later requires rebuilding the index because it determines the graph's structure. ([index-management.org][2])

---

## Effects

Higher ef_construction

```
Much slower indexing

Better graph

Higher recall
```

Lower

```
Fast build

Poor graph

Lower recall
```

---

# 3. ef_search

This is the runtime parameter.

Unlike the previous two,

you can change it every query.

This is why databases expose it.

---

Suppose your graph looks like

```
A --- B --- C
|     |
D --- E --- F
      |
      G
```

You search from A.

---

Small ef_search

Suppose

```
ef_search = 5
```

Algorithm explores only

```
A
B
D
E
F
```

Stops.

Maybe the nearest vector was G.

Never reached.

---

Large ef_search

Suppose

```
ef_search = 100
```

Algorithm explores

```
A
B
D
E
F
G
...
```

Much more of the graph.

Higher chance of finding the true nearest neighbor.

---

## Think of treasure hunting

Small ef_search

```
Search first 5 houses.
```

Large ef_search

```
Search first 500 houses.
```

More effort → better chance of success.

---

## Tradeoff

Higher ef_search

```
Higher recall

Higher latency

More CPU
```

Lower ef_search

```
Very fast

May miss neighbors
```

Unlike the build-time parameters, **ef_search** is intended to be adjusted at query time to trade latency for recall. ([AI/TLDR][1])

---

# Putting everything together

Suppose you're building an HNSW index.

```
                Build Phase
                     │
      ┌──────────────┴──────────────┐
      │                             │
      ▼                             ▼
 M = 32                 ef_construction = 400

Each node              Examine 400 candidates
keeps 32 edges         before selecting the best 32

          Graph is built
               │
               ▼
         Search Phase

      ef_search = 100

Search explores up to 100 candidate nodes
before returning the nearest neighbors.
```

---

# Visual analogy

```
             BUILDING A ROAD NETWORK

         M
         ↓
How many roads every city gets

        ef_construction
               ↓
How carefully engineers choose
which roads to build

----------------------------------

            DRIVING

        ef_search
             ↓
How many roads your GPS explores
before deciding the destination
```

---

# Trade-off table

| Parameter           | Higher Value                             | Lower Value                   |
| ------------------- | ---------------------------------------- | ----------------------------- |
| **M**               | Better recall, more memory, slower build | Less memory, lower recall     |
| **ef_construction** | Better graph quality, slower indexing    | Faster indexing, poorer graph |
| **ef_search**       | Better recall, slower queries            | Faster queries, lower recall  |

---

# Typical production settings

These are common starting points (you should benchmark on your own data):

| Dataset                |     M | ef_construction | ef_search |
| ---------------------- | ----: | --------------: | --------: |
| Small prototypes       |    16 |         100–200 |     32–64 |
| General production RAG | 16–32 |         200–400 |    64–128 |
| High-recall search     | 32–64 |        400–500+ |   128–400 |

The exact values depend on your embedding dimensionality, dataset size, and latency budget. Higher-dimensional embeddings and applications that demand very high recall often benefit from larger **M** and **ef_construction**, while **ef_search** is usually the first parameter tuned in production. ([AI/TLDR][1])

## One intuition to remember

Imagine you're building a city:

* **M** = *How many roads each house is allowed to have.*
* **ef_construction** = *How much time the city planner spends choosing the best roads before construction.*
* **ef_search** = *How many roads your GPS is willing to explore before deciding on the destination.*

A beautifully planned city (high **M** and **ef_construction**) still lets you choose between **fast navigation** (low **ef_search**) and **thorough navigation** (high **ef_search**) depending on the trip. This separation between build-time quality and query-time behavior is one of the reasons HNSW is widely used in production vector databases.

[1]: https://ai-tldr.dev/learn/embeddings-vector-databases/similarity-search-indexing/hnsw-explained/?utm_source=chatgpt.com "HNSW Explained: How Vector Database Indexes Work | AI/TLDR"
[2]: https://www.index-management.org/hnsw-ivfflat-index-creation-tuning/optimizing-m-and-ef_construction-parameters/?utm_source=chatgpt.com "Optimizing m and ef_construction Parameters"
